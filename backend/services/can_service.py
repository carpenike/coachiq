"""
CAN Service

Handles business logic for CAN bus operations, including:
- CAN bus status and queue monitoring
- Raw CAN message sending
- CAN bus management
- Interface information retrieval

This service extracts CAN-related business logic from the API router layer.
"""

import asyncio
import logging
from typing import Any

import can

from backend.integrations.can.manager import buses, can_tx_queue

logger = logging.getLogger(__name__)


class CANService:
    """
    Service for managing CAN bus operations and monitoring.

    This service provides business logic for CAN operations while being
    agnostic to the presentation layer (HTTP, WebSocket, etc.).
    """

    def __init__(self, can_tracking_repository=None, system_state_repository=None):
        """
        Initialize the CAN service.

        Args:
            can_tracking_repository: Repository for CAN tracking operations
            system_state_repository: Repository for system state operations
        """
        self._can_tracking_repository = can_tracking_repository
        self._system_state_repository = system_state_repository

    async def get_queue_status(self) -> dict[str, Any]:
        """
        Get the current status of the CAN transmission queue.

        Returns:
            dict: Dictionary containing queue length and max size information.
        """
        return {
            "length": can_tx_queue.qsize(),
            "maxsize": can_tx_queue.maxsize or "unbounded",
        }

    async def get_interfaces(self) -> list[str]:
        """
        Get a list of active CAN interfaces.

        Returns:
            list: List of interface names that are currently active.
        """
        return list(buses.keys())

    async def get_interface_details(self) -> dict[str, dict[str, Any]]:
        """
        Get detailed information about all CAN interfaces.

        Returns:
            dict: Dictionary mapping interface names to their details.
        """
        interface_details = {}

        for interface_name, bus in buses.items():
            try:
                details = {
                    "name": interface_name,
                    "channel": getattr(bus, "channel", "unknown"),
                    "bustype": getattr(bus, "bus_type", "unknown"),
                    "state": "active" if bus else "inactive",
                }

                # Add additional bus-specific information if available
                if hasattr(bus, "get_stats"):
                    try:
                        stats = bus.get_stats()  # type: ignore[attr-defined]
                        details["stats"] = stats
                    except Exception:
                        pass

                interface_details[interface_name] = details

            except Exception as e:
                logger.warning(f"Failed to get details for interface {interface_name}: {e}")
                interface_details[interface_name] = {
                    "name": interface_name,
                    "error": str(e),
                    "state": "error",
                }

        return interface_details

    async def send_raw_message(
        self, arbitration_id: int, data: bytes, interface: str
    ) -> dict[str, Any]:
        """
        Send a raw CAN message to the specified interface.

        Args:
            arbitration_id: CAN arbitration ID
            data: Raw message data
            interface: Target CAN interface name

        Returns:
            dict: Dictionary with send status and details.

        Raises:
            ValueError: If interface is invalid or message parameters are wrong.
        """
        # Validate arbitration ID
        if not (0 <= arbitration_id <= 0x1FFFFFFF):
            msg = f"Invalid arbitration ID: {arbitration_id}"
            raise ValueError(msg)

        # Validate data length
        if len(data) > 8:
            msg = f"CAN data too long: {len(data)} bytes (max 8)"
            raise ValueError(msg)

        # Validate interface exists
        if interface not in buses:
            available_interfaces = list(buses.keys())
            msg = f"Interface '{interface}' not found. Available interfaces: {available_interfaces}"
            raise ValueError(msg)

        # Create CAN message
        msg = can.Message(
            arbitration_id=arbitration_id,
            data=data,
            is_extended_id=arbitration_id > 0x7FF,
        )

        try:
            # Queue the message for transmission
            await can_tx_queue.put((msg, interface))

            logger.info(
                f"Raw CAN message queued: ID=0x{arbitration_id:08X}, "
                f"data={data.hex().upper()}, interface={interface}"
            )

            return {
                "status": "queued",
                "arbitration_id": arbitration_id,
                "arbitration_id_hex": f"0x{arbitration_id:08X}",
                "data": data.hex().upper(),
                "interface": interface,
                "queue_size": can_tx_queue.qsize(),
            }

        except Exception as e:
            logger.error(f"Failed to queue raw CAN message: {e}")
            return {
                "status": "error",
                "error": str(e),
                "arbitration_id": arbitration_id,
                "arbitration_id_hex": f"0x{arbitration_id:08X}",
                "data": data.hex().upper(),
                "interface": interface,
            }

    async def get_bus_statistics(self) -> dict[str, Any]:
        """
        Get comprehensive statistics about CAN bus operations.

        Returns:
            dict: Dictionary containing bus statistics and metrics.
        """
        # Calculate message rate from recent CAN activity
        message_rate = self._calculate_message_rate()

        stats = {
            "interfaces": {},
            "queue": await self.get_queue_status(),
            "summary": {
                "total_interfaces": len(buses),
                "active_interfaces": len([b for b in buses.values() if b]),
                "queue_utilization": (
                    can_tx_queue.qsize() / can_tx_queue.maxsize if can_tx_queue.maxsize else 0
                ),
                "message_rate": message_rate,
                "total_messages": self._get_total_message_count(),
                "total_errors": 0,  # TODO: Implement error tracking
            },
        }

        # Get per-interface statistics
        for interface_name, bus in buses.items():
            interface_stats = {
                "name": interface_name,
                "active": bool(bus),
                "type": getattr(bus, "bus_type", "unknown") if bus else "unknown",
            }

            if bus:
                try:
                    # Try to get bus-specific statistics
                    if hasattr(bus, "get_stats"):
                        bus_stats = bus.get_stats()  # type: ignore[attr-defined]
                        interface_stats.update(bus_stats)
                except Exception as e:
                    interface_stats["stats_error"] = str(e)

            stats["interfaces"][interface_name] = interface_stats

        return stats

    def _calculate_message_rate(self) -> float:
        """
        Calculate the recent CAN message rate from app state.

        Returns:
            float: Messages per second over the last 10 seconds
        """
        try:
            if not self._can_tracking_repository:
                return 0.0

            # Get recent CAN sniffer entries from repository
            import time

            current_time = time.time()
            # TODO: Implement can_tracking_repository.get_recent_messages(since_timestamp)
            # For now, return 0 as we're removing app_state dependency
            return 0.0

        except Exception as e:
            logger.warning(f"Failed to calculate message rate: {e}")
            return 0.0

    def _get_total_message_count(self) -> int:
        """
        Get the total number of CAN messages seen.

        Returns:
            int: Total message count from app state
        """
        try:
            if not self._can_tracking_repository:
                return 0
            # TODO: Implement can_tracking_repository.get_total_message_count()
            # For now, return 0 as we're removing app_state dependency
            return 0
        except Exception as e:
            logger.warning(f"Failed to get total message count: {e}")
            return 0

    async def start_can_writer(self) -> None:
        """
        Start the CAN writer task.

        This method would typically be called during application startup
        to begin the CAN message transmission loop.
        """
        # CAN writer task is managed by the CAN subsystem directly
        logger.info("CAN writer is managed by the CAN subsystem")
        return

        # Import here to avoid circular imports
        from backend.integrations.can.manager import can_writer

        # Start the CAN writer task and store reference to prevent garbage collection
        # Pass repositories to can_writer if available, fall back to getting from app_state
        can_tracking_repo = self._can_tracking_repository
        system_state_repo = self._system_state_repository

        if not can_tracking_repo or not system_state_repo:
            # Try to get repositories from app_state's ServiceRegistry
            # Service registry should be injected directly, not through app_state
            service_registry = None  # TODO: Inject service registry as dependency
            if not can_tracking_repo:
                can_tracking_repo = service_registry.get_service("can_tracking_repository")
            if not system_state_repo:
                system_state_repo = service_registry.get_service("system_state_repository")

        can_writer_task = asyncio.create_task(
            can_writer(
                can_tracking_repository=can_tracking_repo, system_state_repository=system_state_repo
            )
        )
        self._can_writer_task = can_writer_task
        logger.info("CAN writer task started")

    async def shutdown(self) -> None:
        """
        Shutdown the CAN service and clean up background tasks.

        This method cancels and awaits the CAN writer task to ensure
        graceful shutdown without hanging background tasks.
        """
        logger.info("Shutting down CANService")

        # Cancel and await the CAN writer task if it exists
        if hasattr(self, "_can_writer_task") and self._can_writer_task:
            logger.info("Cancelling CAN writer task")
            self._can_writer_task.cancel()
            try:
                await self._can_writer_task
            except asyncio.CancelledError:
                logger.info("CAN writer task cancelled successfully")
            except Exception as e:
                logger.error(f"Error during CAN writer task cancellation: {e}")

        logger.info("CANService shutdown complete")

    async def send_message(
        self, arbitration_id: int, data: bytes, interface: str
    ) -> dict[str, Any]:
        """
        Send a CAN message (alias for send_raw_message for compatibility).

        Args:
            arbitration_id: CAN arbitration ID
            data: Raw message data
            interface: Target CAN interface name

        Returns:
            dict: Dictionary with send status and details.
        """
        return await self.send_raw_message(arbitration_id, data, interface)

    async def get_recent_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Get recent CAN messages captured on the bus.

        Args:
            limit: Maximum number of messages to return (default: 100)

        Returns:
            list: List of recent CAN messages with decoded information.

        Raises:
            ConnectionError: If no CAN interfaces are available or connected.
        """
        logger.debug(f"Requested {limit} recent CAN messages")

        # Check if we have any active CAN interfaces
        if not buses:
            msg = "No CAN interfaces are configured"
            raise ConnectionError(msg)

        # Check if any interfaces are actually connected/working
        active_interfaces = [name for name, bus in buses.items() if bus is not None]
        if not active_interfaces:
            msg = "No CAN interfaces are connected or available"
            raise ConnectionError(msg)

        # TODO: Implement actual message storage and retrieval
        # This could involve:
        # 1. Keeping a circular buffer of recent messages
        # 2. Storing messages in a database
        # 3. Reading from the CAN sniffer feature if available

        # For now, return empty list when interfaces are available but no messages yet
        return []

    async def initialize_can_interfaces(
        self, interfaces: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Initialize CAN interfaces.

        Args:
            interfaces: List of interface names to initialize. If None, uses all
                       configured interfaces from settings.

        Returns:
            dict: Dictionary with initialization status.
        """
        import os

        from can.exceptions import CanInterfaceNotImplementedError

        # Use configured interfaces if none provided
        if interfaces is None:
            from backend.core.config import get_settings

            settings = get_settings()
            interfaces = settings.can.all_interfaces
            logger.info(f"Using configured CAN interfaces: {interfaces}")

        # Get CAN settings for bustype and bitrate
        from backend.core.config import get_settings

        settings = get_settings()
        default_bustype = os.getenv("CAN_BUSTYPE", settings.can.bustype)
        default_bitrate = settings.can.bitrate

        initialized = []
        failed = []

        for interface_name in interfaces:
            try:
                if interface_name not in buses:
                    bus = can.interface.Bus(
                        channel=interface_name,
                        bustype=default_bustype,
                        bitrate=default_bitrate,
                    )
                    buses[interface_name] = bus
                    initialized.append(interface_name)
                    logger.info(
                        f"Initialized CAN interface: {interface_name} "
                        f"(bustype={default_bustype}, bitrate={default_bitrate})"
                    )
                else:
                    logger.info(f"CAN interface already initialized: {interface_name}")
                    initialized.append(interface_name)
            except CanInterfaceNotImplementedError as e:
                logger.error(f"CAN interface '{interface_name}' not implemented: {e}")
                failed.append({"interface": interface_name, "error": str(e)})
            except Exception as e:
                logger.error(f"Failed to initialize CAN interface '{interface_name}': {e}")
                failed.append({"interface": interface_name, "error": str(e)})

        return {
            "initialized": initialized,
            "failed": failed,
            "total_interfaces": len(buses),
        }

    async def startup(self) -> dict[str, Any]:
        """
        Initialize CAN service during application startup.

        This method ensures all configured CAN interfaces are properly
        initialized and the CAN writer task is started.

        Returns:
            dict: Dictionary with startup status and details.
        """
        logger.info("Starting CAN service")

        # Initialize all configured CAN interfaces
        initialization_result = await self.initialize_can_interfaces()

        # Start the CAN writer task if we have app_state
        if self._can_tracking_repository:
            await self.start_can_writer()
        else:
            logger.warning("Cannot start CAN writer without AppState dependency")

        logger.info(
            f"CAN service startup complete: "
            f"interfaces initialized={initialization_result['initialized']}, "
            f"failed={initialization_result['failed']}"
        )

        return {
            "status": "started",
            "interfaces": initialization_result,
            "writer_started": True,  # CAN writer is always managed by the subsystem
        }
