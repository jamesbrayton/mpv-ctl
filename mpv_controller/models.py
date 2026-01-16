"""Data models and error handling for mpv-controller."""

from typing import Any, Optional

from pydantic import BaseModel, Field


# Error Codes
class ErrorCode:
    """Standard error codes for the application."""

    INSTANCE_NOT_FOUND = "INSTANCE_NOT_FOUND"
    SOCKET_TIMEOUT = "SOCKET_TIMEOUT"
    SOCKET_CONNECTION_ERROR = "SOCKET_CONNECTION_ERROR"
    INVALID_COMMAND = "INVALID_COMMAND"
    COMMAND_EXECUTION_ERROR = "COMMAND_EXECUTION_ERROR"
    PROPERTY_NOT_FOUND = "PROPERTY_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"


# Custom Exceptions
class MpvControllerError(Exception):
    """Base exception for mpv-controller errors."""

    def __init__(self, code: str, message: str, details: Optional[dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class InstanceNotFoundError(MpvControllerError):
    """Raised when a requested mpv instance doesn't exist."""

    def __init__(self, instance_id: str):
        super().__init__(
            code=ErrorCode.INSTANCE_NOT_FOUND,
            message=f"mpv instance '{instance_id}' not found",
            details={"instance_id": instance_id},
        )


class SocketTimeoutError(MpvControllerError):
    """Raised when a socket operation times out."""

    def __init__(self, instance_id: str, timeout: float):
        super().__init__(
            code=ErrorCode.SOCKET_TIMEOUT,
            message=f"Socket operation timed out after {timeout}s for instance '{instance_id}'",
            details={"instance_id": instance_id, "timeout": timeout},
        )


class SocketConnectionError(MpvControllerError):
    """Raised when unable to connect to socket."""

    def __init__(self, instance_id: str, socket_path: str, reason: str):
        super().__init__(
            code=ErrorCode.SOCKET_CONNECTION_ERROR,
            message=f"Failed to connect to socket for instance '{instance_id}': {reason}",
            details={"instance_id": instance_id, "socket_path": socket_path, "reason": reason},
        )


class CommandExecutionError(MpvControllerError):
    """Raised when a command execution fails."""

    def __init__(self, instance_id: str, command: list, reason: str):
        super().__init__(
            code=ErrorCode.COMMAND_EXECUTION_ERROR,
            message=f"Command execution failed for instance '{instance_id}': {reason}",
            details={"instance_id": instance_id, "command": command, "reason": reason},
        )


# API Models
class ErrorDetail(BaseModel):
    """Error details in API responses."""

    code: str = Field(
        ...,
        description="Error code identifying the type of error",
        examples=[ErrorCode.INSTANCE_NOT_FOUND, ErrorCode.SOCKET_TIMEOUT],
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["mpv instance 'mpv-0' not found"],
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context about the error",
        examples=[{"instance_id": "mpv-0"}],
    )


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: ErrorDetail = Field(
        ...,
        description="Error information",
    )


class MpvState(BaseModel):
    """State information from mpv instance."""

    pause: Optional[bool] = Field(
        None,
        description="Whether playback is paused",
        examples=[True, False],
    )
    time_pos: Optional[float] = Field(
        None,
        description="Current playback position in seconds",
        examples=[123.45],
    )
    duration: Optional[float] = Field(
        None,
        description="Total duration of current media in seconds",
        examples=[300.0],
    )
    filename: Optional[str] = Field(
        None,
        description="Currently playing filename",
        examples=["/path/to/video.mp4", "https://example.com/stream.m3u8"],
    )
    volume: Optional[float] = Field(
        None,
        description="Current volume level (0-100)",
        examples=[75.0],
    )


class CommandResult(BaseModel):
    """Result from executing a command."""

    success: bool = Field(
        ...,
        description="Whether the command executed successfully",
        examples=[True, False],
    )
    data: Optional[Any] = Field(
        None,
        description="Data returned from mpv (if any)",
        examples=[None, "success", 42],
    )
    error: Optional[str] = Field(
        None,
        description="Error message if command failed",
        examples=[None, "property unavailable"],
    )


class CommandResponse(BaseModel):
    """Response from a semantic command endpoint."""

    command_result: CommandResult = Field(
        ...,
        description="Result of the command execution",
    )
    state: MpvState = Field(
        ...,
        description="Current state of the mpv instance after command",
    )
    instance_id: str = Field(
        ...,
        description="ID of the mpv instance that executed the command",
        examples=["mpv-0", "living-room"],
    )


class PropertyValue(BaseModel):
    """Value of a specific property."""

    name: str = Field(
        ...,
        description="Name of the property",
        examples=["volume", "pause", "filename"],
    )
    value: Any = Field(
        ...,
        description="Current value of the property",
        examples=[75.0, True, "/path/to/video.mp4"],
    )
    instance_id: str = Field(
        ...,
        description="ID of the mpv instance",
        examples=["mpv-0"],
    )


class RawCommandRequest(BaseModel):
    """Request for executing a raw mpv command."""

    command: list[Any] = Field(
        ...,
        description="Raw mpv command as a list",
        examples=[["loadfile", "/path/to/video.mp4"], ["set_property", "volume", 50]],
        min_length=1,
    )


class InstanceStatus(BaseModel):
    """Status of a single mpv instance."""

    instance_id: str = Field(
        ...,
        description="ID of the mpv instance",
        examples=["mpv-0", "living-room"],
    )
    available: bool = Field(
        ...,
        description="Whether the instance is currently available",
        examples=[True, False],
    )
    socket_path: str = Field(
        ...,
        description="Path to the Unix socket",
        examples=["/run/user/1000/app/io.mpv.Mpv/mpv-0/mpv.sock"],
    )
    display_name: Optional[str] = Field(
        None,
        description="Human-readable display name",
        examples=["Living Room TV"],
    )


class ReadyResponse(BaseModel):
    """Response from the /ready endpoint."""

    ready: bool = Field(
        ...,
        description="Whether the service is ready",
        examples=[True],
    )
    instances: list[InstanceStatus] = Field(
        ...,
        description="Status of all configured mpv instances",
    )


class HealthResponse(BaseModel):
    """Response from the /health endpoint."""

    status: str = Field(
        default="healthy",
        description="Health status of the service",
        examples=["healthy"],
    )


# Request Models for semantic endpoints
class SeekRequest(BaseModel):
    """Request for seeking to a position."""

    position: float = Field(
        ...,
        description="Position to seek to in seconds",
        examples=[123.45],
        ge=0,
    )
    relative: bool = Field(
        default=False,
        description="Whether to seek relative to current position",
        examples=[False, True],
    )


class VolumeRequest(BaseModel):
    """Request for setting volume."""

    volume: float = Field(
        ...,
        description="Volume level (0-100)",
        examples=[75.0],
        ge=0,
        le=100,
    )
