#!/usr/bin/env bash
# Installation script for mpv-controller

set -e

# Configuration - Update this with your actual repository URL
REPO_URL="https://github.com/jamesbrayton/mpv-ctl.git"
VERSION="${1:-main}"  # Default to main branch if no version specified

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

# Check for upgrade flag
UPGRADE=false
if [ "$2" = "--upgrade" ] || [ "$2" = "-u" ]; then
    UPGRADE=true
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: uv is not installed${NC}"
    echo "Install uv with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo -e "${GREEN}✓${NC} uv found: $(uv --version)"

# Check if already installed
if [ -d "${INSTALL_DIR}" ]; then
    if [ "$UPGRADE" = false ]; then
        # Check if running interactively (stdin is a terminal)
        if [ -t 0 ]; then
            echo -e "${YELLOW}⚠${NC}  Existing installation found at ${INSTALL_DIR}"
            echo "Options:"
            echo "  1. Run with --upgrade flag to upgrade: $0 ${VERSION} --upgrade"
            echo "  2. Remove existing installation first: rm -rf ${INSTALL_DIR}"
            echo
            read -p "Do you want to upgrade the existing installation? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                UPGRADE=true
            else
                echo "Installation cancelled."
                exit 0
            fi
        else
            # Non-interactive mode (piped), auto-upgrade
            echo -e "${YELLOW}⚠${NC}  Existing installation found - upgrading automatically"
            UPGRADE=true
        fi
    fi

    if [ "$UPGRADE" = true ]; then
        echo "Upgrading existing installation..."
        # Stop the service if running
        if systemctl --user is-active --quiet mpv-controller 2>/dev/null; then
            echo "Stopping mpv-controller service..."
            systemctl --user stop mpv-controller
        fi
        # Remove old virtual environment
        rm -rf "${INSTALL_DIR}/.venv"
        echo -e "${GREEN}✓${NC} Old virtual environment removed"
    fi
else
    # Create installation directory
    echo
    echo "Creating installation directory: ${INSTALL_DIR}"
    mkdir -p "${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"

# Create virtual environment with uv
echo "Creating virtual environment..."
uv venv .venv

# Install package
echo "Installing mpv-controller from ${REPO_URL} (${VERSION})..."
source .venv/bin/activate
uv pip install "git+${REPO_URL}@${VERSION}"

# Get the installed version
INSTALLED_VERSION=$(python -c "import mpv_controller; print(mpv_controller.__version__)" 2>/dev/null || echo "unknown")

deactivate

echo -e "${GREEN}✓${NC} Package installed (version: ${INSTALLED_VERSION})"

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
ExecStart=%h/.local/share/mpv-controller/.venv/bin/python -m mpv_controller.main
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
if [ "$UPGRADE" = true ]; then
    echo -e "${GREEN}Upgrade Complete!${NC}"
else
    echo -e "${GREEN}Installation Complete!${NC}"
fi
echo
echo "Git branch/tag: ${VERSION}"
echo "Package version: ${INSTALLED_VERSION}"
echo

if [ "$UPGRADE" = true ]; then
    # Check for missing config sections
    MISSING_CONFIG=false
    if [ -f "${CONFIG_DIR}/config.yaml" ]; then
        if ! grep -q "^paths:" "${CONFIG_DIR}/config.yaml" 2>/dev/null; then
            MISSING_CONFIG=true
            echo -e "${YELLOW}⚠${NC}  Your config.yaml is missing the 'paths' section added in this version."
            echo "    To use profile and playlist management features, add to ${CONFIG_DIR}/config.yaml:"
            echo ""
            echo "    paths:"
            echo "      # Required for profile management"
            echo "      profiles_config_path: ~/.config/mpv/profiles.conf"
            echo "      # Required for playlist management"
            echo "      playlist_folder: ~/playlists"
            echo ""
        fi
    fi

    echo "Next steps:"
    if [ "$MISSING_CONFIG" = true ]; then
        echo "  1. Update configuration with new sections (see above)"
        echo "  2. Reload systemd and restart:  systemctl --user daemon-reload && systemctl --user restart mpv-controller"
        echo "  3. Check status:                systemctl --user status mpv-controller"
        echo "  4. View logs:                   journalctl --user -u mpv-controller -f"
    else
        echo "  1. Reload systemd and restart:  systemctl --user daemon-reload && systemctl --user restart mpv-controller"
        echo "  2. Check status:                systemctl --user status mpv-controller"
        echo "  3. View logs:                   journalctl --user -u mpv-controller -f"
    fi
    echo
    echo -e "${YELLOW}Note:${NC} After editing config.yaml or profiles.conf, always run:"
    echo "      systemctl --user daemon-reload"
    echo "      systemctl --user restart mpv-controller"
    echo "      # If using mpv systemd services, also restart them:"
    echo "      systemctl --user restart 'mpv@*'"
else
    echo "Next steps:"
    echo "  1. Edit configuration: ${CONFIG_DIR}/config.yaml"
    echo "  2. Enable service:     systemctl --user enable mpv-controller"
    echo "  3. Start service:      systemctl --user start mpv-controller"
    echo "  4. Check status:       systemctl --user status mpv-controller"
    echo "  5. View logs:          journalctl --user -u mpv-controller -f"
    echo
    echo -e "${YELLOW}Important:${NC} After editing config.yaml or profiles.conf, always run:"
    echo "           systemctl --user daemon-reload"
    echo "           systemctl --user restart mpv-controller"
    echo "           # If using mpv systemd services, also restart them:"
    echo "           systemctl --user restart 'mpv@*'"
fi
echo
echo "API Documentation will be available at: http://localhost:8000/docs"
echo
echo "To upgrade: ./install.sh ${VERSION} --upgrade"
echo "Or: curl -fsSL https://raw.githubusercontent.com/jamesbrayton/mpv-ctl/main/install.sh | bash -s -- main --upgrade"
