# mpv Controller

A Python service for controlling multiple mpv instances via Unix sockets, exposing both REST and gRPC APIs. Designed to run as a systemd user service on the same host as mpv instances, with external access through Kubernetes ingress.

## Features

- **Multi-instance control**: Manage multiple mpv instances simultaneously
- **Dual API**: REST API with OpenAPI/Swagger documentation and gRPC service
- **Semantic commands**: High-level commands (pause, play, seek, volume, speed) with automatic state retrieval
- **Frame navigation**: Single-frame forward/backward stepping
- **Playlist navigation**: Next, previous, restart current video
- **Profile management**: List, create, update, delete mpv profiles; apply profiles to instances
- **Playlist management**: Manage .m3u playlist files; switch playlists with immediate, after-current, or after-playlist modes
- **Raw command support**: Execute any mpv command directly
- **Resilient communication**: Exponential backoff with jitter for read operations
- **Health checks**: Kubernetes-ready `/health` and `/ready` endpoints
- **Structured logging**: JSON-formatted logs with configurable output
- **Configurable**: YAML-based configuration with sensible defaults

## Architecture

```diagram
┌─────────────────┐
│  k8s Ingress    │ (External authentication)
└────────┬────────┘
         │
┌────────▼────────┐
│  REST API :8000 │
│  gRPC API :50051│
└────────┬────────┘
         │
┌────────▼────────┐
│  Socket Manager │ (Retry logic, caching)
└────────┬────────┘
         │
    ┌────┴────┬────────┐
    │         │        │
┌───▼──┐  ┌──▼───┐  ┌─▼────┐
│mpv-0 │  │mpv-1 │  │mpv-2 │ (Unix sockets)
└──────┘  └──────┘  └──────┘
```

## Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- mpv instances running with IPC socket enabled
- (Optional) Kubernetes cluster for ingress setup

## Installation

### Quick Install (Recommended)

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install mpv-controller (latest from main branch)
curl -fsSL https://raw.githubusercontent.com/jamesbrayton/mpv-ctl/main/install.sh | bash

# Or install a specific version/branch/tag
curl -fsSL https://raw.githubusercontent.com/jamesbrayton/mpv-ctl/main/install.sh | bash -s -- v1.0.0
```

This will:

- Create a virtual environment in `~/.local/share/mpv-controller`
- Install the package
- Set up the systemd service
- Create a config template at `~/.config/mpv-controller/config.yaml`

### Upgrading

To upgrade an existing installation:

```bash
# Interactive upgrade (will prompt for confirmation)
curl -fsSL https://raw.githubusercontent.com/jamesbrayton/mpv-ctl/main/install.sh | bash

# Non-interactive upgrade (for scripts)
curl -fsSL https://raw.githubusercontent.com/jamesbrayton/mpv-ctl/main/install.sh | bash -s -- main --upgrade

# Upgrade to specific version
curl -fsSL https://raw.githubusercontent.com/jamesbrayton/mpv-ctl/main/install.sh | bash -s -- v2.0.0 --upgrade
```

The upgrade process will:

- Stop the running service (if active)
- Remove the old virtual environment
- Install the new version
- Preserve your configuration file

### Manual Installation

#### 1. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### 2. Install Package

##### Option A: Install from Git (Recommended for production)

```bash
mkdir -p ~/.local/share/mpv-controller
cd ~/.local/share/mpv-controller
uv venv .venv
source .venv/bin/activate
uv pip install "git+https://github.com/jamesbrayton/mpv-ctl.git"
deactivate
```

##### Option B: Install from Local Clone (For development)

```bash
git clone <your-repo-url> mpv-controller
cd mpv-controller
export UV_CACHE_DIR=~/.uv-cache
uv sync --dev
```

### 3. Configure

Create configuration directory and copy example config:

```bash
mkdir -p ~/.config/mpv-controller
cp config.example.yaml ~/.config/mpv-controller/config.yaml
```

Edit `~/.config/mpv-controller/config.yaml` with your mpv instance details:

```yaml
mpv_instances:
  - id: mpv-0
    socket_path: /run/user/1000/app/io.mpv.Mpv/mpv-0/mpv.sock
    display_name: Primary Player
```

See [config.example.yaml](config.example.yaml) for all configuration options.

### 4. Set Up systemd Service

**If you used the quick install script, the service is already installed. Just enable it:**

```bash
systemctl --user enable mpv-controller.service
systemctl --user start mpv-controller.service
```

**For manual installation, create the service file:**

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/mpv-controller.service << 'EOF'
[Unit]
Description=mpv Controller Service
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/.local/share/mpv-controller
ExecStart=%h/.local/share/mpv-controller/.venv/bin/python -m mpv_controller.main
Restart=always
RestartSec=10
Environment="MPV_CONTROLLER_CONFIG=%h/.config/mpv-controller/config.yaml"
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mpv-controller

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable mpv-controller.service
systemctl --user start mpv-controller.service
```

