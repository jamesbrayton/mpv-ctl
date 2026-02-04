"""REST API implementation with FastAPI."""

from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Path as PathParam, Query, status
from fastapi.responses import JSONResponse

from .config import Config
from .models import (
    CommandResponse,
    CommandResult,
    ErrorCode,
    ErrorResponse,
    HealthResponse,
    InstanceStatus,
    MessageResponse,
    MpvControllerError,
    PlaylistContents,
    PlaylistCreateRequest,
    PlaylistListResponse,
    PlaylistSwitchMode,
    PlaylistSwitchRequest,
    PlaylistUpdateRequest,
    ProfileCreateRequest,
    ProfileInfo,
    ProfileListResponse,
    ProfileUpdateRequest,
    PropertyValue,
    RawCommandRequest,
    ReadyResponse,
    SeekRequest,
    SpeedRequest,
    VolumeRequest,
)
from .playlist_manager import (
    PlaylistConfigError,
    PlaylistExistsError,
    PlaylistManager,
    PlaylistNotFoundError,
)
from .profile_manager import (
    ProfileConfigError,
    ProfileExistsError,
    ProfileManager,
    ProfileNotFoundError,
)
from .socket_manager import MpvSocketManager

logger = structlog.get_logger()


def create_rest_app(
    config: Config,
    socket_manager: MpvSocketManager,
    profile_manager: ProfileManager,
    playlist_manager: PlaylistManager,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Application configuration.
        socket_manager: Socket manager for mpv communication.
        profile_manager: Profile manager for mpv profiles.
        playlist_manager: Playlist manager for playlist files.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="mpv Controller API",
        description="REST API for controlling multiple mpv instances via Unix sockets",
        version="0.2.5",
        docs_url="/docs" if config.server.enable_swagger_ui else None,
        redoc_url="/redoc" if config.server.enable_swagger_ui else None,
    )

    # Exception handler for custom errors
    @app.exception_handler(MpvControllerError)
    async def mpv_error_handler(request, exc: MpvControllerError):
        """Handle custom mpv controller errors."""
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        # Map error codes to HTTP status codes
        if exc.code == ErrorCode.INSTANCE_NOT_FOUND:
            status_code = status.HTTP_404_NOT_FOUND
        elif exc.code == ErrorCode.SOCKET_TIMEOUT:
            status_code = status.HTTP_504_GATEWAY_TIMEOUT
        elif exc.code == ErrorCode.SOCKET_CONNECTION_ERROR:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif exc.code == ErrorCode.VALIDATION_ERROR:
            status_code = status.HTTP_400_BAD_REQUEST

        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(
                error={
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            ).model_dump(),
        )

    @app.exception_handler(ProfileNotFoundError)
    async def profile_not_found_handler(request, exc: ProfileNotFoundError):
        """Handle profile not found errors."""
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                error={
                    "code": "PROFILE_NOT_FOUND",
                    "message": str(exc),
                    "details": {"name": exc.name},
                }
            ).model_dump(),
        )

    @app.exception_handler(ProfileExistsError)
    async def profile_exists_handler(request, exc: ProfileExistsError):
        """Handle profile already exists errors."""
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(
                error={
                    "code": "PROFILE_EXISTS",
                    "message": str(exc),
                    "details": {"name": exc.name},
                }
            ).model_dump(),
        )

    @app.exception_handler(ProfileConfigError)
    async def profile_config_handler(request, exc: ProfileConfigError):
        """Handle profile configuration errors."""
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                error={
                    "code": "PROFILE_CONFIG_ERROR",
                    "message": str(exc),
                    "details": {},
                }
            ).model_dump(),
        )

    @app.exception_handler(PlaylistNotFoundError)
    async def playlist_not_found_handler(request, exc: PlaylistNotFoundError):
        """Handle playlist not found errors."""
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                error={
                    "code": "PLAYLIST_NOT_FOUND",
                    "message": str(exc),
                    "details": {"name": exc.name},
                }
            ).model_dump(),
        )

    @app.exception_handler(PlaylistExistsError)
    async def playlist_exists_handler(request, exc: PlaylistExistsError):
        """Handle playlist already exists errors."""
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(
                error={
                    "code": "PLAYLIST_EXISTS",
                    "message": str(exc),
                    "details": {"name": exc.name},
                }
            ).model_dump(),
        )

    @app.exception_handler(PlaylistConfigError)
    async def playlist_config_handler(request, exc: PlaylistConfigError):
        """Handle playlist configuration errors."""
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                error={
                    "code": "PLAYLIST_CONFIG_ERROR",
                    "message": str(exc),
                    "details": {},
                }
            ).model_dump(),
        )

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Health check endpoint",
        description="Returns the health status of the service. Always returns healthy regardless of individual instance states.",
    )
    async def health():
        """Health check endpoint for k8s liveness probe."""
        return HealthResponse(status="healthy")

    @app.get(
        "/ready",
        response_model=ReadyResponse,
        tags=["Health"],
        summary="Readiness check endpoint",
        description="Returns readiness status and availability of all configured mpv instances.",
    )
    async def ready():
        """Readiness check endpoint for k8s readiness probe."""
        availability = socket_manager.get_instance_availability()
        
        instances = []
        for instance_id, mpv_instance in socket_manager.instances.items():
            instances.append(
                InstanceStatus(
                    instance_id=instance_id,
                    available=availability.get(instance_id, False),
                    socket_path=mpv_instance.socket_path,
                    display_name=mpv_instance.display_name,
                )
            )
        
        return ReadyResponse(
            ready=True,
            instances=instances,
        )

    @app.post(
        "/mpv/{instance_id}/pause",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Toggle pause state",
        description="Toggles the pause state of the specified mpv instance and returns the updated state.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def pause(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Toggle pause state."""
        logger.info("Pause command", instance_id=instance_id)
        
        # Execute pause command
        result = socket_manager.send_command(instance_id, ["cycle", "pause"])
        
        # Get updated state
        state = socket_manager.get_standard_state(instance_id)
        
        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/play",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Resume playback",
        description="Resumes playback on the specified mpv instance and returns the updated state.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def play(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Resume playback."""
        logger.info("Play command", instance_id=instance_id)
        
        # Set pause to false
        result = socket_manager.send_command(instance_id, ["set_property", "pause", False])
        
        # Get updated state
        state = socket_manager.get_standard_state(instance_id)
        
        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/seek",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Seek to position",
        description="Seeks to a specific position in the current media and returns the updated state.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def seek(
        seek_request: SeekRequest,
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Seek to a position."""
        logger.info(
            "Seek command",
            instance_id=instance_id,
            position=seek_request.position,
            relative=seek_request.relative,
        )
        
        # Execute seek command
        mode = "relative" if seek_request.relative else "absolute"
        result = socket_manager.send_command(
            instance_id,
            ["seek", seek_request.position, mode],
        )
        
        # Get updated state
        state = socket_manager.get_standard_state(instance_id)
        
        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/volume",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Set volume",
        description="Sets the volume level for the specified mpv instance and returns the updated state.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def set_volume(
        volume_request: VolumeRequest,
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Set volume level."""
        logger.info(
            "Volume command",
            instance_id=instance_id,
            volume=volume_request.volume,
        )

        # Execute volume command
        result = socket_manager.send_command(
            instance_id,
            ["set_property", "volume", volume_request.volume],
        )

        # Get updated state
        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/volume/up",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Increase volume",
        description="Increases the volume by 5.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def volume_up(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Increase volume by 5."""
        logger.info("Volume up command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["add", "volume", 5],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/volume/down",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Decrease volume",
        description="Decreases the volume by 5.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def volume_down(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Decrease volume by 5."""
        logger.info("Volume down command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["add", "volume", -5],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/mute",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Toggle mute",
        description="Toggles the mute state of the specified mpv instance.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def mute(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Toggle mute state."""
        logger.info("Mute command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["cycle", "mute"],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )
    
    @app.post(
        "/mpv/{instance_id}/loop",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Toggle loop for current file",
        description="Toggles the loop state for the currently playing file between infinite loop and no loop. "
                    "This does not affect playlist looping.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def loop(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Toggle loop state for current file."""
        logger.info("Loop toggle command", instance_id=instance_id)

        # Get current loop-file value
        current_value = socket_manager.get_property(instance_id, "loop-file")
        
        # Toggle between 'inf' and 'no'
        # mpv can return: "inf", "no", False, True, or a number
        # If current value is 'inf', True, or any number > 0, set to 'no'
        # Otherwise, set to 'inf'
        new_value = "no" if (current_value == "inf" or current_value is True or (isinstance(current_value, (int, str)) and str(current_value).isdigit() and int(current_value) > 0)) else "inf"
        
        result = socket_manager.send_command(
            instance_id,
            ["set_property", "loop-file", new_value],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )
    
    @app.post(
        "/mpv/{instance_id}/shuffle",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Toggle shuffle",
        description="Toggles the shuffle state of the current playlist.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def shuffle(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Toggle shuffle state."""
        logger.info("Shuffle toggle command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["cycle", "shuffle"],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )
    
    @app.get(
        "/mpv/{instance_id}/properties",
        tags=["Properties"],
        summary="Get available properties",
        description="Retrieves the list of all available properties from the mpv instance.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def list_properties(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Get list of available properties."""
        logger.info(
            "List properties",
            instance_id=instance_id,
        )
        
        properties = socket_manager.get_property(instance_id, "property-list")
        
        return {
            "instance_id": instance_id,
            "properties": properties,
        }

    @app.get(
        "/mpv/{instance_id}/properties/{property_name}",
        response_model=PropertyValue,
        tags=["Properties"],
        summary="Get property value",
        description="Retrieves the value of a specific property from an mpv instance.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def get_property(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
        property_name: str = PathParam(..., description="Name of the property to get"),
    ):
        """Get a property value."""
        logger.info(
            "Get property",
            instance_id=instance_id,
            property=property_name,
        )
        
        value = socket_manager.get_property(instance_id, property_name)
        
        return PropertyValue(
            name=property_name,
            value=value,
            instance_id=instance_id,
        )

    @app.get(
        "/mpv/{instance_id}/status",
        response_model=CommandResponse,
        tags=["Status"],
        summary="Get instance status",
        description="Retrieves the current status and state of an mpv instance.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def get_status(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Get instance status."""
        logger.info("Get status", instance_id=instance_id)
        
        state = socket_manager.get_standard_state(instance_id)
        
        return CommandResponse(
            command_result=CommandResult(
                success=True,
                data=None,
                error=None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/command",
        response_model=CommandResponse,
        tags=["Raw Commands"],
        summary="Execute raw command",
        description="Executes a raw mpv command and returns the result with updated state.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def raw_command(
        command_request: RawCommandRequest,
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Execute a raw mpv command."""
        logger.info(
            "Raw command",
            instance_id=instance_id,
            command=command_request.command,
        )
        
        # Execute command
        result = socket_manager.send_command(instance_id, command_request.command)
        
        # Get updated state
        state = socket_manager.get_standard_state(instance_id)
        
        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    # ==================== Speed Control Endpoints ====================

    @app.post(
        "/mpv/{instance_id}/speed",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Set playback speed",
        description="Sets the playback speed for the specified mpv instance.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def set_speed(
        speed_request: SpeedRequest,
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Set playback speed."""
        logger.info(
            "Speed command",
            instance_id=instance_id,
            speed=speed_request.speed,
        )

        result = socket_manager.send_command(
            instance_id,
            ["set_property", "speed", speed_request.speed],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/speed/up",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Increase playback speed",
        description="Increases the playback speed by 0.05.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def speed_up(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Increase playback speed by 0.05."""
        logger.info("Speed up command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["add", "speed", 0.05],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/speed/down",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Decrease playback speed",
        description="Decreases the playback speed by 0.05.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def speed_down(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Decrease playback speed by 0.05."""
        logger.info("Speed down command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["add", "speed", -0.05],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    # ==================== Frame Navigation Endpoints ====================

    @app.post(
        "/mpv/{instance_id}/frame/forward",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Advance one frame",
        description="Advances forward by a single frame.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def frame_forward(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Advance forward by one frame."""
        logger.info("Frame forward command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["frame-step"],
        )

        state = socket_manager.get_standard_state(instance_id)
        # frame-step always pauses, but mpv may not have updated the state yet
        state.pause = True

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/frame/backward",
        response_model=CommandResponse,
        tags=["Playback Control"],
        summary="Go back one frame",
        description="Goes backward by a single frame.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def frame_backward(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Go backward by one frame."""
        logger.info("Frame backward command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["frame-back-step"],
        )

        state = socket_manager.get_standard_state(instance_id)
        # frame-back-step always pauses, but mpv may not have updated the state yet
        state.pause = True

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    # ==================== Playlist Navigation Endpoints ====================

    @app.post(
        "/mpv/{instance_id}/playlist/next",
        response_model=CommandResponse,
        tags=["Playlist Navigation"],
        summary="Play next video",
        description="Plays the next video in the playlist.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def playlist_next(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Play next video in playlist."""
        logger.info("Playlist next command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["playlist-next"],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/playlist/previous",
        response_model=CommandResponse,
        tags=["Playlist Navigation"],
        summary="Play previous video",
        description="Plays the previous video in the playlist.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def playlist_previous(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Play previous video in playlist."""
        logger.info("Playlist previous command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["playlist-prev"],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    @app.post(
        "/mpv/{instance_id}/playlist/restart",
        response_model=CommandResponse,
        tags=["Playlist Navigation"],
        summary="Restart current video",
        description="Restarts the current video from the beginning.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def playlist_restart(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Restart current video from the beginning."""
        logger.info("Playlist restart command", instance_id=instance_id)

        result = socket_manager.send_command(
            instance_id,
            ["seek", 0, "absolute"],
        )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    # ==================== Profile Management Endpoints ====================

    @app.get(
        "/profiles",
        response_model=ProfileListResponse,
        tags=["Profiles"],
        summary="List all profiles",
        description="Returns a list of all available mpv profiles.",
        responses={
            503: {"model": ErrorResponse, "description": "Profile configuration error"},
        },
    )
    async def list_profiles():
        """List all available profiles."""
        logger.info("List profiles")
        profiles = profile_manager.list_profiles()
        return ProfileListResponse(profiles=profiles)

    @app.get(
        "/profiles/{name}",
        response_model=ProfileInfo,
        tags=["Profiles"],
        summary="Get profile details",
        description="Returns the details of a specific profile by name.",
        responses={
            404: {"model": ErrorResponse, "description": "Profile not found"},
            503: {"model": ErrorResponse, "description": "Profile configuration error"},
        },
    )
    async def get_profile_details(
        name: str = PathParam(..., description="Name of the profile"),
    ):
        """Get profile details by name."""
        logger.info("Get profile", name=name)
        return profile_manager.get_profile(name)

    @app.post(
        "/profiles",
        response_model=ProfileInfo,
        status_code=status.HTTP_201_CREATED,
        tags=["Profiles"],
        summary="Create a new profile",
        description="Creates a new mpv profile with the specified options.",
        responses={
            409: {"model": ErrorResponse, "description": "Profile already exists"},
            503: {"model": ErrorResponse, "description": "Profile configuration error"},
        },
    )
    async def create_profile(request: ProfileCreateRequest):
        """Create a new profile."""
        logger.info("Create profile", name=request.name)
        return profile_manager.create_profile(request.name, request.options)

    @app.put(
        "/profiles/{name}",
        response_model=ProfileInfo,
        tags=["Profiles"],
        summary="Update a profile",
        description="Updates an existing profile (replaces all options).",
        responses={
            404: {"model": ErrorResponse, "description": "Profile not found"},
            503: {"model": ErrorResponse, "description": "Profile configuration error"},
        },
    )
    async def update_profile(
        request: ProfileUpdateRequest,
        name: str = PathParam(..., description="Name of the profile to update"),
    ):
        """Update an existing profile."""
        logger.info("Update profile", name=name)
        return profile_manager.update_profile(name, request.options)

    @app.delete(
        "/profiles/{name}",
        response_model=MessageResponse,
        tags=["Profiles"],
        summary="Delete a profile",
        description="Deletes a profile by name.",
        responses={
            404: {"model": ErrorResponse, "description": "Profile not found"},
            503: {"model": ErrorResponse, "description": "Profile configuration error"},
        },
    )
    async def delete_profile(
        name: str = PathParam(..., description="Name of the profile to delete"),
    ):
        """Delete a profile."""
        logger.info("Delete profile", name=name)
        profile_manager.delete_profile(name)
        return MessageResponse(success=True, message=f"Profile '{name}' deleted successfully")

    @app.post(
        "/mpv/{instance_id}/profile",
        response_model=CommandResponse,
        tags=["Profiles"],
        summary="Apply profile to instance",
        description="Applies a profile to the specified mpv instance.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance or profile not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error"},
        },
    )
    async def apply_profile(
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
        profile_name: str = Query(..., description="Name of the profile to apply"),
    ):
        """Apply a profile to an mpv instance."""
        logger.info("Apply profile", instance_id=instance_id, profile=profile_name)

        # Get profile with metadata
        profile = profile_manager.get_profile(profile_name)

        result = socket_manager.send_command(
            instance_id,
            ["apply-profile", profile_name],
        )

        # Log the raw result from mpv for debugging
        logger.info(
            "Profile apply result from mpv",
            instance_id=instance_id,
            profile=profile_name,
            mpv_result=result,
        )

        # Track the applied profile if command was successful
        if result.get("error") == "success":
            try:
                socket_manager.track_applied_profile(
                    instance_id,
                    profile_name,
                    profile.profile_type,
                    profile.profile_mode,
                )
                logger.info(
                    "Profile tracked successfully",
                    instance_id=instance_id,
                    profile=profile_name,
                    type=profile.profile_type,
                    mode=profile.profile_mode.value,
                )
            except Exception as e:
                logger.error(
                    "Failed to track profile - exception during tracking",
                    instance_id=instance_id,
                    profile=profile_name,
                    type=profile.profile_type,
                    mode=profile.profile_mode,
                    exception=str(e),
                    exception_type=type(e).__name__,
                    exc_info=True,
                )
        else:
            logger.warning(
                "Profile not tracked - mpv returned error",
                instance_id=instance_id,
                profile=profile_name,
                error=result.get("error"),
            )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    # ==================== Playlist File Management Endpoints ====================

    @app.get(
        "/playlists",
        response_model=PlaylistListResponse,
        tags=["Playlist Management"],
        summary="List all playlists",
        description="Returns a list of all playlists in the configured folder.",
        responses={
            503: {"model": ErrorResponse, "description": "Playlist configuration error"},
        },
    )
    async def list_playlists_in_folder():
        """List all playlists in the folder."""
        logger.info("List playlists")
        playlists = playlist_manager.list_playlists()
        folder = playlist_manager.get_playlist_folder()
        return PlaylistListResponse(playlists=playlists, folder=folder)

    @app.get(
        "/playlists/{name}",
        response_model=PlaylistContents,
        tags=["Playlist Management"],
        summary="Get playlist contents",
        description="Returns the contents of a specific playlist by name.",
        responses={
            404: {"model": ErrorResponse, "description": "Playlist not found"},
            503: {"model": ErrorResponse, "description": "Playlist configuration error"},
        },
    )
    async def get_playlist_contents(
        name: str = PathParam(..., description="Name of the playlist (without .m3u extension)"),
    ):
        """Get playlist contents by name."""
        logger.info("Get playlist", name=name)
        return playlist_manager.get_playlist(name)

    @app.post(
        "/playlists",
        response_model=PlaylistContents,
        status_code=status.HTTP_201_CREATED,
        tags=["Playlist Management"],
        summary="Create a new playlist",
        description="Creates a new playlist file with the specified entries.",
        responses={
            409: {"model": ErrorResponse, "description": "Playlist already exists"},
            503: {"model": ErrorResponse, "description": "Playlist configuration error"},
        },
    )
    async def create_playlist_file(request: PlaylistCreateRequest):
        """Create a new playlist file."""
        logger.info("Create playlist", name=request.name)
        return playlist_manager.create_playlist(request.name, request.entries)

    @app.put(
        "/playlists/{name}",
        response_model=PlaylistContents,
        tags=["Playlist Management"],
        summary="Update a playlist",
        description="Updates a playlist (append or replace entries).",
        responses={
            404: {"model": ErrorResponse, "description": "Playlist not found"},
            503: {"model": ErrorResponse, "description": "Playlist configuration error"},
        },
    )
    async def update_playlist_file(
        request: PlaylistUpdateRequest,
        name: str = PathParam(..., description="Name of the playlist to update"),
    ):
        """Update a playlist."""
        logger.info("Update playlist", name=name, replace=request.replace)
        return playlist_manager.update_playlist(name, request.entries, request.replace)

    @app.delete(
        "/playlists/{name}",
        response_model=MessageResponse,
        tags=["Playlist Management"],
        summary="Delete a playlist",
        description="Deletes a playlist file by name.",
        responses={
            404: {"model": ErrorResponse, "description": "Playlist not found"},
            503: {"model": ErrorResponse, "description": "Playlist configuration error"},
        },
    )
    async def delete_playlist_file(
        name: str = PathParam(..., description="Name of the playlist to delete"),
    ):
        """Delete a playlist file."""
        logger.info("Delete playlist", name=name)
        playlist_manager.delete_playlist(name)
        return MessageResponse(success=True, message=f"Playlist '{name}' deleted successfully")

    @app.post(
        "/mpv/{instance_id}/playlist/switch",
        response_model=CommandResponse,
        tags=["Playlist Navigation"],
        summary="Switch to a playlist",
        description="Switches the mpv instance to play from a specified playlist file.",
        responses={
            404: {"model": ErrorResponse, "description": "Instance or playlist not found"},
            504: {"model": ErrorResponse, "description": "Socket timeout"},
            503: {"model": ErrorResponse, "description": "Socket connection error or configuration error"},
        },
    )
    async def switch_playlist(
        request: PlaylistSwitchRequest,
        instance_id: str = PathParam(..., description="ID of the mpv instance"),
    ):
        """Switch to a playlist."""
        logger.info(
            "Switch playlist",
            instance_id=instance_id,
            playlist=request.name,
            mode=request.mode,
        )

        # Get the playlist to verify it exists and get the path
        playlist = playlist_manager.get_playlist(request.name)
        playlist_path = playlist_manager._get_playlist_path(request.name)

        if request.mode == PlaylistSwitchMode.IMMEDIATE:
            # Load the playlist and start playing immediately
            result = socket_manager.send_command(
                instance_id,
                ["loadlist", str(playlist_path), "replace"],
            )
        elif request.mode == PlaylistSwitchMode.AFTER_CURRENT:
            # Append playlist and it will play after current video
            result = socket_manager.send_command(
                instance_id,
                ["loadlist", str(playlist_path), "append"],
            )
        else:  # AFTER_PLAYLIST
            # Append playlist to end of current playlist
            result = socket_manager.send_command(
                instance_id,
                ["loadlist", str(playlist_path), "append"],
            )

        state = socket_manager.get_standard_state(instance_id)

        return CommandResponse(
            command_result=CommandResult(
                success=result.get("error") == "success",
                data=result.get("data"),
                error=result.get("error") if result.get("error") != "success" else None,
            ),
            state=state,
            instance_id=instance_id,
        )

    return app
