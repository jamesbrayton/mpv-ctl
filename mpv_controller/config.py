"""Configuration management for mpv-controller."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class MpvInstance(BaseModel):
    """Configuration for a single mpv instance."""

    id: str = Field(
        ...,
        description="Unique identifier for this mpv instance",
        examples=["mpv-0", "living-room"],
    )
    socket_path: str = Field(
        ...,
        description="Path to the Unix socket for this mpv instance",
        examples=["/run/user/1000/app/io.mpv.Mpv/mpv-0/mpv.sock"],
    )
    display_name: Optional[str] = Field(
        None,
        description="Human-readable display name for this instance",
        examples=["Living Room TV", "Bedroom Player"],
    )


class ServerSettings(BaseModel):
    """Server configuration settings."""

    rest_port: int = Field(
        default=8000,
        description="Port for the REST API server",
        ge=1,
        le=65535,
    )
    grpc_port: int = Field(
        default=50051,
        description="Port for the gRPC server",
        ge=1,
        le=65535,
    )
    bind_address: str = Field(
        default="0.0.0.0",
        description="Address to bind servers to (0.0.0.0 for all interfaces)",
    )
    enable_swagger_ui: bool = Field(
        default=True,
        description="Enable Swagger UI documentation at /docs",
    )


class LoggingSettings(BaseModel):
    """Logging configuration settings."""

    log_level: str = Field(
        default="INFO",
        description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    log_file: Optional[str] = Field(
        None,
        description="Optional file path for logging (logs to stdout if not specified)",
        examples=["/var/log/mpv-controller/app.log"],
    )


class SocketSettings(BaseModel):
    """Socket communication settings."""

    read_timeout: float = Field(
        default=2.0,
        description="Timeout in seconds for socket read operations",
        gt=0,
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retry attempts for read operations",
        ge=0,
    )
    backoff_multiplier: float = Field(
        default=0.5,
        description="Exponential backoff multiplier for retries",
        gt=0,
    )
    jitter: bool = Field(
        default=True,
        description="Add random jitter to retry backoff timing",
    )
    availability_check_interval: int = Field(
        default=30,
        description="Interval in seconds for checking instance availability (0 to disable caching)",
        ge=0,
    )


class Config(BaseModel):
    """Root configuration model."""

    mpv_instances: list[MpvInstance] = Field(
        ...,
        description="List of mpv instances to control",
        min_length=1,
    )
    server: ServerSettings = Field(
        default_factory=ServerSettings,
        description="Server configuration",
    )
    logging: LoggingSettings = Field(
        default_factory=LoggingSettings,
        description="Logging configuration",
    )
    socket: SocketSettings = Field(
        default_factory=SocketSettings,
        description="Socket communication configuration",
    )


def get_config_path() -> Path:
    """Get the configuration file path from environment or default XDG location."""
    if config_path := os.environ.get("MPV_CONTROLLER_CONFIG"):
        return Path(config_path)

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        config_dir = Path(xdg_config_home)
    else:
        config_dir = Path.home() / ".config"

    return config_dir / "mpv-controller" / "config.yaml"


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Optional path to config file. If not provided, uses default location.

    Returns:
        Parsed and validated Config object.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        yaml.YAMLError: If config file is invalid YAML.
        pydantic.ValidationError: If config doesn't match schema.
    """
    if config_path is None:
        config_path = get_config_path()

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please create a config file at this location or set MPV_CONTROLLER_CONFIG environment variable."
        )

    with open(config_path) as f:
        config_data = yaml.safe_load(f)

    return Config(**config_data)
