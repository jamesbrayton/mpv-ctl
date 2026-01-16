"""REST API implementation with FastAPI."""

from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Path as PathParam, status
from fastapi.responses import JSONResponse

from .config import Config
from .models import (
    CommandResponse,
    CommandResult,
    ErrorCode,
    ErrorResponse,
    HealthResponse,
    InstanceStatus,
    MpvControllerError,
    PropertyValue,
    RawCommandRequest,
    ReadyResponse,
    SeekRequest,
    VolumeRequest,
)
from .socket_manager import MpvSocketManager

logger = structlog.get_logger()


def create_rest_app(config: Config, socket_manager: MpvSocketManager) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Application configuration.
        socket_manager: Socket manager for mpv communication.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="mpv Controller API",
        description="REST API for controlling multiple mpv instances via Unix sockets",
        version="0.1.0",
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

    return app
