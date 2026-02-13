"""Unit tests for socket manager."""

import json
import socket
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from mpv_controller.config import Config, MpvInstance, ServerSettings, SocketSettings
from mpv_controller.models import (
    CommandExecutionError,
    InstanceNotFoundError,
    ProfileMode,
    SocketConnectionError,
    SocketTimeoutError,
)
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
    )


@pytest.fixture
def socket_manager(mock_config):
    """Create a socket manager instance."""
    manager = MpvSocketManager(mock_config)
    yield manager
    manager.shutdown()


def test_validate_instance_success(socket_manager):
    """Test that valid instances are found."""
    instance = socket_manager._validate_instance("mpv-0")
    assert instance.id == "mpv-0"
    assert instance.display_name == "Test Player"


def test_validate_instance_not_found(socket_manager):
    """Test that invalid instances raise error."""
    with pytest.raises(InstanceNotFoundError) as exc_info:
        socket_manager._validate_instance("nonexistent")
    
    assert exc_info.value.code == "INSTANCE_NOT_FOUND"
    assert "nonexistent" in exc_info.value.message


@patch("socket.socket")
def test_send_command_success(mock_socket_class, socket_manager):
    """Test successful command execution."""
    # Setup mock socket
    mock_sock = MagicMock()
    mock_socket_class.return_value.__enter__.return_value = mock_sock
    
    # Mock response
    response = {"error": "success", "data": None}
    mock_sock.recv.return_value = (json.dumps(response) + "\n").encode()
    
    # Execute command
    result = socket_manager.send_command("mpv-0", ["pause"])
    
    # Verify
    assert result == response
    mock_sock.connect.assert_called_once_with("/tmp/mpv-0.sock")
    assert mock_sock.sendall.called


@patch("socket.socket")
def test_send_command_with_multiple_json_responses(mock_socket_class, socket_manager):
    """Test handling of multiple JSON responses from mpv.
    
    When apply-profile is executed, mpv sends the command response followed by
    property-change events. We should parse only the first JSON object.
    """
    mock_sock = MagicMock()
    mock_socket_class.return_value.__enter__.return_value = mock_sock
    
    # Simulate mpv sending command response + event notification
    # This is what happens when apply-profile triggers property changes
    response = {"error": "success"}
    event = {"id": 100, "result": None}
    combined_response = (
        json.dumps(response) + "\n" +
        json.dumps(event) + "\n"
    ).encode()
    
    mock_sock.recv.return_value = combined_response
    
    # Should parse only the first JSON object (the command response)
    result = socket_manager.send_command("mpv-0", ["apply-profile", "anime4k"])
    
    # Verify we got only the command response, not the event
    assert result == response
    assert "id" not in result  # Event field should not be present
    mock_sock.connect.assert_called_once_with("/tmp/mpv-0.sock")


@patch("socket.socket")
def test_send_command_timeout(mock_socket_class, socket_manager):
    """Test command timeout handling."""
    mock_sock = MagicMock()
    mock_socket_class.return_value.__enter__.return_value = mock_sock
    mock_sock.recv.side_effect = socket.timeout()
    
    with pytest.raises(SocketTimeoutError) as exc_info:
        socket_manager.send_command("mpv-0", ["pause"])
    
    assert exc_info.value.code == "SOCKET_TIMEOUT"
    assert "mpv-0" in exc_info.value.message


@patch("socket.socket")
def test_send_command_connection_error(mock_socket_class, socket_manager):
    """Test connection error handling."""
    mock_sock = MagicMock()
    mock_socket_class.return_value.__enter__.return_value = mock_sock
    mock_sock.connect.side_effect = socket.error("Connection refused")
    
    with pytest.raises(SocketConnectionError) as exc_info:
        socket_manager.send_command("mpv-0", ["pause"])
    
    assert exc_info.value.code == "SOCKET_CONNECTION_ERROR"
    assert "mpv-0" in exc_info.value.message


@patch("socket.socket")
def test_get_property_success(mock_socket_class, socket_manager):
    """Test successful property retrieval."""
    mock_sock = MagicMock()
    mock_socket_class.return_value.__enter__.return_value = mock_sock
    
    response = {"error": "success", "data": 75.0}
    mock_sock.recv.return_value = (json.dumps(response) + "\n").encode()
    
    result = socket_manager.get_property("mpv-0", "volume")
    
    assert result == 75.0


@patch("socket.socket")
def test_get_property_with_retry(mock_socket_class, socket_manager):
    """Test that get_property retries on transient errors."""
    # Mock successful response on third attempt
    response = {"error": "success", "data": 50.0}
    
    call_count = [0]
    
    def mock_recv(size):
        call_count[0] += 1
        if call_count[0] < 3:
            # Fail first two attempts
            raise socket.timeout()
        # Succeed on third
        return (json.dumps(response) + "\n").encode()
    
    mock_sock = MagicMock()
    mock_socket_class.return_value.__enter__.return_value = mock_sock
    mock_sock.recv.side_effect = mock_recv
    
    result = socket_manager.get_property("mpv-0", "volume")
    
    assert result == 50.0
    assert mock_sock.connect.call_count == 3  # Initial + 2 retries


