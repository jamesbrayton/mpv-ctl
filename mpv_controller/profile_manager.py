"""Profile management for mpv-controller."""

import os
import re
from pathlib import Path
from typing import Any, Optional

import structlog

from .config import Config
from .models import ProfileInfo, ProfileMode

logger = structlog.get_logger()


class ProfileNotFoundError(Exception):
    """Raised when a profile is not found."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Profile '{name}' not found")


class ProfileExistsError(Exception):
    """Raised when trying to create a profile that already exists."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Profile '{name}' already exists")


class ProfileConfigError(Exception):
    """Raised when profile configuration is missing or invalid."""

    def __init__(self, message: str):
        super().__init__(message)


class ProfileManager:
    """Manages mpv profiles configuration."""

    def __init__(self, config: Config):
        """Initialize the profile manager.

        Args:
            config: Application configuration.
        """
        self.config = config
        self._profiles_path: Optional[Path] = None

        if config.paths.profiles_config_path:
            self._profiles_path = Path(
                os.path.expanduser(config.paths.profiles_config_path)
            )
            logger.info("Profile manager initialized", path=str(self._profiles_path))
        else:
            logger.warning("No profiles config path configured")

    def _ensure_config(self) -> Path:
        """Ensure profiles config path is configured and return it.

        Raises:
            ProfileConfigError: If profiles config path is not configured.
        """
        if not self._profiles_path:
            raise ProfileConfigError(
                "Profiles config path not configured. "
                "Set 'paths.profiles_config_path' in configuration."
            )
        return self._profiles_path

    def _parse_profiles_config(self, content: str) -> dict[str, dict[str, Any]]:
        """Parse mpv profiles.conf content.

        Args:
            content: Raw content of profiles.conf file.

        Returns:
            Dictionary mapping profile names to their options.
            
        Raises:
            ProfileConfigError: If profile is missing required metadata or has invalid values.
        """
        profiles: dict[str, dict[str, Any]] = {}
        current_profile: Optional[str] = None

        for line in content.splitlines():
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Check for profile header [profile-name]
            profile_match = re.match(r"^\[([^\]]+)\]$", line)
            if profile_match:
                current_profile = profile_match.group(1)
                profiles[current_profile] = {}
                continue

            # Parse option=value
            if current_profile is not None and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()

                # Try to convert value to appropriate type
                if value.lower() == "yes" or value.lower() == "true":
                    profiles[current_profile][key] = True
                elif value.lower() == "no" or value.lower() == "false":
                    profiles[current_profile][key] = False
                elif value.isdigit():
                    profiles[current_profile][key] = int(value)
                else:
                    try:
                        profiles[current_profile][key] = float(value)
                    except ValueError:
                        profiles[current_profile][key] = value
        
        # Validate all profiles have required metadata
        for profile_name, options in profiles.items():
            # Check for x-profile-type (any string value allowed)
            if "x-profile-type" not in options:
                raise ProfileConfigError(
                    f"Profile '{profile_name}' missing required field 'x-profile-type'"
                )
            
            # Check for x-profile-mode (must be 'reset' or 'additive')
            if "x-profile-mode" not in options:
                raise ProfileConfigError(
                    f"Profile '{profile_name}' missing required field 'x-profile-mode'"
                )
            
            profile_mode = options["x-profile-mode"]
            if profile_mode not in ["reset", "additive"]:
                raise ProfileConfigError(
                    f"Profile '{profile_name}' has invalid x-profile-mode value '{profile_mode}'. "
                    "Must be 'reset' or 'additive'"
                )

        return profiles

    def _serialize_profiles_config(
        self, profiles: dict[str, dict[str, Any]]
    ) -> str:
        """Serialize profiles to mpv profiles.conf format.

        Args:
            profiles: Dictionary mapping profile names to their options.

        Returns:
            Serialized content for profiles.conf file.
        """
        lines = ["# mpv profiles configuration", "# Managed by mpv-controller", ""]

        for name, options in profiles.items():
            lines.append(f"[{name}]")
            for key, value in options.items():
                if isinstance(value, bool):
                    value_str = "yes" if value else "no"
                else:
                    value_str = str(value)
                lines.append(f"{key}={value_str}")
            lines.append("")

        return "\n".join(lines)

    def list_profiles(self) -> list[ProfileInfo]:
        """List all available profiles.

        Returns:
            List of ProfileInfo objects.

        Raises:
            ProfileConfigError: If profiles config path is not configured.
        """
        profiles_path = self._ensure_config()

        if not profiles_path.exists():
            logger.info("Profiles config file does not exist", path=str(profiles_path))
            return []

        content = profiles_path.read_text()
        profiles = self._parse_profiles_config(content)

        result = []
        for name, options in profiles.items():
            # Extract metadata
            profile_type = options["x-profile-type"]
            profile_mode = ProfileMode(options["x-profile-mode"])
            
            # Create a copy of options without the metadata fields (mpv should ignore them, but clean response)
            options_copy = options.copy()
            
            # Normalize shader values to arrays
            if "glsl-shaders-append" in options_copy:
                value = options_copy["glsl-shaders-append"]
                if isinstance(value, str):
                    options_copy["glsl-shaders-append"] = [value]
            
            result.append(
                ProfileInfo(
                    name=name,
                    options=options_copy,
                    profile_type=profile_type,
                    profile_mode=profile_mode,
                )
            )

        return result

    def get_profile(self, name: str) -> ProfileInfo:
        """Get a specific profile by name.

        Args:
            name: Name of the profile to get.

        Returns:
            ProfileInfo object.

        Raises:
            ProfileNotFoundError: If profile doesn't exist.
            ProfileConfigError: If profiles config path is not configured.
        """
        profiles_path = self._ensure_config()

        if not profiles_path.exists():
            raise ProfileNotFoundError(name)

        content = profiles_path.read_text()
        profiles = self._parse_profiles_config(content)

        if name not in profiles:
            raise ProfileNotFoundError(name)
        
        options = profiles[name]
        
        # Extract metadata
        profile_type = options["x-profile-type"]
        profile_mode = ProfileMode(options["x-profile-mode"])
        
        # Create a copy of options
        options_copy = options.copy()
        
        # Normalize shader values to arrays
        if "glsl-shaders-append" in options_copy:
            value = options_copy["glsl-shaders-append"]
            if isinstance(value, str):
                options_copy["glsl-shaders-append"] = [value]

        return ProfileInfo(
            name=name,
            options=options_copy,
            profile_type=profile_type,
            profile_mode=profile_mode,
        )

    def create_profile(self, name: str, options: dict[str, Any]) -> ProfileInfo:
        """Create a new profile.

        Args:
            name: Name of the profile to create.
            options: Profile options/settings.

        Returns:
            Created ProfileInfo object.

        Raises:
            ProfileExistsError: If profile already exists.
            ProfileConfigError: If profiles config path is not configured or metadata is invalid.
        """
        profiles_path = self._ensure_config()
        
        # Validate metadata fields exist
        if "x-profile-type" not in options:
            raise ProfileConfigError(
                f"Profile '{name}' missing required field 'x-profile-type'"
            )
        if "x-profile-mode" not in options:
            raise ProfileConfigError(
                f"Profile '{name}' missing required field 'x-profile-mode'"
            )
        
        # Validate metadata values (only mode, type can be any string)
        profile_type_str = options["x-profile-type"]
        
        profile_mode_str = options["x-profile-mode"]
        if profile_mode_str not in ["reset", "additive"]:
            raise ProfileConfigError(
                f"Profile '{name}' has invalid x-profile-mode value '{profile_mode_str}'. "
                "Must be 'reset' or 'additive'"
            )

        profiles: dict[str, dict[str, Any]] = {}
        if profiles_path.exists():
            content = profiles_path.read_text()
            # Don't validate existing profiles on create, just parse
            profiles = self._parse_profiles_config(content)

        if name in profiles:
            raise ProfileExistsError(name)

        profiles[name] = options

        # Ensure parent directory exists
        profiles_path.parent.mkdir(parents=True, exist_ok=True)

        # Write updated config
        profiles_path.write_text(self._serialize_profiles_config(profiles))

        logger.info("Created profile", name=name)
        return ProfileInfo(
            name=name,
            options=options,
            profile_type=profile_type_str,
            profile_mode=ProfileMode(profile_mode_str),
        )

    def update_profile(self, name: str, options: dict[str, Any]) -> ProfileInfo:
        """Update an existing profile (replaces all options).

        Args:
            name: Name of the profile to update.
            options: New profile options/settings.

        Returns:
            Updated ProfileInfo object.

        Raises:
            ProfileNotFoundError: If profile doesn't exist.
            ProfileConfigError: If profiles config path is not configured or metadata is invalid.
        """
        profiles_path = self._ensure_config()
        
        # Validate metadata fields exist
        if "x-profile-type" not in options:
            raise ProfileConfigError(
                f"Profile '{name}' missing required field 'x-profile-type'"
            )
        if "x-profile-mode" not in options:
            raise ProfileConfigError(
                f"Profile '{name}' missing required field 'x-profile-mode'"
            )
        
        # Validate metadata values (only mode, type can be any string)
        profile_type_str = options["x-profile-type"]
        
        profile_mode_str = options["x-profile-mode"]
        if profile_mode_str not in ["reset", "additive"]:
            raise ProfileConfigError(
                f"Profile '{name}' has invalid x-profile-mode value '{profile_mode_str}'. "
                "Must be 'reset' or 'additive'"
            )

        if not profiles_path.exists():
            raise ProfileNotFoundError(name)

        content = profiles_path.read_text()
        profiles = self._parse_profiles_config(content)

        if name not in profiles:
            raise ProfileNotFoundError(name)

        profiles[name] = options

        # Write updated config
        profiles_path.write_text(self._serialize_profiles_config(profiles))

        logger.info("Updated profile", name=name)
        return ProfileInfo(
            name=name,
            options=options,
            profile_type=profile_type_str,
            profile_mode=ProfileMode(profile_mode_str),
        )

    def delete_profile(self, name: str) -> None:
        """Delete a profile.

        Args:
            name: Name of the profile to delete.

        Raises:
            ProfileNotFoundError: If profile doesn't exist.
            ProfileConfigError: If profiles config path is not configured.
        """
        profiles_path = self._ensure_config()

        if not profiles_path.exists():
            raise ProfileNotFoundError(name)

        content = profiles_path.read_text()
        profiles = self._parse_profiles_config(content)

        if name not in profiles:
            raise ProfileNotFoundError(name)

        del profiles[name]

        # Write updated config
        profiles_path.write_text(self._serialize_profiles_config(profiles))

        logger.info("Deleted profile", name=name)
