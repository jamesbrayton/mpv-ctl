"""Unit tests for profile manager."""

import tempfile
from pathlib import Path

import pytest

from mpv_controller.config import Config, MpvInstance, PathSettings, SocketSettings
from mpv_controller.models import ProfileMode
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
        options = {
            "vo": "gpu",
            "hwdec": "auto",
            "x-profile-type": "setting",
            "x-profile-mode": "additive",
        }
        profile = profile_manager.create_profile("test-profile", options)

        assert profile.name == "test-profile"
        assert profile.options == options
        assert profile.profile_type == "setting"
        assert profile.profile_mode == ProfileMode.ADDITIVE

    def test_create_profile_already_exists(self, profile_manager):
        """Test creating a profile that already exists."""
        options = {
            "vo": "gpu",
            "x-profile-type": "setting",
            "x-profile-mode": "reset",
        }
        profile_manager.create_profile("test-profile", options)

        with pytest.raises(ProfileExistsError) as exc_info:
            profile_manager.create_profile("test-profile", options)
        assert exc_info.value.name == "test-profile"

    def test_list_profiles_after_create(self, profile_manager):
        """Test listing profiles after creating one."""
        profile_manager.create_profile(
            "profile-1",
            {"vo": "gpu", "x-profile-type": "setting", "x-profile-mode": "reset"},
        )
        profile_manager.create_profile(
            "profile-2",
            {"hwdec": "auto", "x-profile-type": "setting", "x-profile-mode": "additive"},
        )

        profiles = profile_manager.list_profiles()
        assert len(profiles) == 2
        names = [p.name for p in profiles]
        assert "profile-1" in names
        assert "profile-2" in names

    def test_get_profile(self, profile_manager):
        """Test getting a specific profile."""
        options = {
            "vo": "gpu",
            "hwdec": "auto",
            "x-profile-type": "setting",
            "x-profile-mode": "additive",
        }
        profile_manager.create_profile("test-profile", options)

        profile = profile_manager.get_profile("test-profile")
        assert profile.name == "test-profile"
        assert profile.options == options
        assert profile.profile_type == "setting"
        assert profile.profile_mode == ProfileMode.ADDITIVE

    def test_get_profile_not_found(self, profile_manager):
        """Test getting a profile that doesn't exist."""
        with pytest.raises(ProfileNotFoundError) as exc_info:
            profile_manager.get_profile("nonexistent")
        assert exc_info.value.name == "nonexistent"

    def test_update_profile(self, profile_manager):
        """Test updating an existing profile."""
        profile_manager.create_profile(
            "test-profile",
            {"vo": "gpu", "x-profile-type": "setting", "x-profile-mode": "reset"},
        )

        new_options = {
            "vo": "sdl",
            "hwdec": "no",
            "x-profile-type": "setting",
            "x-profile-mode": "additive",
        }
        profile = profile_manager.update_profile("test-profile", new_options)

        assert profile.name == "test-profile"
        assert profile.options == new_options
        assert profile.profile_type == "setting"
        assert profile.profile_mode == ProfileMode.ADDITIVE

    def test_update_profile_not_found(self, profile_manager):
        """Test updating a profile that doesn't exist."""
        with pytest.raises(ProfileNotFoundError):
            profile_manager.update_profile(
                "nonexistent",
                {"vo": "gpu", "x-profile-type": "setting", "x-profile-mode": "reset"},
            )

    def test_delete_profile(self, profile_manager):
        """Test deleting a profile."""
        profile_manager.create_profile(
            "test-profile",
            {"vo": "gpu", "x-profile-type": "setting", "x-profile-mode": "reset"},
        )
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
#x-profile-type=setting
#x-profile-mode=additive
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
#x-profile-type=shader
#x-profile-mode=reset

[profile-b]
vo=sdl
hwdec=no
#x-profile-type=setting
#x-profile-mode=additive
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


