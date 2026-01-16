# mpv Controller - Implementation Complete ✅

A Python service for controlling multiple mpv instances via Unix sockets, exposing both REST and gRPC APIs.

## Implementation Status

All phases completed:

1. ✅ **Project Structure** - uv-based Python project with proper dependencies
2. ✅ **Configuration System** - YAML-based config with XDG support
3. ✅ **Socket Manager** - Resilient communication with retry logic and caching
4. ✅ **Models & Error Handling** - Standardized error responses with named codes
5. ✅ **REST API** - OpenAPI/Swagger documentation with semantic endpoints
6. ✅ **gRPC Service** - Full service implementation mirroring REST
7. ✅ **Server Startup** - Concurrent REST/gRPC with graceful shutdown
8. ✅ **Deployment** - systemd service file and k8s manifests

## Project Structure

```
mpv-controller/
├── mpv_controller/           # Main package
│   ├── __init__.py
│   ├── config.py            # YAML configuration loading
│   ├── models.py            # Pydantic models and error handling
│   ├── socket_manager.py    # mpv socket communication with retry
│   ├── rest_api.py          # FastAPI application
│   ├── grpc_service.py      # gRPC service implementation
│   ├── mpv_control.proto    # gRPC service definition
│   └── main.py              # Application entry point
├── tests/                    # Unit tests
│   ├── __init__.py
│   └── test_socket_manager.py
├── docs/                     # Documentation
│   └── README.md
├── k8s/                      # Kubernetes manifests
│   ├── service.yaml         # Service + Endpoints
│   └── ingress.yaml         # Ingress configuration
├── config.example.yaml       # Example configuration
├── mpv-controller.service    # systemd user service
├── pyproject.toml            # uv project configuration
└── README.md                 # Main documentation
```

## Quick Start

1. **Install dependencies:**
   ```bash
   export UV_CACHE_DIR=~/.uv-cache
   uv sync --dev
   ```

2. **Configure:**
   ```bash
   mkdir -p ~/.config/mpv-controller
   cp config.example.yaml ~/.config/mpv-controller/config.yaml
   # Edit config.yaml with your mpv socket paths
   ```

3. **Run locally:**
   ```bash
   export MPV_CONTROLLER_CONFIG=~/.config/mpv-controller/config.yaml
   uv run python -m mpv_controller.main
   ```

4. **Install as systemd service:**
   ```bash
   cp mpv-controller.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now mpv-controller
   ```

5. **Access API documentation:**
   ```
   http://localhost:8000/docs
   ```

## Key Features Implemented

### Multi-Instance Management
- Registry of mpv instances with ID-based routing
- Cached availability checking with configurable intervals
- Thread-safe socket operations

### REST API (Port 8000)
- `/mpv/{instance_id}/pause` - Toggle pause
- `/mpv/{instance_id}/play` - Resume playback
- `/mpv/{instance_id}/seek` - Seek to position
- `/mpv/{instance_id}/volume` - Set volume
- `/mpv/{instance_id}/properties/{name}` - Get property
- `/mpv/{instance_id}/status` - Get full status
- `/mpv/{instance_id}/command` - Raw command execution
- `/health` - Kubernetes liveness probe
- `/ready` - Kubernetes readiness probe

### gRPC API (Port 50051)
- `Pause`, `Play`, `Seek`, `SetVolume` - Semantic commands
- `GetProperty`, `GetStatus` - Property access
- `SendRawCommand` - Raw command execution
- `Check` - Health check

### Error Handling
- Standardized error codes: `INSTANCE_NOT_FOUND`, `SOCKET_TIMEOUT`, etc.
- Proper HTTP status codes (404, 503, 504, 500)
- Detailed error messages with context

### Resilience
- Exponential backoff with jitter for read operations
- Single-attempt writes to avoid duplicate commands
- Configurable timeouts and retry attempts
- Graceful degradation with per-instance availability

### Observability
- Structured JSON logging with structlog
- Request tracing and correlation
- Health and readiness endpoints
- Optional file logging

## Testing

Run the test suite:
```bash
uv run pytest -v
```

All 8 unit tests passing ✅

## Next Steps (Future Enhancements)

### Phase 2 - Playlist Management
- Playlist endpoints for managing m3u files
- Profile-based playlist switching
- Playlist deduplication

### Future Improvements
- Prometheus metrics endpoint
- WebSocket support for live state updates
- gRPC ingress configuration examples
- Integration tests with mock mpv instances
- Docker/Podman container support

## Configuration

See `config.example.yaml` for full configuration options:
- **mpv_instances**: Array of instances with IDs and socket paths
- **server**: Ports and bind addresses
- **logging**: Level and optional file output
- **socket**: Timeout, retry, and caching settings

## Deployment

### Local Development
Run directly with uv for development and testing.

### Production (systemd)
Runs as a user service with automatic restarts.

### Kubernetes Access
External access via Ingress with authentication handled by k8s.

---

**Status**: Ready for deployment and testing with real mpv instances!