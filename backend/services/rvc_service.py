"""
RVC Service - Repository Pattern Implementation

Service for RV-C protocol-specific operations using repository pattern.
"""

import asyncio
import contextlib
import logging
from typing import Any

from backend.repositories import CANTrackingRepository, RVCConfigRepository

logger = logging.getLogger(__name__)


class RVCService:
    """
    Service for RV-C protocol-specific operations using repository pattern.

    This service handles:
    - RV-C protocol message translation
    - Instance tracking for multi-instance devices
    - Protocol-specific filters and routing

    Uses repositories directly, eliminating AppState dependency.
    """

    def __init__(
        self,
        rvc_config_repository: RVCConfigRepository,
        can_tracking_repository: CANTrackingRepository | None = None,
    ):
        """
        Initialize the RVC service with repository dependencies.

        Args:
            rvc_config_repository: Repository for RVC configuration data
            can_tracking_repository: Optional repository for CAN message tracking
        """
        self._rvc_config_repo = rvc_config_repository
        self._can_tracking_repo = can_tracking_repository
        self._running = False
        self._processing_task: asyncio.Task | None = None
        self._instance_mapping: dict[str, dict[int, str]] = {}
        self._message_handlers: dict[int, Any] = {}

        logger.info("RVCService initialized with repositories")

    async def start(self) -> None:
        """Start the RVC service and its background tasks."""
        if self._running:
            return

        logger.info("Starting RVC Service")

        # Start background processing task
        self._processing_task = asyncio.create_task(self._process_messages())

        # Only mark as running after task creation succeeds
        self._running = True

        # Initialize message handlers for different DGNs
        self._init_message_handlers()

        logger.info("RVC Service started successfully")

    async def stop(self) -> None:
        """Stop the RVC service and clean up resources."""
        if not self._running:
            return

        logger.info("Stopping RVC Service")
        self._running = False

        # Cancel and clean up background task
        if self._processing_task:
            self._processing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._processing_task
            self._processing_task = None

        logger.info("RVC Service stopped")

    def _init_message_handlers(self) -> None:
        """Initialize handlers for different RV-C message types."""
        # Map DGN numbers to handler methods
        # Example: self._message_handlers[0x1FFFF] = self._handle_temperature

    async def _process_messages(self) -> None:
        """
        Background task to process incoming RV-C messages.

        This continuously processes messages from the CAN queue and
        routes them to appropriate handlers based on DGN.
        """
        logger.info("RVC message processing task started")

        try:
            while self._running:
                # Wait for new messages from CAN tracking repository if available
                await asyncio.sleep(0.1)  # Placeholder for message queue processing

                # If we have CAN tracking repository, we could process messages from it
                if self._can_tracking_repo:
                    # Future implementation: process messages from repository
                    pass

        except asyncio.CancelledError:
            logger.info("RVC message processing task cancelled")
            raise
        except Exception as e:
            logger.exception("Error in RVC message processing task: %s", e)

    def decode_message(self, dgn: int, data: bytes, source: int) -> dict[str, Any] | None:
        """
        Decode an RV-C message into a structured format.

        Args:
            dgn: Data Group Number of the message
            data: Raw message bytes
            source: Source address

        Returns:
            Decoded message as a dictionary, or None if message can't be decoded
        """
        # Use RVC config repository to get DGN information
        dgn_hex = f"0x{dgn:05X}"
        dgn_name = self._rvc_config_repo.get_pgn_name(dgn_hex)

        if dgn_name:
            # Future implementation: Use repository data for decoding
            return {
                "dgn": dgn,
                "dgn_hex": dgn_hex,
                "dgn_name": dgn_name,
                "source": source,
                "data": data.hex(),
                # Additional decoded fields would go here
            }

        return None

    def get_instance_name(self, dgn: int, instance: int) -> str:
        """
        Get a human-readable name for a specific instance.

        Args:
            dgn: The Data Group Number
            instance: The instance number

        Returns:
            Human-readable instance name or default if not available
        """
        # First check local mapping
        local_name = self._instance_mapping.get(str(dgn), {}).get(instance)
        if local_name:
            return local_name

        # Then check repository for configured instance names
        # This could be expanded to use repository data for instance mappings
        return f"Instance {instance}"

    def register_instance_name(self, dgn: int, instance: int, name: str) -> None:
        """
        Register a human-readable name for a specific instance.

        Args:
            dgn: The Data Group Number
            instance: The instance number
            name: Human-readable name for this instance
        """
        dgn_str = str(dgn)
        if dgn_str not in self._instance_mapping:
            self._instance_mapping[dgn_str] = {}
        self._instance_mapping[dgn_str][instance] = name

    def get_health_status(self) -> dict[str, Any]:
        """
        Get service health status.

        Returns:
            Health status information
        """
        repo_health = self._rvc_config_repo.get_health_status()

        return {
            "service": "RVCService",
            "healthy": self._running and repo_health.get("healthy", False),
            "running": self._running,
            "repository_health": repo_health,
            "instance_mappings": len(self._instance_mapping),
            "message_handlers": len(self._message_handlers),
        }

    def get_rvc_configuration_summary(self) -> dict[str, Any]:
        """
        Get summary of RVC configuration.

        Returns:
            Configuration summary from repository
        """
        return self._rvc_config_repo.get_configuration_summary()

    def get_command_status_pair(self, command_dgn: str) -> str | None:
        """
        Get the status DGN for a command DGN.

        Args:
            command_dgn: Command DGN to look up

        Returns:
            Status DGN or None if not found
        """
        return self._rvc_config_repo.get_command_status_pair(command_dgn)


def create_rvc_service() -> RVCService:
    """
    Factory function for creating RVCService with dependencies.

    This would be registered with ServiceRegistry and automatically
    get the repositories injected.
    """
    # In real usage, this would get the repositories from ServiceRegistry
    # For now, we'll document the pattern
    raise NotImplementedError(
        "This factory should be registered with ServiceRegistry "
        "to get automatic dependency injection of repositories"
    )
