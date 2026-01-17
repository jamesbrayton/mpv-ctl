"""Unit tests for configuration module."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from mpv_controller.config import (
    Config,
    LoggingSettings,
    MpvInstance,
    PathSettings,
    ServerSettings,
    SocketSettings,
    get_config_path,
    load_config,
)


class TestGetConfigPath:
    """Tests for get_config_path function."""

    def test_env_var_override(self, monkeypatch):
        """Test that MPV_CONTROLLER_CONFIG env var takes precedence."""
        monkeypatch.setenv("MPV_CONTROLLER_CONFIG", "/custom/path/config.yaml")
        path = get_config_path()
        assert path == Path("/custom/path/config.yaml")

    def test_xdg_config_home(self, monkeypatch):
        """Test XDG_CONFIG_HOME is used when set."""
        monkeypatch.delenv("MPV_CONTROLLER_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg/config")
        path = get_config_path()
        assert path == Path("/xdg/config/mpv-controller/config.yaml")

    def test_default_home_config(self, monkeypatch):
        """Test fallback to ~/.config when no env vars set."""
        monkeypatch.delenv("MPV_CONTROLLER_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        path = get_config_path()
        assert path == Path.home() / ".config" / "mpv-controller" / "config.yaml"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self):
        """Test loading a valid configuration file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            config_data = {
                "mpv_instances": [
                    {"id": "mpv-0", "socket_path": "/tmp/mpv.sock"}
                ],
                "server": {"rest_port": 9000},
                "logging": {"log_level": "DEBUG"},
            }
            yaml.dump(config_data, f)
            f.flush()

            try:
                config = load_config(Path(f.name))
                assert len(config.mpv_instances) == 1
                assert config.mpv_instances[0].id == "mpv-0"
                assert config.server.rest_port == 9000
                assert config.logging.log_level == "DEBUG"
            finally:
                os.unlink(f.name)

    def test_load_config_file_not_found(self):
        """Test loading a non-existent config file raises error."""
        with pytest.raises(FileNotFoundError) as exc_info:
            load_config(Path("/nonexistent/path/config.yaml"))
        assert "not found" in str(exc_info.value)

    def test_load_config_with_paths(self):
        """Test loading config with paths section."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            config_data = {
                "mpv_instances": [
                    {"id": "mpv-0", "socket_path": "/tmp/mpv.sock"}
                ],
                "paths": {
                    "profiles_config_path": "~/.config/mpv/profiles.conf",
                    "playlist_folder": "~/playlists",
                },
            }
            yaml.dump(config_data, f)
            f.flush()

            try:
                config = load_config(Path(f.name))
                assert config.paths.profiles_config_path == "~/.config/mpv/profiles.conf"
                assert config.paths.playlist_folder == "~/playlists"
            finally:
                os.unlink(f.name)


class TestConfigModels:
    """Tests for configuration model validation."""

    def test_mpv_instance_required_fields(self):
        """Test MpvInstance requires id and socket_path."""
        instance = MpvInstance(id="test", socket_path="/tmp/test.sock")
        assert instance.id == "test"
        assert instance.socket_path == "/tmp/test.sock"
        assert instance.display_name is None

    def test_mpv_instance_with_display_name(self):
        """Test MpvInstance with display_name."""
        instance = MpvInstance(
            id="test", socket_path="/tmp/test.sock", display_name="Test Player"
        )
        assert instance.display_name == "Test Player"

    def test_server_settings_defaults(self):
        """Test ServerSettings default values."""
        settings = ServerSettings()
        assert settings.rest_port == 8000
        assert settings.grpc_port == 50051
        assert settings.bind_address == "0.0.0.0"
        assert settings.enable_swagger_ui is True

    def test_logging_settings_defaults(self):
        """Test LoggingSettings default values."""
        settings = LoggingSettings()
        assert settings.log_level == "INFO"
        assert settings.log_file is None

    def test_socket_settings_defaults(self):
        """Test SocketSettings default values."""
        settings = SocketSettings()
        assert settings.read_timeout == 2.0
        assert settings.max_retries == 3
        assert settings.backoff_multiplier == 0.5
        assert settings.jitter is True
        assert settings.availability_check_interval == 30

    def test_path_settings_defaults(self):
        """Test PathSettings default values."""
        settings = PathSettings()
        assert settings.mpv_config_path is None
        assert settings.profiles_config_path is None
        assert settings.playlist_folder is None

    def test_config_requires_mpv_instances(self):
        """Test Config requires at least one mpv instance."""
        with pytest.raises(ValueError):
            Config(mpv_instances=[])

    def test_config_with_all_sections(self):
        """Test Config with all configuration sections."""
        config = Config(
            mpv_instances=[
                MpvInstance(id="mpv-0", socket_path="/tmp/mpv.sock")
            ],
            server=ServerSettings(rest_port=9000),
            logging=LoggingSettings(log_level="DEBUG"),
            socket=SocketSettings(read_timeout=5.0),
            paths=PathSettings(playlist_folder="~/playlists"),
        )
        assert config.server.rest_port == 9000
        assert config.logging.log_level == "DEBUG"
        assert config.socket.read_timeout == 5.0
        assert config.paths.playlist_folder == "~/playlists"
