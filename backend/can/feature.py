"""
CAN bus feature for the new architecture.

This module provides a Feature-based implementation for CAN bus integration,
listening to CAN messages and integrating with the event system.
"""

import asyncio
import contextlib
import logging
import time
from typing import Any

from backend.integrations.rvc import BAMHandler, decode_payload, decode_product_id
from backend.services.feature_base import Feature
from backend.services.feature_models import SafetyClassification

logger = logging.getLogger(__name__)


class CANBusFeature(Feature):
    """
    Feature for CAN bus integration.

    This feature manages CAN bus interfaces, listening for messages and
    processing them according to the configured decoders.
    """

    def __init__(
        self,
        name: str = "can_feature",
        enabled: bool = True,
        core: bool = True,
        config: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        friendly_name: str | None = None,
        safety_classification: SafetyClassification | None = None,
        log_state_transitions: bool = True,
    ) -> None:
        """
        Initialize the CAN bus feature.

        Args:
            name: Feature name (default: "can_feature")
            enabled: Whether the feature is enabled (default: True)
            core: Whether this is a core feature (default: True)
            config: Configuration options (default: None)
            dependencies: Feature dependencies (default: ["app_state"])
            friendly_name: Human-readable display name for the feature
            safety_classification: Safety classification for state validation
            log_state_transitions: Whether to log state transitions for audit
        """
        # Ensure we depend on app_state (required for CAN service initialization)
        deps = dependencies or []
        if "app_state" not in deps:
            deps.append("app_state")

        # Initialize with provided config or defaults from settings
        config_dict = config or {}

        # Get interfaces from settings if not provided in config
        if "interfaces" not in config_dict:
            from backend.core.config import get_settings

            settings = get_settings()
            default_interfaces = settings.can.all_interfaces
        else:
            default_interfaces = config_dict["interfaces"]

        self.config = {
            "interfaces": config_dict.get("interfaces", default_interfaces),
            "bustype": config_dict.get("bustype", "socketcan"),
            "bitrate": config_dict.get("bitrate", 500000),
            "poll_interval": config_dict.get("poll_interval", 0.1),  # seconds
            "simulate": config_dict.get("simulate", False),
        }

        super().__init__(
            name=name,
            enabled=enabled,
            core=core,
            config=self.config,
            dependencies=deps,
            friendly_name=friendly_name,
            safety_classification=safety_classification,
            log_state_transitions=log_state_transitions,
        )

        # CAN bus related attributes
        self._listeners: list[Any] = []  # Will store CAN listeners or notifiers
        # Writer task is now handled by CANService
        # Message queue and writer are now handled by CANService

        # State
        self._is_running = False
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

        # Anomaly detector for security monitoring
        self.anomaly_detector = None

    async def startup(self) -> None:
        """
        Start CAN bus listeners and message processing.

        This method is called automatically by the FeatureManager.
        """
        logger.info("Starting CAN bus feature")
        # Mark the feature as running before spawning listener/simulation tasks
        # so that they don't exit immediately when checking this flag.
        self._is_running = True

        # Initialize message deduplicator for bridged interfaces
        from backend.integrations.can.message_deduplicator import CANMessageDeduplicator
        self._deduplicator = CANMessageDeduplicator(window_ms=50)

        # Initialize BAM handler for multi-packet message support
        self.bam_handler = BAMHandler(session_timeout=30.0, max_concurrent_sessions=50)

        # Initialize pattern recognition engine for unknown message analysis
        try:
            from backend.integrations.can.pattern_recognition_engine import get_pattern_recognition_engine
            self.pattern_engine = get_pattern_recognition_engine()
            await self.pattern_engine.start()
            logger.info("Pattern recognition engine started")
        except Exception as e:
            logger.warning(f"Failed to initialize pattern recognition engine: {e}")
            self.pattern_engine = None

        # Initialize anomaly detector for security monitoring
        try:
            from backend.integrations.can.anomaly_detector import get_anomaly_detector
            self.anomaly_detector = get_anomaly_detector()
            await self.anomaly_detector.start()
            logger.info("CAN anomaly detector started")
        except Exception as e:
            logger.warning(f"Failed to initialize anomaly detector: {e}")
            self.anomaly_detector = None

        # Load RVC decoder configuration
        try:
            logger.info("Loading RVC decoder configuration")

            # Get settings to pass environment variable paths
            from backend.core.config import get_settings

            settings = get_settings()

            # Convert Path objects to strings if they exist
            spec_path = str(settings.rvc_spec_path) if settings.rvc_spec_path else None
            map_path = (
                str(settings.rvc_coach_mapping_path) if settings.rvc_coach_mapping_path else None
            )

            logger.info(f"Using RVC spec path: {spec_path}")
            logger.info(f"Using device mapping path: {map_path}")

            # Use structured configuration loader
            from backend.integrations.rvc import load_config_data_v2

            rvc_config = load_config_data_v2(
                rvc_spec_path_override=spec_path, device_mapping_path_override=map_path
            )

            # Extract values from structured config
            self.decoder_map = rvc_config.dgn_dict
            _spec_meta = rvc_config.spec_meta  # metadata about the spec file
            _mapping_dict = rvc_config.mapping_dict  # mapping data organized by (dgn_hex, instance)
            _entity_map = rvc_config.entity_map  # entity mapping data
            _entity_ids = rvc_config.entity_ids  # set of entity IDs
            self.entity_id_lookup = rvc_config.inst_map  # entity ID to config lookup
            _light_command_info = rvc_config.unique_instances  # light command information
            self.pgn_hex_to_name_map = rvc_config.pgn_hex_to_name_map  # PGN hex to name mapping
            _dgn_pairs = rvc_config.dgn_pairs  # DGN pairs
            _coach_info = rvc_config.coach_info  # coach information

            # Extract additional lookup tables from mapping dict
            # This is needed for device and status lookups
            for (dgn_hex, instance), device_config in _mapping_dict.items():
                self.device_lookup[(dgn_hex.upper(), str(instance))] = device_config

            # Copy entity map to device lookup for compatibility
            for (dgn_hex, instance), device_config in _entity_map.items():
                self.device_lookup[(dgn_hex.upper(), str(instance))] = device_config

            # Build status lookup from device lookup for devices with status_dgn
            for (_dgn_hex, instance), device_config in self.device_lookup.items():
                status_dgn = device_config.get("status_dgn")
                if status_dgn:
                    self.status_lookup[(status_dgn.upper(), str(instance))] = device_config

            # Store raw device mapping for unmapped entry suggestions
            self.raw_device_mapping = _mapping_dict  # This is the device_mapping dict

            logger.info(
                f"Loaded RVC configuration: {len(self.decoder_map)} decoders, "
                f"{len(self.device_lookup)} device mappings"
            )

        except Exception as e:
            logger.error(f"Failed to load RVC decoder configuration: {e}")
            logger.warning("CAN bus feature will run without RVC decoding capabilities")

        if self.config["simulate"]:
            # Start simulation mode
            logger.info("Starting CAN bus simulation mode")
            self._simulation_task = asyncio.create_task(self._simulate_can_messages())
        else:
            # Start real CAN bus listeners
            try:
                # Import and initialize CAN interfaces using the existing manager
                from backend.services.can_service import CANService

                interfaces = self.config["interfaces"]
                bustype = self.config["bustype"]
                bitrate = self.config["bitrate"]

                logger.info(
                    f"Setting up CAN bus listeners: interfaces={interfaces}, "
                    f"bustype={bustype}, bitrate={bitrate}"
                )

                # Get the app_state dependency from the feature manager
                from backend.services.feature_manager import get_feature_manager

                feature_manager = get_feature_manager()
                app_state = feature_manager.get_feature("app_state")

                if not app_state:
                    msg = "AppState feature is required but not found"
                    raise RuntimeError(msg)

                # Initialize CAN service with app_state and full startup (interfaces + writer)
                can_service = CANService(app_state)
                startup_result = await can_service.startup()

                logger.info(
                    f"CAN interface initialization complete: "
                    f"initialized={startup_result['interfaces']['initialized']}, "
                    f"failed={startup_result['interfaces']['failed']}"
                )

                if startup_result["interfaces"]["failed"]:
                    logger.warning(
                        f"Some CAN interfaces failed to initialize: "
                        f"{startup_result['interfaces']['failed']}"
                    )

                # CAN writer task is started by the CAN service startup method

                # Set up CAN message listeners for each active interface
                await self._setup_can_listeners()

            except ImportError:
                logger.warning(
                    "python-can package not available. CAN bus feature will not start. "
                    "Install with 'poetry add python-can'."
                )
                # Fall back to simulation mode
                logger.info("Falling back to CAN bus simulation mode")
                self._simulation_task = asyncio.create_task(self._simulate_can_messages())
            except Exception as e:
                logger.error(f"Failed to start CAN bus listeners: {e}", exc_info=True)
                return

    async def _setup_can_listeners(self) -> None:
        """Set up CAN message listeners for all active interfaces using python-can's asyncio support."""
        try:
            import can

            from backend.integrations.can.manager import buses

            if not buses:
                logger.warning("No active CAN buses found, cannot set up listeners")
                return

            logger.info(
                f"Setting up CAN listeners for {len(buses)} interfaces: {list(buses.keys())}"
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

                    logger.info(f"Started CAN listener for interface: {interface_name}")

                except Exception as e:
                    logger.error(f"Failed to start CAN listener for {interface_name}: {e}")

        except Exception as e:
            logger.error(f"Failed to set up CAN listeners: {e}", exc_info=True)

    async def _can_listener_task(self, interface_name: str, reader) -> None:
        """
        Async task to continuously listen for CAN messages using AsyncBufferedReader.

        Args:
            interface_name: Name of the CAN interface (e.g., 'can0', 'can1')
            reader: can.AsyncBufferedReader object for non-blocking message reception
        """
        logger.info(f"CAN listener started for interface: {interface_name}")

        try:
            while self._is_running:
                try:
                    # Non-blocking async message reception
                    message = await reader.get_message()

                    if message is not None:
                        # Process the received message
                        await self._process_received_message(message, interface_name)

                        # Send to CAN recorder if available
                        if self.feature_manager:
                            recorder = self.feature_manager.get_feature("can_bus_recorder")
                            if recorder and hasattr(recorder, 'recording_state') and recorder.recording_state.value == "recording":
                                await recorder.record_message(
                                    can_id=message.arbitration_id,
                                    data=message.data,
                                    interface=interface_name,
                                    is_extended=message.is_extended_id,
                                    is_error=message.is_error_frame,
                                    is_remote=message.is_remote_frame,
                                )

                            # Send to protocol analyzer if available
                            analyzer = self.feature_manager.get_feature("can_protocol_analyzer")
                            if analyzer:
                                await analyzer.analyze_message(
                                    can_id=message.arbitration_id,
                                    data=message.data,
                                    interface=interface_name,
                                )

                            # Send to message filter if available
                            message_filter = self.feature_manager.get_feature("can_message_filter")
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
                                    logger.debug(
                                        f"Message {message.arbitration_id:08X} blocked by filter"
                                    )
                                    continue

                except Exception as e:
                    if self._is_running:  # Only log errors if we're still supposed to be running
                        logger.error(f"Error receiving CAN message on {interface_name}: {e}")
                    break

        except asyncio.CancelledError:
            logger.info(f"CAN listener for {interface_name} cancelled")
            raise
        except Exception as e:
            logger.error(f"CAN listener for {interface_name} failed: {e}", exc_info=True)
        finally:
            logger.info(f"CAN listener for {interface_name} stopped")

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
                    f"Ignoring duplicate message {message.arbitration_id:08X} on {interface_name}"
                )
                return

            # Log the received message
            logger.debug(
                f"CAN RX: {interface_name} ID: {message.arbitration_id:08X} "
                f"Data: {message.data.hex().upper()} DLC: {message.dlc}"
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
                        message.arbitration_id,
                        message.data,
                        msg_dict["timestamp"]
                    )

                    # Check if message should be blocked due to security concerns
                    if "message_blocked" in anomaly_result.get("actions_taken", []):
                        logger.warning(f"Blocked message due to security policy: {message.arbitration_id:08X}")
                        return  # Don't process blocked messages further

                    # Log any anomalies detected
                    if anomaly_result.get("anomalies_detected"):
                        logger.debug(f"Anomalies detected in message {message.arbitration_id:08X}: "
                                   f"{len(anomaly_result['anomalies_detected'])} alerts")

                except Exception as e:
                    logger.debug(f"Error in anomaly detection: {e}")

            # Process the message through the RV-C decoder
            await self._process_message(msg_dict)

        except Exception as e:
            logger.error(f"Error processing received CAN message: {e}", exc_info=True)

    async def _add_sniffer_entry(self, message, interface_name: str, direction: str) -> None:
        """Add a CAN message to the sniffer entries for monitoring."""
        try:
            import time

            from backend.core.state import app_state

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

            app_state.add_can_sniffer_entry(sniffer_entry)

        except Exception as e:
            logger.error(f"Error adding sniffer entry: {e}")

    async def shutdown(self) -> None:
        """
        Shutdown CAN bus listeners and clean up resources.

        This method is called automatically by the FeatureManager.
        """
        logger.info("Shutting down CAN bus feature")

        self._is_running = False

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
                logger.error(f"Error stopping pattern recognition engine: {e}")

        # Stop anomaly detector
        if self.anomaly_detector:
            try:
                await self.anomaly_detector.stop()
                logger.info("CAN anomaly detector stopped")
            except Exception as e:
                logger.error(f"Error stopping anomaly detector: {e}")

        # Writer task cleanup is handled by CANService

        # Cleanup CAN bus listeners
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

                    logger.debug(f"Cleaned up CAN listener for {interface}")

                elif isinstance(listener_info, asyncio.Task):
                    # Legacy task-only structure (for compatibility)
                    listener_info.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await listener_info

            except Exception as e:
                logger.error(f"Error cleaning up CAN listener: {e}")

        self._listeners = []

    @property
    def health(self) -> str:
        """Return the health status of the feature."""
        if not self.enabled:
            return "healthy"  # Disabled is considered healthy

        if self._is_running:
            return "healthy"

        return "failed"

    @property
    def health_details(self) -> dict[str, Any]:
        """Return detailed health information for diagnostics."""
        if not self.enabled:
            return {"status": "disabled", "reason": "Feature not enabled"}

        if self._is_running:
            details = {"status": "healthy"}
            if self.config["simulate"]:
                details["mode"] = "simulation"
                details["description"] = "Running in simulation mode"
            else:
                details["mode"] = "production"
                details["description"] = "Connected to CAN interfaces"
            return details

        return {"status": "unhealthy", "reason": "CAN bus not running"}

    # CAN message sending is now handled by CANService

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
            from backend.services.feature_manager import get_feature_manager
            from backend.websocket.entity_integration import notify_entity_update

            # Get entity manager from feature manager
            feature_manager = get_feature_manager()
            entity_manager_feature = feature_manager.get_feature("entity_manager")
            if entity_manager_feature is None:
                logger.warning("EntityManager feature not found in feature manager")
                return

            entity_manager = entity_manager_feature.get_entity_manager()
            entity = entity_manager.get_entity(entity_id)

            if not entity:
                logger.warning(f"Entity {entity_id} not found in entity manager")
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
                logger.debug(f"Updated entity {entity_id} state from CAN message")

                # Broadcast the update via WebSocket
                await notify_entity_update(entity_id, updated_entity.to_dict())

                # Check if this completes a pending command (for optimistic UI updates)
                await self._check_pending_command_completion(entity_id, payload)
            else:
                logger.warning(f"Failed to update entity {entity_id} state")

        except Exception as e:
            logger.error(f"Error updating entity {entity_id} from CAN message: {e}", exc_info=True)

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
                f"Light state: operating_status={operating_status}, brightness={brightness_pct}%, state={state_str}"
            )

        except Exception as e:
            logger.error(f"Error processing light state: {e}")
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
            from backend.core.state import app_state

            # Get the timestamp from the payload
            update_timestamp = payload.get("timestamp", time.time())

            # Check if there are any pending commands for this entity
            # This will help correlate commands with responses for UI feedback
            pending_commands = [
                cmd
                for cmd in app_state.pending_commands
                if cmd.get("entity_id") == entity_id
                and (update_timestamp - cmd.get("timestamp", 0)) < 5.0  # Within 5 seconds
            ]

            if pending_commands:
                logger.debug(
                    f"Found {len(pending_commands)} pending commands for {entity_id}, state update may complete them"
                )

                # Mark commands as potentially completed
                # The actual command correlation is handled by the app_state.try_group_response method
                for _cmd in pending_commands:
                    app_state.try_group_response(payload)

        except Exception as e:
            logger.error(f"Error checking pending command completion: {e}")

    async def _process_message(self, msg: dict[str, Any]) -> None:
        """
        Process an incoming CAN message.

        This method would be called by the CAN bus listener when a message is received.
        It processes the message using RVC decoding for logging and analysis.

        Args:
            msg: The CAN message as a dictionary with keys like arbitration_id, data, etc.
        """
        try:
            # Extract message data
            arbitration_id = msg.get("arbitration_id")
            data = msg.get("data")
            _ = msg.get("timestamp", time.time())  # Keep for potential future use

            if arbitration_id is None or data is None:
                logger.warning("Received invalid CAN message")
                return

            # Convert data to bytes if it's not already
            if isinstance(data, str):
                data = bytes.fromhex(data)
            elif isinstance(data, bytearray):
                data = bytes(data)  # Convert bytearray to bytes
            elif not isinstance(data, bytes):
                logger.warning(f"Unexpected data type: {type(data)}")
                return

            # Log the message at debug level
            logger.debug(f"CAN message received: id=0x{arbitration_id:x}, data={data.hex()}")

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
                        logger.info(f"Decoded Product ID: {decoded}")
                        # TODO: Update entity with product information
                    else:
                        logger.debug(f"Reassembled multi-packet message for PGN {target_pgn:05X}")

                # Don't process transport protocol messages further
                return

            # Try to decode the message using RVC decoder
            if self.decoder_map and arbitration_id in self.decoder_map:
                try:
                    entry = self.decoder_map[arbitration_id]
                    decoded_data, raw_data = decode_payload(entry, data)

                    # Extract DGN and instance for device lookup
                    dgn_hex = entry.get("dgn_hex")
                    instance = raw_data.get("instance") if raw_data else None

                    logger.debug(
                        f"Decoded CAN message: DGN={dgn_hex}, instance={instance}, "
                        f"decoded={decoded_data}, raw={raw_data}"
                    )

                    # Check if this maps to a known device/entity
                    if dgn_hex and instance is not None:
                        device_key = (dgn_hex.upper(), str(instance))
                        device_config = self.device_lookup.get(device_key)

                        if device_config:
                            entity_id = device_config.get("entity_id")
                            if entity_id:
                                logger.debug(f"Mapped to entity: {entity_id}")
                                # Update entity state with the decoded CAN message
                                await self._update_entity_from_can_message(
                                    entity_id, device_config, decoded_data, raw_data, msg
                                )
                        else:
                            logger.debug(f"Unmapped device: {dgn_hex}:{instance}")
                            # Analyze unmapped but decodable message for patterns
                            if self.pattern_engine:
                                try:
                                    pattern_analysis = await self.pattern_engine.analyze_message(
                                        arbitration_id, data, msg.get("timestamp", time.time())
                                    )
                                    logger.debug(f"Pattern analysis for unmapped {dgn_hex}:{instance}: {pattern_analysis}")
                                except Exception as pattern_error:
                                    logger.debug(f"Pattern analysis error: {pattern_error}")

                except Exception as decode_error:
                    logger.error(f"Error decoding CAN message: {decode_error}")
            else:
                logger.debug(f"No decoder found for arbitration ID 0x{arbitration_id:x}")
                # Analyze completely unknown message for patterns
                if self.pattern_engine:
                    try:
                        pattern_analysis = await self.pattern_engine.analyze_message(
                            arbitration_id, data, msg.get("timestamp", time.time())
                        )
                        logger.debug(f"Pattern analysis for unknown 0x{arbitration_id:X}: {pattern_analysis}")
                    except Exception as pattern_error:
                        logger.debug(f"Pattern analysis error: {pattern_error}")

        except Exception as e:
            logger.error(f"Error processing CAN message: {e}")

    # CAN message writing is now handled by CANService

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

        while self._is_running:
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
                                logger.debug(f"Error generating signal data: {e}")
                    else:
                        # No signals defined, use some default pattern
                        for i in range(entry_length):
                            data[i] = (counter + i * 13) % 256

                    data = bytes(data)
                    logger.debug(f"Simulating message from decoder: {entry.get('name', 'Unknown')}")

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
                logger.error(f"Error in CAN message simulation: {e}")
                await asyncio.sleep(5)  # Longer sleep on error


# Singleton instance and accessor functions
_can_feature: CANBusFeature | None = None


def initialize_can_feature(
    config: dict[str, Any] | None = None,
) -> CANBusFeature:
    """
    Initialize the CAN feature singleton.

    Args:
        config: Optional configuration dictionary

    Returns:
        The initialized CANBusFeature instance
    """
    global _can_feature

    if _can_feature is None:
        _can_feature = CANBusFeature(
            config=config,
        )

    return _can_feature


def get_can_feature() -> CANBusFeature:
    """
    Get the CAN feature singleton instance.

    Returns:
        The CANBusFeature instance

    Raises:
        RuntimeError: If the CAN feature has not been initialized
    """
    if _can_feature is None:
        msg = "CAN feature has not been initialized. Call initialize_can_feature() first."
        raise RuntimeError(
            msg
        )

    return _can_feature