class TestProfileMetadataValidation:
    """Tests for profile metadata validation."""

    def test_create_profile_missing_type(self, profile_manager):
        """Test that creating a profile without x-profile-type raises error."""
        options = {"vo": "gpu", "x-profile-mode": "reset"}
        with pytest.raises(ProfileConfigError) as exc_info:
            profile_manager.create_profile("test-profile", options)
        assert "x-profile-type" in str(exc_info.value)

    def test_create_profile_missing_mode(self, profile_manager):
        """Test that creating a profile without x-profile-mode raises error."""
        options = {"vo": "gpu", "x-profile-type": "shader"}
        with pytest.raises(ProfileConfigError) as exc_info:
            profile_manager.create_profile("test-profile", options)
        assert "x-profile-mode" in str(exc_info.value)

    def test_create_profile_custom_type(self, profile_manager):
        """Test that creating a profile with custom x-profile-type works (e.g., 'vf', 'ao')."""
        options = {
            "vo": "gpu",
            "x-profile-type": "vf",  # Custom type
            "x-profile-mode": "reset",
        }
        profile = profile_manager.create_profile("test-profile", options)
        assert profile.profile_type == "vf"
        assert profile.profile_mode == ProfileMode.RESET

    def test_create_profile_invalid_mode(self, profile_manager):
        """Test that creating a profile with invalid x-profile-mode raises error."""
        options = {
            "vo": "gpu",
            "x-profile-type": "shader",
            "x-profile-mode": "invalid-mode",
        }
        with pytest.raises(ProfileConfigError) as exc_info:
            profile_manager.create_profile("test-profile", options)
        assert "invalid x-profile-mode" in str(exc_info.value)

    def test_update_profile_missing_metadata(self, profile_manager):
        """Test that updating a profile without metadata raises error."""
        # Create valid profile first
        profile_manager.create_profile(
            "test-profile",
            {"vo": "gpu", "x-profile-type": "shader", "x-profile-mode": "reset"},
        )

        # Try to update without metadata
        with pytest.raises(ProfileConfigError):
            profile_manager.update_profile("test-profile", {"vo": "sdl"})

    def test_parse_profiles_missing_metadata(self, profile_manager, temp_profiles_dir):
        """Test that parsing profiles without metadata skips them (tolerant behavior)."""
        profiles_path = temp_profiles_dir / "profiles.conf"
        content = """
[bad-profile]
vo=gpu
hwdec=auto
"""
        profiles_path.write_text(content)

        # Should not raise - just skip profiles without metadata
        profiles = profile_manager.list_profiles()
        assert len(profiles) == 0

    def test_shader_profile_type(self, profile_manager):
        """Test creating a shader type profile."""
        options = {
            "glsl-shaders-clr": True,
            "glsl-shaders-append": "~/shaders/test.glsl",
            "x-profile-type": "shader",
            "x-profile-mode": "reset",
        }
        profile = profile_manager.create_profile("shader-profile", options)
        assert profile.profile_type == "shader"
        assert profile.profile_mode == ProfileMode.RESET

    def test_normalize_shader_array(self, profile_manager):
        """Test that shader strings are normalized to arrays."""
        options = {
            "glsl-shaders-append": "~/shaders/test.glsl",
            "x-profile-type": "shader",
            "x-profile-mode": "additive",
        }
        profile = profile_manager.create_profile("shader-profile", options)
        
        # Retrieve the profile and check normalization
        retrieved = profile_manager.get_profile("shader-profile")
        assert isinstance(retrieved.options["glsl-shaders-append"], list)
        assert retrieved.options["glsl-shaders-append"] == ["~/shaders/test.glsl"]

    def test_custom_profile_types(self, profile_manager):
        """Test that custom profile types (vf, ao, etc.) work without code changes."""
        # Create profile with custom type "vf"
        vf_options = {
            "vf": "gradfun=radius=16",
            "x-profile-type": "vf",
            "x-profile-mode": "reset",
        }
        vf_profile = profile_manager.create_profile("vf-profile", vf_options)
        assert vf_profile.profile_type == "vf"
        assert vf_profile.profile_mode == ProfileMode.RESET

        # Create profile with custom type "ao"
        ao_options = {
            "ao": "pulse",
            "x-profile-type": "ao",
            "x-profile-mode": "additive",
        }
        ao_profile = profile_manager.create_profile("ao-profile", ao_options)
        assert ao_profile.profile_type == "ao"
        assert ao_profile.profile_mode == ProfileMode.ADDITIVE

        # List profiles and verify both exist
        profiles = profile_manager.list_profiles()
        profile_types = {p.name: p.profile_type for p in profiles}
        assert profile_types["vf-profile"] == "vf"
        assert profile_types["ao-profile"] == "ao"