**Check status:**

```bash
systemctl --user status mpv-controller.service
journalctl --user -u mpv-controller.service -f
```

### 5. (Optional) Configure Kubernetes Ingress

Edit [k8s/service.yaml](k8s/service.yaml) to set your host machine IP:

```yaml
subsets:
  - addresses:
      - ip: 192.168.1.100  # Your host IP
```

Edit [k8s/ingress.yaml](k8s/ingress.yaml) to set your domain and authentication:

```yaml
spec:
  rules:
    - host: mpv-controller.example.com  # Your domain
```

Apply manifests:

```bash
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

## API Usage

### REST API

Once running, access Swagger UI documentation at:

```code
http://localhost:8000/docs
```

#### Examples

**Pause/Resume:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/pause
```

**Seek:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/seek \
  -H "Content-Type: application/json" \
  -d '{"position": 120.0, "relative": false}'
```

**Set Volume:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/volume \
  -H "Content-Type: application/json" \
  -d '{"volume": 75.0}'
```

**List All Available Properties:**

```bash
curl http://localhost:8000/mpv/mpv-0/properties
```

**Get Specific Property:**

```bash
curl http://localhost:8000/mpv/mpv-0/properties/filename
```

**Get Status:**

```bash
curl http://localhost:8000/mpv/mpv-0/status
```

**Raw Command:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/command \
  -H "Content-Type: application/json" \
  -d '{"command": ["loadfile", "/path/to/video.mp4"]}'
```

#### Speed Control

**Set Playback Speed:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/speed \
  -H "Content-Type: application/json" \
  -d '{"speed": 1.5}'
```

**Increase Speed by 0.05:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/speed/up
```

**Decrease Speed by 0.05:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/speed/down
```

#### Frame Navigation

**Advance One Frame:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/frame/forward
```

**Go Back One Frame:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/frame/backward
```

#### Playlist Navigation

**Play Next Video:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/playlist/next
```

**Play Previous Video:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/playlist/previous
```

**Restart Current Video:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/playlist/restart
```

**Switch to Playlist (immediate):**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/playlist/switch \
  -H "Content-Type: application/json" \
  -d '{"name": "favorites", "mode": "immediate"}'
```

#### Profile Management

Profiles must include metadata fields that control tracking behavior:

**Profile Metadata Requirements:**

All profiles require two metadata fields (mpv ignores these `x-` prefixed fields):

- **x-profile-type**: Type of configuration (`shader` or `setting`)
  - `shader`: Manages GLSL shaders (glsl-shaders-append, glsl-shaders-clr)
  - `setting`: Manages other settings (vo, hwdec, vf, af, etc.)

- **x-profile-mode**: Application mode (`reset` or `additive`)
  - `reset`: Clears all previously applied profiles of the same type
  - `additive`: Adds to existing profiles of the same type

**Example Profile Configuration:**

```ini
# Shader profile with reset mode (clears other shaders)
[anime4k-medium]
x-profile-type=shader
x-profile-mode=reset
profile-desc=Anime4K Medium Quality
glsl-shaders-clr
glsl-shaders-append=~~/shaders/Anime4K_Upscale_L.glsl
glsl-shaders-append=~~/shaders/Anime4K_Auto_Downscale.glsl

# Setting profile with additive mode (stacks with other settings)
[debanding]
x-profile-type=setting
x-profile-mode=additive
profile-desc=Enable debanding filter
vf=gradfun=radius=16

# Clear all shaders
[none]
x-profile-type=shader
x-profile-mode=reset
profile-desc=Clear all shaders
glsl-shaders-clr
```

**List All Profiles:**

```bash
curl http://localhost:8000/profiles
```

**Get Profile Details:**

```bash
curl http://localhost:8000/profiles/gpu-hq
```

**Create Profile:**

```bash
curl -X POST http://localhost:8000/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-profile",
    "options": {
      "vo": "gpu",
      "hwdec": "auto",
      "x-profile-type": "setting",
      "x-profile-mode": "reset"
    }
  }'
```

**Update Profile:**

```bash
curl -X PUT http://localhost:8000/profiles/my-profile \
  -H "Content-Type: application/json" \
  -d '{
    "options": {
      "vo": "sdl",
      "x-profile-type": "setting",
      "x-profile-mode": "additive"
    }
  }'
```

