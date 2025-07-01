"""
CAN Bus Service - Clean Service Implementation

Service for CAN bus integration without Feature inheritance.
Uses repository injection pattern for all dependencies.
"""

import asyncio
import contextlib
import logging
import time
from typing import Any

from backend.core.config import get_settings
from backend.core.safety_interfaces import (
    SafeStateAction,
    SafetyAware,
    SafetyClassification,
    SafetyStatus,
)
from backend.integrations.rvc import BAMHandler, decode_payload, decode_product_id
from backend.repositories.can_tracking_repository import CANTrackingRepository
from backend.repositories.system_state_repository import SystemStateRepository

logger = logging.getLogger(__name__)


class CANBusService(SafetyAware):
    """
    Service that manages CAN bus integration.

    This is a clean service implementation without Feature inheritance,
    using repository injection for all dependencies.
    """

    def __init__(
        self,
        can_tracking_repository: CANTrackingRepository,
        system_state_repository: SystemStateRepository,
        can_anomaly_detector: Any | None = None,
    ):
        """
        Initialize the CAN bus service with repository dependencies.

        Args:
            can_tracking_repository: Repository for CAN message tracking
            system_state_repository: Repository for system state management
            can_anomaly_detector: Optional CAN anomaly detector for security monitoring
        """
        super().__init__(
            safety_classification=SafetyClassification.CRITICAL,
            safe_state_action=SafeStateAction.DISABLE,
        )
        self._can_tracking_repository = can_tracking_repository
        self._system_state_repository = system_state_repository

        self.settings = get_settings()
        self._running = False

        # Configuration - use settings from environment
        self.config = {
            "interfaces": self.settings.can.all_interfaces,
            "bustype": self.settings.can.bustype,
            "bitrate": self.settings.can.bitrate,
            "poll_interval": 0.1,  # seconds
            "simulate": False,  # TODO: This could also be a setting
        }

        # CAN bus related attributes
        self._listeners: list[Any] = []  # Will store CAN listeners or notifiers
        self._task: asyncio.Task | None = None
        self._simulation_task: asyncio.Task | None = None
        self._deduplicator = None  # Will be initialized in startup

        # RVC decoder data - will be loaded on startup
        self.decoder_map: dict[int, dict] = {}
        self.device_lookup: dict[tuple[str, str], dict] = {}
        self.status_lookup: dict[tuple[str, str], dict] = {}
        self.pgn_hex_to_name_map: dict[str, str] = {}
        self.raw_device_mapping: dict = {}
        self.entity_id_lookup: dict[str, dict] = {}

        # BAM handler for multi-packet messages
        self.bam_handler: BAMHandler | None = None

        # Pattern recognition engine for unknown messages
        self.pattern_engine = None

        # Anomaly detector for security monitoring (injected)
        self.anomaly_detector = can_anomaly_detector

        logger.info("CANBusService initialized with repositories")

    async def start(self) -> None:
        """Start the CAN bus service and initialize components."""
        if self._running:
            return

        logger.info("Starting CAN bus service")
        self._running = True

        try:
            # Initialize message deduplicator for bridged interfaces
            from backend.integrations.can.message_deduplicator import CANMessageDeduplicator

            self._deduplicator = CANMessageDeduplicator(window_ms=50)

            # Initialize BAM handler for multi-packet message support
            self.bam_handler = BAMHandler(session_timeout=30.0, max_concurrent_sessions=50)

            # Initialize pattern recognition engine for unknown message analysis
            try:
                from backend.integrations.can.pattern_recognition_engine import (
                    get_pattern_recognition_engine,
                )

                self.pattern_engine = get_pattern_recognition_engine()
                await self.pattern_engine.start()
                logger.info("Pattern recognition engine started")
            except Exception as e:
                logger.warning("Failed to initialize pattern recognition engine: %s", e)
                self.pattern_engine = None

            # Start anomaly detector if provided
            if self.anomaly_detector:
                try:
                    await self.anomaly_detector.start()
                    logger.info("CAN anomaly detector started")
                except Exception as e:
                    logger.warning("Failed to start anomaly detector: %s", e)
                    self.anomaly_detector = None

            # Load RVC decoder configuration
            await self._load_rvc_configuration()

            # Start CAN bus operation
            if self.config["simulate"]:
                # Start simulation mode
                logger.info("Starting CAN bus simulation mode")
                self._simulation_task = asyncio.create_task(self._simulate_can_messages())
            else:
                # Start real CAN bus listeners
                await self._start_can_listeners()

            logger.info("CAN bus service started successfully")

        except Exception as e:
            logger.error("Failed to start CAN bus service: %s", e)
            self._running = False
            raise

    async def stop(self) -> None:
        """Stop the CAN bus service and clean up resources."""
        if not self._running:
            return

        logger.info("Stopping CAN bus service")
        self._running = False

        # Cancel simulation task if running
        if self._simulation_task:
            self._simulation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._simulation_task

        # Stop pattern recognition engine
        if self.pattern_engine:
            try:
                await self.pattern_engine.stop()
                logger.info("Pattern recognition engine stopped")
            except Exception as e:
                logger.error("Error stopping pattern recognition engine: %s", e)

        # Stop anomaly detector
        if self.anomaly_detector:
            try:
                await self.anomaly_detector.stop()
                logger.info("CAN anomaly detector stopped")
            except Exception as e:
                logger.error("Error stopping anomaly detector: %s", e)

        # Cleanup CAN bus listeners
        await self._cleanup_can_listeners()

        logger.info("CAN bus service stopped")

    async def emergency_stop(self, reason: str) -> None:
        """Emergency stop implementation."""
        logger.critical(f"CANBusService emergency stop: {reason}")
        self._set_emergency_stop_active(True)
        self._running = False

        # Stop all listeners and tasks
        await self._cleanup_can_listeners()

        if self._simulation_task:
            self._simulation_task.cancel()

        if self.pattern_engine:
            await self.pattern_engine.stop()

        if self.anomaly_detector:
            await self.anomaly_detector.stop()

    async def get_safety_status(self) -> SafetyStatus:
        """Get current safety status."""
        if self._emergency_stop_active:
            return SafetyStatus.EMERGENCY_STOP
        if not self._running:
            return SafetyStatus.UNSAFE
        return SafetyStatus.SAFE

    def get_health_status(self) -> dict[str, Any]:
        """
        Get service health status.

        Returns:
            Health status information
        """
        try:
            if self._running:
                return {
                    "service": "CANBusService",
                    "healthy": True,
                    "running": True,
                    "mode": "simulation" if self.config["simulate"] else "production",
                    "interfaces": self.config["interfaces"],
                    "decoders_loaded": len(self.decoder_map),
                    "device_mappings": len(self.device_lookup),
                }
            return {
                "service": "CANBusService",
                "healthy": False,
                "running": False,
                "error": "Service not running",
            }
        except Exception as e:
            logger.error("Error getting CAN bus service health: %s", e)
            return {
                "service": "CANBusService",
                "healthy": False,
                "running": self._running,
                "error": str(e),
            }

    async def get_service_info(self) -> dict[str, Any]:
        """
        Get service information and current status.

        Returns:
            Service information
        """
        return {
            "name": "CAN Bus Service",
            "description": "CAN bus integration for message processing and entity updates",
            "version": "2.0.0",
            "status": "running" if self._running else "stopped",
            "configuration": {
                "interfaces": self.config["interfaces"],
                "bustype": self.config["bustype"],
                "bitrate": self.config["bitrate"],
                "simulate": self.config["simulate"],
            },
            "statistics": {
                "decoders_loaded": len(self.decoder_map),
                "device_mappings": len(self.device_lookup),
                "active_listeners": len(self._listeners),
            },
        }

    async def _load_rvc_configuration(self) -> None:
        """Load RVC decoder configuration."""
        try:
            logger.info("Loading RVC decoder configuration")

            # Convert Path objects to strings if they exist
            spec_path = str(self.settings.rvc_spec_path) if self.settings.rvc_spec_path else None
            map_path = (
                str(self.settings.rvc_coach_mapping_path)
                if self.settings.rvc_coach_mapping_path
                else None
            )

            logger.info("Using RVC spec path: %s", spec_path)
            logger.info("Using device mapping path: %s", map_path)

            # Use structured configuration loader
            from backend.integrations.rvc import load_config_data_v2

            rvc_config = load_config_data_v2(
                rvc_spec_path_override=spec_path, device_mapping_path_override=map_path
            )

            # Extract values from structured config
            self.decoder_map = rvc_config.dgn_dict
            self.entity_id_lookup = rvc_config.inst_map  # entity ID to config lookup
            self.pgn_hex_to_name_map = rvc_config.pgn_hex_to_name_map  # PGN hex to name mapping

            # Extract additional lookup tables from mapping dict
            # This is needed for device and status lookups
            for (dgn_hex, instance), device_config in rvc_config.mapping_dict.items():
                self.device_lookup[(dgn_hex.upper(), str(instance))] = device_config

            # Copy entity map to device lookup for compatibility
            for (dgn_hex, instance), device_config in rvc_config.entity_map.items():
                self.device_lookup[(dgn_hex.upper(), str(instance))] = device_config

            # Build status lookup from device lookup for devices with status_dgn
            for (_dgn_hex, instance), device_config in self.device_lookup.items():
                status_dgn = device_config.get("status_dgn")
                if status_dgn:
                    self.status_lookup[(status_dgn.upper(), str(instance))] = device_config

            # Store raw device mapping for unmapped entry suggestions
            self.raw_device_mapping = rvc_config.mapping_dict  # This is the device_mapping dict

            logger.info(
                "Loaded RVC configuration: %d decoders, %d device mappings",
                len(self.decoder_map),
                len(self.device_lookup),
            )

        except Exception as e:
            logger.error("Failed to load RVC decoder configuration: %s", e)
            logger.warning("CAN bus service will run without RVC decoding capabilities")

    async def _start_can_listeners(self) -> None:
        """Start real CAN bus listeners."""
        try:
            # Import CAN interface manager directly
            import can

            from backend.integrations.can.manager import buses

            interfaces_config = self.config["interfaces"]
            bustype = self.config["bustype"]
            bitrate = self.config["bitrate"]

            logger.info(
                "Setting up CAN bus listeners: interfaces=%s, bustype=%s, bitrate=%s",
                interfaces_config,
                bustype,
                bitrate,
            )

            # Initialize CAN interfaces directly
            failed_interfaces = []
            for interface in interfaces_config:
                try:
                    # Create the bus directly
                    bus = can.interface.Bus(channel=interface, bustype=bustype, bitrate=bitrate)
                    buses[interface] = bus
                    logger.info(f"Initialized CAN interface: {interface}")
                except Exception as e:
                    logger.error(f"Failed to initialize interface {interface}: {e}")
                    failed_interfaces.append(interface)

            initialized_count = len(buses)
            logger.info(
                "CAN interface initialization complete: initialized=%s, failed=%s",
                initialized_count,
                failed_interfaces,
            )

            if failed_interfaces:
                logger.warning(
                    "Some CAN interfaces failed to initialize: %s",
                    failed_interfaces,
                )

            # CAN writer task is started by the CAN service startup method

            # Set up CAN message listeners for each active interface
            await self._setup_can_listeners()

        except ImportError:
            logger.warning(
                "python-can package not available. CAN bus service will not start. "
                "Install with 'poetry add python-can'."
            )
            # Fall back to simulation mode
            logger.info("Falling back to CAN bus simulation mode")
            self._simulation_task = asyncio.create_task(self._simulate_can_messages())
        except Exception as e:
            logger.error("Failed to start CAN bus listeners: %s", e, exc_info=True)
            raise

    async def _setup_can_listeners(self) -> None:
        """
        Set up CAN message listeners for all active interfaces using python-can's asyncio support.
        """
        try:
            import can

            from backend.integrations.can.manager import buses

            if not buses:
                logger.warning("No active CAN buses found, cannot set up listeners")
                return

            logger.info(
                "Setting up CAN listeners for %d interfaces: %s", len(buses), list(buses.keys())
            )

            for interface_name, bus in buses.items():
                try:
                    # Create AsyncBufferedReader for non-blocking message reception
                    # Limit buffer to prevent memory buildup (1000 messages max)
                    reader = can.AsyncBufferedReader()  # type: ignore

                    # Create Notifier with asyncio event loop integration
                    loop = asyncio.get_running_loop()
                    notifier = can.Notifier(bus, [reader], loop=loop)  # type: ignore

                    # Create a listener task for this interface
                    listener_task = asyncio.create_task(
                        self._can_listener_task(interface_name, reader),
                        name=f"can_listener_{interface_name}",
                    )

                    # Store both the task and notifier for cleanup
                    self._listeners.append(
                        {
                            "task": listener_task,
                            "notifier": notifier,
                            "reader": reader,
                            "interface": interface_name,
                        }
                    )

                    logger.info("Started CAN listener for interface: %s", interface_name)

                except Exception as e:
                    logger.error("Failed to start CAN listener for %s: %s", interface_name, e)

        except Exception as e:
            logger.error("Failed to set up CAN listeners: %s", e, exc_info=True)

    async def _cleanup_can_listeners(self) -> None:
        """Cleanup CAN bus listeners."""
        for listener_info in self._listeners:
            try:
                if isinstance(listener_info, dict):
                    # New dictionary structure with task, notifier, reader
                    interface = listener_info.get("interface", "unknown")

                    # Cancel the async task
                    task = listener_info.get("task")
                    if task and isinstance(task, asyncio.Task):
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task

                    # Stop the notifier
                    notifier = listener_info.get("notifier")
                    if notifier:
                        notifier.stop()

                    logger.debug("Cleaned up CAN listener for %s", interface)

                elif isinstance(listener_info, asyncio.Task):
                    # Legacy task-only structure (for compatibility)
                    listener_info.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await listener_info

            except Exception as e:
                logger.error("Error cleaning up CAN listener: %s", e)

        self._listeners = []

    async def _can_listener_task(self, interface_name: str, reader) -> None:
        """
        Async task to continuously listen for CAN messages using AsyncBufferedReader.

        Args:
            interface_name: Name of the CAN interface (e.g., 'can0', 'can1')
            reader: can.AsyncBufferedReader object for non-blocking message reception
        """
        logger.info("CAN listener started for interface: %s", interface_name)

        try:
            while self._running:
                try:
                    # Non-blocking async message reception
                    message = await reader.get_message()

                    if message is not None:
                        # Send to CAN tools first (filter may block the message)
                        should_process = await self._send_to_can_tools(message, interface_name)

                        # Process the received message if not blocked by filter
                        if should_process is not False:
                            await self._process_received_message(message, interface_name)

                except Exception as e:
                    if self._running:  # Only log errors if we're still supposed to be running
                        logger.error("Error receiving CAN message on %s: %s", interface_name, e)
                    break

        except asyncio.CancelledError:
            logger.info("CAN listener for %s cancelled", interface_name)
            raise
        except Exception as e:
            logger.error("CAN listener for %s failed: %s", interface_name, e, exc_info=True)
        finally:
            logger.info("CAN listener for %s stopped", interface_name)

    async def _send_to_can_tools(self, message, interface_name: str) -> bool:
        """
        Send CAN message to optional analysis tools through ServiceRegistry.

        Args:
            message: python-can Message object
            interface_name: Name of the interface that received the message
        """
        try:
            # Get ServiceRegistry through dependency injection
            from backend.core.dependencies import get_service_registry

            try:
                service_registry = get_service_registry()
            except Exception:
                # ServiceRegistry not available yet
                return True

            # Send to CAN recorder if available
            try:
                recorder = service_registry.get_service("can_bus_recorder")
                if recorder and hasattr(recorder, "recording_state"):
                    # Check if recording is active
                    from backend.integrations.can.can_bus_recorder import RecordingState

                    if recorder.recording_state == RecordingState.RECORDING:
                        await recorder.record_message(
                            can_id=message.arbitration_id,
                            data=message.data,
                            interface=interface_name,
                            is_extended=message.is_extended_id,
                            is_error=message.is_error_frame,
                            is_remote=message.is_remote_frame,
                        )
            except Exception as e:
                logger.debug("Failed to send to CAN recorder: %s", e)

            # Send to protocol analyzer if available
            try:
                analyzer = service_registry.get_service("can_protocol_analyzer")
                if analyzer:
                    await analyzer.analyze_message(
                        can_id=message.arbitration_id,
                        data=message.data,
                        interface=interface_name,
                    )
            except Exception as e:
                logger.debug("Failed to send to protocol analyzer: %s", e)

            # Send to message filter if available
            try:
                message_filter = service_registry.get_service("can_message_filter")
                if message_filter:
                    # Prepare message dict for filter
                    filter_msg = {
                        "can_id": message.arbitration_id,
                        "data": message.data,
                        "interface": interface_name,
                        "timestamp": time.time(),
                        "is_extended": message.is_extended_id,
                    }

                    # Process through filter
                    should_pass = await message_filter.process_message(filter_msg)

                    # If message is blocked, don't process further
                    if not should_pass:
                        logger.debug("Message %08X blocked by filter", message.arbitration_id)
                        # Note: Caller should check return value to skip processing
                        return False
            except Exception as e:
                logger.debug("Failed to send to message filter: %s", e)

            return True  # Message should continue processing

        except Exception as e:
            logger.debug("Error sending to CAN tools: %s", e)
            return True  # Don't block message processing on tool errors

    async def _process_received_message(self, message, interface_name: str) -> None:
        """
        Process a received CAN message.

        Args:
            message: python-can Message object
            interface_name: Name of the interface that received the message
        """
        try:
            # Check for duplicate messages when using bridged interfaces
            if self._deduplicator and self._deduplicator.is_duplicate(
                message.arbitration_id, message.data
            ):
                logger.debug(
                    "Ignoring duplicate message %08X on %s", message.arbitration_id, interface_name
                )
                return

            # Log the received message
            logger.debug(
                "CAN RX: %s ID: %08X Data: %s DLC: %d",
                interface_name,
                message.arbitration_id,
                message.data.hex().upper(),
                message.dlc,
            )

            # Add to CAN sniffer for monitoring
            await self._add_sniffer_entry(message, interface_name, "rx")

            # Convert python-can Message to dictionary format expected by _process_message
            msg_dict = {
                "arbitration_id": message.arbitration_id,
                "data": message.data,
                "timestamp": time.time(),
                "interface": interface_name,
                "dlc": message.dlc,
                "is_extended": message.is_extended_id,
            }

            # Run anomaly detection first (security check)
            if self.anomaly_detector:
                try:
                    anomaly_result = await self.anomaly_detector.analyze_message(
                        message.arbitration_id, message.data, msg_dict["timestamp"]
                    )

                    # Check if message should be blocked due to security concerns
                    if "message_blocked" in anomaly_result.get("actions_taken", []):
                        logger.warning(
                            "Blocked message due to security policy: %08X", message.arbitration_id
                        )
                        return  # Don't process blocked messages further

                    # Log any anomalies detected
                    if anomaly_result.get("anomalies_detected"):
                        logger.debug(
                            "Anomalies detected in message %08X: %d alerts",
                            message.arbitration_id,
                            len(anomaly_result["anomalies_detected"]),
                        )

                except Exception as e:
                    logger.debug("Error in anomaly detection: %s", e)

            # Process the message through the RV-C decoder
            await self._process_message(msg_dict)

        except Exception as e:
            logger.error("Error processing received CAN message: %s", e, exc_info=True)

    async def _add_sniffer_entry(self, message, interface_name: str, direction: str) -> None:
        """Add a CAN message to the sniffer entries for monitoring."""
        try:
            sniffer_entry = {
                "timestamp": time.time(),
                "interface": interface_name,
                "can_id": f"{message.arbitration_id:08X}",
                "data": message.data.hex().upper(),
                "dlc": message.dlc,
                "is_extended": message.is_extended_id,
                "direction": direction,
                "decoded": None,  # Will be filled by _process_message if decoded
                "origin": "other",  # RX messages are from other devices
            }

            self._can_tracking_repository.add_can_sniffer_entry(sniffer_entry)

        except Exception as e:
            logger.error("Error adding sniffer entry: %s", e)

    async def _process_message(self, msg: dict[str, Any]) -> None:
        """
        Process an incoming CAN message.

        This method processes the message using RVC decoding for logging and analysis.

        Args:
            msg: The CAN message as a dictionary with keys like arbitration_id, data, etc.
        """
        try:
            # Extract message data
            arbitration_id = msg.get("arbitration_id")
            data = msg.get("data")

            if arbitration_id is None or data is None:
                logger.warning("Received invalid CAN message")
                return

            # Convert data to bytes if it's not already
            if isinstance(data, str):
                data = bytes.fromhex(data)
            elif isinstance(data, bytearray):
                data = bytes(data)  # Convert bytearray to bytes
            elif not isinstance(data, bytes):
                logger.warning("Unexpected data type: %s", type(data))
                return

            # Log the message at debug level
            logger.debug("CAN message received: id=0x%x, data=%s", arbitration_id, data.hex())

            # Extract PGN and source address from arbitration ID
            # RV-C uses 29-bit extended CAN IDs: Priority (3 bits) + PGN (18 bits) + Source (8 bits)
            pgn = (arbitration_id >> 8) & 0x3FFFF
            source_address = arbitration_id & 0xFF

            # Check if this is a BAM transport protocol message
            if self.bam_handler and pgn in [BAMHandler.TP_CM_PGN, BAMHandler.TP_DT_PGN]:
                # Process through BAM handler
                result = self.bam_handler.process_frame(pgn, data, source_address)

                if result:
                    # We have a complete multi-packet message
                    target_pgn, reassembled_data = result

                    # Handle specific multi-packet PGNs
                    if target_pgn == 0x1FEF2:  # Product Identification
                        decoded = decode_product_id(reassembled_data)
                        logger.info("Decoded Product ID: %s", decoded)
                        # TODO: Update entity with product information
                    else:
                        logger.debug("Reassembled multi-packet message for PGN %05X", target_pgn)

                # Don't process transport protocol messages further
                return

            # Try to decode the message using RVC decoder
            if self.decoder_map and arbitration_id in self.decoder_map:
                try:
                    entry = self.decoder_map[arbitration_id]
                    decoded_data, raw_data = decode_payload(entry, data)

                    # Extract DGN and instance for device lookup
                    dgn_hex = entry.get("dgn_hex")
                    instance = raw_data.get("instance") if isinstance(raw_data, dict) else None

                    logger.debug(
                        "Decoded CAN message: DGN=%s, instance=%s, decoded=%s, raw=%s",
                        dgn_hex,
                        instance,
                        decoded_data,
                        raw_data,
                    )

                    # Check if this maps to a known device/entity
                    if dgn_hex and instance is not None:
                        device_key = (dgn_hex.upper(), str(instance))
                        device_config = self.device_lookup.get(device_key)

                        if device_config:
                            entity_id = device_config.get("entity_id")
                            if entity_id:
                                logger.debug("Mapped to entity: %s", entity_id)
                                # Update entity state with the decoded CAN message
                                await self._update_entity_from_can_message(
                                    entity_id, device_config, decoded_data, raw_data, msg
                                )
                        else:
                            logger.debug("Unmapped device: %s:%s", dgn_hex, instance)
                            # Analyze unmapped but decodable message for patterns
                            if self.pattern_engine:
                                try:
                                    pattern_analysis = await self.pattern_engine.analyze_message(
                                        arbitration_id, data, msg.get("timestamp", time.time())
                                    )
                                    logger.debug(
                                        "Pattern analysis for unmapped %s:%s: %s",
                                        dgn_hex,
                                        instance,
                                        pattern_analysis,
                                    )
                                except Exception as pattern_error:
                                    logger.debug("Pattern analysis error: %s", pattern_error)

                except Exception as decode_error:
                    logger.error("Error decoding CAN message: %s", decode_error)
            else:
                logger.debug("No decoder found for arbitration ID 0x%x", arbitration_id)
                # Analyze completely unknown message for patterns
                if self.pattern_engine:
                    try:
                        pattern_analysis = await self.pattern_engine.analyze_message(
                            arbitration_id, data, msg.get("timestamp", time.time())
                        )
                        logger.debug(
                            "Pattern analysis for unknown 0x%X: %s",
                            arbitration_id,
                            pattern_analysis,
                        )
                    except Exception as pattern_error:
                        logger.debug("Pattern analysis error: %s", pattern_error)

        except Exception as e:
            logger.error("Error processing CAN message: %s", e)

    async def _update_entity_from_can_message(
        self,
        entity_id: str,
        device_config: dict[str, Any],
        decoded_data: dict[str, Any],
        raw_data: dict[str, Any],
        msg: dict[str, Any],
    ) -> None:
        """
        Update entity state based on a decoded CAN message.

        Args:
            entity_id: The entity ID to update
            device_config: Device configuration from the mapping
            decoded_data: Decoded signal values from the CAN message
            raw_data: Raw signal values from the CAN message
            msg: Original CAN message dictionary
        """
        try:
            # Get ServiceRegistry
            from backend.core.dependencies import get_service_registry

            try:
                service_registry = get_service_registry()
            except Exception:
                logger.warning("ServiceRegistry not available for entity update")
                return
            entity_manager_service = service_registry.get_service("entity_manager")
            if entity_manager_service is None:
                logger.warning("EntityManagerService not found in ServiceRegistry")
                return

            entity_manager = entity_manager_service.get_entity_manager()
            entity = entity_manager.get_entity(entity_id)

            if not entity:
                logger.warning("Entity %s not found in entity manager", entity_id)
                return

            # Build state update payload
            timestamp = msg.get("timestamp", time.time())

            # Start with the decoded and raw data
            payload = {
                "entity_id": entity_id,
                "timestamp": timestamp,
                "value": decoded_data or {},
                "raw": raw_data or {},
            }

            # Add configuration fields from device config
            for config_field in [
                "suggested_area",
                "device_type",
                "capabilities",
                "friendly_name",
                "groups",
            ]:
                if config_field in device_config:
                    payload[config_field] = device_config[config_field]

            # Handle light-specific state updates
            if device_config.get("device_type") == "light":
                await self._update_light_state(payload, decoded_data, raw_data)

            # Update the entity state
            updated_entity = entity_manager.update_entity_state(entity_id, payload)

            if updated_entity:
                logger.debug("Updated entity %s state from CAN message", entity_id)

                # Broadcast the update via WebSocket
                # Broadcast entity update via WebSocket
                websocket_service = service_registry.get_service("websocket_service")
                if websocket_service:
                    broadcast_data = {
                        "type": "entity_update",
                        "entity_id": entity_id,
                        "data": updated_entity.to_dict(),
                    }
                    await websocket_service.broadcast_data(broadcast_data)

                # Check if this completes a pending command (for optimistic UI updates)
                await self._check_pending_command_completion(entity_id, payload)
            else:
                logger.warning("Failed to update entity %s state", entity_id)

        except Exception as e:
            logger.error(
                "Error updating entity %s from CAN message: %s", entity_id, e, exc_info=True
            )

    async def _update_light_state(
        self, payload: dict[str, Any], decoded_data: dict[str, Any], raw_data: dict[str, Any]
    ) -> None:
        """
        Update light-specific state fields based on decoded CAN data.

        Args:
            payload: The payload being built for entity state update
            decoded_data: Decoded signal values
            raw_data: Raw signal values
        """
        try:
            # Extract operating status (brightness level in CAN terms)
            operating_status = raw_data.get("operating_status", 0)

            if isinstance(operating_status, str):
                operating_status = int(operating_status)

            # Convert CAN operating status (0-200) to UI brightness (0-100)
            brightness_pct = int((operating_status / 200.0) * 100)
            brightness_pct = max(0, min(100, brightness_pct))  # Clamp to 0-100

            # Determine on/off state
            is_on = operating_status > 0
            state_str = "on" if is_on else "off"

            # Update payload with light-specific fields
            payload.update(
                {
                    "state": state_str,
                    "brightness": brightness_pct,
                }
            )

            logger.debug(
                "Light state: operating_status=%s, brightness=%d%%, state=%s",
                operating_status,
                brightness_pct,
                state_str,
            )

        except Exception as e:
            logger.error("Error processing light state: %s", e)
            # Fallback to safe defaults
            payload.update(
                {
                    "state": "off",
                    "brightness": 0,
                }
            )

    async def _check_pending_command_completion(
        self, entity_id: str, payload: dict[str, Any]
    ) -> None:
        """
        Check if this state update completes a pending command.

        Args:
            entity_id: The entity that was updated
            payload: The state update payload
        """
        try:
            # Get the timestamp from the payload
            update_timestamp = payload.get("timestamp", time.time())

            # Check if there are any pending commands for this entity
            # This will help correlate commands with responses for UI feedback
            pending_commands = [
                cmd
                for cmd in self._can_tracking_repository._pending_commands
                if cmd.get("entity_id") == entity_id
                and (update_timestamp - cmd.get("timestamp", 0)) < 5.0  # Within 5 seconds
            ]

            if pending_commands:
                logger.debug(
                    "Found %d pending commands for %s, state update may complete them",
                    len(pending_commands),
                    entity_id,
                )

                # Mark commands as potentially completed
                # The actual command correlation is handled by the try_group_response method
                for _cmd in pending_commands:
                    # Need to get known pairs from somewhere - for now just log
                    # TODO: This needs access to RVC config repository for known pairs
                    logger.debug("Would try to group response for command: %s", _cmd)

        except Exception as e:
            logger.error("Error checking pending command completion: %s", e)

    async def _simulate_can_messages(self) -> None:
        """
        Simulate CAN messages for testing purposes.

        This method generates simulated CAN messages at regular intervals,
        using actual decoder definitions when available.
        """
        logger.info("Starting CAN message simulation")

        # Counter for cycling through different message types
        counter = 0

        # Get a list of available decoders for more realistic simulation
        available_decoders = list(self.decoder_map.keys()) if self.decoder_map else []

        while self._running:
            try:
                await asyncio.sleep(1.0)  # 1 message per second

                # If we have decoders, use real PGN IDs, otherwise use hardcoded ones
                if available_decoders:
                    # Use real decoder entries
                    decoder_key = available_decoders[counter % len(available_decoders)]
                    entry = self.decoder_map[decoder_key]

                    arbitration_id = decoder_key
                    entry_length = entry.get("length", 8)

                    # Generate semi-realistic data based on the entry's signals
                    data = bytearray(entry_length)
                    if "signals" in entry:
                        for signal in entry["signals"]:
                            try:
                                start_bit = signal.get("start_bit", 0)
                                length = signal.get("length", 8)

                                # Generate a reasonable value for the signal
                                if signal.get("name", "").lower() in ["instance"]:
                                    # Instance fields should be 0-255
                                    value = counter % 256
                                elif signal.get("name", "").lower() in [
                                    "operating_status",
                                    "status",
                                ]:
                                    # Status fields - alternate between 0 and some value
                                    value = (counter % 2) * 128
                                else:
                                    # Other fields - some variation
                                    value = (counter * 17) % (1 << min(length, 16))

                                # Set the bits in the data array
                                byte_offset = start_bit // 8
                                if byte_offset < len(data):
                                    data[byte_offset] = value & 0xFF
                            except Exception as e:
                                logger.debug("Error generating signal data: %s", e)
                    else:
                        # No signals defined, use some default pattern
                        for i in range(entry_length):
                            data[i] = (counter + i * 13) % 256

                    data = bytes(data)
                    logger.debug(
                        "Simulating message from decoder: %s", entry.get("name", "Unknown")
                    )

                else:
                    # Fallback to hardcoded simulation messages
                    msg_type = counter % 4

                    if msg_type == 0:
                        # Simulate a temperature message (DGN 1FEA5 / 130725)
                        arbitration_id = 0x1FEA5
                        # Temperature of 72.5°F (22.5°C)
                        data = bytes([0x02, 0x01, 0x00, 0x00, 0xE1, 0x01, 0x00, 0xFF])
                    elif msg_type == 1:
                        # Simulate a battery state message (DGN 1FFFD / 131069)
                        arbitration_id = 0x1FFFD
                        # Battery at 80% charge
                        data = bytes([0x01, 0x50, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF])
                    elif msg_type == 2:
                        # Simulate a light status message (DGN 1FEED / 130797)
                        arbitration_id = 0x1FEED
                        # Light is on
                        data = bytes([0x01, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
                    else:
                        # Simulate a tank level message (DGN 1FF9D / 130973)
                        arbitration_id = 0x1FF9D
                        # Tank at 65% capacity
                        data = bytes([0x01, 0x41, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF])

                # Process the simulated message
                await self._process_message(
                    {
                        "arbitration_id": arbitration_id,
                        "data": data,
                        "extended_id": True,
                        "timestamp": time.time(),
                    }
                )

                counter += 1

            except asyncio.CancelledError:
                logger.info("CAN message simulation cancelled")
                break
            except Exception as e:
                logger.error("Error in CAN message simulation: %s", e)
                await asyncio.sleep(5)  # Longer sleep on error


def create_can_bus_service() -> CANBusService:
    """
    Factory function for creating CANBusService with dependencies.

    This would be registered with ServiceRegistry and automatically
    get the repositories injected.
    """
    msg = (
        "This factory should be registered with ServiceRegistry "
        "to get automatic dependency injection of repositories"
    )
    raise NotImplementedError(msg)
