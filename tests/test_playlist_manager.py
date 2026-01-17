"""Unit tests for playlist manager."""

import tempfile
from pathlib import Path

import pytest

from mpv_controller.config import Config, MpvInstance, PathSettings, SocketSettings
from mpv_controller.models import PlaylistEntry
from mpv_controller.playlist_manager import (
    PlaylistConfigError,
    PlaylistExistsError,
    PlaylistManager,
    PlaylistNotFoundError,
)


@pytest.fixture
def temp_playlist_dir():
    """Create a temporary directory for playlists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config(temp_playlist_dir):
    """Create a mock configuration with paths."""
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
            playlist_folder=str(temp_playlist_dir),
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
def playlist_manager(mock_config):
    """Create a playlist manager instance."""
    return PlaylistManager(mock_config)


@pytest.fixture
def playlist_manager_no_paths(mock_config_no_paths):
    """Create a playlist manager without paths configured."""
    return PlaylistManager(mock_config_no_paths)


class TestPlaylistManagerInit:
    """Tests for playlist manager initialization."""

    def test_init_with_paths(self, playlist_manager, temp_playlist_dir):
        """Test initialization with paths configured."""
        assert playlist_manager._playlist_folder is not None
        assert playlist_manager._playlist_folder == temp_playlist_dir

    def test_init_without_paths(self, playlist_manager_no_paths):
        """Test initialization without paths configured."""
        assert playlist_manager_no_paths._playlist_folder is None


class TestPlaylistManagerConfigError:
    """Tests for configuration error handling."""

    def test_list_playlists_no_config(self, playlist_manager_no_paths):
        """Test listing playlists without config raises error."""
        with pytest.raises(PlaylistConfigError) as exc_info:
            playlist_manager_no_paths.list_playlists()
        assert "not configured" in str(exc_info.value)

    def test_get_playlist_no_config(self, playlist_manager_no_paths):
        """Test getting playlist without config raises error."""
        with pytest.raises(PlaylistConfigError):
            playlist_manager_no_paths.get_playlist("test")

    def test_create_playlist_no_config(self, playlist_manager_no_paths):
        """Test creating playlist without config raises error."""
        with pytest.raises(PlaylistConfigError):
            playlist_manager_no_paths.create_playlist("test", [])


class TestPlaylistManagerOperations:
    """Tests for playlist CRUD operations."""

    def test_list_playlists_empty(self, playlist_manager, temp_playlist_dir):
        """Test listing playlists when folder is empty."""
        temp_playlist_dir.mkdir(parents=True, exist_ok=True)
        playlists = playlist_manager.list_playlists()
        assert playlists == []

    def test_create_playlist(self, playlist_manager, temp_playlist_dir):
        """Test creating a new playlist."""
        entries = [
            PlaylistEntry(path="/media/video1.mp4", title="Video 1"),
            PlaylistEntry(path="/media/video2.mp4", title="Video 2"),
        ]
        playlist = playlist_manager.create_playlist("test-playlist", entries)

        assert playlist.name == "test-playlist"
        assert len(playlist.entries) == 2
        assert playlist.entries[0].path == "/media/video1.mp4"

        # Verify file was created
        assert (temp_playlist_dir / "test-playlist.m3u").exists()

    def test_create_playlist_already_exists(self, playlist_manager):
        """Test creating a playlist that already exists."""
        entries = [PlaylistEntry(path="/media/video1.mp4")]
        playlist_manager.create_playlist("test-playlist", entries)

        with pytest.raises(PlaylistExistsError) as exc_info:
            playlist_manager.create_playlist("test-playlist", entries)
        assert exc_info.value.name == "test-playlist"

    def test_list_playlists_after_create(self, playlist_manager):
        """Test listing playlists after creating some."""
        playlist_manager.create_playlist(
            "playlist-1", [PlaylistEntry(path="/media/video1.mp4")]
        )
        playlist_manager.create_playlist(
            "playlist-2", [PlaylistEntry(path="/media/video2.mp4")]
        )

        playlists = playlist_manager.list_playlists()
        assert len(playlists) == 2
        names = [p.name for p in playlists]
        assert "playlist-1" in names
        assert "playlist-2" in names

    def test_get_playlist(self, playlist_manager):
        """Test getting a specific playlist."""
        entries = [
            PlaylistEntry(path="/media/video1.mp4", title="Video 1"),
            PlaylistEntry(path="/media/video2.mp4"),
        ]
        playlist_manager.create_playlist("test-playlist", entries)

        playlist = playlist_manager.get_playlist("test-playlist")
        assert playlist.name == "test-playlist"
        assert len(playlist.entries) == 2
        assert playlist.entries[0].title == "Video 1"
        assert playlist.entries[1].title is None

    def test_get_playlist_not_found(self, playlist_manager):
        """Test getting a playlist that doesn't exist."""
        with pytest.raises(PlaylistNotFoundError) as exc_info:
            playlist_manager.get_playlist("nonexistent")
        assert exc_info.value.name == "nonexistent"

    def test_update_playlist_append(self, playlist_manager):
        """Test updating a playlist with append mode."""
        entries = [PlaylistEntry(path="/media/video1.mp4")]
        playlist_manager.create_playlist("test-playlist", entries)

        new_entries = [PlaylistEntry(path="/media/video2.mp4")]
        playlist = playlist_manager.update_playlist(
            "test-playlist", new_entries, replace=False
        )

        assert len(playlist.entries) == 2
        assert playlist.entries[0].path == "/media/video1.mp4"
        assert playlist.entries[1].path == "/media/video2.mp4"

    def test_update_playlist_replace(self, playlist_manager):
        """Test updating a playlist with replace mode."""
        entries = [
            PlaylistEntry(path="/media/video1.mp4"),
            PlaylistEntry(path="/media/video2.mp4"),
        ]
        playlist_manager.create_playlist("test-playlist", entries)

        new_entries = [PlaylistEntry(path="/media/new-video.mp4")]
        playlist = playlist_manager.update_playlist(
            "test-playlist", new_entries, replace=True
        )

        assert len(playlist.entries) == 1
        assert playlist.entries[0].path == "/media/new-video.mp4"

    def test_update_playlist_not_found(self, playlist_manager):
        """Test updating a playlist that doesn't exist."""
        with pytest.raises(PlaylistNotFoundError):
            playlist_manager.update_playlist(
                "nonexistent", [PlaylistEntry(path="/media/video.mp4")]
            )

    def test_delete_playlist(self, playlist_manager, temp_playlist_dir):
        """Test deleting a playlist."""
        entries = [PlaylistEntry(path="/media/video1.mp4")]
        playlist_manager.create_playlist("test-playlist", entries)

        # Verify file exists
        assert (temp_playlist_dir / "test-playlist.m3u").exists()

        playlist_manager.delete_playlist("test-playlist")

        # Verify file was deleted
        assert not (temp_playlist_dir / "test-playlist.m3u").exists()

        with pytest.raises(PlaylistNotFoundError):
            playlist_manager.get_playlist("test-playlist")

    def test_delete_playlist_not_found(self, playlist_manager):
        """Test deleting a playlist that doesn't exist."""
        with pytest.raises(PlaylistNotFoundError):
            playlist_manager.delete_playlist("nonexistent")

    def test_get_playlist_folder(self, playlist_manager, temp_playlist_dir):
        """Test getting the playlist folder path."""
        folder = playlist_manager.get_playlist_folder()
        assert folder == str(temp_playlist_dir)