**Delete Profile:**

```bash
curl -X DELETE http://localhost:8000/profiles/my-profile
```

**Apply Profile to Instance:**

```bash
curl -X POST http://localhost:8000/mpv/mpv-0/profile?profile_name=gpu-hq
```

The status response includes `applied_profiles` showing which profiles are currently active:

```json
{
  "state": {
    "pause": false,
    "glsl_shaders": ["/path/to/shader.glsl"],
    "applied_profiles": ["anime4k-medium", "debanding"]
  }
}
```

#### Playlist File Management

**List All Playlists:**

```bash
curl http://localhost:8000/playlists
```

**Get Playlist Contents:**

```bash
curl http://localhost:8000/playlists/favorites
```

**Create Playlist:**

```bash
curl -X POST http://localhost:8000/playlists \
  -H "Content-Type: application/json" \
  -d '{"name": "new-playlist", "entries": [{"path": "/media/video1.mp4", "title": "Video 1"}]}'
```

**Update Playlist (append):**

```bash
curl -X PUT http://localhost:8000/playlists/favorites \
  -H "Content-Type: application/json" \
  -d '{"entries": [{"path": "/media/video2.mp4"}], "replace": false}'
```

**Update Playlist (replace):**

```bash
curl -X PUT http://localhost:8000/playlists/favorites \
  -H "Content-Type: application/json" \
  -d '{"entries": [{"path": "/media/new.mp4"}], "replace": true}'
```

**Delete Playlist:**

```bash
curl -X DELETE http://localhost:8000/playlists/favorites
```

### gRPC API

See [mpv_control.proto](mpv_controller/mpv_control.proto) for service definition.

Example Python client:

```python
import grpc
from mpv_controller import mpv_control_pb2, mpv_control_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = mpv_control_pb2_grpc.MpvControllerStub(channel)

# Pause
request = mpv_control_pb2.InstanceRequest(instance_id="mpv-0")
response = stub.Pause(request)
print(f"Paused: {response.state.pause}")
```

## Development

### Running Tests

```bash
uv run pytest
```

### Regenerating gRPC Code

After modifying `mpv_control.proto`:

```bash
uv run python -m grpc_tools.protoc \
  -I mpv_controller \
  --python_out=mpv_controller \
  --grpc_python_out=mpv_controller \
  mpv_controller/mpv_control.proto

# Fix the import in the generated file
sed -i 's/^import mpv_control_pb2/from . import mpv_control_pb2/' \
  mpv_controller/mpv_control_pb2_grpc.py
```

### Local Development

Run directly without systemd:

```bash
export MPV_CONTROLLER_CONFIG=~/.config/mpv-controller/config.yaml
uv run python -m mpv_controller.main
```

## Configuration Reference

See [config.example.yaml](config.example.yaml) for detailed configuration options including:

- **mpv_instances**: List of mpv instances with socket paths
- **server**: REST/gRPC port and bind settings
- **logging**: Log level and optional file output
- **socket**: Timeout, retry, and availability check settings
- **paths**: File paths for profiles and playlists
  - `profiles_config_path`: Path to mpv profiles configuration file (required for profile management)
  - `playlist_folder`: Path to folder containing .m3u playlist files (required for playlist management)

## Error Handling

All errors follow a standardized format:

```json
{
  "error": {
    "code": "INSTANCE_NOT_FOUND",
    "message": "mpv instance 'mpv-0' not found",
    "details": {"instance_id": "mpv-0"}
  }
}
```

Error codes:

- `INSTANCE_NOT_FOUND` (404): Instance ID doesn't exist
- `SOCKET_TIMEOUT` (504): Socket operation timed out
- `SOCKET_CONNECTION_ERROR` (503): Cannot connect to socket
- `COMMAND_EXECUTION_ERROR` (500): Command failed
- `VALIDATION_ERROR` (400): Invalid request
- `PROFILE_NOT_FOUND` (404): Profile doesn't exist
- `PROFILE_EXISTS` (409): Profile already exists
- `PROFILE_CONFIG_ERROR` (503): Profile configuration not set up
- `PLAYLIST_NOT_FOUND` (404): Playlist doesn't exist
- `PLAYLIST_EXISTS` (409): Playlist already exists
- `PLAYLIST_CONFIG_ERROR` (503): Playlist configuration not set up

## Documentation

Additional documentation:

- [docs/](docs/) - Setup guides for mpv with systemd (future)
- [API Documentation](http://localhost:8000/docs) - Interactive Swagger UI
- [API Reference](http://localhost:8000/redoc) - ReDoc documentation

## License

[Your chosen license]

## Contributing

[Your contribution guidelines]
