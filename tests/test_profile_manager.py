"""Unit tests for profile manager."""

import tempfile
from pathlib import Path

import pytest

from mpv_controller.config import Config, MpvInstance, PathSettings, SocketSettings
from mpv_controller.profile_manager import (
    ProfileConfigError,
    ProfileExistsError,
    ProfileManager,
    ProfileNotFoundError,
)


@pytest.fixture
def temp_profiles_dir():
    """Create a temporary directory for profiles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config(temp_profiles_dir):
    """Create a mock configuration with paths."""
    profiles_path = temp_profiles_dir / "profiles.conf"
    return Config(
        mpv_instances=[
            MpvInstance(
                id="mpv-0",
                socket_path="/tmp/mpv-0.sock",
                display_name="Test Player",
            ),
        ],
        socket=SocketSettings(
            read_timeout=1.0,
            max_retries=2,
            availability_check_interval=0,
        ),
        paths=PathSettings(
            profiles_config_path=str(profiles_path),
        ),
    )


@pytest.fixture
def mock_config_no_paths():
    """Create a mock configuration without paths."""
    return Config(
        mpv_instances=[
            MpvInstance(
                id="mpv-0",
                socket_path="/tmp/mpv-0.sock",
            ),
        ],
        socket=SocketSettings(
            read_timeout=1.0,
            max_retries=2,
            availability_check_interval=0,
        ),
    )


@pytest.fixture
def profile_manager(mock_config):
    """Create a profile manager instance."""
    return ProfileManager(mock_config)


@pytest.fixture
def profile_manager_no_paths(mock_config_no_paths):
    """Create a profile manager without paths configured."""
    return ProfileManager(mock_config_no_paths)


class TestProfileManagerInit:
    """Tests for profile manager initialization."""

    def test_init_with_paths(self, profile_manager, temp_profiles_dir):
        """Test initialization with paths configured."""
        assert profile_manager._profiles_path is not None
        assert profile_manager._profiles_path.parent == temp_profiles_dir

    def test_init_without_paths(self, profile_manager_no_paths):
        """Test initialization without paths configured."""
        assert profile_manager_no_paths._profiles_path is None


class TestProfileManagerConfigError:
    """Tests for configuration error handling."""

    def test_list_profiles_no_config(self, profile_manager_no_paths):
        """Test listing profiles without config raises error."""
        with pytest.raises(ProfileConfigError) as exc_info:
            profile_manager_no_paths.list_profiles()
        assert "not configured" in str(exc_info.value)

    def test_get_profile_no_config(self, profile_manager_no_paths):
        """Test getting profile without config raises error."""
        with pytest.raises(ProfileConfigError):
            profile_manager_no_paths.get_profile("test")

    def test_create_profile_no_config(self, profile_manager_no_paths):
        """Test creating profile without config raises error."""
        with pytest.raises(ProfileConfigError):
            profile_manager_no_paths.create_profile("test", {"vo": "gpu"})


class TestProfileManagerOperations:
    """Tests for profile CRUD operations."""

    def test_list_profiles_empty(self, profile_manager):
        """Test listing profiles when file doesn't exist."""
        profiles = profile_manager.list_profiles()
        assert profiles == []

    def test_create_profile(self, profile_manager):
        """Test creating a new profile."""
        options = {"vo": "gpu", "hwdec": "auto"}
        profile = profile_manager.create_profile("test-profile", options)

        assert profile.name == "test-profile"
        assert profile.options == options

    def test_create_profile_already_exists(self, profile_manager):
        """Test creating a profile that already exists."""
        profile_manager.create_profile("test-profile", {"vo": "gpu"})

        with pytest.raises(ProfileExistsError) as exc_info:
            profile_manager.create_profile("test-profile", {"vo": "gpu"})
        assert exc_info.value.name == "test-profile"

    def test_list_profiles_after_create(self, profile_manager):
        """Test listing profiles after creating one."""
        profile_manager.create_profile("profile-1", {"vo": "gpu"})
        profile_manager.create_profile("profile-2", {"hwdec": "auto"})

        profiles = profile_manager.list_profiles()
        assert len(profiles) == 2
        names = [p.name for p in profiles]
        assert "profile-1" in names
        assert "profile-2" in names

    def test_get_profile(self, profile_manager):
        """Test getting a specific profile."""
        options = {"vo": "gpu", "hwdec": "auto"}
        profile_manager.create_profile("test-profile", options)

        profile = profile_manager.get_profile("test-profile")
        assert profile.name == "test-profile"
        assert profile.options == options

    def test_get_profile_not_found(self, profile_manager):
        """Test getting a profile that doesn't exist."""
        with pytest.raises(ProfileNotFoundError) as exc_info:
            profile_manager.get_profile("nonexistent")
        assert exc_info.value.name == "nonexistent"

    def test_update_profile(self, profile_manager):
        """Test updating an existing profile."""
        profile_manager.create_profile("test-profile", {"vo": "gpu"})

        new_options = {"vo": "sdl", "hwdec": "no"}
        profile = profile_manager.update_profile("test-profile", new_options)

        assert profile.name == "test-profile"
        assert profile.options == new_options

    def test_update_profile_not_found(self, profile_manager):
        """Test updating a profile that doesn't exist."""
        with pytest.raises(ProfileNotFoundError):
            profile_manager.update_profile("nonexistent", {"vo": "gpu"})

    def test_delete_profile(self, profile_manager):
        """Test deleting a profile."""
        profile_manager.create_profile("test-profile", {"vo": "gpu"})
        profile_manager.delete_profile("test-profile")

        with pytest.raises(ProfileNotFoundError):
            profile_manager.get_profile("test-profile")

    def test_delete_profile_not_found(self, profile_manager):
        """Test deleting a profile that doesn't exist."""
        with pytest.raises(ProfileNotFoundError):
            profile_manager.delete_profile("nonexistent")


class TestProfileConfigParsing:
    """Tests for profile config parsing and serialization."""

    def test_parse_profiles_with_various_types(self, profile_manager, temp_profiles_dir):
        """Test parsing profiles with various value types."""
        profiles_path = temp_profiles_dir / "profiles.conf"
        content = """
[test-profile]
vo=gpu
hwdec=auto
volume=75
mute=yes
pause=no
speed=1.5
"""
        profiles_path.write_text(content)

        profile = profile_manager.get_profile("test-profile")
        assert profile.options["vo"] == "gpu"
        assert profile.options["hwdec"] == "auto"
        assert profile.options["volume"] == 75
        assert profile.options["mute"] is True
        assert profile.options["pause"] is False
        assert profile.options["speed"] == 1.5

    def test_multiple_profiles_in_file(self, profile_manager, temp_profiles_dir):
        """Test parsing multiple profiles from a file."""
        profiles_path = temp_profiles_dir / "profiles.conf"
        content = """
[profile-a]
vo=gpu

[profile-b]
vo=sdl
hwdec=no
"""
        profiles_path.write_text(content)

        profiles = profile_manager.list_profiles()
        assert len(profiles) == 2

        profile_a = profile_manager.get_profile("profile-a")
        assert profile_a.options["vo"] == "gpu"

        profile_b = profile_manager.get_profile("profile-b")
        assert profile_b.options["vo"] == "sdl"
        # "no" is parsed as boolean False
        assert profile_b.options["hwdec"] is False
