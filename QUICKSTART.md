# Quick Start Guide

Get mpv-controller running in 5 minutes!

## Prerequisites

- Python 3.11+
- uv package manager
- mpv with IPC socket enabled

## 1. Install uv (if needed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2. Set Up Project

```bash
# Clone or navigate to project directory
cd /path/to/mpv-controller

# Set cache directory
export UV_CACHE_DIR=~/.uv-cache

# Install dependencies
uv sync --dev

# Run tests to verify
uv run pytest -v
```

## 3. Configure Your mpv Instances

### Option A: Find Existing Sockets

```bash
# Look for mpv sockets
find /run/user/$(id -u) -name "*.sock" 2>/dev/null | grep mpv
```

### Option B: Start mpv with IPC

```bash
# Start mpv with IPC socket
mpv --input-ipc-server=/tmp/mpv-socket-0 your-video.mp4
```

## 4. Create Configuration

```bash
# Create config directory
mkdir -p ~/.config/mpv-controller

# Copy and edit config
cp config.example.yaml ~/.config/mpv-controller/config.yaml

# Edit with your socket paths
nano ~/.config/mpv-controller/config.yaml
```

Minimal config:
```yaml
mpv_instances:
  - id: mpv-0
    socket_path: /tmp/mpv-socket-0
    display_name: Main Player

server:
  rest_port: 8000
  grpc_port: 50051
```

## 5. Run the Service

```bash
# Set config path
export MPV_CONTROLLER_CONFIG=~/.config/mpv-controller/config.yaml

# Run service
uv run python -m mpv_controller.main
```

Service will start on:
- **REST API**: http://localhost:8000
- **gRPC API**: localhost:50051
- **API Docs**: http://localhost:8000/docs

## 6. Test the API

### Using curl

```bash
# Check health
curl http://localhost:8000/health

# Check readiness (shows instance status)
curl http://localhost:8000/ready

# Pause/unpause
curl -X POST http://localhost:8000/mpv/mpv-0/pause

# Set volume to 50%
curl -X POST http://localhost:8000/mpv/mpv-0/volume \
  -H "Content-Type: application/json" \
  -d '{"volume": 50.0}'

# Get current filename
curl http://localhost:8000/mpv/mpv-0/properties/filename

# Get full status
curl http://localhost:8000/mpv/mpv-0/status
```

### Using Swagger UI

Open http://localhost:8000/docs in your browser for interactive API documentation!

## 7. Install as systemd Service (Optional)

```bash
# Copy service file
mkdir -p ~/.config/systemd/user
cp mpv-controller.service ~/.config/systemd/user/

# Reload systemd
systemctl --user daemon-reload

# Enable and start
systemctl --user enable mpv-controller.service
systemctl --user start mpv-controller.service

# Check status
systemctl --user status mpv-controller.service

# View logs
journalctl --user -u mpv-controller.service -f
```

## Troubleshooting

### Service won't start
```bash
# Check config is valid
uv run python -c "from mpv_controller.config import load_config; load_config()"

# Check socket exists
ls -la /path/to/your/socket.sock
```

### Can't connect to socket
```bash
# Test socket manually
echo '{"command": ["get_property", "pause"]}' | socat - /path/to/socket.sock

# Check permissions
ls -la /path/to/socket.sock
```

### Import errors
```bash
# Reinstall dependencies
uv sync --dev --reinstall
```

## Next Steps

1. **Test all endpoints** using Swagger UI
2. **Monitor logs** to see request/response flow
3. **Add more mpv instances** to your config
4. **Set up Kubernetes ingress** for external access
5. **Configure authentication** via your ingress controller

## Common Commands

```bash
# Run locally
uv run python -m mpv_controller.main

# Run tests
uv run pytest -v

# View systemd logs
journalctl --user -u mpv-controller -f

# Restart service
systemctl --user restart mpv-controller

# Stop service
systemctl --user stop mpv-controller
```

## Getting Help

- Check [README.md](README.md) for detailed documentation
- Review [config.example.yaml](config.example.yaml) for all options
- See [IMPLEMENTATION.md](IMPLEMENTATION.md) for technical details
- API documentation at http://localhost:8000/docs

Enjoy controlling your mpv instances! 🎬
