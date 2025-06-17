"""
CAN Service V2 - Repository Pattern Implementation

This is the migrated version of CANService that uses repositories directly
instead of accessing AppState. Part of Phase 2R.3 migration.
"""

import asyncio
import logging
from typing import Any, Optional

import can

from backend.integrations.can.manager import buses, can_tx_queue
from backend.repositories import CANTrackingRepository, RVCConfigRepository

logger = logging.getLogger(__name__)


class CANServiceV2:
    """
    Service for managing CAN bus operations using repository pattern.

    This service provides business logic for CAN operations using repositories
    directly, eliminating AppState dependency.
    """

    def __init__(
        self,
        can_tracking_repository: CANTrackingRepository,
        rvc_config_repository: RVCConfigRepository,
        controller_source_addr: int = 0xF9,
    ):
        """
        Initialize the CAN service with repository dependencies.

        Args:
            can_tracking_repository: Repository for CAN message tracking
            rvc_config_repository: Repository for RVC configuration data
            controller_source_addr: Controller's source address (default: 0xF9)
        """
        self._can_tracking_repo = can_tracking_repository
        self._rvc_config_repo = rvc_config_repository
        self._controller_source_addr = controller_source_addr
        self._can_writer_task: Optional[asyncio.Task] = None
        logger.info("CANServiceV2 initialized with repositories")

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
            raise ValueError(
                msg
            )

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
        Calculate the recent CAN message rate from repository.

        Returns:
            float: Messages per second over the last 10 seconds
        """
        try:
            # Get recent CAN sniffer entries from repository
            import time

            current_time = time.time()
            recent_messages = [
                entry
                for entry in self._can_tracking_repo.get_can_sniffer_log()
                if current_time - entry.get("timestamp", 0) <= 10.0  # Last 10 seconds
            ]

            # Calculate rate as messages per second
            if len(recent_messages) > 0:
                return len(recent_messages) / 10.0
            return 0.0

        except Exception as e:
            logger.warning(f"Failed to calculate message rate: {e}")
            return 0.0

    def _get_total_message_count(self) -> int:
        """
        Get the total number of CAN messages seen.

        Returns:
            int: Total message count from repository
        """
        try:
            return len(self._can_tracking_repo.get_can_sniffer_log())
        except Exception as e:
            logger.warning(f"Failed to get total message count: {e}")
            return 0

    def get_controller_source_addr(self) -> int:
        """
        Get the controller's source address.

        Returns:
            int: Controller source address
        """
        return self._controller_source_addr

    async def start_can_writer(self) -> None:
        """
        Start the CAN writer task.

        This method would typically be called during application startup
        to begin the CAN message transmission loop.
        """
        # Import here to avoid circular imports
        from backend.integrations.can.manager_v2 import can_writer_v2

        # Create a writer context with repositories
        writer_context = CANWriterContext(
            can_tracking_repo=self._can_tracking_repo,
            controller_source_addr=self._controller_source_addr,
        )

        # Start the CAN writer task and store reference to prevent garbage collection
        self._can_writer_task = asyncio.create_task(can_writer_v2(writer_context))
        logger.info("CAN writer task started with repository pattern")

    async def shutdown(self) -> None:
        """
        Shutdown the CAN service and clean up background tasks.

        This method cancels and awaits the CAN writer task to ensure
        graceful shutdown without hanging background tasks.
        """
        logger.info("Shutting down CANServiceV2")

        # Cancel and await the CAN writer task if it exists
        if self._can_writer_task:
            logger.info("Cancelling CAN writer task")
            self._can_writer_task.cancel()
            try:
                await self._can_writer_task
            except asyncio.CancelledError:
                logger.info("CAN writer task cancelled successfully")
            except Exception as e:
                logger.error(f"Error during CAN writer task cancellation: {e}")

        logger.info("CANServiceV2 shutdown complete")

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

        # Get recent messages from repository
        messages = self._can_tracking_repo.get_can_sniffer_log()

        # Return up to 'limit' most recent messages
        return list(messages)[-limit:] if messages else []

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
        logger.info("Starting CAN service V2")

        # Initialize all configured CAN interfaces
        initialization_result = await self.initialize_can_interfaces()

        # Start the CAN writer task
        await self.start_can_writer()

        logger.info(
            f"CAN service V2 startup complete: "
            f"interfaces initialized={initialization_result['initialized']}, "
            f"failed={initialization_result['failed']}"
        )

        return {
            "status": "started",
            "interfaces": initialization_result,
            "writer_started": True,
        }


class CANWriterContext:
    """
    Context object for CAN writer to access repositories without AppState.
    """

    def __init__(
        self,
        can_tracking_repo: CANTrackingRepository,
        controller_source_addr: int,
    ):
        """
        Initialize writer context.

        Args:
            can_tracking_repo: Repository for tracking CAN messages
            controller_source_addr: Controller's source address
        """
        self.can_tracking_repo = can_tracking_repo
        self.controller_source_addr = controller_source_addr

    def add_can_sniffer_entry(self, entry: dict[str, Any]) -> None:
        """Add a CAN sniffer entry."""
        self.can_tracking_repo.add_can_sniffer_entry(entry)

    def add_pending_command(self, entry: dict[str, Any]) -> None:
        """Add a pending command."""
        self.can_tracking_repo.add_pending_command(entry)

    def get_controller_source_addr(self) -> int:
        """Get controller source address."""
        return self.controller_source_addr


def create_can_service_v2() -> CANServiceV2:
    """
    Factory function for creating CANServiceV2 with dependencies.

    This would be registered with ServiceRegistry and automatically
    get the repositories injected.
    """
    # In real usage, this would get the repositories from ServiceRegistry
    # For now, we'll document the pattern
    raise NotImplementedError(
        "This factory should be registered with ServiceRegistry "
        "to get automatic dependency injection of repositories"
    )
