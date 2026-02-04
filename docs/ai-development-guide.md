# AI Development Guide for mpv-controller

This guide provides essential knowledge for AI coding agents working in this codebase.

## Project Overview

mpv-controller is a Python service for controlling multiple mpv media player instances via Unix sockets. It exposes both REST and gRPC APIs for remote control. Designed to run as a systemd user service on the same host as mpv instances, with external access through Kubernetes ingress.

## Critical Architecture Patterns

### Dual-API Requirement

**ALL changes to REST API endpoints MUST be mirrored in gRPC implementation.** The APIs provide equivalent functionality—if you add a feature to one, implement it in both.

Files to update in parallel:
- `rest_api.py` - FastAPI endpoints
- `grpc_service.py` - gRPC service implementation
- `mpv_control.proto` - Protocol buffer definitions (if messages change)

### Data Flow

```
Client → REST/gRPC API → SocketManager (retry logic + caching) → Unix sockets → mpv instances
```

### Availability Caching Pattern

`SocketManager` runs a background thread that periodically checks socket availability. This reduces overhead on Kubernetes readiness probe calls (`/ready` endpoint).

**Implementation details:**
- Background thread updates `_instance_availability` dict every N seconds (configurable)
- Health checks query cached state instead of probing sockets directly
- See `socket_manager.py._availability_checker()` for the polling logic

### Error Response Format

All errors use standardized `ErrorCode` from `models.py` with consistent HTTP status codes:

```python
# Error codes and their HTTP status mappings
INSTANCE_NOT_FOUND = 404
SOCKET_TIMEOUT = 504
SOCKET_CONNECTION_ERROR = 503
COMMAND_EXECUTION_ERROR = 500
VALIDATION_ERROR = 400
```

Custom exceptions inherit from `MpvControllerError`:

```python
raise InstanceNotFoundError(
    instance_id="mpv-0",
    details={"available_instances": ["mpv-1", "mpv-2"]}
)
```

REST API error response format:
```json
{
  "error": {
    "code": "INSTANCE_NOT_FOUND",
    "message": "Instance 'mpv-0' not found",
    "details": {
      "available_instances": ["mpv-1", "mpv-2"]
    }
  }
}
```

### Retry Strategy

**Critical distinction:**
- **Read operations** (GET/query): Exponential backoff with jitter using `tenacity`
- **Write operations** (POST/PUT): Single-attempt only to prevent duplicate commands

See `socket_manager.py` decorators:
- `@retry_on_socket_error` for read operations
- No retry decorator on write operations

## Development Workflow

### Package Manager: uv (NOT pip/venv)

All Python operations use `uv`:

```bash
# Install dependencies
uv sync --dev

# Run tests (REQUIRED before any commit)
uv run pytest --cov=mpv_controller --cov-report=term-missing
# Must maintain ≥80% coverage

# Run application locally
export MPV_CONTROLLER_CONFIG=~/.config/mpv-controller/config.yaml
uv run python -m mpv_controller.main
```

### Protobuf Regeneration

After modifying `mpv_control.proto`:

```bash
uv run python -m grpc_tools.protoc \
  -I mpv_controller \
  --python_out=mpv_controller \
  --grpc_python_out=mpv_controller \
  mpv_controller/mpv_control.proto

# Fix import path in generated file
sed -i 's/^import mpv_control_pb2/from . import mpv_control_pb2/' \
  mpv_controller/mpv_control_pb2_grpc.py
```

Commit both `.proto` and generated `_pb2.py`/`_pb2_grpc.py` files.

## Quality Standards (Non-Negotiable)

Every feature/fix requires ALL of these:

### 1. Unit Tests
- Create/update tests for all new/changed functionality
- Maintain minimum 80% test coverage across codebase
- Use `unittest.mock` for socket mocking
- Use `fastapi.testclient.TestClient` for REST API testing
- Mock-based approach—no running mpv required
- See `tests/test_socket_manager.py` for socket mocking patterns

### 2. API Consistency
- Changes to REST endpoints MUST be reflected in gRPC
- Both APIs should provide equivalent functionality
- Update `rest_api.py` and `grpc_service.py` in parallel

### 3. Protocol Buffer Updates
- Update `mpv_control.proto` when adding/changing gRPC messages
- Regenerate Python files using commands above
- Commit both `.proto` and generated files

### 4. Version Management
Increment version following semantic versioning:
- **Patch** (0.2.X): Bug fixes, no API changes
- **Minor** (0.X.0): New features, backward-compatible API changes
- **Major** (X.0.0): Breaking changes

Update version in ALL 3 locations:
- `pyproject.toml`
- `mpv_controller/__init__.py`
- `rest_api.py` (OpenAPI version)

