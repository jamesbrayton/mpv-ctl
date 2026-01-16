#!/usr/bin/env bash
# Installation script for mpv-controller

set -e

INSTALL_DIR="${HOME}/.local/share/mpv-controller"
CONFIG_DIR="${HOME}/.config/mpv-controller"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🎬 mpv-controller Installation Script"
echo "======================================"
echo

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: uv is not installed${NC}"
    echo "Install uv with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo -e "${GREEN}✓${NC} uv found: $(uv --version)"

# Create installation directory
echo
echo "Creating installation directory: ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
cd "${INSTALL_DIR}"

# Create virtual environment
echo "Creating virtual environment..."
uv venv

# Install package
if [ -n "${1}" ]; then
    # Install from provided URL (e.g., git+https://...)
    echo "Installing mpv-controller from: ${1}"
    uv pip install "${1}"
else
    # Install from current directory (for development)
    echo "Installing mpv-controller from local directory..."
    if [ -f "${INSTALL_DIR}/../../mpv-controller/pyproject.toml" ]; then
        uv pip install -e "${INSTALL_DIR}/../../mpv-controller"
    else
        echo -e "${RED}Error: No installation source specified${NC}"
        echo "Usage: $0 [git+https://github.com/user/repo.git]"
        exit 1
    fi
fi

echo -e "${GREEN}✓${NC} Package installed"

# Create config directory
echo
echo "Setting up configuration..."
mkdir -p "${CONFIG_DIR}"

# Check if config exists
if [ ! -f "${CONFIG_DIR}/config.yaml" ]; then
    if [ -f "$(dirname $0)/config.example.yaml" ]; then
        cp "$(dirname $0)/config.example.yaml" "${CONFIG_DIR}/config.yaml"
        echo -e "${GREEN}✓${NC} Created config.yaml from example"
        echo -e "${YELLOW}⚠${NC}  Please edit ${CONFIG_DIR}/config.yaml with your mpv socket paths"
    else
        echo -e "${YELLOW}⚠${NC}  No example config found. Please create ${CONFIG_DIR}/config.yaml manually"
    fi
else
    echo -e "${GREEN}✓${NC} config.yaml already exists"
fi

# Install systemd service
echo
echo "Installing systemd service..."
mkdir -p "${SYSTEMD_DIR}"

# Create service file
cat > "${SYSTEMD_DIR}/mpv-controller.service" << 'EOF'
[Unit]
Description=mpv Controller Service
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/.local/share/mpv-controller
ExecStart=%h/.local/share/mpv-controller/venv/bin/python -m mpv_controller.main
Restart=always
RestartSec=10

# Environment
Environment="MPV_CONTROLLER_CONFIG=%h/.config/mpv-controller/config.yaml"

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mpv-controller

[Install]
WantedBy=default.target
EOF

echo -e "${GREEN}✓${NC} Service file created"

# Reload systemd
systemctl --user daemon-reload
echo -e "${GREEN}✓${NC} systemd reloaded"

echo
echo "======================================"
echo -e "${GREEN}Installation Complete!${NC}"
echo
echo "Next steps:"
echo "  1. Edit configuration: ${CONFIG_DIR}/config.yaml"
echo "  2. Enable service:     systemctl --user enable mpv-controller"
echo "  3. Start service:      systemctl --user start mpv-controller"
echo "  4. Check status:       systemctl --user status mpv-controller"
echo "  5. View logs:          journalctl --user -u mpv-controller -f"
echo
echo "API Documentation will be available at: http://localhost:8000/docs"
