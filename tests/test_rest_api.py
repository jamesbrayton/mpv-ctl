"""Unit tests for REST API."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from mpv_controller.config import Config, MpvInstance, ServerSettings, SocketSettings
from mpv_controller.models import (
    InstanceNotFoundError,
    SocketConnectionError,
    SocketTimeoutError,
)
from mpv_controller.rest_api import create_rest_app
from mpv_controller.socket_manager import MpvSocketManager


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return Config(
        mpv_instances=[
            MpvInstance(
                id="mpv-0",
                socket_path="/tmp/mpv-0.sock",
                display_name="Test Player",
            ),
            MpvInstance(
                id="mpv-1",
                socket_path="/tmp/mpv-1.sock",
            ),
        ],
        socket=SocketSettings(
            read_timeout=1.0,
            max_retries=2,
            availability_check_interval=0,  # Disable for tests
        ),
        server=ServerSettings(
            rest_port=8000,
            grpc_port=50051,
            enable_swagger_ui=True,
        ),
    )


@pytest.fixture
def socket_manager(mock_config):
    """Create a socket manager instance."""
    manager = MpvSocketManager(mock_config)
    yield manager
    manager.shutdown()


@pytest.fixture
def client(mock_config, socket_manager):
    """Create a test client for the REST API."""
    app = create_rest_app(mock_config, socket_manager)
    return TestClient(app)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_ready(self, client, socket_manager):
        """Test readiness check endpoint."""
        # Mock availability
        socket_manager.get_instance_availability = Mock(
            return_value={"mpv-0": True, "mpv-1": False}
        )
        
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert len(data["instances"]) == 2
        assert data["instances"][0]["instance_id"] == "mpv-0"
        assert data["instances"][0]["available"] is True
        assert data["instances"][1]["instance_id"] == "mpv-1"
        assert data["instances"][1]["available"] is False


class TestPlaybackControl:
    """Tests for playback control endpoints."""

    def test_pause(self, client, socket_manager):
        """Test pause endpoint."""
        # Mock socket manager methods
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value={
                "pause": True,
                "time_pos": 120.5,
                "duration": 300.0,
                "volume": 100.0,
                "filename": "test.mp4",
            }
        )
        
        response = client.post("/mpv/mpv-0/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["command_result"]["success"] is True
        assert data["instance_id"] == "mpv-0"
        assert data["state"]["pause"] is True

    def test_play(self, client, socket_manager):
        """Test play endpoint."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value={
                "pause": False,
                "time_pos": 120.5,
                "duration": 300.0,
                "volume": 100.0,
                "filename": "test.mp4",
            }
        )
        
        response = client.post("/mpv/mpv-0/play")
        assert response.status_code == 200
        data = response.json()
        assert data["command_result"]["success"] is True
        assert data["state"]["pause"] is False

    def test_seek(self, client, socket_manager):
        """Test seek endpoint."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value={
                "pause": False,
                "time_pos": 120.0,
                "duration": 300.0,
                "volume": 100.0,
                "filename": "test.mp4",
            }
        )
        
        response = client.post(
            "/mpv/mpv-0/seek",
            json={"position": 120.0, "relative": False}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["command_result"]["success"] is True
        assert data["state"]["time_pos"] == 120.0

    def test_volume(self, client, socket_manager):
        """Test volume endpoint."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value={
                "pause": False,
                "time_pos": 120.5,
                "duration": 300.0,
                "volume": 75.0,
                "filename": "test.mp4",
            }
        )
        
        response = client.post(
            "/mpv/mpv-0/volume",
            json={"volume": 75.0}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["command_result"]["success"] is True
        assert data["state"]["volume"] == 75.0


class TestPropertiesEndpoints:
    """Tests for properties endpoints."""

    def test_list_properties_success(self, client, socket_manager):
        """Test listing all available properties."""
        # Mock get_property to return a list of properties
        mock_properties = [
            "pause",
            "time-pos",
            "duration",
            "volume",
            "filename",
            "path",
            "media-title",
            "playlist-pos",
            "playlist-count",
        ]
        socket_manager.get_property = Mock(return_value=mock_properties)
        
        response = client.get("/mpv/mpv-0/properties")
        assert response.status_code == 200
        data = response.json()
        assert data["instance_id"] == "mpv-0"
        assert data["properties"] == mock_properties
        assert "pause" in data["properties"]
        assert "time-pos" in data["properties"]
        
        # Verify socket_manager.get_property was called with correct arguments
        socket_manager.get_property.assert_called_once_with("mpv-0", "property-list")

    def test_list_properties_instance_not_found(self, client, socket_manager):
        """Test listing properties for non-existent instance."""
        socket_manager.get_property = Mock(
            side_effect=InstanceNotFoundError("nonexistent")
        )
        
        response = client.get("/mpv/nonexistent/properties")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "INSTANCE_NOT_FOUND"
        assert "nonexistent" in data["error"]["message"]

    def test_list_properties_socket_timeout(self, client, socket_manager):
        """Test listing properties with socket timeout."""
        socket_manager.get_property = Mock(
            side_effect=SocketTimeoutError("mpv-0", 1.0)
        )
        
        response = client.get("/mpv/mpv-0/properties")
        assert response.status_code == 504
        data = response.json()
        assert data["error"]["code"] == "SOCKET_TIMEOUT"

    def test_list_properties_socket_connection_error(self, client, socket_manager):
        """Test listing properties with socket connection error."""
        socket_manager.get_property = Mock(
            side_effect=SocketConnectionError("mpv-0", "/tmp/mpv-0.sock", "Connection refused")
        )
        
        response = client.get("/mpv/mpv-0/properties")
        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "SOCKET_CONNECTION_ERROR"

    def test_get_property_success(self, client, socket_manager):
        """Test getting a specific property value."""
        socket_manager.get_property = Mock(return_value="test.mp4")
        
        response = client.get("/mpv/mpv-0/properties/filename")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "filename"
        assert data["value"] == "test.mp4"
        assert data["instance_id"] == "mpv-0"
        
        # Verify socket_manager.get_property was called with correct arguments
        socket_manager.get_property.assert_called_once_with("mpv-0", "filename")

    def test_get_property_numeric_value(self, client, socket_manager):
        """Test getting a numeric property value."""
        socket_manager.get_property = Mock(return_value=75.5)
        
        response = client.get("/mpv/mpv-0/properties/volume")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "volume"
        assert data["value"] == 75.5
        assert data["instance_id"] == "mpv-0"

    def test_get_property_boolean_value(self, client, socket_manager):
        """Test getting a boolean property value."""
        socket_manager.get_property = Mock(return_value=True)
        
        response = client.get("/mpv/mpv-0/properties/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "pause"
        assert data["value"] is True
        assert data["instance_id"] == "mpv-0"

    def test_get_property_instance_not_found(self, client, socket_manager):
        """Test getting property for non-existent instance."""
        socket_manager.get_property = Mock(
            side_effect=InstanceNotFoundError("nonexistent")
        )
        
        response = client.get("/mpv/nonexistent/properties/filename")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "INSTANCE_NOT_FOUND"


class TestStatusEndpoint:
    """Tests for status endpoint."""

    def test_get_status(self, client, socket_manager):
        """Test status endpoint."""
        socket_manager.get_standard_state = Mock(
            return_value={
                "pause": False,
                "time_pos": 120.5,
                "duration": 300.0,
                "volume": 100.0,
                "filename": "test.mp4",
            }
        )
        
        response = client.get("/mpv/mpv-0/status")
        assert response.status_code == 200
        data = response.json()
        assert data["command_result"]["success"] is True
        assert data["instance_id"] == "mpv-0"
        assert data["state"]["filename"] == "test.mp4"


class TestRawCommand:
    """Tests for raw command endpoint."""

    def test_raw_command(self, client, socket_manager):
        """Test raw command execution."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value={
                "pause": False,
                "time_pos": 0.0,
                "duration": 300.0,
                "volume": 100.0,
                "filename": "new.mp4",
            }
        )
        
        response = client.post(
            "/mpv/mpv-0/command",
            json={"command": ["loadfile", "/path/to/video.mp4"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["command_result"]["success"] is True


class TestErrorHandling:
    """Tests for error handling."""

    def test_instance_not_found_error(self, client, socket_manager):
        """Test that instance not found errors return 404."""
        socket_manager.send_command = Mock(
            side_effect=InstanceNotFoundError("nonexistent")
        )
        
        response = client.post("/mpv/nonexistent/pause")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "INSTANCE_NOT_FOUND"
        assert "nonexistent" in data["error"]["message"]

    def test_socket_timeout_error(self, client, socket_manager):
        """Test that socket timeout errors return 504."""
        socket_manager.send_command = Mock(
            side_effect=SocketTimeoutError("mpv-0", 1.0)
        )
        
        response = client.post("/mpv/mpv-0/pause")
        assert response.status_code == 504
        data = response.json()
        assert data["error"]["code"] == "SOCKET_TIMEOUT"

    def test_socket_connection_error(self, client, socket_manager):
        """Test that socket connection errors return 503."""
        socket_manager.send_command = Mock(
            side_effect=SocketConnectionError("mpv-0", "/tmp/mpv-0.sock", "Connection refused")
        )
        
        response = client.post("/mpv/mpv-0/pause")
        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "SOCKET_CONNECTION_ERROR"