class TestProfileParsingEdgeCases:
    """Tests for profile parsing edge cases."""

    def test_parse_option_without_value(self, profile_manager, temp_profiles_dir):
        """Test parsing options without values (flags/commands like glsl-shaders-clr)."""
        profiles_path = temp_profiles_dir / "profiles.conf"
        content = """
[no-shaders]
glsl-shaders-clr
#x-profile-type=shader
#x-profile-mode=reset
"""
        profiles_path.write_text(content)

        profiles = profile_manager.list_profiles()
        assert len(profiles) == 1
        
        profile = profile_manager.get_profile("no-shaders")
        assert profile.name == "no-shaders"
        assert profile.profile_type == "shader"
        assert profile.profile_mode == ProfileMode.RESET
        # Option without value should be stored as True
        assert profile.options["glsl-shaders-clr"] is True

    def test_parse_option_with_empty_value(self, profile_manager, temp_profiles_dir):
        """Test parsing options with empty values (e.g., vf=)."""
        profiles_path = temp_profiles_dir / "profiles.conf"
        content = """
[vf-off]
vf=
#x-profile-type=vf
#x-profile-mode=reset
"""
        profiles_path.write_text(content)

        profiles = profile_manager.list_profiles()
        assert len(profiles) == 1
        
        profile = profile_manager.get_profile("vf-off")
        assert profile.name == "vf-off"
        assert profile.profile_type == "vf"
        assert profile.profile_mode == ProfileMode.RESET
        # Empty value should be stored as empty string
        assert profile.options["vf"] == ""

    def test_parse_mixed_option_formats(self, profile_manager, temp_profiles_dir):
        """Test parsing profiles with mixed option formats."""
        profiles_path = temp_profiles_dir / "profiles.conf"
        content = """
[mixed-format]
profile-desc="Test profile with mixed formats"
glsl-shaders-clr
glsl-shaders-append=~/shaders/test.glsl
scale=ewa_lanczos
sharpen=0.5
vf=
#x-profile-type=shader
#x-profile-mode=reset
"""
        profiles_path.write_text(content)

        profile = profile_manager.get_profile("mixed-format")
        assert profile.name == "mixed-format"
        assert profile.profile_type == "shader"
        assert profile.profile_mode == ProfileMode.RESET
        # Quotes are preserved in the value as mpv expects them
        assert profile.options["profile-desc"] == '"Test profile with mixed formats"'
        # Option without value
        assert profile.options["glsl-shaders-clr"] is True
        # Normal options
        assert profile.options["glsl-shaders-append"] == ["~/shaders/test.glsl"]
        assert profile.options["scale"] == "ewa_lanczos"
        assert profile.options["sharpen"] == 0.5
        # Empty value
        assert profile.options["vf"] == ""

    def test_parse_vf_interpolation_profile(self, profile_manager, temp_profiles_dir):
        """Test parsing vf interpolation profile from user's profiles.conf."""
        profiles_path = temp_profiles_dir / "profiles.conf"
        content = """
[vf-interp-120]
profile-desc="minterpolate 120fps (CPU-heavy)"
vf=lavfi=minterpolate=fps=120
#x-profile-type=vf
#x-profile-mode=reset
"""
        profiles_path.write_text(content)

        profile = profile_manager.get_profile("vf-interp-120")
        assert profile.name == "vf-interp-120"
        assert profile.profile_type == "vf"
        assert profile.profile_mode == ProfileMode.RESET
        # Quotes are preserved in the value as mpv expects them
        assert profile.options["profile-desc"] == '"minterpolate 120fps (CPU-heavy)"'
        assert profile.options["vf"] == "lavfi=minterpolate=fps=120"

    def test_parse_additive_shader_profile(self, profile_manager, temp_profiles_dir):
        """Test parsing additive shader profile (e.g., fun effects)."""
        profiles_path = temp_profiles_dir / "profiles.conf"
        content = """
[bloom]
profile-desc="Spiral bloom highlight glow"
glsl-shaders-append=~~/shaders/fun/bloom-spiral.glsl
#x-profile-type=shader
#x-profile-mode=additive
"""
        profiles_path.write_text(content)

        profile = profile_manager.get_profile("bloom")
        assert profile.name == "bloom"
        assert profile.profile_type == "shader"
        assert profile.profile_mode == ProfileMode.ADDITIVE
        assert profile.options["glsl-shaders-append"] == ["~~/shaders/fun/bloom-spiral.glsl"]

    def test_real_world_no_shaders_profile(self, profile_manager, temp_profiles_dir):
        """Test the exact no-shaders profile from user's profiles.conf."""
        profiles_path = temp_profiles_dir / "profiles.conf"
        content = """
[no-shaders]
profile-desc="Disable all shaders"
glsl-shaders-clr
#x-profile-type=shader
#x-profile-mode=reset
"""
        profiles_path.write_text(content)

        profile = profile_manager.get_profile("no-shaders")
        assert profile.name == "no-shaders"
        assert profile.profile_type == "shader"
        assert profile.profile_mode == ProfileMode.RESET
        # Quotes are preserved in the value as mpv expects them
        assert profile.options["profile-desc"] == '"Disable all shaders"'
        assert profile.options["glsl-shaders-clr"] is True
