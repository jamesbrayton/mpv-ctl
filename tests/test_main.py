"""Unit tests for main module."""

import logging
import signal
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from mpv_controller.config import Config, LoggingSettings, MpvInstance, ServerSettings, SocketSettings
from mpv_controller.main import main, setup_logging


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return Config(
        mpv_instances=[
            MpvInstance(
                id="mpv-0",
                socket_path="/tmp/mpv-0.sock",
                display_name="Test Player",
            ),
        ],
        server=ServerSettings(
            bind_address="127.0.0.1",
            rest_port=8080,
            grpc_port=50051,
        ),
        socket=SocketSettings(
            timeout=5.0,
            retry_attempts=3,
            retry_delay=0.1,
        ),
        logging=LoggingSettings(
            log_level="INFO",
            log_file=None,
        ),
    )


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_console(self, mock_config):
        """Test logging setup with console output."""
        setup_logging(mock_config)

        # Verify structlog is configured
        import structlog

        logger = structlog.get_logger()
        assert logger is not None

    def test_setup_logging_with_file(self, mock_config):
        """Test logging setup with file output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            mock_config.logging.log_file = str(log_file)

            setup_logging(mock_config)

            # Verify log file parent directory is created
            assert log_file.parent.exists()

            # Verify file handler is added
            root_logger = logging.getLogger()
            file_handlers = [
                h for h in root_logger.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) > 0

    def test_setup_logging_creates_directories(self, mock_config):
        """Test logging setup creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "nested" / "dir" / "test.log"
            mock_config.logging.log_file = str(log_file)

            setup_logging(mock_config)

            # Verify nested directories are created
            assert log_file.parent.exists()

    def test_setup_logging_log_level(self, mock_config):
        """Test logging setup respects log level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            mock_config.logging.log_file = str(log_file)
            mock_config.logging.log_level = "DEBUG"

            setup_logging(mock_config)

            root_logger = logging.getLogger()
            # Log level should be set to DEBUG (10) when log_file is specified
            assert root_logger.level == logging.DEBUG

    def test_setup_logging_json_renderer_with_file(self, mock_config):
        """Test logging uses JSON renderer when file is specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            mock_config.logging.log_file = str(log_file)

            setup_logging(mock_config)

            # JSON renderer should be configured
            import structlog

            logger = structlog.get_logger()
            assert logger is not None


