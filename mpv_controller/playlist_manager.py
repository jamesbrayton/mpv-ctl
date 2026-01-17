"""Playlist management for mpv-controller."""

import os
import re
from pathlib import Path
from typing import Optional

import structlog

from .config import Config
from .models import PlaylistContents, PlaylistEntry, PlaylistInfo

logger = structlog.get_logger()


class PlaylistNotFoundError(Exception):
    """Raised when a playlist is not found."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Playlist '{name}' not found")


class PlaylistExistsError(Exception):
    """Raised when trying to create a playlist that already exists."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Playlist '{name}' already exists")


class PlaylistConfigError(Exception):
    """Raised when playlist configuration is missing or invalid."""

    def __init__(self, message: str):
        super().__init__(message)


class PlaylistManager:
    """Manages playlist files in the configured folder."""

    def __init__(self, config: Config):
        """Initialize the playlist manager.

        Args:
            config: Application configuration.
        """
        self.config = config
        self._playlist_folder: Optional[Path] = None

        if config.paths.playlist_folder:
            self._playlist_folder = Path(
                os.path.expanduser(config.paths.playlist_folder)
            )
            logger.info(
                "Playlist manager initialized", folder=str(self._playlist_folder)
            )
        else:
            logger.warning("No playlist folder configured")

    def _ensure_config(self) -> Path:
        """Ensure playlist folder is configured and return it.

        Raises:
            PlaylistConfigError: If playlist folder is not configured.
        """
        if not self._playlist_folder:
            raise PlaylistConfigError(
                "Playlist folder not configured. "
                "Set 'paths.playlist_folder' in configuration."
            )
        return self._playlist_folder

    def _get_playlist_path(self, name: str) -> Path:
        """Get the full path for a playlist file.

        Args:
            name: Name of the playlist (without .m3u extension).

        Returns:
            Full path to the playlist file.
        """
        folder = self._ensure_config()
        return folder / f"{name}.m3u"

    def _parse_m3u(self, content: str) -> list[PlaylistEntry]:
        """Parse M3U playlist content.

        Args:
            content: Raw content of M3U file.

        Returns:
            List of PlaylistEntry objects.
        """
        entries: list[PlaylistEntry] = []
        current_title: Optional[str] = None

        for line in content.splitlines():
            line = line.strip()

            # Skip empty lines and the M3U header
            if not line or line == "#EXTM3U":
                continue

            # Check for EXTINF (extended info) line
            if line.startswith("#EXTINF:"):
                # Format: #EXTINF:duration,title
                match = re.match(r"#EXTINF:[^,]*,(.*)$", line)
                if match:
                    current_title = match.group(1).strip() or None
                continue

            # Skip other comment lines
            if line.startswith("#"):
                continue

            # This is a file path
            entries.append(PlaylistEntry(path=line, title=current_title))
            current_title = None

        return entries

    def _serialize_m3u(self, entries: list[PlaylistEntry]) -> str:
        """Serialize entries to M3U format.

        Args:
            entries: List of PlaylistEntry objects.

        Returns:
            M3U formatted content.
        """
        lines = ["#EXTM3U"]

        for entry in entries:
            if entry.title:
                lines.append(f"#EXTINF:-1,{entry.title}")
            lines.append(entry.path)

        return "\n".join(lines) + "\n"

    def list_playlists(self) -> list[PlaylistInfo]:
        """List all playlists in the folder.

        Returns:
            List of PlaylistInfo objects.

        Raises:
            PlaylistConfigError: If playlist folder is not configured.
        """
        folder = self._ensure_config()

        if not folder.exists():
            logger.info("Playlist folder does not exist", folder=str(folder))
            return []

        playlists = []
        for file_path in folder.glob("*.m3u"):
            try:
                content = file_path.read_text()
                entries = self._parse_m3u(content)
                playlists.append(
                    PlaylistInfo(
                        name=file_path.stem,
                        path=str(file_path),
                        entry_count=len(entries),
                    )
                )
            except Exception as e:
                logger.warning(
                    "Error reading playlist file",
                    file=str(file_path),
                    error=str(e),
                )

        return sorted(playlists, key=lambda p: p.name)

    def get_playlist(self, name: str) -> PlaylistContents:
        """Get the contents of a specific playlist.

        Args:
            name: Name of the playlist (without .m3u extension).

        Returns:
            PlaylistContents object.

        Raises:
            PlaylistNotFoundError: If playlist doesn't exist.
            PlaylistConfigError: If playlist folder is not configured.
        """
        playlist_path = self._get_playlist_path(name)

        if not playlist_path.exists():
            raise PlaylistNotFoundError(name)

        content = playlist_path.read_text()
        entries = self._parse_m3u(content)

        return PlaylistContents(name=name, entries=entries)

    def create_playlist(
        self, name: str, entries: list[PlaylistEntry]
    ) -> PlaylistContents:
        """Create a new playlist.

        Args:
            name: Name of the playlist (without .m3u extension).
            entries: Initial entries for the playlist.

        Returns:
            Created PlaylistContents object.

        Raises:
            PlaylistExistsError: If playlist already exists.
            PlaylistConfigError: If playlist folder is not configured.
        """
        playlist_path = self._get_playlist_path(name)

        if playlist_path.exists():
            raise PlaylistExistsError(name)

        # Ensure folder exists
        folder = self._ensure_config()
        folder.mkdir(parents=True, exist_ok=True)

        # Write playlist
        content = self._serialize_m3u(entries)
        playlist_path.write_text(content)

        logger.info("Created playlist", name=name, entries=len(entries))
        return PlaylistContents(name=name, entries=entries)

    def update_playlist(
        self, name: str, entries: list[PlaylistEntry], replace: bool = False
    ) -> PlaylistContents:
        """Update a playlist.

        Args:
            name: Name of the playlist (without .m3u extension).
            entries: Entries to add or replace with.
            replace: If True, replace all entries; if False, append.

        Returns:
            Updated PlaylistContents object.

        Raises:
            PlaylistNotFoundError: If playlist doesn't exist.
            PlaylistConfigError: If playlist folder is not configured.
        """
        playlist_path = self._get_playlist_path(name)

        if not playlist_path.exists():
            raise PlaylistNotFoundError(name)

        if replace:
            final_entries = entries
        else:
            # Append to existing
            current = self.get_playlist(name)
            final_entries = current.entries + entries

        # Write updated playlist
        content = self._serialize_m3u(final_entries)
        playlist_path.write_text(content)

        logger.info(
            "Updated playlist",
            name=name,
            entries=len(final_entries),
            mode="replace" if replace else "append",
        )
        return PlaylistContents(name=name, entries=final_entries)

    def delete_playlist(self, name: str) -> None:
        """Delete a playlist.

        Args:
            name: Name of the playlist (without .m3u extension).

        Raises:
            PlaylistNotFoundError: If playlist doesn't exist.
            PlaylistConfigError: If playlist folder is not configured.
        """
        playlist_path = self._get_playlist_path(name)

        if not playlist_path.exists():
            raise PlaylistNotFoundError(name)

        playlist_path.unlink()
        logger.info("Deleted playlist", name=name)

    def get_playlist_folder(self) -> str:
        """Get the configured playlist folder path.

        Returns:
            Path to the playlist folder.

        Raises:
            PlaylistConfigError: If playlist folder is not configured.
        """
        folder = self._ensure_config()
        return str(folder)
