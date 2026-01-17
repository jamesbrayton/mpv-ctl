# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

mpv-controller is a Python service for controlling multiple mpv media player instances via Unix sockets. It exposes both REST and gRPC APIs for remote control. Designed to run as a systemd user service on the same host as mpv instances, with external access through Kubernetes ingress.

## Development Commands

```bash
# Install dependencies (uses uv package manager)
export UV_CACHE_DIR=~/.uv-cache
uv sync --dev

# Run tests
uv run pytest
uv run pytest -v                              # verbose
uv run pytest tests/test_socket_manager.py    # single file

# Run the application locally
export MPV_CONTROLLER_CONFIG=~/.config/mpv-controller/config.yaml
uv run python -m mpv_controller.main

# Regenerate gRPC code after modifying mpv_control.proto
uv run python -m grpc_tools.protoc \
  -I mpv_controller \
  --python_out=mpv_controller \
  --grpc_python_out=mpv_controller \
  mpv_controller/mpv_control.proto
sed -i 's/^import mpv_control_pb2/from . import mpv_control_pb2/' \
  mpv_controller/mpv_control_pb2_grpc.py
```

## Architecture

```
┌─────────────────┐
│  k8s Ingress    │ (External authentication)
└────────┬────────┘
         │
┌────────▼────────┐
│  REST API :8000 │  ← FastAPI with OpenAPI docs at /docs
│  gRPC API :50051│  ← Protocol Buffers defined in mpv_control.proto
└────────┬────────┘
         │
┌────────▼────────┐
│  Socket Manager │  ← Retry logic with exponential backoff, availability caching
└────────┬────────┘
         │
    ┌────┴────┬────────┐
    │         │        │
┌───▼──┐  ┌──▼───┐  ┌─▼────┐
│mpv-0 │  │mpv-1 │  │mpv-2 │  ← Unix sockets (IPC)
└──────┘  └──────┘  └──────┘
```

### Key Components

- **main.py**: Entry point with concurrent server startup (REST in thread, gRPC in main), signal handling for graceful shutdown
- **config.py**: YAML configuration loading with Pydantic validation, XDG-compliant paths
- **models.py**: Pydantic data models, standardized error codes (`ErrorCode` class), custom exception hierarchy (`MpvControllerError` and subclasses)
- **socket_manager.py**: Multi-instance Unix socket communication with tenacity-based retry logic, availability caching via background thread
- **rest_api.py**: FastAPI application with semantic endpoints (/pause, /play, /seek, /volume), property endpoints, health/readiness checks
- **grpc_service.py**: gRPC service implementation mirroring REST functionality

### Design Decisions

- **Retry strategy**: Only GET/read operations use exponential backoff with jitter; writes are single-attempt to prevent duplicate commands
- **Availability caching**: Background thread periodically checks socket availability to reduce overhead on readiness endpoint calls
- **Synchronous sockets**: Direct socket operations for immediate responsiveness; REST/gRPC servers run concurrently via threading

## Configuration

Configuration file location priority:
1. `$MPV_CONTROLLER_CONFIG` environment variable
2. `$XDG_CONFIG_HOME/mpv-controller/config.yaml`
3. `~/.config/mpv-controller/config.yaml`

See `config.example.yaml` for all options. Key sections: `mpv_instances`, `server`, `logging`, `socket`.

## Error Handling

All errors use standardized codes defined in `models.py`:
- `INSTANCE_NOT_FOUND` (404)
- `SOCKET_TIMEOUT` (504)
- `SOCKET_CONNECTION_ERROR` (503)
- `COMMAND_EXECUTION_ERROR` (500)
- `VALIDATION_ERROR` (400)

Custom exceptions inherit from `MpvControllerError` with code, message, and details fields.

## Testing

Tests use pytest with mock-based unit testing (no running mpv required). Test files are in `tests/` directory. Uses `unittest.mock` for socket mocking and `fastapi.testclient.TestClient` for REST API testing.
