"""Socket manager for communicating with mpv instances."""

import json
import socket
import threading
import time
from pathlib import Path
from typing import Any, Optional

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from .config import Config, MpvInstance, SocketSettings
from .models import (
    CommandExecutionError,
    InstanceNotFoundError,
    MpvState,
    SocketConnectionError,
    SocketTimeoutError,
)

logger = structlog.get_logger()

# Standard properties to fetch after commands
STANDARD_PROPERTIES = ["pause", "time-pos", "duration", "filename", "volume"]


class MpvSocketManager:
    """Manages connections and communication with mpv instances via Unix sockets."""

    def __init__(self, config: Config):
        """Initialize the socket manager.

        Args:
            config: Application configuration containing mpv instances and socket settings.
        """
        self.config = config
        self.socket_settings = config.socket
        self.instances: dict[str, MpvInstance] = {
            instance.id: instance for instance in config.mpv_instances
        }
        
        # Availability cache
        # Note: Using cached availability checks for performance.
        # May need real-time checks for responsive dashboards in the future.
        self._availability_cache: dict[str, bool] = {}
        self._availability_lock = threading.Lock()
        self._stop_checker = threading.Event()
        
        # Start availability checker if caching is enabled
        if self.socket_settings.availability_check_interval > 0:
            self._checker_thread = threading.Thread(
                target=self._availability_checker_loop,
                daemon=True,
            )
            self._checker_thread.start()
            logger.info(
                "Started availability checker",
                interval=self.socket_settings.availability_check_interval,
            )

    def shutdown(self):
        """Shutdown the socket manager and background threads."""
        self._stop_checker.set()
        if hasattr(self, "_checker_thread"):
            self._checker_thread.join(timeout=5)
        logger.info("Socket manager shutdown complete")

    def _availability_checker_loop(self):
        """Background thread that periodically checks instance availability."""
        while not self._stop_checker.is_set():
            try:
                self._update_availability_cache()
            except Exception as e:
                logger.error("Error updating availability cache", error=str(e))
            
            # Sleep in small increments to allow quick shutdown
            for _ in range(self.socket_settings.availability_check_interval * 10):
                if self._stop_checker.is_set():
                    break
                time.sleep(0.1)

    def _update_availability_cache(self):
        """Update the availability status for all instances."""
        new_cache = {}
        for instance_id, instance in self.instances.items():
            try:
                # Try to connect to the socket
                sock_path = Path(instance.socket_path)
                available = sock_path.exists() and sock_path.is_socket()
                
                if available:
                    # Do a quick connection test
                    try:
                        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                            s.settimeout(1.0)
                            s.connect(instance.socket_path)
                            available = True
                    except (socket.error, OSError):
                        available = False
                
                new_cache[instance_id] = available
                logger.debug(
                    "Checked instance availability",
                    instance_id=instance_id,
                    available=available,
                )
            except Exception as e:
                logger.warning(
                    "Error checking instance availability",
                    instance_id=instance_id,
                    error=str(e),
                )
                new_cache[instance_id] = False
        
        with self._availability_lock:
            self._availability_cache = new_cache

    def get_instance_availability(self) -> dict[str, bool]:
        """Get availability status for all instances.

        Returns:
            Dictionary mapping instance IDs to availability status.
        """
        with self._availability_lock:
            return self._availability_cache.copy()

    def _validate_instance(self, instance_id: str) -> MpvInstance:
        """Validate that an instance exists.

        Args:
            instance_id: The instance ID to validate.

        Returns:
            The MpvInstance object.

        Raises:
            InstanceNotFoundError: If instance doesn't exist.
        """
        if instance_id not in self.instances:
            raise InstanceNotFoundError(instance_id)
        return self.instances[instance_id]

    def send_command(
        self,
        instance_id: str,
        command: list[Any],
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """Send a command to an mpv instance (single attempt, no retry).

        Args:
            instance_id: ID of the mpv instance.
            command: Command to send as a list (e.g., ["pause"]).
            timeout: Optional timeout override.

        Returns:
            Response from mpv as a dictionary.

        Raises:
            InstanceNotFoundError: If instance doesn't exist.
            SocketConnectionError: If unable to connect to socket.
            SocketTimeoutError: If operation times out.
            CommandExecutionError: If command execution fails.
        """
        instance = self._validate_instance(instance_id)
        timeout = timeout or self.socket_settings.read_timeout
        
        logger.debug(
            "Sending command",
            instance_id=instance_id,
            command=command,
            timeout=timeout,
        )
        
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect(instance.socket_path)
                
                # Send command
                command_json = json.dumps({"command": command})
                s.sendall(command_json.encode() + b"\n")
                
                # Receive response
                response_data = b""
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                    if b"\n" in response_data:
                        break
                
                response = json.loads(response_data.decode().strip())
                logger.debug(
                    "Command executed",
                    instance_id=instance_id,
                    command=command,
                    response=response,
                )
                return response
                
        except socket.timeout:
            raise SocketTimeoutError(instance_id, timeout)
        except (socket.error, OSError) as e:
            raise SocketConnectionError(instance_id, instance.socket_path, str(e))
        except json.JSONDecodeError as e:
            raise CommandExecutionError(
                instance_id,
                command,
                f"Invalid JSON response: {e}",
            )
        except Exception as e:
            raise CommandExecutionError(instance_id, command, str(e))

    def get_property(
        self,
        instance_id: str,
        property_name: str,
        timeout: Optional[float] = None,
    ) -> Any:
        """Get a property value from an mpv instance (with retry logic).

        Args:
            instance_id: ID of the mpv instance.
            property_name: Name of the property to get.
            timeout: Optional timeout override.

        Returns:
            The property value.

        Raises:
            InstanceNotFoundError: If instance doesn't exist.
            SocketConnectionError: If unable to connect after retries.
            SocketTimeoutError: If operation times out after retries.
            CommandExecutionError: If command execution fails.
        """
        instance = self._validate_instance(instance_id)
        timeout = timeout or self.socket_settings.read_timeout
        
        # Create retry decorator with configured settings
        retry_decorator = retry(
            retry=retry_if_exception_type(SocketTimeoutError),
            stop=stop_after_attempt(self.socket_settings.max_retries + 1),
            wait=wait_exponential(multiplier=self.socket_settings.backoff_multiplier)
            + (wait_random(0, 1) if self.socket_settings.jitter else wait_exponential(0)),
            reraise=True,
        )
        
        @retry_decorator
        def _get_property_with_retry():
            return self.send_command(
                instance_id,
                ["get_property", property_name],
                timeout,
            )
        
        try:
            response = _get_property_with_retry()
            if response.get("error") != "success":
                error_msg = response.get("error", "unknown error")
                raise CommandExecutionError(
                    instance_id,
                    ["get_property", property_name],
                    error_msg,
                )
            return response.get("data")
        except SocketTimeoutError:
            # Already the right exception type
            raise
        except SocketConnectionError:
            # Already the right exception type
            raise

    def get_standard_state(self, instance_id: str) -> MpvState:
        """Get the standard state properties from an mpv instance.

        Args:
            instance_id: ID of the mpv instance.

        Returns:
            MpvState object with current property values.
        """
        state_data = {}
        
        for prop_name in STANDARD_PROPERTIES:
            try:
                value = self.get_property(instance_id, prop_name)
                # Convert property names with hyphens to underscores for model
                model_key = prop_name.replace("-", "_")
                state_data[model_key] = value
            except Exception as e:
                logger.warning(
                    "Failed to get property",
                    instance_id=instance_id,
                    property=prop_name,
                    error=str(e),
                )
                # Property may not be available, continue with others
        
        return MpvState(**state_data)
