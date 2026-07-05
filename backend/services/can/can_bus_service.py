"""
CAN Bus Service - Clean Service Implementation

Service for CAN bus integration without Feature inheritance.
Uses repository injection pattern for all dependencies.
"""

import asyncio
import contextlib
import datetime
import time
from typing import Any, override

from backend.core.config import get_settings
from backend.core.guardrail_interfaces import (
    CommandHaltAction,
    GuardrailParticipant,
    GuardrailStatus,
    GuardrailTier,
)
from backend.core.structured_logging import get_logger, log_execution_time, log_safety_critical
from backend.integrations.diagnostics.handler import DiagnosticHandler
from backend.integrations.diagnostics.models import DTCSeverity, ProtocolType, SystemType
from backend.integrations.rvc import (
    BAMHandler,
    climate_units,
    decode_component_id,
    decode_payload,
)
from backend.integrations.rvc.decoder_core import DecodedValue
from backend.repositories.can_tracking_repository import CANTrackingRepository
from backend.repositories.system_state_repository import SystemStateRepository

logger = get_logger(__name__, "CANBusService")

# The coach bus carries both diagnostic dialects: J1939 DM1 (PGN FECA) from
# the chassis nodes, and RV-C DM_RV (DGN 1FECA, Sec. 3.2.5.1) from house nodes
# such as the ATS at SA 0x4F. Both share the same payload layout.
J1939_DM1_PGN = 0xFECA
DM_RV_PGN = 0x1FECA
DIAGNOSTIC_PGNS = {J1939_DM1_PGN, DM_RV_PGN}
DM_RV_CLEAR_SPN = 0x7FFFF
DM_RV_CLEAR_FMI = 31
DM_RV_CLEAR_OCCURRENCE_COUNT = 127
# RV-C Product Identification (Sec. 3.2.8) shares DGN FEEB and the
# '*'-delimited multi-packet payload with the J1939 Component ID.
COMPONENT_IDENTIFICATION_PGN = 0xFEEB
PENDING_COMMAND_WINDOW_SECONDS = 5.0
LIGHT_STATUS_SIMULATION_TYPE = 2
SIMULATION_ERROR_SLEEP_SECONDS = 5


def _device_lookup_key(dgn_hex: str, instance: Any) -> tuple[str, str]:
    """Normalize a spec DGN hex + instance into a coach-mapping device_lookup key.

    Spec entries carry ``dgn_hex`` values like ``"0x1FEDA"`` while the coach
    mapping's device_lookup keys are bare uppercase hex like ``"1FEDA"``, so the
    ``0X`` prefix must be stripped after uppercasing for lookups to hit.
    """
    return (dgn_hex.upper().removeprefix("0X"), str(instance))


