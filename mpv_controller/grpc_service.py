"""gRPC service implementation for mpv controller."""

import json
from concurrent import futures

import grpc
import structlog

from .config import Config
from .models import ErrorCode, InstanceNotFoundError, MpvControllerError
from .profile_manager import ProfileManager, ProfileNotFoundError
from .mpv_control_pb2 import (
    CommandResponse,
    CommandResult,
    ErrorDetail,
    HealthCheckResponse,
    MpvPlaylistItem,
    MpvState,
    PropertyResponse,
)
from .mpv_control_pb2_grpc import (
    MpvControllerServicer,
    add_MpvControllerServicer_to_server,
)
from .socket_manager import MpvSocketManager

logger = structlog.get_logger()


class MpvControllerService(MpvControllerServicer):
    """gRPC service implementation for mpv controller."""

    def __init__(self, config: Config, socket_manager: MpvSocketManager, profile_manager: ProfileManager):
        """Initialize the service.

        Args:
            config: Application configuration.
            socket_manager: Socket manager for mpv communication.
            profile_manager: Profile manager for mpv profiles.
        """
        self.config = config
        self.socket_manager = socket_manager
        self.profile_manager = profile_manager

    def _create_error_detail(self, error: MpvControllerError) -> ErrorDetail:
        """Create an ErrorDetail message from an exception.

        Args:
            error: The exception to convert.

        Returns:
            ErrorDetail protobuf message.
        """
        return ErrorDetail(
            code=error.code,
            message=error.message,
            details_json=json.dumps(error.details),
        )

    def _mpv_state_to_proto(self, state) -> MpvState:
        """Convert models.MpvState to protobuf MpvState.

        Args:
            state: models.MpvState instance.

        Returns:
            MpvState protobuf message.
        """
        proto_state = MpvState()

        if state.pause is not None:
            proto_state.pause = state.pause
        if state.time_pos is not None:
            proto_state.time_pos = state.time_pos
        if state.duration is not None:
            proto_state.duration = state.duration
        if state.filename is not None:
            proto_state.filename = state.filename
        if state.volume is not None:
            proto_state.volume = state.volume
        if state.speed is not None:
            proto_state.speed = state.speed
        if state.mute is not None:
            proto_state.mute = state.mute
        if state.playlist is not None:
            for item in state.playlist:
                proto_item = MpvPlaylistItem(filename=item.filename)
                if item.current is not None:
                    proto_item.current = item.current
                if item.playing is not None:
                    proto_item.playing = item.playing
                if item.title is not None:
                    proto_item.title = item.title
                proto_state.playlist.append(proto_item)
        if state.glsl_shaders is not None:
            proto_state.glsl_shaders.extend(state.glsl_shaders)
        if state.media_title is not None:
            proto_state.media_title = state.media_title
        if state.loop_file is not None:
            # Convert loop_file to string for protobuf
            # mpv can return: "inf", "no", False, True, or a number
            if isinstance(state.loop_file, bool):
                proto_state.loop_file = "no" if state.loop_file is False else "inf"
            else:
                proto_state.loop_file = str(state.loop_file)
        if state.shuffle is not None:
            proto_state.shuffle = state.shuffle

        return proto_state

    def Pause(self, request, context):
        """Toggle pause state."""
        try:
            logger.info("gRPC Pause command", instance_id=request.instance_id)
            
            # Execute command
            result = self.socket_manager.send_command(
                request.instance_id,
                ["cycle", "pause"],
            )
            
            # Get state
            state = self.socket_manager.get_standard_state(request.instance_id)
            
            return CommandResponse(
                command_result=CommandResult(
                    success=result.get("error") == "success",
                    data_json=json.dumps(result.get("data")),
                    error_message=result.get("error") if result.get("error") != "success" else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC Pause error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def Play(self, request, context):
        """Resume playback."""
        try:
            logger.info("gRPC Play command", instance_id=request.instance_id)
            
            result = self.socket_manager.send_command(
                request.instance_id,
                ["set_property", "pause", False],
            )
            
            state = self.socket_manager.get_standard_state(request.instance_id)
            
            return CommandResponse(
                command_result=CommandResult(
                    success=result.get("error") == "success",
                    data_json=json.dumps(result.get("data")),
                    error_message=result.get("error") if result.get("error") != "success" else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC Play error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def Seek(self, request, context):
        """Seek to position."""
        try:
            logger.info(
                "gRPC Seek command",
                instance_id=request.instance_id,
                position=request.position,
                relative=request.relative,
            )
            
            mode = "relative" if request.relative else "absolute"
            result = self.socket_manager.send_command(
                request.instance_id,
                ["seek", request.position, mode],
            )
            
            state = self.socket_manager.get_standard_state(request.instance_id)
            
            return CommandResponse(
                command_result=CommandResult(
                    success=result.get("error") == "success",
                    data_json=json.dumps(result.get("data")),
                    error_message=result.get("error") if result.get("error") != "success" else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC Seek error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def SetVolume(self, request, context):
        """Set volume level."""
        try:
            logger.info(
                "gRPC SetVolume command",
                instance_id=request.instance_id,
                volume=request.volume,
            )

            result = self.socket_manager.send_command(
                request.instance_id,
                ["set_property", "volume", request.volume],
            )

            state = self.socket_manager.get_standard_state(request.instance_id)

            return CommandResponse(
                command_result=CommandResult(
                    success=result.get("error") == "success",
                    data_json=json.dumps(result.get("data")),
                    error_message=result.get("error") if result.get("error") != "success" else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC SetVolume error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def VolumeUp(self, request, context):
        """Increase volume by 5."""
        try:
            logger.info("gRPC VolumeUp command", instance_id=request.instance_id)

            result = self.socket_manager.send_command(
                request.instance_id,
                ["add", "volume", 5],
            )

            state = self.socket_manager.get_standard_state(request.instance_id)

            return CommandResponse(
                command_result=CommandResult(
                    success=result.get("error") == "success",
                    data_json=json.dumps(result.get("data")),
                    error_message=result.get("error") if result.get("error") != "success" else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC VolumeUp error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def VolumeDown(self, request, context):
        """Decrease volume by 5."""
        try:
            logger.info("gRPC VolumeDown command", instance_id=request.instance_id)

            result = self.socket_manager.send_command(
                request.instance_id,
                ["add", "volume", -5],
            )

            state = self.socket_manager.get_standard_state(request.instance_id)

            return CommandResponse(
                command_result=CommandResult(
                    success=result.get("error") == "success",
                    data_json=json.dumps(result.get("data")),
                    error_message=result.get("error") if result.get("error") != "success" else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC VolumeDown error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def Mute(self, request, context):
        """Toggle mute state."""
        try:
            logger.info("gRPC Mute command", instance_id=request.instance_id)

            result = self.socket_manager.send_command(
                request.instance_id,
                ["cycle", "mute"],
            )

            state = self.socket_manager.get_standard_state(request.instance_id)

            return CommandResponse(
                command_result=CommandResult(
                    success=result.get("error") == "success",
                    data_json=json.dumps(result.get("data")),
                    error_message=result.get("error") if result.get("error") != "success" else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC Mute error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def Loop(self, request, context):
        """Toggle loop state for current file."""
        try:
            logger.info("gRPC Loop command", instance_id=request.instance_id)

            # Get current loop-file value
            current_value = self.socket_manager.get_property(request.instance_id, "loop-file")
            
            # Toggle between 'inf' and 'no'
            # mpv can return: "inf", "no", False, True, or a number
            # If current value is 'inf', True, or any number > 0, set to 'no'
            # Otherwise, set to 'inf'
            data = current_value
            new_value = "no" if (data == "inf" or data is True or (isinstance(data, (int, str)) and str(data).isdigit() and int(data) > 0)) else "inf"

            result = self.socket_manager.send_command(
                request.instance_id,
                ["set_property", "loop-file", new_value],
            )

            state = self.socket_manager.get_standard_state(request.instance_id)

            return CommandResponse(
                command_result=CommandResult(
                    success=result.get("error") == "success",
                    data_json=json.dumps(result.get("data")),
                    error_message=result.get("error") if result.get("error") != "success" else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC Loop error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def Shuffle(self, request, context):
        """Toggle shuffle state."""
        try:
            logger.info("gRPC Shuffle command", instance_id=request.instance_id)

            result = self.socket_manager.send_command(
                request.instance_id,
                ["cycle", "shuffle"],
            )

            state = self.socket_manager.get_standard_state(request.instance_id)

            return CommandResponse(
                command_result=CommandResult(
                    success=result.get("error") == "success",
                    data_json=json.dumps(result.get("data")),
                    error_message=result.get("error") if result.get("error") != "success" else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC Shuffle error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def GetProperty(self, request, context):
        """Get property value."""
        try:
            logger.info(
                "gRPC GetProperty",
                instance_id=request.instance_id,
                property=request.property_name,
            )
            
            value = self.socket_manager.get_property(
                request.instance_id,
                request.property_name,
            )
            
            return PropertyResponse(
                name=request.property_name,
                value_json=json.dumps(value),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC GetProperty error", error=str(e), code=e.code)
            return PropertyResponse(
                name=request.property_name,
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def GetStatus(self, request, context):
        """Get instance status."""
        try:
            logger.info("gRPC GetStatus", instance_id=request.instance_id)
            
            state = self.socket_manager.get_standard_state(request.instance_id)
            
            return CommandResponse(
                command_result=CommandResult(success=True, data_json="null"),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC GetStatus error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def SendRawCommand(self, request, context):
        """Execute raw command."""
        try:
            logger.info(
                "gRPC SendRawCommand",
                instance_id=request.instance_id,
                command=list(request.command),
            )
            
            result = self.socket_manager.send_command(
                request.instance_id,
                list(request.command),
            )
            
            state = self.socket_manager.get_standard_state(request.instance_id)
            
            return CommandResponse(
                command_result=CommandResult(
                    success=result.get("error") == "success",
                    data_json=json.dumps(result.get("data")),
                    error_message=result.get("error") if result.get("error") != "success" else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )
        except MpvControllerError as e:
            logger.error("gRPC SendRawCommand error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def RemoveProfile(self, request, context):
        """Remove an applied profile from an mpv instance."""
        try:
            logger.info(
                "gRPC RemoveProfile",
                instance_id=request.instance_id,
                profile=request.profile_name,
            )

            # Check if profile is currently applied
            applied_profiles = self.socket_manager.get_applied_profiles(request.instance_id)
            if request.profile_name not in applied_profiles:
                error_detail = ErrorDetail(
                    code="PROFILE_NOT_APPLIED",
                    message=f"Profile '{request.profile_name}' is not currently applied to instance '{request.instance_id}'",
                    details_json=json.dumps({
                        "instance_id": request.instance_id,
                        "profile": request.profile_name,
                        "applied_profiles": applied_profiles,
                    }),
                )
                return CommandResponse(
                    command_result=CommandResult(success=False),
                    instance_id=request.instance_id,
                    error=error_detail,
                )

            # Get profile metadata
            try:
                profile = self.profile_manager.get_profile(request.profile_name)
            except ProfileNotFoundError as e:
                logger.error("Profile not found", profile=request.profile_name)
                error_detail = ErrorDetail(
                    code="PROFILE_NOT_FOUND",
                    message=str(e),
                    details_json=json.dumps({"profile": request.profile_name}),
                )
                return CommandResponse(
                    command_result=CommandResult(success=False),
                    instance_id=request.instance_id,
                    error=error_detail,
                )

            # Only shader profiles can be properly removed
            if profile.profile_type != "shader":
                error_detail = ErrorDetail(
                    code="PROFILE_TYPE_NOT_REMOVABLE",
                    message=f"Only shader profiles can be removed. Profile '{request.profile_name}' is type '{profile.profile_type}'",
                    details_json=json.dumps({
                        "instance_id": request.instance_id,
                        "profile": request.profile_name,
                        "profile_type": profile.profile_type,
                    }),
                )
                return CommandResponse(
                    command_result=CommandResult(success=False),
                    instance_id=request.instance_id,
                    error=error_detail,
                )

            # Extract shaders from profile options
            shaders_to_remove = []
            for key, value in profile.options.items():
                if key == "glsl-shaders-append":
                    # Normalize to list
                    if isinstance(value, str):
                        shaders_to_remove.append(value)
                    elif isinstance(value, list):
                        shaders_to_remove.extend(value)

            # Remove shaders in reverse order (LIFO for shader stack)
            removal_errors = []
            for shader in reversed(shaders_to_remove):
                try:
                    result = self.socket_manager.send_command(
                        request.instance_id,
                        ["change-list", "glsl-shaders", "remove", shader],
                    )
                    if result.get("error") != "success":
                        removal_errors.append(f"{shader}: {result.get('error')}")
                        logger.warning(
                            "Failed to remove shader",
                            instance_id=request.instance_id,
                            shader=shader,
                            error=result.get("error"),
                        )
                except Exception as e:
                    removal_errors.append(f"{shader}: {str(e)}")
                    logger.error(
                        "Exception while removing shader",
                        instance_id=request.instance_id,
                        shader=shader,
                        exception=str(e),
                    )

            # Remove profile from tracking (do this even if shader removal had errors)
            if request.instance_id in self.socket_manager._applied_profiles:
                self.socket_manager._applied_profiles[request.instance_id] = [
                    (name, ptype)
                    for name, ptype in self.socket_manager._applied_profiles[request.instance_id]
                    if name != request.profile_name
                ]

            logger.info(
                "Removed profile",
                instance_id=request.instance_id,
                profile=request.profile_name,
                shaders_removed=len(shaders_to_remove),
                errors=len(removal_errors),
            )

            # Get updated state
            state = self.socket_manager.get_standard_state(request.instance_id)

            # Determine overall success
            command_success = len(removal_errors) == 0

            # Build response data
            response_data = {
                "shaders_removed": len(shaders_to_remove),
            }
            if removal_errors:
                response_data["errors"] = removal_errors

            return CommandResponse(
                command_result=CommandResult(
                    success=command_success,
                    data_json=json.dumps(response_data),
                    error_message=f"Failed to remove {len(removal_errors)} shader(s)" if removal_errors else "",
                ),
                state=self._mpv_state_to_proto(state),
                instance_id=request.instance_id,
            )

        except MpvControllerError as e:
            logger.error("gRPC RemoveProfile error", error=str(e), code=e.code)
            return CommandResponse(
                command_result=CommandResult(success=False),
                instance_id=request.instance_id,
                error=self._create_error_detail(e),
            )

    def Check(self, request, context):
        """Health check."""
        logger.debug("gRPC health check")
        return HealthCheckResponse(
            status=HealthCheckResponse.SERVING
        )


def create_grpc_server(
    config: Config,
    socket_manager: MpvSocketManager,
    profile_manager: ProfileManager,
) -> grpc.Server:
    """Create and configure the gRPC server.

    Args:
        config: Application configuration.
        socket_manager: Socket manager for mpv communication.
        profile_manager: Profile manager for mpv profiles.

    Returns:
        Configured gRPC server (not started).
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    service = MpvControllerService(config, socket_manager, profile_manager)
    add_MpvControllerServicer_to_server(service, server)
    
    bind_address = f"{config.server.bind_address}:{config.server.grpc_port}"
    server.add_insecure_port(bind_address)
    
    logger.info("gRPC server configured", address=bind_address)
    
    return server