### 5. Documentation
- Update `README.md` if user-facing behavior changes (keep succinct)
- Create/update detailed docs in `/docs` for complex topics
- Follow documentation style guide (see below)

### 6. Feature Planning & Implementation Documentation
- Create feature subfolder: `/docs/features/<feature-name>/`
- Store ALL feature-related planning/implementation docs in this subfolder:
  - Planning documents (e.g., `PLAN.md`, `DESIGN.md`)
  - Implementation guides (e.g., `IMPLEMENTATION.md`)
  - Feature-specific notes and tracking
- Keep root directory clean—NO feature planning docs in root
- Preserve feature folders for historical record (do NOT delete after completion)

Example structure:
```
/docs/features/profile-tracking/
  PROFILE_TRACKING_PLAN.md
  IMPLEMENTATION.md
  VERIFICATION.md
```

### 7. Architectural Decision Records (ADRs)
- Create ADR in `/docs/ADRs/` for any design/architecture decisions
- Number sequentially (001, 002, etc.)
- Keep ADRs concise and focused (see existing ADRs 001-006 as templates)
- If ADR is significantly longer than existing ones, the decision scope is too large—break it up or reevaluate

## Documentation Style Guide

### README.md
- Succinct, to-the-point content
- Reference `/docs` folder for expanded information
- Include quick examples and common use cases
- Keep technical details minimal

### `/docs` Files
1. **State the Focus**: Clear title and purpose statement
2. **ELI5 Description**: Explain-like-I'm-5 overview for quick understanding
3. **Detailed Technical Content**: In-depth information, instructions, examples

### ADRs (`/docs/ADRs`)
- Short and explicit
- Follow existing template structure:
  - **Status**: (Accepted/Proposed/Deprecated)
  - **Context**: Why the decision is needed
  - **Decision**: What was decided
  - **Consequences**: Impacts and trade-offs
  - **Alternatives Considered**: (if applicable)
- Use existing ADRs (001-006) as length/style reference
- If ADR grows too long, reconsider the decision's scope

## Project-Specific Patterns

### Profile Tracking
Profiles require metadata fields (mpv ignores `x-` prefixed fields):
- `x-profile-type`: `shader` or `setting`
- `x-profile-mode`: `reset` or `additive`

See `ProfileManager._parse_profiles_config()` for validation logic. Shader arrays are automatically normalized.

### Configuration
XDG-compliant paths with Pydantic validation.

Priority order:
1. `$MPV_CONTROLLER_CONFIG` environment variable
2. `$XDG_CONFIG_HOME/mpv-controller/config.yaml`
3. `~/.config/mpv-controller/config.yaml`

See `config.example.yaml` for all options.

### Systemd Service Deployment
The service runs as a systemd user service (not system service) on the same host as mpv instances.

**Installation pattern:**
- Virtual environment in `~/.local/share/mpv-controller`
- Configuration in `~/.config/mpv-controller/config.yaml`
- Service file in `~/.config/systemd/user/mpv-controller.service`
- Logs to systemd journal (view with `journalctl --user -u mpv-controller`)

**Upgrade handling:**
- Stop service before removing virtual environment
- Preserve configuration file across upgrades
- Restart service after installing new version

See `install.sh` for complete installation/upgrade logic.

## Key Files

- `socket_manager.py`: Multi-instance Unix socket communication, availability caching, retry logic
- `models.py`: Pydantic models, error codes, exception hierarchy
- `profile_manager.py`: Profile parsing with metadata validation
- `main.py`: Concurrent server startup (REST in thread, gRPC in main), signal handling
- `config.py`: YAML configuration loading with Pydantic validation
- `docs/ADRs/`: Architectural decisions (retry strategy, profile metadata, etc.)

## Pre-Commit Checklist

Before considering work complete:
- [ ] Unit tests created/updated and passing
- [ ] Test coverage ≥80% (check with `--cov` flag)
- [ ] REST API changes mirrored in gRPC
- [ ] Protobuf files updated and regenerated (if applicable)
- [ ] Version incremented in all 3 locations
- [ ] README.md updated (if user-facing changes)
- [ ] Detailed docs created/updated in `/docs` (if needed)
- [ ] Feature planning/implementation docs in `/docs/features/<feature-name>` (if applicable)
- [ ] ADR created for design decisions
- [ ] All tests pass: `uv run pytest -v`

## Common Pitfalls

- Forgetting to update version in all 3 locations
- Adding REST endpoint without gRPC equivalent
- Not regenerating protobuf files after `.proto` changes
- Creating feature planning docs in root instead of `/docs/features/<feature-name>/`
- Writing ADRs that are too long (compare length to existing ADRs 001-006)
- Using `pip` or `venv` instead of `uv`
- Adding retry logic to write operations (only read operations should retry)