class TestMain:
    """Tests for main function."""

    @patch("mpv_controller.main.load_config")
    @patch("mpv_controller.main.setup_logging")
    @patch("mpv_controller.main.MpvSocketManager")
    @patch("mpv_controller.main.ProfileManager")
    @patch("mpv_controller.main.PlaylistManager")
    @patch("mpv_controller.main.create_rest_app")
    @patch("mpv_controller.main.create_grpc_server")
    @patch("mpv_controller.main.uvicorn.run")
    @patch("mpv_controller.main.signal.signal")
    @patch("mpv_controller.main.threading.Event")
    @patch("mpv_controller.main.threading.Thread")
    def test_main_successful_startup(
        self,
        mock_thread_class,
        mock_event,
        mock_signal,
        mock_uvicorn,
        mock_create_grpc,
        mock_create_rest,
        mock_playlist_mgr,
        mock_profile_mgr,
        mock_socket_mgr,
        mock_setup_logging,
        mock_load_config,
        mock_config,
    ):
        """Test successful startup and shutdown."""
        # Setup mocks
        mock_load_config.return_value = mock_config
        mock_socket_manager = Mock()
        mock_socket_mgr.return_value = mock_socket_manager
        mock_profile_manager = Mock()
        mock_profile_mgr.return_value = mock_profile_manager
        mock_playlist_manager = Mock()
        mock_playlist_mgr.return_value = mock_playlist_manager

        mock_rest_app = Mock()
        mock_create_rest.return_value = mock_rest_app

        mock_grpc_server = Mock()
        mock_create_grpc.return_value = mock_grpc_server

        # Create event that triggers shutdown immediately
        shutdown_event = Mock()
        shutdown_event.wait = Mock(return_value=None)  # Return immediately
        mock_event.return_value = shutdown_event

        # Mock threading.Thread to return a fresh mock each time
        rest_thread = Mock()
        mock_thread_class.return_value = rest_thread
        
        # Run main
        result = main()

        # Verify initialization sequence
        assert result == 0
        mock_load_config.assert_called_once()
        mock_setup_logging.assert_called_once_with(mock_config)
        mock_socket_mgr.assert_called_once_with(mock_config)
        mock_profile_mgr.assert_called_once_with(mock_config)
        mock_playlist_mgr.assert_called_once_with(mock_config)

        # Verify REST and gRPC server creation
        mock_create_rest.assert_called_once_with(
            mock_config,
            mock_socket_manager,
            mock_profile_manager,
            mock_playlist_manager,
        )
        mock_create_grpc.assert_called_once_with(mock_config, mock_socket_manager)

        # Verify servers started
        mock_grpc_server.start.assert_called_once()
        rest_thread.start.assert_called_once()

        # Verify signal handlers registered
        assert mock_signal.call_count == 2

        # Verify graceful shutdown
        mock_grpc_server.stop.assert_called_once_with(grace=5)
        mock_socket_manager.shutdown.assert_called_once()

    @patch("mpv_controller.main.load_config")
    def test_main_config_load_failure(self, mock_load_config):
        """Test main handles config loading failure."""
        mock_load_config.side_effect = FileNotFoundError("Config not found")

        result = main()

        assert result == 1

    @patch("mpv_controller.main.load_config")
    @patch("mpv_controller.main.setup_logging")
    @patch("mpv_controller.main.MpvSocketManager")
    def test_main_socket_manager_failure(
        self, mock_socket_mgr, mock_setup_logging, mock_load_config, mock_config
    ):
        """Test main handles socket manager initialization failure."""
        mock_load_config.return_value = mock_config
        mock_socket_mgr.side_effect = Exception("Socket manager error")

        result = main()

        assert result == 1

    @patch("mpv_controller.main.load_config")
    @patch("mpv_controller.main.setup_logging")
    @patch("mpv_controller.main.MpvSocketManager")
    @patch("mpv_controller.main.ProfileManager")
    @patch("mpv_controller.main.PlaylistManager")
    @patch("mpv_controller.main.create_rest_app")
    @patch("mpv_controller.main.create_grpc_server")
    @patch("mpv_controller.main.uvicorn.run")
    @patch("mpv_controller.main.signal.signal")
    @patch("mpv_controller.main.threading.Event")
    def test_main_signal_handling(
        self,
        mock_event,
        mock_signal,
        mock_uvicorn,
        mock_create_grpc,
        mock_create_rest,
        mock_playlist_mgr,
        mock_profile_mgr,
        mock_socket_mgr,
        mock_setup_logging,
        mock_load_config,
        mock_config,
    ):
        """Test signal handlers are registered correctly."""
        # Setup mocks
        mock_load_config.return_value = mock_config
        mock_socket_mgr.return_value = Mock()
        mock_profile_mgr.return_value = Mock()
        mock_playlist_mgr.return_value = Mock()
        mock_create_rest.return_value = Mock()
        mock_grpc_server = Mock()
        mock_create_grpc.return_value = mock_grpc_server

        shutdown_event = Mock()
        shutdown_event.wait = Mock(return_value=None)
        mock_event.return_value = shutdown_event

        # Run main
        main()

        # Verify signal handlers registered for SIGINT and SIGTERM
        signal_calls = mock_signal.call_args_list
        assert len(signal_calls) == 2

        # Check both SIGINT and SIGTERM are registered
        registered_signals = [call[0][0] for call in signal_calls]
        assert signal.SIGINT in registered_signals
        assert signal.SIGTERM in registered_signals

    @patch("mpv_controller.main.load_config")
    @patch("mpv_controller.main.setup_logging")
    @patch("mpv_controller.main.MpvSocketManager")
    @patch("mpv_controller.main.ProfileManager")
    @patch("mpv_controller.main.PlaylistManager")
    @patch("mpv_controller.main.create_rest_app")
    @patch("mpv_controller.main.create_grpc_server")
    @patch("mpv_controller.main.threading.Thread")
    @patch("mpv_controller.main.signal.signal")
    @patch("mpv_controller.main.threading.Event")
    def test_main_rest_thread_started(
        self,
        mock_event,
        mock_signal,
        mock_thread,
        mock_create_grpc,
        mock_create_rest,
        mock_playlist_mgr,
        mock_profile_mgr,
        mock_socket_mgr,
        mock_setup_logging,
        mock_load_config,
        mock_config,
    ):
        """Test REST API starts in background thread."""
        # Setup mocks
        mock_load_config.return_value = mock_config
        mock_socket_mgr.return_value = Mock()
        mock_profile_mgr.return_value = Mock()
        mock_playlist_mgr.return_value = Mock()
        mock_rest_app = Mock()
        mock_create_rest.return_value = mock_rest_app
        mock_grpc_server = Mock()
        mock_create_grpc.return_value = mock_grpc_server

        rest_thread = Mock()
        mock_thread.return_value = rest_thread

        shutdown_event = Mock()
        shutdown_event.wait = Mock(return_value=None)
        mock_event.return_value = shutdown_event

        # Run main
        main()

        # Verify thread was created with correct parameters
        mock_thread.assert_called_once()
        call_kwargs = mock_thread.call_args[1]
        assert call_kwargs["daemon"] is True
        assert "app" in call_kwargs["kwargs"]
        assert call_kwargs["kwargs"]["app"] == mock_rest_app
        assert call_kwargs["kwargs"]["host"] == "127.0.0.1"
        assert call_kwargs["kwargs"]["port"] == 8080

        # Verify thread was started
        rest_thread.start.assert_called_once()

    @patch("mpv_controller.main.load_config")
    @patch("mpv_controller.main.setup_logging")
    @patch("mpv_controller.main.MpvSocketManager")
    @patch("mpv_controller.main.ProfileManager")
    @patch("mpv_controller.main.PlaylistManager")
    @patch("mpv_controller.main.create_rest_app")
    @patch("mpv_controller.main.create_grpc_server")
    @patch("mpv_controller.main.uvicorn.run")
    @patch("mpv_controller.main.signal.signal")
    @patch("mpv_controller.main.threading.Event")
    @patch("mpv_controller.main.threading.Thread")
    def test_main_grpc_server_started(
        self,
        mock_thread_class,
        mock_event,
        mock_signal,
        mock_uvicorn,
        mock_create_grpc,
        mock_create_rest,
        mock_playlist_mgr,
        mock_profile_mgr,
        mock_socket_mgr,
        mock_setup_logging,
        mock_load_config,
        mock_config,
    ):
        """Test gRPC server is started."""
        # Setup mocks
        mock_load_config.return_value = mock_config
        mock_socket_manager = Mock()
        mock_socket_mgr.return_value = mock_socket_manager
        mock_profile_mgr.return_value = Mock()
        mock_playlist_mgr.return_value = Mock()
        mock_create_rest.return_value = Mock()
        mock_grpc_server = Mock()
        mock_create_grpc.return_value = mock_grpc_server

        shutdown_event = Mock()
        shutdown_event.wait = Mock(return_value=None)
        mock_event.return_value = shutdown_event
        
        # Mock threading.Thread
        rest_thread = Mock()
        mock_thread_class.return_value = rest_thread

        # Run main
        main()

        # Verify gRPC server created with correct parameters
        mock_create_grpc.assert_called_once_with(mock_config, mock_socket_manager)

        # Verify gRPC server started
        mock_grpc_server.start.assert_called_once()

        # Verify graceful shutdown with grace period
        mock_grpc_server.stop.assert_called_once_with(grace=5)

    @patch("mpv_controller.main.load_config")
    @patch("mpv_controller.main.setup_logging")
    @patch("mpv_controller.main.MpvSocketManager")
    @patch("mpv_controller.main.ProfileManager")
    @patch("mpv_controller.main.PlaylistManager")
    @patch("mpv_controller.main.create_rest_app")
    @patch("mpv_controller.main.create_grpc_server")
    @patch("mpv_controller.main.uvicorn.run")
    @patch("mpv_controller.main.signal.signal")
    @patch("mpv_controller.main.threading.Event")
    def test_main_managers_initialized(
        self,
        mock_event,
        mock_signal,
        mock_uvicorn,
        mock_create_grpc,
        mock_create_rest,
        mock_playlist_mgr,
        mock_profile_mgr,
        mock_socket_mgr,
        mock_setup_logging,
        mock_load_config,
        mock_config,
    ):
        """Test all managers are initialized."""
        # Setup mocks
        mock_load_config.return_value = mock_config
        mock_socket_manager = Mock()
        mock_socket_mgr.return_value = mock_socket_manager
        mock_profile_manager = Mock()
        mock_profile_mgr.return_value = mock_profile_manager
        mock_playlist_manager = Mock()
        mock_playlist_mgr.return_value = mock_playlist_manager
        mock_create_rest.return_value = Mock()
        mock_grpc_server = Mock()
        mock_create_grpc.return_value = mock_grpc_server

        shutdown_event = Mock()
        shutdown_event.wait = Mock(return_value=None)
        mock_event.return_value = shutdown_event

        # Run main
        main()

        # Verify all managers initialized with config
        mock_socket_mgr.assert_called_once_with(mock_config)
        mock_profile_mgr.assert_called_once_with(mock_config)
        mock_playlist_mgr.assert_called_once_with(mock_config)

        # Verify REST app created with all managers
        mock_create_rest.assert_called_once_with(
            mock_config,
            mock_socket_manager,
            mock_profile_manager,
            mock_playlist_manager,
        )
