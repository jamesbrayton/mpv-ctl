"""Data models and error handling for mpv-controller."""

from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class ProfileMode(str, Enum):
    """Mode of profile application."""

    RESET = "reset"
    ADDITIVE = "additive"
    RESET_ADDITIVE = "reset,additive"


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


class MpvPlaylistItem(BaseModel):
    """A single item in the mpv playlist."""

    filename: str = Field(
        ...,
        description="Path or URL of the media file",
        examples=["/path/to/video.mp4", "https://example.com/stream.m3u8"],
    )
    current: Optional[bool] = Field(
        None,
        description="Whether this is the current playlist item",
        examples=[True, False],
    )
    playing: Optional[bool] = Field(
        None,
        description="Whether this item is currently playing",
        examples=[True, False],
    )
    title: Optional[str] = Field(
        None,
        description="Title of the media if available",
        examples=["My Video"],
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
    speed: Optional[float] = Field(
        None,
        description="Current playback speed multiplier",
        examples=[1.0, 1.5, 2.0],
    )
    mute: Optional[bool] = Field(
        None,
        description="Whether audio is muted",
        examples=[True, False],
    )
    playlist: Optional[list[MpvPlaylistItem]] = Field(
        None,
        description="Current playlist contents",
    )
    glsl_shaders: Optional[list[str]] = Field(
        None,
        description="List of GLSL shaders currently applied",
        examples=[["/path/to/shader1.glsl", "/path/to/shader2.glsl"]],
    )
    media_title: Optional[str] = Field(
        None,
        description="Title of the current media (may differ from filename)",
        examples=["Movie Title", "Stream Name"],
    )
    loop_file: Optional[Union[str, bool, int]] = Field(
        None,
        description="Loop status for current file ('inf' for infinite loop, 'no' or False for disabled, or a number)",
        examples=["inf", "no", False, 3],
    )
    shuffle: Optional[bool] = Field(
        None,
        description="Whether playlist shuffle is enabled",
        examples=[True, False],
    )
    applied_profiles: Optional[list[str]] = Field(
        None,
        description="List of currently applied profile names in application order",
        examples=[["anime4k-medium", "debanding"]],
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


class SpeedRequest(BaseModel):
    """Request for setting playback speed."""

    speed: float = Field(
        ...,
        description="Playback speed multiplier (0.01-100)",
        examples=[1.0, 1.5, 2.0],
        ge=0.01,
        le=100,
    )


# Profile Models
class ProfileInfo(BaseModel):
    """Information about an mpv profile."""

    name: str = Field(
        ...,
        description="Name of the profile",
        examples=["gpu-hq", "low-latency"],
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Profile options/settings",
        examples=[{"vo": "gpu", "hwdec": "auto"}],
    )
    profile_type: str = Field(
        ...,
        description="Type of profile (e.g., 'shader', 'setting', 'vf', 'ao')",
    )
    profile_mode: ProfileMode = Field(
        ...,
        description="Application mode (reset, additive, or reset,additive)",
    )
    track: bool = Field(
        True,
        description="Whether to track this profile in applied_profiles list (default: True)",
    )


class ProfileCreateRequest(BaseModel):
    """Request for creating a new profile."""

    name: str = Field(
        ...,
        description="Name of the profile to create",
        examples=["my-custom-profile"],
        min_length=1,
        max_length=100,
    )
    options: dict[str, Any] = Field(
        ...,
        description="Profile options/settings",
        examples=[{"vo": "gpu", "hwdec": "auto"}],
    )


class ProfileUpdateRequest(BaseModel):
    """Request for updating a profile."""

    options: dict[str, Any] = Field(
        ...,
        description="New profile options/settings (replaces existing)",
        examples=[{"vo": "gpu", "hwdec": "auto"}],
    )


class ProfileListResponse(BaseModel):
    """Response containing list of profiles."""

    profiles: list[ProfileInfo] = Field(
        ...,
        description="List of available profiles",
    )


# Playlist Models
class PlaylistInfo(BaseModel):
    """Information about a playlist."""

    name: str = Field(
        ...,
        description="Name of the playlist (without .m3u extension)",
        examples=["favorites", "workout"],
    )
    path: str = Field(
        ...,
        description="Full path to the playlist file",
        examples=["/media/playlists/favorites.m3u"],
    )
    entry_count: int = Field(
        ...,
        description="Number of entries in the playlist",
        examples=[10, 25],
        ge=0,
    )


class PlaylistEntry(BaseModel):
    """A single entry in a playlist."""

    path: str = Field(
        ...,
        description="Path to the media file",
        examples=["/media/videos/video1.mp4"],
    )
    title: Optional[str] = Field(
        None,
        description="Optional title for the entry",
        examples=["My Favorite Video"],
    )


class PlaylistContents(BaseModel):
    """Contents of a playlist."""

    name: str = Field(
        ...,
        description="Name of the playlist",
        examples=["favorites"],
    )
    entries: list[PlaylistEntry] = Field(
        ...,
        description="List of entries in the playlist",
    )


class PlaylistListResponse(BaseModel):
    """Response containing list of playlists."""

    playlists: list[PlaylistInfo] = Field(
        ...,
        description="List of available playlists",
    )
    folder: str = Field(
        ...,
        description="Path to the playlist folder",
        examples=["/media/playlists"],
    )


class PlaylistCreateRequest(BaseModel):
    """Request for creating a new playlist."""

    name: str = Field(
        ...,
        description="Name of the playlist to create (without .m3u extension)",
        examples=["my-new-playlist"],
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_\-]+$",
    )
    entries: list[PlaylistEntry] = Field(
        ...,
        description="Initial entries for the playlist",
    )


class PlaylistUpdateRequest(BaseModel):
    """Request for updating a playlist."""

    entries: list[PlaylistEntry] = Field(
        ...,
        description="Entries to add or replace",
    )
    replace: bool = Field(
        default=False,
        description="If true, replace all entries; if false, append to existing",
    )


class PlaylistSwitchMode(str, Enum):
    """Mode for switching to a new playlist."""

    IMMEDIATE = "immediate"
    AFTER_CURRENT = "after_current"
    AFTER_PLAYLIST = "after_playlist"


class PlaylistSwitchRequest(BaseModel):
    """Request for switching to a playlist."""

    name: str = Field(
        ...,
        description="Name of the playlist to switch to",
        examples=["favorites"],
    )
    mode: PlaylistSwitchMode = Field(
        default=PlaylistSwitchMode.IMMEDIATE,
        description="When to switch to the new playlist",
    )


class MessageResponse(BaseModel):
    """Generic success response with a message."""

    success: bool = Field(
        default=True,
        description="Whether the operation was successful",
    )
    message: str = Field(
        ...,
        description="Description of what was done",
        examples=["Profile created successfully"],
    )