class TestM3UParsing:
    """Tests for M3U parsing and serialization."""

    def test_parse_m3u_with_extinf(self, playlist_manager, temp_playlist_dir):
        """Test parsing M3U with EXTINF metadata."""
        content = """#EXTM3U
#EXTINF:-1,Video Title 1
/media/video1.mp4
#EXTINF:-1,Video Title 2
/media/video2.mp4
/media/video3.mp4
"""
        playlist_path = temp_playlist_dir / "test.m3u"
        playlist_path.write_text(content)

        playlist = playlist_manager.get_playlist("test")
        assert len(playlist.entries) == 3
        assert playlist.entries[0].title == "Video Title 1"
        assert playlist.entries[1].title == "Video Title 2"
        assert playlist.entries[2].title is None

    def test_parse_m3u_simple(self, playlist_manager, temp_playlist_dir):
        """Test parsing simple M3U without metadata."""
        content = """/media/video1.mp4
/media/video2.mp4
/media/video3.mp4
"""
        playlist_path = temp_playlist_dir / "simple.m3u"
        playlist_path.write_text(content)

        playlist = playlist_manager.get_playlist("simple")
        assert len(playlist.entries) == 3
        assert all(e.title is None for e in playlist.entries)

    def test_serialize_m3u_with_titles(self, playlist_manager):
        """Test that serialized M3U includes EXTINF for entries with titles."""
        entries = [
            PlaylistEntry(path="/media/video1.mp4", title="Video 1"),
            PlaylistEntry(path="/media/video2.mp4"),
        ]
        playlist = playlist_manager.create_playlist("test-playlist", entries)

        # Read back and verify
        playlist = playlist_manager.get_playlist("test-playlist")
        assert playlist.entries[0].title == "Video 1"

    def test_playlist_entry_count(self, playlist_manager):
        """Test that playlist info includes correct entry count."""
        entries = [
            PlaylistEntry(path="/media/video1.mp4"),
            PlaylistEntry(path="/media/video2.mp4"),
            PlaylistEntry(path="/media/video3.mp4"),
        ]
        playlist_manager.create_playlist("test-playlist", entries)

        playlists = playlist_manager.list_playlists()
        assert len(playlists) == 1
        assert playlists[0].entry_count == 3
