"""Unit tests for gRPC service."""

import json
from unittest.mock import Mock

import pytest

from mpv_controller.config import Config, MpvInstance, ServerSettings, SocketSettings
from mpv_controller.grpc_service import MpvControllerService, create_grpc_server
from mpv_controller.models import (
    ErrorCode,
    InstanceNotFoundError,
    MpvPlaylistItem,
    MpvState,
    ProfileInfo,
    ProfileMode,
    SocketConnectionError,
    SocketTimeoutError,
)
from mpv_controller.profile_manager import ProfileManager, ProfileNotFoundError
from mpv_controller.mpv_control_pb2 import (
    HealthCheckRequest,
    InstanceRequest,
    PropertyRequest,
    RawCommandRequest,
    SeekRequest,
    VolumeRequest,
)
from mpv_controller.socket_manager import MpvSocketManager


class MockContext:
    """Mock gRPC context for testing."""

    def __init__(self):
        self._code = None
        self._details = None

    def set_code(self, code):
        """Set the status code."""
        self._code = code

    def set_details(self, details):
        """Set the status details."""
        self._details = details

    def code(self):
        """Get the status code."""
        return self._code

    def details(self):
        """Get the status details."""
        return self._details


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
        server=ServerSettings(
            bind_address="127.0.0.1",
            rest_port=8080,
            grpc_port=50051,
        ),
        socket=SocketSettings(
            timeout=5.0,
            retry_attempts=3,
            retry_delay=0.1,
        ),
    )


@pytest.fixture
def socket_manager(mock_config):
    """Create a mock socket manager."""
    return Mock(spec=MpvSocketManager)


@pytest.fixture
def profile_manager():
    """Create a mock profile manager."""
    return Mock(spec=ProfileManager)


@pytest.fixture
def service(mock_config, socket_manager, profile_manager):
    """Create gRPC service instance."""
    return MpvControllerService(mock_config, socket_manager, profile_manager)


@pytest.fixture
def context():
    """Create mock gRPC context."""
    return MockContext()


