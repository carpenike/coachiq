"""
Device Discovery Service V2

Enhanced version using the new service pattern for better dependency management
and lifecycle control.
"""

import asyncio
import logging
import time
from typing import Any, Optional

import can

from backend.core.config import get_settings
from backend.core.service_patterns import BackgroundServiceBase, ServiceProxy
from backend.integrations.can.manager import can_tx_queue
from backend.services.device_discovery_service import DeviceInfo, PollRequest, NetworkTopology

logger = logging.getLogger(__name__)


class DeviceDiscoveryServiceV2(BackgroundServiceBase):
    """
    Enhanced device discovery service using the new service pattern.

    This service extends BackgroundServiceBase to provide better
    dependency management and lifecycle control.
    """

    def __init__(self, config: Any | None = None):
        """
        Initialize the device discovery service.

        Args:
            config: Configuration instance
        """
        # Initialize base with service proxies
        super().__init__(service_proxies={
            'can_service': ServiceProxy('can_service'),
            'app_state': ServiceProxy('app_state'),
            'feature_manager': ServiceProxy('feature_manager')
        })

        self.config = config or get_settings()

        # Discovery state
        self.topology = NetworkTopology()
        self.active_polls: dict[str, PollRequest] = {}
        self.poll_schedules: dict[str, dict[str, Any]] = {}
        self.discovery_active = False

        # Configuration from feature flags
        self.enable_device_polling = getattr(self.config, "device_discovery", {}).get(
            "enable_device_polling", True
        )

        self.polling_interval = getattr(self.config, "device_discovery", {}).get(
            "polling_interval", 30.0  # 30 seconds default
        )

        self.discovery_interval = getattr(self.config, "device_discovery", {}).get(
            "discovery_interval", 300.0  # 5 minutes default
        )

        self.enable_active_discovery = getattr(self.config, "device_discovery", {}).get(
            "enable_active_discovery", True
        )

        # RV-C specific configuration
        self.rvc_product_id_pgn = 0xFEEB  # Product ID PGN
        self.rvc_address_claim_pgn = 0xEE00  # Address claim PGN

        # Timing
        self._last_discovery = 0.0
        self._last_poll_check = 0.0

    async def _initialize_services(self) -> None:
        """Initialize service connections."""
        # Verify CAN service is available
        can_service = self.get_service('can_service')
        if not can_service:
            logger.warning("CAN service not available, device discovery will be limited")

        # Get app state for potential entity updates
        app_state = self.get_service('app_state')
        if app_state:
            logger.info("Connected to app state for entity updates")

    async def _cleanup_services(self) -> None:
        """Cleanup service connections."""
        # No specific cleanup needed for proxied services
        pass

    async def _run(self) -> None:
        """Main background task loop."""
        logger.info("Device discovery service started")

        while self._running:
            try:
                now = time.time()

                # Run periodic discovery
                if self.enable_active_discovery and (now - self._last_discovery) > self.discovery_interval:
                    await self._run_discovery()
                    self._last_discovery = now

                # Check poll schedules
                if self.enable_device_polling and (now - self._last_poll_check) > 1.0:
                    await self._check_poll_schedules()
                    self._last_poll_check = now

                # Update device status
                self._update_device_status()

                # Sleep briefly
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in device discovery loop: {e}")
                await asyncio.sleep(1.0)  # Back off on error

    async def _run_discovery(self) -> None:
        """Run active device discovery."""
        logger.info("Running device discovery scan")

        can_service = self.get_service('can_service')
        if not can_service:
            logger.warning("Cannot run discovery - CAN service not available")
            return

        # Send RV-C product ID request (broadcast)
        request_msg = can.Message(
            arbitration_id=0x18EAFF00,  # RV-C request PGN with broadcast destination
            data=[self.rvc_product_id_pgn & 0xFF,
                  (self.rvc_product_id_pgn >> 8) & 0xFF,
                  (self.rvc_product_id_pgn >> 16) & 0xFF],
            is_extended_id=True
        )

        try:
            await can_tx_queue.put(request_msg)
            logger.debug("Sent RV-C product ID discovery request")
        except Exception as e:
            logger.error(f"Failed to send discovery request: {e}")

        # Mark discovery time
        self.topology.last_discovery = time.time()

    async def _check_poll_schedules(self) -> None:
        """Check and execute scheduled polls."""
        now = time.time()

        for poll_id, schedule in self.poll_schedules.items():
            if not schedule.get("enabled", True):
                continue

            last_poll = schedule.get("last_poll", 0)
            interval = schedule.get("interval", 60.0)

            if (now - last_poll) >= interval:
                poll_request = schedule.get("request")
                if poll_request:
                    await self._execute_poll(poll_request)
                    schedule["last_poll"] = now

    async def _execute_poll(self, poll_request: PollRequest) -> None:
        """Execute a poll request."""
        can_service = self.get_service('can_service')
        if not can_service:
            return

        # Build CAN message for poll
        if poll_request.protocol == "rvc":
            # RV-C request format
            dest_addr = poll_request.target_address if poll_request.target_address is not None else 0xFF
            arbitration_id = 0x18EA0000 | (dest_addr << 8) | 0xF9  # Request PGN with source 0xF9

            data = [
                poll_request.target_pgn & 0xFF,
                (poll_request.target_pgn >> 8) & 0xFF,
                (poll_request.target_pgn >> 16) & 0xFF
            ]

            msg = can.Message(
                arbitration_id=arbitration_id,
                data=data,
                is_extended_id=True
            )

            try:
                await can_tx_queue.put(msg)
                poll_request.last_sent = time.time()
                logger.debug(f"Sent poll request for PGN {poll_request.target_pgn:04X}")
            except Exception as e:
                logger.error(f"Failed to send poll request: {e}")

    def _update_device_status(self) -> None:
        """Update device online/offline status based on last seen times."""
        now = time.time()
        offline_threshold = 60.0  # 60 seconds

        for device in self.topology.devices.values():
            if device.status == "online" and (now - device.last_seen) > offline_threshold:
                device.status = "offline"
                logger.info(f"Device {device.source_address:02X} marked offline")
            elif device.status == "offline" and (now - device.last_seen) <= offline_threshold:
                device.status = "online"
                logger.info(f"Device {device.source_address:02X} marked online")

    def process_can_message(self, msg: can.Message) -> None:
        """
        Process a CAN message for device discovery.

        This should be called by the CAN service when messages are received.

        Args:
            msg: CAN message to process
        """
        if not msg.is_extended_id:
            return  # RV-C uses extended IDs

        # Extract source address
        source_addr = msg.arbitration_id & 0xFF
        pgn = (msg.arbitration_id >> 8) & 0x1FFFF

        # Update device last seen
        if source_addr in self.topology.devices:
            self.topology.devices[source_addr].last_seen = time.time()
            self.topology.devices[source_addr].response_count += 1

        # Handle specific PGNs
        if pgn == self.rvc_product_id_pgn and len(msg.data) >= 8:
            # Product ID response
            self._handle_product_id(source_addr, msg.data)
        elif pgn == self.rvc_address_claim_pgn and len(msg.data) >= 8:
            # Address claim
            self._handle_address_claim(source_addr, msg.data)

    def _handle_product_id(self, source_addr: int, data: bytes) -> None:
        """Handle RV-C product ID message."""
        # Create or update device info
        if source_addr not in self.topology.devices:
            self.topology.devices[source_addr] = DeviceInfo(
                source_address=source_addr,
                protocol="rvc"
            )

        device = self.topology.devices[source_addr]

        # Parse product ID data (simplified)
        try:
            device.manufacturer = f"Mfg_{data[0]:02X}{data[1]:02X}"
            device.product_id = f"Product_{data[2]:02X}{data[3]:02X}"
            device.version = f"{data[4]}.{data[5]}"
            device.status = "online"

            logger.info(f"Discovered device {source_addr:02X}: {device.manufacturer} {device.product_id}")
        except Exception as e:
            logger.error(f"Failed to parse product ID: {e}")

    def _handle_address_claim(self, source_addr: int, data: bytes) -> None:
        """Handle RV-C address claim message."""
        # Create or update device info
        if source_addr not in self.topology.devices:
            self.topology.devices[source_addr] = DeviceInfo(
                source_address=source_addr,
                protocol="rvc"
            )

        device = self.topology.devices[source_addr]
        device.status = "online"

        # Could parse NAME field for more info
        logger.debug(f"Address claim from {source_addr:02X}")

    def add_poll_schedule(self, poll_id: str, poll_request: PollRequest,
                         interval: float = 60.0, enabled: bool = True) -> None:
        """
        Add a scheduled poll.

        Args:
            poll_id: Unique ID for this poll schedule
            poll_request: The poll request to execute
            interval: Polling interval in seconds
            enabled: Whether the schedule is enabled
        """
        self.poll_schedules[poll_id] = {
            "request": poll_request,
            "interval": interval,
            "enabled": enabled,
            "last_poll": 0.0
        }

        logger.info(f"Added poll schedule '{poll_id}' with {interval}s interval")

    def remove_poll_schedule(self, poll_id: str) -> None:
        """Remove a scheduled poll."""
        if poll_id in self.poll_schedules:
            del self.poll_schedules[poll_id]
            logger.info(f"Removed poll schedule '{poll_id}'")

    def get_topology(self) -> NetworkTopology:
        """Get current network topology."""
        return self.topology

    def get_device_info(self, source_addr: int) -> Optional[DeviceInfo]:
        """Get info for a specific device."""
        return self.topology.devices.get(source_addr)