class CANBusService(GuardrailParticipant):
    """
    Service that manages CAN bus integration.

    This is a clean service implementation without Feature inheritance,
    using repository injection for all dependencies.
    """

    def __init__(  # noqa: PLR0913
        self,
        can_tracking_repository: CANTrackingRepository,
        system_state_repository: SystemStateRepository,
        can_anomaly_detector: Any | None = None,
        diagnostic_handler: DiagnosticHandler | None = None,
        can_bus_recorder: Any | None = None,
        can_protocol_analyzer: Any | None = None,
        can_message_filter: Any | None = None,
        device_discovery_service: Any | None = None,
        entity_manager_service: Any | None = None,
        websocket_manager: Any | None = None,
        entity_state_repository: Any | None = None,
        diagnostics_repository: Any | None = None,
    ):
        """
        Initialize the CAN bus service with repository dependencies.

        Args:
            can_tracking_repository: Repository for CAN message tracking
            system_state_repository: Repository for system state management
            can_anomaly_detector: Optional CAN anomaly detector for security monitoring
            diagnostic_handler: Optional diagnostic DTC handler for DM_RV ingestion
        """
        super().__init__(
            guardrail_tier=GuardrailTier.CRITICAL,
            command_halt_action=CommandHaltAction.DISABLE_COMMANDS,
        )
        self._can_tracking_repository = can_tracking_repository
        self._system_state_repository = system_state_repository

        self.settings = get_settings()
        self._running = False

        # Configuration - use settings from environment
        self.config: dict[str, Any] = {
            "interfaces": self.settings.can.all_interfaces,
            "bustype": self.settings.can.bustype,
            "bitrate": self.settings.can.bitrate,
            "poll_interval": 0.1,  # seconds
            "simulate": False,  # Could also become a setting.
        }

        # CAN bus related attributes
        self._listeners: list[Any] = []  # Will store CAN listeners or notifiers
        self._task: asyncio.Task[None] | None = None
        self._simulation_task: asyncio.Task[None] | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._deduplicator = None  # Will be initialized in startup

        # RVC decoder data - will be loaded on startup
        self.decoder_map: dict[int, dict[str, Any]] = {}
        self.decoder_frame_id_map: dict[int, dict[str, Any]] = {}
        self.decoder_pgn_map: dict[int, dict[str, Any]] = {}
        self.device_lookup: dict[tuple[str, str], Any] = {}
        self.status_lookup: dict[tuple[str, str], dict[str, Any]] = {}
        self.pgn_hex_to_name_map: dict[str, str] = {}
        self.raw_device_mapping: dict[Any, Any] = {}
        self.entity_id_lookup: dict[str, dict[str, Any]] = {}

        # BAM handler for multi-packet messages
        self.bam_handler: BAMHandler | None = None
        self._component_identity_seen: set[tuple[int, bytes]] = set()

        # Pattern recognition engine for unknown messages
        self.pattern_engine = None

        # Anomaly detector for security monitoring (injected)
        self.anomaly_detector = can_anomaly_detector

        # Diagnostic handler for DTC ingestion (injected)
        self._diagnostic_handler = diagnostic_handler
        self._can_bus_recorder = can_bus_recorder
        self._can_protocol_analyzer = can_protocol_analyzer
        self._can_message_filter = can_message_filter
        self._device_discovery_service = device_discovery_service
        self._entity_manager_service = entity_manager_service
        self._websocket_manager = websocket_manager
        self._entity_state_repository = entity_state_repository
        self._diagnostics_repository = diagnostics_repository

        logger.info(
            "CANBusService initialized",
            interfaces=self.config["interfaces"],
            bustype=self.config["bustype"],
            bitrate=self.config["bitrate"],
            has_anomaly_detector=bool(can_anomaly_detector),
            has_diagnostic_handler=bool(diagnostic_handler),
        )

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
                logger.warning("Failed to initialize pattern recognition engine", error=str(e))
                self.pattern_engine = None

            # Start anomaly detector if provided
            if self.anomaly_detector:
                try:
                    await self.anomaly_detector.start()
                    logger.info("CAN anomaly detector started")
                except Exception as e:
                    logger.warning("Failed to start anomaly detector", error=str(e))
                    self.anomaly_detector = None

            # Start the per-frame tool services. Every received frame is
            # dispatched to these; leaving them stopped made each one log a
            # "blocked: service not running" warning PER FRAME (~29k journal
            # lines/min on the coach at real bus rates).
            for tool_name, tool in (
                ("protocol analyzer", self._can_protocol_analyzer),
                ("message filter", self._can_message_filter),
            ):
                if tool is None:
                    continue
                try:
                    await tool.start()
                    logger.info("CAN %s started", tool_name)
                except Exception as e:
                    logger.warning("Failed to start CAN %s: %s", tool_name, e)

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

            # Start the TX writer that drains can_tx_queue onto the bus. Without
            # this, every entity control command builds a frame, enqueues it,
            # and nothing ever transmits it (commands silently time out). The
            # writer was orphaned when the service layer replaced the old
            # feature system — this is where it gets launched.
            from backend.integrations.can.manager import can_writer

            self._writer_task = asyncio.create_task(
                can_writer(self._can_tracking_repository, self._system_state_repository)
            )
            logger.info("CAN writer (TX queue drainer) started")

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

        # Cancel the TX writer task
        if self._writer_task:
            self._writer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer_task

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

    @log_safety_critical(safety_level="CRITICAL")
    @override
    async def halt_command_emission(self, reason: str) -> None:
        """Emergency stop implementation."""
        logger.critical("CANBusService emergency stop triggered", reason=reason)
        self._set_command_halt_active(True)
        self._running = False

        # Stop all listeners and tasks
        await self._cleanup_can_listeners()

        if self._simulation_task:
            self._simulation_task.cancel()

        if self.pattern_engine:
            await self.pattern_engine.stop()

        if self.anomaly_detector:
            await self.anomaly_detector.stop()

    @override
    async def get_guardrail_status(self) -> GuardrailStatus:
        """Get current safety status."""
        if self._command_halt_active:
            return GuardrailStatus.COMMAND_HALTED
        if not self._running:
            return GuardrailStatus.UNSAFE
        return GuardrailStatus.SAFE

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

    @log_execution_time(threshold_ms=500)
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

            logger.info("Using RVC spec path", spec_path=spec_path)
            logger.info("Using device mapping path", map_path=map_path)

            # Use structured configuration loader
            from backend.integrations.rvc import load_config_data_v2

            rvc_config = load_config_data_v2(
                rvc_spec_path_override=spec_path, device_mapping_path_override=map_path
            )

            # Extract values from structured config
            self.decoder_map = rvc_config.dgn_dict
            self.decoder_frame_id_map = rvc_config.frame_id_dict
            # Build the PGN fallback from the id-keyed map when available:
            # dgn_dict drops spec entries that share a PGN (its keys collide),
            # so it under-populates the fallback.
            self.decoder_pgn_map = self._build_decoder_pgn_map(
                self.decoder_frame_id_map or self.decoder_map
            )
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
                "Loaded RVC configuration",
                decoders=len(self.decoder_map),
                device_mappings=len(self.device_lookup),
            )

        except Exception as e:
            logger.error("Failed to load RVC decoder configuration", error=str(e))
            logger.warning("CAN bus service will run without RVC decoding capabilities")

    @staticmethod
    def _build_decoder_pgn_map(decoder_map: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
        """Build a PGN lookup table for source-address-specific received frames."""
        pgn_map: dict[int, dict[str, Any]] = {}
        for entry in decoder_map.values():
            pgn_value = entry.get("pgn") if isinstance(entry, dict) else None
            if not isinstance(pgn_value, str):
                continue
            try:
                pgn = int(pgn_value, 16)
            except ValueError:
                continue
            current = pgn_map.get(pgn)
            if current is None or str(current.get("name", "")).startswith("UNKNOWN"):
                pgn_map[pgn] = entry
        return pgn_map

    def _get_decoder_entry(self, arbitration_id: int, pgn: int) -> dict[str, Any] | None:
        """Get a decoder entry by exact 29-bit arbitration id, else PGN fallback.

        The exact match must use the id-keyed map: decoder_map (dgn_dict) keys
        are ``(priority << 18) | pgn`` with an assumed priority, so they never
        equal a full arbitration id.
        """
        entry = self.decoder_frame_id_map.get(arbitration_id)
        if entry is not None:
            return entry
        return self.decoder_pgn_map.get(pgn)

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
                "Setting up CAN bus listeners",
                interfaces=interfaces_config,
                bustype=bustype,
                bitrate=bitrate,
            )

            # Initialize CAN interfaces directly
            failed_interfaces = []
            for interface in interfaces_config:
                try:
                    # Create the bus directly
                    bus = can.interface.Bus(channel=interface, bustype=bustype, bitrate=bitrate)
                    buses[interface] = bus  # type: ignore[assignment]
                    logger.info("Initialized CAN interface: %s", interface)
                except Exception as e:
                    logger.error("Failed to initialize interface %s: %s", interface, e)
                    failed_interfaces.append(interface)

            initialized_count = len(buses)
            logger.info(
                "CAN interface initialization complete",
                initialized=initialized_count,
                failed=failed_interfaces,
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
            missing_can_message = (
                "python-can package not available. CAN bus service will not start. "
                + "Install with 'poetry add python-can'."
            )
            logger.warning("%s", missing_can_message)
            # Fall back to simulation mode
            logger.info("Falling back to CAN bus simulation mode")
            self._simulation_task = asyncio.create_task(self._simulate_can_messages())
        except Exception:
            logger.exception("Failed to start CAN bus listeners")
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
                "Setting up CAN listeners",
                interface_count=len(buses),
                interfaces=list(buses.keys()),
            )

            for interface_name, bus in buses.items():
                try:
                    # Create AsyncBufferedReader for non-blocking message reception
                    # Limit buffer to prevent memory buildup (1000 messages max)
                    reader = can.AsyncBufferedReader()  # type: ignore[attr-defined]

                    # Create Notifier with asyncio event loop integration
                    loop = asyncio.get_running_loop()
                    notifier = can.Notifier(bus, [reader], loop=loop)  # type: ignore[attr-defined]

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

                    logger.info("Started CAN listener for interface", interface_name=interface_name)

                except Exception as e:
                    logger.error(
                        "Failed to start CAN listener", interface_name=interface_name, error=str(e)
                    )

        except Exception:
            logger.exception("Failed to set up CAN listeners")

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

    async def _can_listener_task(self, interface_name: str, reader: Any) -> None:
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
                        logger.error(
                            "Error receiving CAN message", interface=interface_name, error=str(e)
                        )
                    break

        except asyncio.CancelledError:
            logger.info("CAN listener cancelled", interface=interface_name)
            raise
        except Exception:
            logger.exception("CAN listener failed", interface=interface_name)
        finally:
            logger.info("CAN listener stopped", interface=interface_name)

    async def _send_to_can_tools(self, message: Any, interface_name: str) -> bool:
        """
        Send CAN message to optional analysis tools through composition root.

        Args:
            message: python-can Message object
            interface_name: Name of the interface that received the message
        """
        try:
            # Send to CAN recorder if available
            try:
                recorder = self._can_bus_recorder
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

            # Send to protocol analyzer if available. Gate on the tool's own
            # running flag: dispatching to a stopped tool logs a warning per
            # frame, which floods the journal at bus rates.
            try:
                analyzer = self._can_protocol_analyzer
                if analyzer and getattr(analyzer, "_is_running", True):
                    await analyzer.analyze_message(
                        can_id=message.arbitration_id,
                        data=message.data,
                        interface=interface_name,
                    )
            except Exception as e:
                logger.debug("Failed to send to protocol analyzer: %s", e)

            # Send to message filter if available (same running-flag gate as
            # the analyzer above).
            try:
                message_filter = self._can_message_filter
                if message_filter and getattr(message_filter, "_is_running", True):
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

    async def _process_received_message(self, message: Any, interface_name: str) -> None:
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

        except Exception:
            logger.exception("Error processing received CAN message")

    async def _add_sniffer_entry(self, message: Any, interface_name: str, direction: str) -> None:
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

            # Broadcast the live frame to CAN sniffer WebSocket clients. Mirrors
            # the entity RX broadcast: guarded so a broken client (or a missing
            # websocket manager) never breaks the CAN RX path.
            await self._broadcast_sniffer_entry(message, interface_name, direction)

        except Exception as e:
            logger.error("Error adding sniffer entry: %s", e)

    async def _broadcast_sniffer_entry(
        self, message: Any, interface_name: str, direction: str
    ) -> None:
        """Broadcast a live CAN frame to sniffer WebSocket clients (best effort).

        The sniffer page (``useCANScanWebSocket``) consumes each frame as a bare
        ``CANMessage``: ``pgn`` (hex string), ``source`` (int), ``data`` (byte
        list), ``timestamp`` (ISO-8601), plus ``interface``/``error``. RV-C uses
        29-bit extended IDs: Priority(3) + PGN(18) + Source(8).
        """
        websocket_manager = self._websocket_manager
        if websocket_manager is None:
            return
        try:
            arbitration_id = message.arbitration_id
            pgn = (arbitration_id >> 8) & 0x3FFFF
            source_address = arbitration_id & 0xFF
            frame = {
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                "pgn": f"{pgn:X}",
                "source": source_address,
                "data": list(message.data),
                "interface": interface_name,
                "error": bool(getattr(message, "is_error_frame", False)),
                "direction": direction,
            }
            await websocket_manager.broadcast_can_sniffer_entry(frame)
        except Exception as broadcast_error:
            logger.debug("Unable to broadcast sniffer entry: %s", broadcast_error)

    async def _process_message(self, msg: dict[str, Any]) -> None:  # noqa: C901, PLR0912, PLR0915
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
            normalized_pgn = BAMHandler.normalize_transport_pgn(pgn)
            if self.bam_handler and normalized_pgn in [BAMHandler.TP_CM_PGN, BAMHandler.TP_DT_PGN]:
                # Process through BAM handler
                result = self.bam_handler.process_frame(normalized_pgn, data, source_address)

                if result:
                    # We have a complete multi-packet message
                    target_pgn, reassembled_data = result

                    self._process_reassembled_message(
                        target_pgn, reassembled_data, source_address, msg
                    )

                # Don't process transport protocol messages further
                return

            # Try to decode the message using RVC decoder
            entry = self._get_decoder_entry(arbitration_id, pgn) if self.decoder_map else None
            if entry is not None:
                try:
                    decoded_results, _decode_errors = decode_payload(entry, data)
                    decoded_data, raw_data = self._split_decoded_payload(decoded_results)

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

                    self._process_diagnostic_frame(arbitration_id, data, decoded_results, msg)

                    # Check if this maps to a known device/entity
                    if dgn_hex and instance is not None:
                        device_key = _device_lookup_key(dgn_hex, instance)
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
                            self._record_unmapped_device(dgn_hex, instance, entry, data, msg)
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
                self._record_unknown_pgn(arbitration_id, pgn, data, msg)
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

    def _record_unknown_pgn(
        self, arbitration_id: int, pgn: int, data: bytes, msg: dict[str, Any]
    ) -> None:
        """Record an undecodable PGN in the diagnostics repository (best effort)."""
        if self._diagnostics_repository is None:
            return
        try:
            timestamp = float(msg.get("timestamp", time.time()))
            self._diagnostics_repository.upsert_unknown_pgn(
                f"{pgn:X}",
                {
                    "arbitration_id_hex": f"{arbitration_id:X}",
                    "first_seen_timestamp": timestamp,
                    "last_seen_timestamp": timestamp,
                    "last_data_hex": data.hex().upper(),
                },
            )
        except Exception as e:
            logger.debug("Unable to record unknown PGN %X: %s", pgn, e)

    def _record_unmapped_device(
        self,
        dgn_hex: str,
        instance: Any,
        entry: dict[str, Any],
        data: bytes,
        msg: dict[str, Any],
    ) -> None:
        """Record a decoded-but-unmapped device in the diagnostics repository (best effort)."""
        if self._diagnostics_repository is None:
            return
        try:
            timestamp = float(msg.get("timestamp", time.time()))
            dgn_name = entry.get("name")
            self._diagnostics_repository.upsert_unmapped_entry(
                f"{dgn_hex}-{instance}",
                {
                    "pgn_hex": str(entry.get("pgn", dgn_hex)),
                    "pgn_name": dgn_name,
                    "dgn_hex": dgn_hex,
                    "dgn_name": dgn_name,
                    "instance": str(instance),
                    "last_data_hex": data.hex().upper(),
                    "first_seen_timestamp": timestamp,
                    "last_seen_timestamp": timestamp,
                },
            )
        except Exception as e:
            logger.debug("Unable to record unmapped device %s:%s: %s", dgn_hex, instance, e)

    def _process_reassembled_message(
        self,
        target_pgn: int,
        reassembled_data: bytes,
        source_address: int,
        msg: dict[str, Any],
    ) -> None:
        """Process a completed BAM message from the receive path."""
        if target_pgn == COMPONENT_IDENTIFICATION_PGN:
            self._record_component_identification(source_address, reassembled_data, msg)
            return

        logger.debug("Reassembled multi-packet message for PGN %05X", target_pgn)

    def _record_component_identification(
        self, source_address: int, reassembled_data: bytes, msg: dict[str, Any]
    ) -> None:
        """Decode and record J1939 Component Identification in DeviceDiscoveryService."""
        identity_key = (source_address, reassembled_data)
        if identity_key in self._component_identity_seen:
            return
        self._component_identity_seen.add(identity_key)

        component_id = decode_component_id(reassembled_data)
        if "error" in component_id:
            logger.debug("Skipping invalid Component ID from source 0x%02X", source_address)
            return

        try:
            discovery_service = self._device_discovery_service
            if discovery_service is None:
                return
            discovery_service.record_component_identification(
                source_address=source_address,
                component_id=component_id,
                interface=msg.get("interface") if isinstance(msg.get("interface"), str) else None,
            )
        except Exception as e:
            logger.debug("Unable to record Component ID for source 0x%02X: %s", source_address, e)

    @staticmethod
    def _split_decoded_payload(
        decoded_results: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Split decoder-core results into value and raw-value dictionaries."""
        decoded_data: dict[str, Any] = {}
        raw_data: dict[str, int] = {}
        for signal_name, result in decoded_results.items():
            if not isinstance(result, DecodedValue):
                decoded_data[signal_name] = str(result)
                continue
            decoded_data[signal_name] = None if result.unavailable else result.value
            if result.raw_value is not None:
                raw_data[signal_name] = result.raw_value
        return decoded_data, raw_data

    @staticmethod
    def _decoded_raw_value(decoded_data: dict[str, Any], signal_name: str) -> int | None:
        """Extract a raw integer signal value from decoder-core results."""
        value = decoded_data.get(signal_name)
        if isinstance(value, DecodedValue):
            return value.raw_value
        return None

    def _process_diagnostic_frame(
        self,
        arbitration_id: int,
        data: bytes,
        decoded_results: dict[str, Any],
        msg: dict[str, Any],
    ) -> None:
        """Ingest decoded DM_RV/J1939 DM1 frames into the diagnostic handler."""
        if self._diagnostic_handler is None:
            return

        pgn = (arbitration_id >> 8) & 0x3FFFF
        if pgn not in DIAGNOSTIC_PGNS:
            return

        source_address = arbitration_id & 0xFF
        spn_msb = self._decoded_raw_value(decoded_results, "SPN_MSB")
        spn_isb = self._decoded_raw_value(decoded_results, "SPN_ISB")
        spn_lsb = self._decoded_raw_value(decoded_results, "SPN_LSB")
        fmi = self._decoded_raw_value(decoded_results, "FMI")
        occurrence_count = self._decoded_raw_value(decoded_results, "occurrence_count")
        yellow_lamp_status = self._decoded_raw_value(decoded_results, "yellow_lamp_status")
        red_lamp_status = self._decoded_raw_value(decoded_results, "red_lamp_status")

        if spn_msb is None or spn_isb is None or spn_lsb is None or fmi is None:
            logger.debug("Skipping DM_RV frame with incomplete DTC decode: %08X", arbitration_id)
            return

        spn = (spn_lsb << 16) | (spn_isb << 8) | spn_msb
        is_clear_heartbeat = (
            spn == DM_RV_CLEAR_SPN
            and fmi == DM_RV_CLEAR_FMI
            and occurrence_count == DM_RV_CLEAR_OCCURRENCE_COUNT
            and yellow_lamp_status == 0
            and red_lamp_status == 0
        )
        if is_clear_heartbeat:
            logger.debug("Ignoring clean DM_RV heartbeat from source 0x%02X", source_address)
            return

        if red_lamp_status:
            severity = DTCSeverity.CRITICAL
        elif yellow_lamp_status:
            severity = DTCSeverity.HIGH
        else:
            severity = DTCSeverity.MEDIUM

        if pgn == J1939_DM1_PGN:
            protocol, system_type, dialect = ProtocolType.J1939, SystemType.CHASSIS, "DM1"
        else:
            protocol, system_type, dialect = ProtocolType.RVC, SystemType.UNKNOWN, "DM_RV"

        code = (spn << 5) | fmi
        self._diagnostic_handler.process_dtc(
            code=code,
            protocol=protocol,
            system_type=system_type,
            source_address=source_address,
            pgn=pgn,
            dgn=pgn,
            raw_data=data,
            severity=severity,
            description=f"{dialect} active DTC SPN {spn} FMI {fmi}",
            metadata={
                "spn": spn,
                "fmi": fmi,
                "occurrence_count": occurrence_count,
                "yellow_lamp_status": yellow_lamp_status,
                "red_lamp_status": red_lamp_status,
                "interface": msg.get("interface"),
            },
        )

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
            entity_manager_service = self._entity_manager_service
            if entity_manager_service is None:
                logger.warning("EntityManagerService not available for entity update")
                return

            entity_manager = entity_manager_service.get_entity_manager()
            entity = entity_manager.get_entity(entity_id)

            if not entity:
                logger.warning("Entity %s not found in entity manager", entity_id)
                return

            # Build state update payload
            timestamp = msg.get("timestamp", time.time())

            merged_value, merged_raw = self._merged_signal_dicts(entity, decoded_data, raw_data)

            payload = {
                "entity_id": entity_id,
                "timestamp": timestamp,
                "value": merged_value,
                "raw": merged_raw,
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

            # Handle device-type-specific state shaping
            device_type = device_config.get("device_type")
            if device_type == "light":
                await self._update_light_state(payload, decoded_data, raw_data)
            elif device_type in (
                "climate",
                "air_conditioner",
                "water_heater",
                "tank",
                "temperature",
                "ac_load",
            ):
                self._update_climate_family_state(device_type, payload, merged_raw)

            # Update the entity state
            updated_entity = entity_manager.update_entity_state(entity_id, payload)

            if updated_entity:
                logger.debug("Updated entity %s state from CAN message", entity_id)

                # Persist to the runtime state repository so API reads
                # (which go through EntityRuntimeStateRepository, not the
                # EntityManager) see live CAN-derived state.
                await self._persist_entity_state(entity_id, updated_entity)

                # Broadcast the update via WebSocket. Envelope matches what
                # the frontend's entity_update handler expects (data ->
                # {entity_id, entity_data}), same as the control paths emit.
                websocket_service = self._websocket_manager
                if websocket_service:
                    broadcast_data = {
                        "type": "entity_update",
                        "data": {
                            "entity_id": entity_id,
                            "entity_data": updated_entity.to_dict(),
                        },
                    }
                    await websocket_service.broadcast_to_data_clients(broadcast_data)

                # Check if this completes a pending command (for optimistic UI updates)
                await self._check_pending_command_completion(entity_id, payload)
            else:
                logger.warning("Failed to update entity %s state", entity_id)

        except Exception:
            logger.exception("Error updating entity %s from CAN message", entity_id)

    @staticmethod
    def _merged_signal_dicts(
        entity: Any,
        decoded_data: dict[str, Any] | None,
        raw_data: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Merge new decoded/raw signals over the entity's previous ones.

        Some entities are fed by more than one DGN (a climate zone combines
        THERMOSTAT_STATUS_1 setpoints with THERMOSTAT_AMBIENT_STATUS
        temperature; the Aqua-Hot combines WATERHEATER_STATUS and
        WATERHEATER_STATUS_2), and Entity.update_state swaps value/raw
        wholesale. Tolerates Entity look-alikes without get_state().
        """
        previous_value: dict[str, Any] = {}
        previous_raw: dict[str, Any] = {}
        get_state = getattr(entity, "get_state", None)
        if callable(get_state):
            previous_state = get_state()
            previous_value = dict(getattr(previous_state, "value", None) or {})
            previous_raw = dict(getattr(previous_state, "raw", None) or {})
        return (
            {**previous_value, **(decoded_data or {})},
            {**previous_raw, **(raw_data or {})},
        )

    async def _persist_entity_state(self, entity_id: str, updated_entity: Any) -> None:
        """Persist a live entity update to the runtime state repository (best effort)."""
        if self._entity_state_repository is None:
            return
        try:
            await self._entity_state_repository.save_entity_state(
                entity_id, updated_entity.to_dict()
            )
        except Exception as repo_error:
            logger.debug(
                "Unable to persist entity %s state to repository: %s",
                entity_id,
                repo_error,
            )

    async def _update_light_state(
        self, payload: dict[str, Any], _decoded_data: dict[str, Any], raw_data: dict[str, Any]
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

    @staticmethod
    def _update_climate_family_state(
        device_type: str, payload: dict[str, Any], merged_raw: dict[str, Any]
    ) -> None:
        """Shape state for climate-family entities (thermostat zones, ACs, Aqua-Hot).

        Adds UI-friendly derived fields (Fahrenheit temperatures, percent fan
        speeds) into the raw signal dict — the v2 entities API exposes that
        dict as the entity's ``state`` — and sets the human-readable ``state``
        string from the operating mode.
        """
        try:
            if device_type == "climate":
                merged_raw.update(climate_units.derive_climate_fields(merged_raw))
                payload["state"] = climate_units.climate_state_label(merged_raw)
                # Zones whose compressor is an energy-managed AC load also
                # carry AC_LOAD_STATUS (operating_status) — surface shed.
                if "operating_status" in merged_raw:
                    _label, shed = climate_units.ac_load_state(merged_raw)
                    merged_raw["shed"] = shed
            elif device_type == "air_conditioner":
                merged_raw.update(climate_units.derive_ac_fields(merged_raw))
                payload["state"] = climate_units.ac_state_label(merged_raw)
            elif device_type == "water_heater":
                merged_raw.update(climate_units.derive_water_heater_fields(merged_raw))
                payload["state"] = climate_units.water_heater_state_label(merged_raw)
            elif device_type == "tank":
                merged_raw.update(climate_units.derive_tank_fields(merged_raw))
                payload["state"] = climate_units.tank_state_label(merged_raw)
            elif device_type == "temperature":
                merged_raw.update(climate_units.derive_climate_fields(merged_raw))
                payload["state"] = climate_units.temperature_state_label(merged_raw)
            elif device_type == "ac_load":
                merged_raw.update(climate_units.derive_ac_load_fields(merged_raw))
                state_label, _shed = climate_units.ac_load_state(merged_raw)
                payload["state"] = state_label
        except Exception as e:
            logger.error("Error shaping %s state: %s", device_type, e)

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
            pending_command_source = getattr(self._can_tracking_repository, "_pending_commands", [])
            pending_commands = [
                cmd
                for cmd in pending_command_source
                if cmd.get("entity_id") == entity_id
                and (update_timestamp - cmd.get("timestamp", 0)) < PENDING_COMMAND_WINDOW_SECONDS
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
                    # Future work: use RVC config repository for known pairs.
                    logger.debug("Would try to group response for command: %s", _cmd)

        except Exception as e:
            logger.error("Error checking pending command completion: %s", e)

    async def _simulate_can_messages(self) -> None:  # noqa: C901, PLR0912, PLR0915
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
                    elif msg_type == LIGHT_STATUS_SIMULATION_TYPE:
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
                await asyncio.sleep(SIMULATION_ERROR_SLEEP_SECONDS)  # Longer sleep on error


def create_can_bus_service() -> CANBusService:
    """
    Factory function for creating CANBusService with dependencies.

    This would be registered with composition root and automatically
    get the repositories injected.
    """
    msg = (
        "This factory should be registered with composition root "
        "to get automatic dependency injection of repositories"
    )
    raise NotImplementedError(msg)