@patch("socket.socket")
def test_get_standard_state(mock_socket_class, socket_manager):
    """Test getting standard state properties."""
    mock_sock = MagicMock()
    mock_socket_class.return_value.__enter__.return_value = mock_sock
    
    # Mock responses for different properties
    responses = {
        "pause": False,
        "time-pos": 123.45,
        "duration": 300.0,
        "filename": "/test/video.mp4",
        "volume": 75.0,
    }
    
    def mock_recv(size):
        # Get the command from sendall
        cmd = json.loads(mock_sock.sendall.call_args[0][0].decode().strip())
        prop_name = cmd["command"][1]
        response = {"error": "success", "data": responses.get(prop_name)}
        return (json.dumps(response) + "\n").encode()
    
    mock_sock.recv.side_effect = mock_recv
    
    state = socket_manager.get_standard_state("mpv-0")
    
    assert state.pause is False
    assert state.time_pos == 123.45
    assert state.duration == 300.0
    assert state.filename == "/test/video.mp4"
    assert state.volume == 75.0


class TestProfileTracking:
    """Tests for profile tracking functionality."""

    def test_track_applied_profile_shader_reset(self, socket_manager):
        """Test tracking a shader profile with reset mode."""
        socket_manager.track_applied_profile(
            "mpv-0",
            "anime4k",
            "shader",
            ProfileMode.RESET,
        )
        
        profiles = socket_manager.get_applied_profiles("mpv-0")
        assert profiles == ["anime4k"]

    def test_track_applied_profile_additive(self, socket_manager):
        """Test tracking profiles in additive mode."""
        socket_manager.track_applied_profile(
            "mpv-0",
            "anime4k",
            "shader",
            ProfileMode.RESET,
        )
        socket_manager.track_applied_profile(
            "mpv-0",
            "sharpen",
            "shader",
            ProfileMode.ADDITIVE,
        )
        
        profiles = socket_manager.get_applied_profiles("mpv-0")
        assert profiles == ["anime4k", "sharpen"]

    def test_track_applied_profile_type_specific_reset(self, socket_manager):
        """Test that reset mode only clears profiles of the same type."""
        # Apply shader profile
        socket_manager.track_applied_profile(
            "mpv-0",
            "anime4k",
            "shader",
            ProfileMode.RESET,
        )
        # Apply setting profile
        socket_manager.track_applied_profile(
            "mpv-0",
            "debanding",
            "setting",
            ProfileMode.ADDITIVE,
        )
        # Apply new shader profile with reset
        socket_manager.track_applied_profile(
            "mpv-0",
            "none",
            "shader",
            ProfileMode.RESET,
        )
        
        profiles = socket_manager.get_applied_profiles("mpv-0")
        # Should have setting profile and new shader profile
        assert profiles == ["debanding", "none"]

    def test_track_applied_profile_multiple_instances(self, socket_manager):
        """Test tracking profiles across multiple instances."""
        socket_manager.track_applied_profile(
            "mpv-0",
            "anime4k",
            "shader",
            ProfileMode.RESET,
        )
        socket_manager.track_applied_profile(
            "mpv-1",
            "debanding",
            "setting",
            ProfileMode.RESET,
        )
        
        profiles_0 = socket_manager.get_applied_profiles("mpv-0")
        profiles_1 = socket_manager.get_applied_profiles("mpv-1")
        
        assert profiles_0 == ["anime4k"]
        assert profiles_1 == ["debanding"]

    def test_get_applied_profiles_empty(self, socket_manager):
        """Test getting applied profiles for instance with none applied."""
        profiles = socket_manager.get_applied_profiles("mpv-0")
        assert profiles == []

    def test_get_standard_state_includes_applied_profiles(self, socket_manager):
        """Test that get_standard_state includes applied_profiles."""
        with patch("socket.socket") as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value.__enter__.return_value = mock_sock
            
            # Mock responses for properties
            responses = {
                "pause": False,
                "time-pos": 120.0,
            }
            
            def mock_recv(size):
                cmd = json.loads(mock_sock.sendall.call_args[0][0].decode().strip())
                prop_name = cmd["command"][1]
                response = {"error": "success", "data": responses.get(prop_name)}
                return (json.dumps(response) + "\n").encode()
            
            mock_sock.recv.side_effect = mock_recv
            
            # Track some profiles
            socket_manager.track_applied_profile(
                "mpv-0",
                "anime4k",
                "shader",
                ProfileMode.RESET,
            )
            socket_manager.track_applied_profile(
                "mpv-0",
                "debanding",
                "setting",
                ProfileMode.ADDITIVE,
            )
            
            state = socket_manager.get_standard_state("mpv-0")
            
            assert state.applied_profiles == ["anime4k", "debanding"]

    def test_complex_profile_stacking(self, socket_manager):
        """Test complex profile stacking scenario."""
        # Apply shader profile (reset)
        socket_manager.track_applied_profile(
            "mpv-0",
            "anime4k-medium",
            "shader",
            ProfileMode.RESET,
        )
        # Add setting profile (additive)
        socket_manager.track_applied_profile(
            "mpv-0",
            "debanding",
            "setting",
            ProfileMode.ADDITIVE,
        )
        # Add another shader (additive)
        socket_manager.track_applied_profile(
            "mpv-0",
            "sharpen",
            "shader",
            ProfileMode.ADDITIVE,
        )
        # Add another setting (additive)
        socket_manager.track_applied_profile(
            "mpv-0",
            "tone-mapping",
            "setting",
            ProfileMode.ADDITIVE,
        )
        
        profiles = socket_manager.get_applied_profiles("mpv-0")
        assert profiles == ["anime4k-medium", "debanding", "sharpen", "tone-mapping"]
        
        # Now apply a shader reset
        socket_manager.track_applied_profile(
            "mpv-0",
            "none",
            "shader",
            ProfileMode.RESET,
        )
        
        profiles = socket_manager.get_applied_profiles("mpv-0")
        # Should only have setting profiles and the new shader profile
        assert profiles == ["debanding", "tone-mapping", "none"]
