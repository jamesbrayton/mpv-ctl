# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Note**: This file is synchronized with `.github/copilot-instructions.md` and any future `AGENTS.md`. All AI coding assistants follow the same standards. See `docs/ai-development-guide.md` for comprehensive details.

## Project Overview

mpv-controller is a Python service for controlling multiple mpv media player instances via Unix sockets. It exposes both REST and gRPC APIs for remote control. Designed to run as a systemd user service on the same host as mpv instances, with external access through Kubernetes ingress.

## Development Process & Quality Standards

### Required for ALL Feature/Fix Work

Every feature implementation or bug fix MUST include:

1. **Unit Tests**
   - Create/update tests for all new/changed functionality
   - Maintain minimum 80% test coverage across codebase
   - Run `uv run pytest --cov=mpv_controller --cov-report=term-missing` to verify coverage
   - Tests must pass before considering work complete

2. **API Consistency**
   - Changes to REST API endpoints MUST be reflected in gRPC implementation
   - Both APIs should provide equivalent functionality
   - Update both `rest_api.py` and `grpc_service.py` in parallel

3. **Protocol Buffer Updates**
   - Update `mpv_control.proto` when adding/changing gRPC messages
   - Regenerate Python files (see Development Commands section)
   - Commit both `.proto` and generated `_pb2.py` files

4. **Version Management**
   - Increment version for all changes following semantic versioning:
     - **Patch** (0.2.X): Bug fixes, no API changes
     - **Minor** (0.X.0): New features, backward-compatible API changes
     - **Major** (X.0.0): Breaking changes
   - Update version in ALL locations:
     - `pyproject.toml`
     - `mpv_controller/__init__.py`
     - `rest_api.py` (OpenAPI version)

5. **Documentation**
   - Update `README.md` if user-facing behavior changes (keep succinct)
   - Create/update detailed docs in `/docs` for complex topics
   - Follow documentation style guide (see below)

6. **Feature Planning & Implementation Documentation**
   - Create feature subfolder: `/docs/features/<feature-name>`
   - Store ALL feature-related planning/implementation docs in this subfolder:
     - Planning documents (e.g., `PLAN.md`, `DESIGN.md`)
     - Implementation guides (e.g., `IMPLEMENTATION.md`)
     - Feature-specific notes and tracking
   - Keep root directory clean—NO feature planning docs in root
   - Preserve feature folders for historical record (do NOT delete after completion)
   - Example structure:
     ```
     /docs/features/profile-tracking/
       PROFILE_TRACKING_PLAN.md
       IMPLEMENTATION.md
       VERIFICATION.md
     ```

7. **Architectural Decision Records (ADRs)**
   - Create ADR in `/docs/ADRs` for any design/architecture decisions
   - Number sequentially (001, 002, etc.)
   - Keep ADRs concise and focused (see existing ADRs as templates)
   - If ADR is significantly longer than existing ones, the decision scope is too large—break it up or reevaluate

### Documentation Style Guide

**README.md:**
- Succinct, to-the-point content
- Reference `/docs` folder for expanded information
- Include quick examples and common use cases
- Keep technical details minimal

**`/docs` Files:**
1. **State the Focus**: Clear title and purpose statement
2. **ELI5 Description**: Explain-like-I'm-5 overview for quick understanding
3. **Detailed Technical Content**: In-depth information, instructions, examples

**ADRs (`/docs/ADRs`):**
- Short and explicit
- Follow existing template structure:
  - **Status**: (Accepted/Proposed/Deprecated)
  - **Context**: Why the decision is needed
  - **Decision**: What was decided
  - **Consequences**: Impacts and trade-offs
  - **Alternatives Considered**: (if applicable)
- Use existing ADRs (001-006) as length/style reference
- If ADR grows too long, reconsider the decision's scope

### Pre-Commit Checklist

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

## Additional Resources

- **Comprehensive AI Development Guide**: See `docs/ai-development-guide.md` for detailed information on:
  - Availability caching patterns in SocketManager
  - Standardized error response formats with examples
  - Systemd service deployment patterns
  - Complete retry strategy implementation details
- **GitHub Copilot Instructions**: `.github/copilot-instructions.md` (synchronized with this file)
- **Architectural Decisions**: `docs/ADRs/` directory
