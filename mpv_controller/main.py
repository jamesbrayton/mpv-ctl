"""Main entry point for mpv-controller service."""

import logging
import signal
import sys
import threading
from pathlib import Path

import structlog
import uvicorn

from .config import load_config
from .grpc_service import create_grpc_server
from .playlist_manager import PlaylistManager
from .profile_manager import ProfileManager
from .rest_api import create_rest_app
from .socket_manager import MpvSocketManager


def setup_logging(config):
    """Configure structured logging.

    Args:
        config: Application configuration containing logging settings.
    """
    # Configure structlog for JSON output
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    
    # Add JSON or console renderer based on config
    if config.logging.log_file:
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Console output for stdout
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, config.logging.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # If log file is specified, also write there
    if config.logging.log_file:
        log_path = Path(config.logging.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)
        root_logger.setLevel(getattr(logging, config.logging.log_level))


def main():
    """Main entry point for the service."""
    logger = structlog.get_logger()
    
    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded", instances=len(config.mpv_instances))
        
        # Setup logging
        setup_logging(config)
        logger.info("Logging configured", level=config.logging.log_level)
        
        # Initialize socket manager
        socket_manager = MpvSocketManager(config)
        logger.info("Socket manager initialized")

        # Initialize profile manager
        profile_manager = ProfileManager(config)
        logger.info("Profile manager initialized")

        # Initialize playlist manager
        playlist_manager = PlaylistManager(config)
        logger.info("Playlist manager initialized")

        # Create REST app
        rest_app = create_rest_app(config, socket_manager, profile_manager, playlist_manager)
        logger.info("REST API configured", port=config.server.rest_port)
        
        # Create gRPC server
        grpc_server = create_grpc_server(config, socket_manager, profile_manager)
        logger.info("gRPC server configured", port=config.server.grpc_port)
        
        # Setup shutdown handler
        shutdown_event = threading.Event()
        
        def shutdown_handler(signum, frame):
            """Handle shutdown signals."""
            logger.info("Shutdown signal received", signal=signum)
            shutdown_event.set()
        
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
        
        # Start gRPC server in background thread
        grpc_server.start()
        logger.info("gRPC server started", port=config.server.grpc_port)
        
        # Start REST API in background thread
        rest_thread = threading.Thread(
            target=uvicorn.run,
            kwargs={
                "app": rest_app,
                "host": config.server.bind_address,
                "port": config.server.rest_port,
                "log_level": config.logging.log_level.lower(),
            },
            daemon=True,
        )
        rest_thread.start()
        logger.info("REST API started", port=config.server.rest_port)
        
        # Wait for shutdown signal
        logger.info("Service ready")
        shutdown_event.wait()
        
        # Graceful shutdown
        logger.info("Shutting down...")
        grpc_server.stop(grace=5)
        socket_manager.shutdown()
        logger.info("Shutdown complete")
        
        return 0
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error("Fatal error", error=str(e), exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
