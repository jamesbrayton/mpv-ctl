# GitHub Copilot Instructions for mpv-controller

> **Note**: This file is synchronized with `CLAUDE.md` and any future `AGENTS.md`. All AI coding assistants follow the same standards. See `docs/ai-development-guide.md` for comprehensive details including:
> - Availability caching patterns in SocketManager
> - Standardized error response formats with examples
> - Systemd service deployment patterns
> - Complete retry strategy implementation details

## Project Architecture

This is a dual-API service (REST + gRPC) for controlling multiple mpv media player instances via Unix sockets. Think: one Python service managing many mpv processes on the same host, exposed to external clients through Kubernetes ingress.

**Critical pattern**: ALL changes to REST API endpoints (`rest_api.py`) MUST be mirrored in gRPC (`grpc_service.py`). The APIs provide equivalent functionality—if you add a feature to one, implement it in both.

**Data flow**: Client → REST/gRPC API → SocketManager (retry logic + caching) → Unix sockets → mpv instances

## Development Workflow

Use `uv` (not pip/venv) for all Python operations:

```bash
# Install dependencies
uv sync --dev

# Run tests (REQUIRED before any commit)
uv run pytest --cov=mpv_controller --cov-report=term-missing
# Must maintain ≥80% coverage

# Run locally
export MPV_CONTROLLER_CONFIG=~/.config/mpv-controller/config.yaml
uv run python -m mpv_controller.main

# After modifying mpv_control.proto
uv run python -m grpc_tools.protoc -I mpv_controller --python_out=mpv_controller --grpc_python_out=mpv_controller mpv_controller/mpv_control.proto
sed -i 's/^import mpv_control_pb2/from . import mpv_control_pb2/' mpv_controller/mpv_control_pb2_grpc.py
```

## Quality Standards (Non-Negotiable)

Every feature/fix requires ALL of these:

1. **Unit tests** with ≥80% coverage (use `unittest.mock` for sockets, `fastapi.testclient.TestClient` for REST)
2. **Version increment** in 3 places: `pyproject.toml`, `mpv_controller/__init__.py`, `rest_api.py` (semantic versioning: patch for fixes, minor for features, major for breaking)
3. **Feature docs** in `/docs/features/<feature-name>/` (planning, implementation notes—NOT in root)
4. **ADR** in `/docs/ADRs/` for design decisions (keep concise; use existing 001-006 as length reference)
5. **README update** if user-facing (succinct; reference `/docs` for details)
6. **Protobuf updates** if gRPC messages change (regenerate both `.proto` and `_pb2.py` files)

## Project-Specific Patterns

**Error handling**: All errors use standardized `ErrorCode` from `models.py` (INSTANCE_NOT_FOUND=404, SOCKET_TIMEOUT=504, etc.). Custom exceptions inherit from `MpvControllerError`.

**Retry strategy**: Read operations use exponential backoff with jitter (via `tenacity`). Write operations are single-attempt to prevent duplicate commands.

**Profile tracking**: Profiles require `x-profile-type` (shader/setting) and `x-profile-mode` (reset/additive) metadata. See `ProfileManager._parse_profiles_config()` for validation logic.

**Testing**: Mock-based (no running mpv required). See `tests/test_socket_manager.py` for socket mocking patterns.

**Configuration**: XDG-compliant paths with Pydantic validation. Priority: `$MPV_CONTROLLER_CONFIG` → `$XDG_CONFIG_HOME/mpv-controller/config.yaml` → `~/.config/mpv-controller/config.yaml`

## Key Files

- `socket_manager.py`: Multi-instance Unix socket communication, availability caching, retry logic
- `models.py`: Pydantic models, error codes, exception hierarchy
- `profile_manager.py`: Profile parsing with metadata validation
- `CLAUDE.md`: Comprehensive development standards and workflows
- `docs/ADRs/`: Architectural decisions (retry strategy, profile metadata, etc.)

## Common Pitfalls

- Forgetting to update version in all 3 locations
- Adding REST endpoint without gRPC equivalent
- Not regenerating protobuf files after `.proto` changes
- Creating feature planning docs in root instead of `/docs/features/<feature-name>/`
- Writing ADRs that are too long (compare length to existing ADRs 001-006)
- Using `pip` or `venv` instead of `uv`
- Adding retry logic to write operations (only read operations should retry)

## Additional Resources

- **Comprehensive AI Development Guide**: `docs/ai-development-guide.md`
- **Claude Instructions**: `CLAUDE.md` (synchronized with this file)
- **Architectural Decisions**: `docs/ADRs/` directory