class TestMpvControllerService:
    """Tests for MpvControllerService gRPC methods."""

    def test_pause(self, service, socket_manager, context):
        """Test Pause command."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=True,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.Pause(request, context)

        assert response.command_result.success is True
        assert response.instance_id == "mpv-0"
        assert response.state.pause is True
        socket_manager.send_command.assert_called_once_with("mpv-0", ["cycle", "pause"])

    def test_pause_error(self, service, socket_manager, context):
        """Test Pause command with error."""
        socket_manager.send_command = Mock(
            side_effect=InstanceNotFoundError("mpv-0")
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.Pause(request, context)

        assert response.command_result.success is False
        assert response.error.code == ErrorCode.INSTANCE_NOT_FOUND
        assert "mpv-0" in response.error.message

    def test_play(self, service, socket_manager, context):
        """Test Play command."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.Play(request, context)

        assert response.command_result.success is True
        assert response.state.pause is False
        socket_manager.send_command.assert_called_once_with(
            "mpv-0", ["set_property", "pause", False]
        )

    def test_play_error(self, service, socket_manager, context):
        """Test Play command with error."""
        socket_manager.send_command = Mock(
            side_effect=SocketTimeoutError("mpv-0", 5.0)
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.Play(request, context)

        assert response.command_result.success is False
        assert response.error.code == ErrorCode.SOCKET_TIMEOUT

    def test_seek_absolute(self, service, socket_manager, context):
        """Test Seek command with absolute positioning."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=60.0,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
            )
        )

        request = SeekRequest(instance_id="mpv-0", position=60.0, relative=False)
        response = service.Seek(request, context)

        assert response.command_result.success is True
        assert response.state.time_pos == 60.0
        socket_manager.send_command.assert_called_once_with(
            "mpv-0", ["seek", 60.0, "absolute"]
        )

    def test_seek_relative(self, service, socket_manager, context):
        """Test Seek command with relative positioning."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=130.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
            )
        )

        request = SeekRequest(instance_id="mpv-0", position=10.0, relative=True)
        response = service.Seek(request, context)

        assert response.command_result.success is True
        socket_manager.send_command.assert_called_once_with(
            "mpv-0", ["seek", 10.0, "relative"]
        )

    def test_set_volume(self, service, socket_manager, context):
        """Test SetVolume command."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=75.0,
                filename="test.mp4",
            )
        )

        request = VolumeRequest(instance_id="mpv-0", volume=75.0)
        response = service.SetVolume(request, context)

        assert response.command_result.success is True
        assert response.state.volume == 75.0
        socket_manager.send_command.assert_called_once_with(
            "mpv-0", ["set_property", "volume", 75.0]
        )

    def test_volume_up(self, service, socket_manager, context):
        """Test VolumeUp command."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=105.0,
                filename="test.mp4",
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.VolumeUp(request, context)

        assert response.command_result.success is True
        socket_manager.send_command.assert_called_once_with("mpv-0", ["add", "volume", 5])

    def test_volume_down(self, service, socket_manager, context):
        """Test VolumeDown command."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=95.0,
                filename="test.mp4",
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.VolumeDown(request, context)

        assert response.command_result.success is True
        socket_manager.send_command.assert_called_once_with("mpv-0", ["add", "volume", -5])

    def test_mute(self, service, socket_manager, context):
        """Test Mute command."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                mute=True,
                filename="test.mp4",
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.Mute(request, context)

        assert response.command_result.success is True
        assert response.state.mute is True
        socket_manager.send_command.assert_called_once_with("mpv-0", ["cycle", "mute"])

    def test_loop_toggle_to_no(self, service, socket_manager, context):
        """Test Loop command toggling from 'inf' to 'no'."""
        socket_manager.get_property = Mock(return_value="inf")
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
                loop_file="no",
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.Loop(request, context)

        assert response.command_result.success is True
        assert response.state.loop_file == "no"
        socket_manager.get_property.assert_called_once_with("mpv-0", "loop-file")
        socket_manager.send_command.assert_called_once_with(
            "mpv-0", ["set_property", "loop-file", "no"]
        )

    def test_loop_toggle_to_inf(self, service, socket_manager, context):
        """Test Loop command toggling from 'no' to 'inf'."""
        socket_manager.get_property = Mock(return_value="no")
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
                loop_file="inf",
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.Loop(request, context)

        assert response.command_result.success is True
        assert response.state.loop_file == "inf"
        socket_manager.send_command.assert_called_once_with(
            "mpv-0", ["set_property", "loop-file", "inf"]
        )

    def test_loop_from_number(self, service, socket_manager, context):
        """Test Loop command toggling from number to 'no'."""
        socket_manager.get_property = Mock(return_value="3")
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
                loop_file="no",
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.Loop(request, context)

        assert response.command_result.success is True
        socket_manager.send_command.assert_called_once_with(
            "mpv-0", ["set_property", "loop-file", "no"]
        )

    def test_loop_from_false(self, service, socket_manager, context):
        """Test Loop command toggling from False to 'inf'."""
        socket_manager.get_property = Mock(return_value=False)
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
                loop_file=False,
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.Loop(request, context)

        assert response.command_result.success is True
        socket_manager.send_command.assert_called_once_with(
            "mpv-0", ["set_property", "loop-file", "inf"]
        )

    def test_shuffle(self, service, socket_manager, context):
        """Test Shuffle command."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
                shuffle=True,
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.Shuffle(request, context)

        assert response.command_result.success is True
        assert response.state.shuffle is True
        socket_manager.send_command.assert_called_once_with("mpv-0", ["cycle", "shuffle"])

    def test_get_property(self, service, socket_manager, context):
        """Test GetProperty."""
        socket_manager.get_property = Mock(return_value=100.0)

        request = PropertyRequest(instance_id="mpv-0", property_name="volume")
        response = service.GetProperty(request, context)

        assert response.name == "volume"
        assert json.loads(response.value_json) == 100.0
        assert response.instance_id == "mpv-0"
        socket_manager.get_property.assert_called_once_with("mpv-0", "volume")

    def test_get_property_error(self, service, socket_manager, context):
        """Test GetProperty with error."""
        socket_manager.get_property = Mock(
            side_effect=InstanceNotFoundError("mpv-0")
        )

        request = PropertyRequest(instance_id="mpv-0", property_name="volume")
        response = service.GetProperty(request, context)

        assert response.error.code == ErrorCode.INSTANCE_NOT_FOUND

    def test_get_status(self, service, socket_manager, context):
        """Test GetStatus."""
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
            )
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.GetStatus(request, context)

        assert response.command_result.success is True
        assert response.state.pause is False
        assert response.state.time_pos == 120.5

    def test_get_status_error(self, service, socket_manager, context):
        """Test GetStatus with error."""
        socket_manager.get_standard_state = Mock(
            side_effect=SocketConnectionError("mpv-0", "/tmp/mpv-0.sock", "Connection refused")
        )

        request = InstanceRequest(instance_id="mpv-0")
        response = service.GetStatus(request, context)

        assert response.command_result.success is False
        assert response.error.code == ErrorCode.SOCKET_CONNECTION_ERROR

    def test_send_raw_command(self, service, socket_manager, context):
        """Test SendRawCommand."""
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": "result"}
        )
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
            )
        )

        request = RawCommandRequest(instance_id="mpv-0", command=["get_property", "volume"])
        response = service.SendRawCommand(request, context)

        assert response.command_result.success is True
        assert json.loads(response.command_result.data_json) == "result"
        socket_manager.send_command.assert_called_once_with(
            "mpv-0", ["get_property", "volume"]
        )

    def test_send_raw_command_error(self, service, socket_manager, context):
        """Test SendRawCommand with error."""
        socket_manager.send_command = Mock(
            side_effect=SocketTimeoutError("mpv-0", 5.0)
        )

        request = RawCommandRequest(instance_id="mpv-0", command=["get_property", "volume"])
        response = service.SendRawCommand(request, context)

        assert response.command_result.success is False
        assert response.error.code == ErrorCode.SOCKET_TIMEOUT

    def test_check_health(self, service, context):
        """Test health check."""
        from mpv_controller.mpv_control_pb2 import HealthCheckResponse

        request = HealthCheckRequest()
        response = service.Check(request, context)

        assert response.status == HealthCheckResponse.SERVING


class TestHelperMethods:
    """Tests for helper methods."""

    def test_create_error_detail(self, service):
        """Test _create_error_detail conversion."""
        error = InstanceNotFoundError("mpv-0")
        error_detail = service._create_error_detail(error)

        assert error_detail.code == ErrorCode.INSTANCE_NOT_FOUND
        assert "mpv-0" in error_detail.message
        details = json.loads(error_detail.details_json)
        assert details["instance_id"] == "mpv-0"

    def test_mpv_state_to_proto(self, service):
        """Test _mpv_state_to_proto conversion."""
        state = MpvState(
            pause=False,
            time_pos=120.5,
            duration=300.0,
            volume=100.0,
            speed=1.5,
            mute=False,
            filename="test.mp4",
            media_title="Test Media",
            loop_file="inf",
            shuffle=True,
            playlist=[
                MpvPlaylistItem(filename="file1.mp4", current=True, playing=True),
                MpvPlaylistItem(filename="file2.mp4", current=False, playing=False),
            ],
            glsl_shaders=["/path/to/shader1.glsl", "/path/to/shader2.glsl"],
        )

        proto_state = service._mpv_state_to_proto(state)

        assert proto_state.pause is False
        assert proto_state.time_pos == 120.5
        assert proto_state.duration == 300.0
        assert proto_state.volume == 100.0
        assert proto_state.speed == 1.5
        assert proto_state.mute is False
        assert proto_state.filename == "test.mp4"
        assert proto_state.media_title == "Test Media"
        assert proto_state.loop_file == "inf"
        assert proto_state.shuffle is True
        assert len(proto_state.playlist) == 2
        assert proto_state.playlist[0].filename == "file1.mp4"
        assert proto_state.playlist[0].current is True
        assert len(proto_state.glsl_shaders) == 2

    def test_mpv_state_to_proto_loop_file_bool(self, service):
        """Test _mpv_state_to_proto with boolean loop_file."""
        state = MpvState(
            pause=False,
            loop_file=False,
        )

        proto_state = service._mpv_state_to_proto(state)

        assert proto_state.loop_file == "no"

        state.loop_file = True
        proto_state = service._mpv_state_to_proto(state)

        assert proto_state.loop_file == "inf"

    def test_mpv_state_to_proto_partial(self, service):
        """Test _mpv_state_to_proto with partial state."""
        state = MpvState(
            pause=True,
            filename="test.mp4",
        )

        proto_state = service._mpv_state_to_proto(state)

        assert proto_state.pause is True
        assert proto_state.filename == "test.mp4"
        # Other fields should not be set
        assert not proto_state.HasField("time_pos")
        assert not proto_state.HasField("duration")

    def test_remove_profile_success(self, service, socket_manager, profile_manager, context):
        """Test RemoveProfile successfully removes a shader profile."""
        from mpv_controller.mpv_control_pb2 import RemoveProfileRequest
        
        # Mock applied profiles
        socket_manager.get_applied_profiles = Mock(return_value=["anime4k"])
        
        # Mock profile metadata
        profile = ProfileInfo(
            name="anime4k",
            options={
                "glsl-shaders-append": [
                    "~~/shaders/Anime4K_Clamp_Highlights.glsl",
                    "~~/shaders/Anime4K_Upscale_DoG.glsl",
                ]
            },
            profile_type="shader",
            profile_mode=ProfileMode.ADDITIVE,
        )
        profile_manager.get_profile = Mock(return_value=profile)
        
        # Mock shader removal
        socket_manager.send_command = Mock(
            return_value={"error": "success", "data": None}
        )
        
        # Mock tracking state
        socket_manager._applied_profiles = {
            "mpv-0": [("anime4k", "shader"), ("other-profile", "setting")]
        }
        
        # Mock state
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(
                pause=False,
                time_pos=120.5,
                duration=300.0,
                volume=100.0,
                filename="test.mp4",
            )
        )
        
        request = RemoveProfileRequest(instance_id="mpv-0", profile_name="anime4k")
        response = service.RemoveProfile(request, context)
        
        assert response.command_result.success is True
        result_data = json.loads(response.command_result.data_json)
        assert result_data["shaders_removed"] == 2
        
        # Check shaders were removed in reverse order
        assert socket_manager.send_command.call_count == 2
        calls = socket_manager.send_command.call_args_list
        assert calls[0][0] == (
            "mpv-0",
            ["change-list", "glsl-shaders", "remove", "~~/shaders/Anime4K_Upscale_DoG.glsl"],
        )
        assert calls[1][0] == (
            "mpv-0",
            ["change-list", "glsl-shaders", "remove", "~~/shaders/Anime4K_Clamp_Highlights.glsl"],
        )
        
        # Check profile was removed from tracking
        assert socket_manager._applied_profiles["mpv-0"] == [("other-profile", "setting")]

    def test_remove_profile_not_applied(self, service, socket_manager, profile_manager, context):
        """Test RemoveProfile returns error when profile is not applied."""
        from mpv_controller.mpv_control_pb2 import RemoveProfileRequest
        
        socket_manager.get_applied_profiles = Mock(return_value=["other-profile"])
        
        request = RemoveProfileRequest(instance_id="mpv-0", profile_name="anime4k")
        response = service.RemoveProfile(request, context)
        
        assert response.command_result.success is False
        assert response.error.code == "PROFILE_NOT_APPLIED"
        assert "not currently applied" in response.error.message

    def test_remove_profile_not_shader_type(self, service, socket_manager, profile_manager, context):
        """Test RemoveProfile returns error for non-shader profiles."""
        from mpv_controller.mpv_control_pb2 import RemoveProfileRequest
        
        socket_manager.get_applied_profiles = Mock(return_value=["quality-high"])
        
        profile = ProfileInfo(
            name="quality-high",
            options={"profile-desc": "High quality"},
            profile_type="setting",
            profile_mode=ProfileMode.RESET,
        )
        profile_manager.get_profile = Mock(return_value=profile)
        
        request = RemoveProfileRequest(instance_id="mpv-0", profile_name="quality-high")
        response = service.RemoveProfile(request, context)
        
        assert response.command_result.success is False
        assert response.error.code == "PROFILE_TYPE_NOT_REMOVABLE"
        assert "Only shader profiles can be removed" in response.error.message

    def test_remove_profile_not_found(self, service, socket_manager, profile_manager, context):
        """Test RemoveProfile when profile doesn't exist in config."""
        from mpv_controller.mpv_control_pb2 import RemoveProfileRequest
        
        socket_manager.get_applied_profiles = Mock(return_value=["nonexistent"])
        profile_manager.get_profile = Mock(side_effect=ProfileNotFoundError("nonexistent"))
        
        request = RemoveProfileRequest(instance_id="mpv-0", profile_name="nonexistent")
        response = service.RemoveProfile(request, context)
        
        assert response.command_result.success is False
        assert response.error is not None

    def test_remove_profile_with_shader_removal_errors(self, service, socket_manager, profile_manager, context):
        """Test RemoveProfile when shader removal partially fails."""
        from mpv_controller.mpv_control_pb2 import RemoveProfileRequest
        
        socket_manager.get_applied_profiles = Mock(return_value=["anime4k"])
        
        profile = ProfileInfo(
            name="anime4k",
            options={
                "glsl-shaders-append": [
                    "~~/shaders/shader1.glsl",
                    "~~/shaders/shader2.glsl",
                ]
            },
            profile_type="shader",
            profile_mode=ProfileMode.ADDITIVE,
        )
        profile_manager.get_profile = Mock(return_value=profile)
        
        # First shader removal succeeds, second fails
        def send_command_side_effect(instance_id, command):
            if command[3] == "~~/shaders/shader1.glsl":
                return {"error": "success", "data": None}
            else:
                return {"error": "shader not found", "data": None}
        
        socket_manager.send_command = Mock(side_effect=send_command_side_effect)
        socket_manager._applied_profiles = {"mpv-0": [("anime4k", "shader")]}
        socket_manager.get_standard_state = Mock(
            return_value=MpvState(pause=False, filename="test.mp4")
        )
        
        request = RemoveProfileRequest(instance_id="mpv-0", profile_name="anime4k")
        response = service.RemoveProfile(request, context)
        
        # Should mark as not successful due to errors
        assert response.command_result.success is False
        result_data = json.loads(response.command_result.data_json)
        assert result_data["shaders_removed"] == 2
        assert "errors" in result_data
        assert len(result_data["errors"]) == 1
        
        # Profile should still be removed from tracking
        assert socket_manager._applied_profiles["mpv-0"] == []


class TestCreateGrpcServer:
    """Tests for create_grpc_server function."""

    def test_create_grpc_server(self, mock_config, socket_manager, profile_manager):
        """Test gRPC server creation."""
        server = create_grpc_server(mock_config, socket_manager, profile_manager)

        assert server is not None
        # Server should be configured but not started
