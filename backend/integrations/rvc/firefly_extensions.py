"""
Firefly RV Systems Extensions for RV-C Protocol

This module provides Firefly-specific extensions including:
- Proprietary DGN decoding and encoding
- Message multiplexing/demultiplexing
- Safety interlock monitoring
- CAN Detective integration (optional)
- State-driven control logic

Based on research into Firefly Integrations RV systems, this implementation
handles their proprietary extensions to the standard RV-C protocol.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.core.config import FireflySettings, get_firefly_settings

logger = logging.getLogger(__name__)


class FireflyDGNType(Enum):
    """Firefly-specific DGN types based on research findings."""

    STANDARD_RVC = "standard"
    FIREFLY_CUSTOM = "firefly_custom"
    MULTIPLEXED = "multiplexed"
    SAFETY_INTERLOCK = "safety_interlock"
    CAN_DETECTIVE = "can_detective"


class FireflyComponentType(Enum):
    """Firefly component types for classification."""

    LIGHTING = "lighting"
    CLIMATE = "climate"
    SLIDES = "slides"
    AWNINGS = "awnings"
    TANKS = "tanks"
    INVERTERS = "inverters"
    GENERATORS = "generators"
    TRANSFER_SWITCHES = "transfer_switches"
    PUMPS = "pumps"
    SAFETY_SYSTEMS = "safety_systems"


class CommandPreconditionState(Enum):
    """Safety interlock states for Firefly systems."""

    UNKNOWN = "unknown"
    SAFE = "safe"
    UNSAFE = "unsafe"
    BYPASSED = "bypassed"
    FAULT = "fault"


@dataclass
class FireflyMessage:
    """Represents a decoded Firefly message."""

    dgn: int
    source_address: int
    data: bytes
    timestamp: float
    dgn_type: FireflyDGNType
    component_type: FireflyComponentType | None = None
    multiplexed_data: dict[str, Any] | None = None
    guardrail_status: CommandPreconditionState | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class MultiplexBuffer:
    """Buffer for assembling multiplexed messages."""

    dgn: int
    source_address: int
    sequence_id: int
    total_parts: int
    received_parts: dict[int, bytes] = field(default_factory=dict)
    first_received: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    def is_complete(self) -> bool:
        """Check if all parts of the multiplexed message have been received."""
        return len(self.received_parts) == self.total_parts

    def is_expired(self, timeout_ms: int) -> bool:
        """Check if the buffer has expired."""
        return (time.time() - self.first_received) * 1000 > timeout_ms


@dataclass
class CommandPrecondition:
    """Represents a safety interlock requirement."""

    component: str
    required_conditions: list[str]
    current_state: CommandPreconditionState
    last_check: float
    override_active: bool = False
    fault_reason: str | None = None


class FireflyDecoder:
    """
    Firefly-specific RV-C message decoder with proprietary extensions.

    This decoder handles:
    - Standard RV-C messages with Firefly-specific interpretations
    - Firefly proprietary DGNs
    - Multiplexed message assembly
    - Safety interlock monitoring
    - State-driven control validation
    """

    def __init__(self, settings: FireflySettings | None = None):
        """Initialize the Firefly decoder."""
        self.settings = settings or get_firefly_settings()
        self.multiplex_buffers: dict[str, MultiplexBuffer] = {}
        self.safety_interlocks: dict[str, CommandPrecondition] = {}
        self.component_states: dict[str, dict[str, Any]] = {}
        self._initialize_safety_interlocks()

        logger.info("Firefly decoder initialized")

    def _initialize_safety_interlocks(self) -> None:
        """Initialize safety interlocks based on configuration."""
        for component in self.settings.safety_interlock_components:
            required_conditions = self.settings.required_interlocks.get(component, [])
            self.safety_interlocks[component] = CommandPrecondition(
                component=component,
                required_conditions=required_conditions,
                current_state=CommandPreconditionState.UNKNOWN,
                last_check=time.time(),
            )

    def decode_message(
        self, dgn: int, source_address: int, data: bytes, timestamp: float, can_id: int
    ) -> FireflyMessage | None:
        """
        Decode a Firefly RV-C message.

        Args:
            dgn: Data Group Number
            source_address: CAN source address
            data: Raw message data
            timestamp: Message timestamp
            can_id: Full CAN ID

        Returns:
            FireflyMessage object or None if message couldn't be decoded
        """
        try:
            # Classify the DGN type
            dgn_type = self._classify_dgn(dgn)

            # Create base message object
            message = FireflyMessage(
                dgn=dgn,
                source_address=source_address,
                data=data,
                timestamp=timestamp,
                dgn_type=dgn_type,
            )

            # Handle different message types
            if dgn_type == FireflyDGNType.MULTIPLEXED:
                return self._handle_multiplexed_message(message)
            if dgn_type == FireflyDGNType.FIREFLY_CUSTOM:
                return self._decode_firefly_custom_dgn(message)
            if dgn_type == FireflyDGNType.SAFETY_INTERLOCK:
                return self._decode_safety_interlock(message)
            return self._decode_standard_rvc_with_firefly_extensions(message)

        except Exception as e:
            logger.error(f"Error decoding Firefly message DGN {dgn:04X}: {e}")
            return None

    def _classify_dgn(self, dgn: int) -> FireflyDGNType:
        """Classify a DGN based on Firefly-specific patterns."""
        # Check for Firefly custom DGN range
        if self.settings.custom_dgn_range_start <= dgn <= self.settings.custom_dgn_range_end:
            return FireflyDGNType.FIREFLY_CUSTOM

        # Check for known multiplexed DGNs (tank levels, status aggregation)
        multiplexed_dgns = [0x1FFB7, 0x1FFB6, 0x1FEF5]  # Tank, temp, generic status
        if dgn in multiplexed_dgns:
            return FireflyDGNType.MULTIPLEXED

        # Check for safety interlock DGNs
        safety_dgns = [0x1FECA, 0x1FED9]  # Diagnostic, safety status
        if dgn in safety_dgns:
            return FireflyDGNType.SAFETY_INTERLOCK

        return FireflyDGNType.STANDARD_RVC

    def _handle_multiplexed_message(self, message: FireflyMessage) -> FireflyMessage | None:
        """Handle Firefly multiplexed message assembly."""
        if not self.settings.enable_multiplexing:
            return None

        try:
            # Extract multiplex header (first 2 bytes typically)
            if len(message.data) < 2:
                return None

            sequence_id = message.data[0] & 0x0F
            total_parts = (message.data[0] & 0xF0) >> 4
            part_number = message.data[1] & 0x0F

            # Create buffer key
            buffer_key = f"{message.dgn}_{message.source_address}_{sequence_id}"

            # Initialize buffer if needed
            if buffer_key not in self.multiplex_buffers:
                self.multiplex_buffers[buffer_key] = MultiplexBuffer(
                    dgn=message.dgn,
                    source_address=message.source_address,
                    sequence_id=sequence_id,
                    total_parts=total_parts,
                )

            # Add this part to the buffer
            buffer = self.multiplex_buffers[buffer_key]
            buffer.received_parts[part_number] = message.data[2:]  # Skip header
            buffer.last_updated = time.time()

            # Check if message is complete
            if buffer.is_complete():
                # Assemble complete message
                assembled_data = bytearray()
                for i in range(total_parts):
                    if i in buffer.received_parts:
                        assembled_data.extend(buffer.received_parts[i])

                # Clean up buffer
                del self.multiplex_buffers[buffer_key]

                # Decode assembled message
                message.multiplexed_data = self._decode_multiplexed_data(
                    message.dgn, bytes(assembled_data)
                )
                return message

            # Message incomplete, clean up expired buffers
            self._cleanup_expired_buffers()
            return None

        except Exception as e:
            logger.error(f"Error handling multiplexed message: {e}")
            return None

    def _decode_multiplexed_data(self, dgn: int, data: bytes) -> dict[str, Any]:
        """Decode assembled multiplexed data based on DGN."""
        decoded = {}

        if dgn == 0x1FFB7:  # Tank levels
            decoded.update(self._decode_tank_levels(data))
        elif dgn == 0x1FFB6:  # Temperature data
            decoded.update(self._decode_temperature_data(data))
        elif dgn == 0x1FEF5:  # Generic status
            decoded.update(self._decode_generic_status(data))

        return decoded

    def _decode_tank_levels(self, data: bytes) -> dict[str, Any]:
        """Decode Firefly tank level data."""
        tanks = {}

        # Firefly typically packs multiple tank readings
        # Format: [tank_id, level_percent, capacity_gallons, ...]
        for i in range(0, len(data), 4):
            if i + 3 < len(data):
                tank_id = data[i]
                level_percent = data[i + 1]
                capacity_high = data[i + 2]
                capacity_low = data[i + 3]
                capacity_gallons = (capacity_high << 8) | capacity_low

                tank_name = self._get_tank_name(tank_id)
                tanks[tank_name] = {
                    "level_percent": level_percent if level_percent != 0xFF else None,
                    "capacity_gallons": capacity_gallons if capacity_gallons != 0xFFFF else None,
                    "level_gallons": (level_percent * capacity_gallons / 100)
                    if level_percent != 0xFF and capacity_gallons != 0xFFFF
                    else None,
                }

        return {"tanks": tanks}

    def _decode_temperature_data(self, data: bytes) -> dict[str, Any]:
        """Decode Firefly temperature sensor data."""
        temperatures = {}

        # Format: [sensor_id, temp_high, temp_low, ...]
        for i in range(0, len(data), 3):
            if i + 2 < len(data):
                sensor_id = data[i]
                temp_raw = (data[i + 1] << 8) | data[i + 2]

                # Convert from raw to actual temperature (Firefly specific scaling)
                temp_celsius = (temp_raw - 8736) / 128.0 if temp_raw != 0xFFFF else None
                temp_fahrenheit = (temp_celsius * 9 / 5 + 32) if temp_celsius is not None else None

                sensor_name = self._get_temperature_sensor_name(sensor_id)
                temperatures[sensor_name] = {
                    "celsius": temp_celsius,
                    "fahrenheit": temp_fahrenheit,
                    "raw": temp_raw,
                }

        return {"temperatures": temperatures}

    def _decode_generic_status(self, data: bytes) -> dict[str, Any]:
        """Decode Firefly generic status data."""
        status = {}

        if len(data) >= 8:
            # Firefly status typically includes system health, power status, etc.
            status["system_health"] = data[0]
            status["power_status"] = data[1]
            status["communication_health"] = data[2]
            status["last_error_code"] = (data[3] << 8) | data[4]
            status["uptime_hours"] = (data[5] << 16) | (data[6] << 8) | data[7]

        return {"system_status": status}

    def _decode_firefly_custom_dgn(self, message: FireflyMessage) -> FireflyMessage:
        """Decode Firefly proprietary DGNs."""
        if not self.settings.enable_custom_dgns:
            return message

        # Firefly custom DGN patterns based on research
        custom_dgn_patterns = {
            0x1F100: self._decode_firefly_lighting_control,
            0x1F101: self._decode_firefly_climate_control,
            0x1F102: self._decode_firefly_slide_awning_control,
            0x1F103: self._decode_firefly_power_management,
            0x1F104: self._decode_firefly_diagnostic_extended,
        }

        decoder_func = custom_dgn_patterns.get(message.dgn)
        if decoder_func:
            try:
                message.signals = decoder_func(message.data)
                message.component_type = self._get_component_type_for_dgn(message.dgn)
            except Exception as e:
                logger.error(f"Error decoding custom DGN {message.dgn:04X}: {e}")
                message.validation_errors.append(f"Custom DGN decode error: {e}")

        return message

    def _decode_firefly_lighting_control(self, data: bytes) -> dict[str, Any]:
        """Decode Firefly lighting control messages."""
        if len(data) < 8:
            return {}

        return {
            "lighting_zone": data[0],
            "command_type": data[1],  # 0=off, 1=on, 2=dim, 3=scene
            "brightness_level": data[2],
            "scene_id": data[3],
            "fade_time_ms": (data[4] << 8) | data[5],
            "group_mask": data[6],
            "status_flags": data[7],
        }

    def _decode_firefly_climate_control(self, data: bytes) -> dict[str, Any]:
        """Decode Firefly climate control messages."""
        if len(data) < 8:
            return {}

        return {
            "zone_id": data[0],
            "target_temp_f": data[1],
            "current_temp_f": data[2],
            "hvac_mode": data[3],  # 0=off, 1=heat, 2=cool, 3=auto
            "fan_speed": data[4],  # 0-100%
            "humidity_percent": data[5],
            "system_status": data[6],
            "fault_codes": data[7],
        }

    def _decode_firefly_slide_awning_control(self, data: bytes) -> dict[str, Any]:
        """Decode Firefly slide/awning control messages."""
        if len(data) < 8:
            return {}

        return {
            "device_id": data[0],
            "device_type": data[1],  # 0=slide, 1=awning, 2=jack
            "position_percent": data[2],
            "target_position": data[3],
            "movement_state": data[4],  # 0=stopped, 1=extending, 2=retracting
            "guardrail_status": data[5],
            "current_draw_amps": data[6],
            "fault_flags": data[7],
        }

    def _decode_firefly_power_management(self, data: bytes) -> dict[str, Any]:
        """Decode Firefly power management messages."""
        if len(data) < 8:
            return {}

        return {
            "battery_voltage": ((data[0] << 8) | data[1]) / 100.0,
            "battery_current": ((data[2] << 8) | data[3]) / 10.0,
            "inverter_status": data[4],
            "shore_power_status": data[5],
            "generator_status": data[6],
            "load_management_flags": data[7],
        }

    def _decode_firefly_diagnostic_extended(self, data: bytes) -> dict[str, Any]:
        """Decode Firefly extended diagnostic messages."""
        if len(data) < 8:
            return {}

        return {
            "diagnostic_source": data[0],
            "error_category": data[1],
            "error_severity": data[2],
            "error_code": (data[3] << 8) | data[4],
            "occurrence_count": data[5],
            "time_since_first": (data[6] << 8) | data[7],
        }

    def _decode_safety_interlock(self, message: FireflyMessage) -> FireflyMessage:
        """Decode safety interlock messages."""
        if not self.settings.enable_state_interlocks:
            return message

        try:
            # Extract safety status information
            if len(message.data) >= 4:
                component_id = message.data[0]
                safety_state = CommandPreconditionState(
                    message.data[1] if message.data[1] < 5 else 0
                )
                conditions_met = message.data[2]
                fault_code = message.data[3]

                component_name = self._get_component_name(component_id)

                # Update safety interlock status
                if component_name in self.safety_interlocks:
                    interlock = self.safety_interlocks[component_name]
                    interlock.current_state = safety_state
                    interlock.last_check = time.time()
                    if fault_code != 0:
                        interlock.fault_reason = f"Fault code: {fault_code}"

                message.guardrail_status = safety_state
                message.signals = {
                    "component": component_name,
                    "safety_state": safety_state.value,
                    "conditions_met": conditions_met,
                    "fault_code": fault_code,
                }

        except Exception as e:
            logger.error(f"Error decoding safety interlock: {e}")
            message.validation_errors.append(f"Safety interlock decode error: {e}")

        return message

    def _decode_standard_rvc_with_firefly_extensions(
        self, message: FireflyMessage
    ) -> FireflyMessage:
        """Decode standard RV-C messages with Firefly-specific interpretations."""
        # This would integrate with the existing RVC decoder but add Firefly-specific
        # interpretations for fields that Firefly uses differently

        # For now, return the message as-is since the main RVC decoder handles standard messages
        return message

    def validate_command_preconditions(
        self, component: str, operation: str
    ) -> tuple[bool, list[str]]:
        """
        Validate safety interlocks before allowing an operation.

        Args:
            component: Component name (e.g., "slides", "awnings")
            operation: Operation type (e.g., "extend", "retract")

        Returns:
            Tuple of (is_safe, list_of_violations)
        """
        if not self.settings.enable_state_interlocks:
            return True, []

        violations = []

        if component not in self.safety_interlocks:
            return True, []  # No interlocks defined for this component

        interlock = self.safety_interlocks[component]

        # Check if interlock is in a safe state
        if interlock.current_state == CommandPreconditionState.UNSAFE:
            violations.append(f"{component} safety interlock is in UNSAFE state")
        elif interlock.current_state == CommandPreconditionState.FAULT:
            violations.append(f"{component} safety interlock has FAULT: {interlock.fault_reason}")
        elif interlock.current_state == CommandPreconditionState.UNKNOWN:
            violations.append(f"{component} safety interlock state is UNKNOWN")

        # Check specific conditions (this would integrate with vehicle state monitoring)
        for condition in interlock.required_conditions:
            if not self._check_safety_condition(condition):
                violations.append(f"Safety condition not met: {condition}")

        return len(violations) == 0, violations

    def _check_safety_condition(self, condition: str) -> bool:
        """
        Check a specific safety condition.

        This would integrate with the main vehicle state management to check
        conditions like park_brake, engine_off, wind_speed, etc.
        """
        # Placeholder implementation - would integrate with actual vehicle state
        vehicle_state = self.component_states.get("vehicle", {})

        condition_checks = {
            "park_brake": vehicle_state.get("park_brake_set", False),
            "engine_off": not vehicle_state.get("engine_running", True),
            "wind_speed": vehicle_state.get("wind_speed_mph", 0) < 15,
            "vehicle_level": vehicle_state.get("is_level", False),
        }

        return condition_checks.get(condition, False)

    def _cleanup_expired_buffers(self) -> None:
        """Clean up expired multiplex buffers."""
        expired_keys = []

        for key, buffer in self.multiplex_buffers.items():
            if buffer.is_expired(self.settings.multiplex_timeout_ms):
                expired_keys.append(key)

        for key in expired_keys:
            logger.debug(f"Cleaning up expired multiplex buffer: {key}")
            del self.multiplex_buffers[key]

    def _get_tank_name(self, tank_id: int) -> str:
        """Map tank ID to human-readable name."""
        tank_names = {
            0: "fresh_water",
            1: "gray_water",
            2: "black_water",
            3: "propane",
            4: "diesel_fuel",
            5: "gasoline_fuel",
            6: "hydraulic_fluid",
            7: "engine_oil",
        }
        return tank_names.get(tank_id, f"tank_{tank_id}")

    def _get_temperature_sensor_name(self, sensor_id: int) -> str:
        """Map sensor ID to human-readable name."""
        sensor_names = {
            0: "interior_ambient",
            1: "exterior_ambient",
            2: "refrigerator",
            3: "freezer",
            4: "hot_water_heater",
            5: "engine_coolant",
            6: "transmission_fluid",
            7: "exhaust_gas",
        }
        return sensor_names.get(sensor_id, f"sensor_{sensor_id}")

    def _get_component_name(self, component_id: int) -> str:
        """Map component ID to human-readable name."""
        component_names = {
            0: "slides",
            1: "awnings",
            2: "leveling_jacks",
            3: "entry_door",
            4: "generator",
            5: "inverter",
            6: "main_breaker",
        }
        return component_names.get(component_id, f"component_{component_id}")

    def _get_component_type_for_dgn(self, dgn: int) -> FireflyComponentType | None:
        """Get component type based on DGN."""
        dgn_to_component = {
            0x1F100: FireflyComponentType.LIGHTING,
            0x1F101: FireflyComponentType.CLIMATE,
            0x1F102: FireflyComponentType.SLIDES,
            0x1F103: FireflyComponentType.INVERTERS,
            0x1F104: FireflyComponentType.SAFETY_SYSTEMS,
        }
        return dgn_to_component.get(dgn)

    def get_decoder_status(self) -> dict[str, Any]:
        """Get comprehensive decoder status."""
        return {
            "enabled": self.settings.enabled,
            "configuration": {
                "multiplexing_enabled": self.settings.enable_multiplexing,
                "custom_dgns_enabled": self.settings.enable_custom_dgns,
                "safety_interlocks_enabled": self.settings.enable_state_interlocks,
                "can_detective_integration": self.settings.enable_can_detective_integration,
            },
            "runtime_status": {
                "active_multiplex_buffers": len(self.multiplex_buffers),
                "safety_interlocks_count": len(self.safety_interlocks),
                "component_states_tracked": len(self.component_states),
            },
            "multiplex_buffers": [
                {
                    "key": key,
                    "dgn": buffer.dgn,
                    "parts_received": len(buffer.received_parts),
                    "total_parts": buffer.total_parts,
                    "age_ms": (time.time() - buffer.first_received) * 1000,
                }
                for key, buffer in self.multiplex_buffers.items()
            ],
            "safety_interlocks": {
                name: {
                    "component": interlock.component,
                    "state": interlock.current_state.value,
                    "required_conditions": interlock.required_conditions,
                    "last_check_age_s": time.time() - interlock.last_check,
                    "override_active": interlock.override_active,
                    "fault_reason": interlock.fault_reason,
                }
                for name, interlock in self.safety_interlocks.items()
            },
        }

    def update_vehicle_state(self, component: str, state_data: dict[str, Any]) -> None:
        """Update vehicle state for safety interlock checking."""
        if component not in self.component_states:
            self.component_states[component] = {}

        self.component_states[component].update(state_data)
        logger.debug(f"Updated {component} state: {state_data}")


class FireflyEncoder:
    """
    Firefly-specific RV-C message encoder for sending commands.

    This encoder handles:
    - Standard RV-C command encoding with Firefly extensions
    - Firefly proprietary command DGNs
    - Safety interlock validation before command transmission
    - State-driven command sequences
    """

    def __init__(self, settings: FireflySettings | None = None):
        """Initialize the Firefly encoder."""
        self.settings = settings or get_firefly_settings()
        self.decoder = FireflyDecoder(settings)  # For safety validation

        logger.info("Firefly encoder initialized")

    def encode_command(
        self,
        component: str,
        operation: str,
        parameters: dict[str, Any],
        validate_safety: bool = True,
    ) -> list[tuple[int, int, bytes]]:
        """
        Encode a Firefly command into CAN messages.

        Args:
            component: Component to control (e.g., "lighting", "slides")
            operation: Operation to perform (e.g., "set_brightness", "extend")
            parameters: Operation parameters
            validate_safety: Whether to validate safety interlocks

        Returns:
            List of tuples (dgn, source_address, data) representing CAN messages
        """
        messages = []

        try:
            # Validate safety interlocks if enabled
            if validate_safety and self.settings.enable_state_interlocks:
                is_safe, violations = self.decoder.validate_command_preconditions(
                    component, operation
                )
                if not is_safe:
                    logger.warning(f"Command blocked due to safety violations: {violations}")
                    return []

            # Route to appropriate encoder based on component
            if component == "lighting":
                messages.extend(self._encode_lighting_command(operation, parameters))
            elif component == "climate":
                messages.extend(self._encode_climate_command(operation, parameters))
            elif component in ["slides", "awnings"]:
                messages.extend(self._encode_slide_awning_command(component, operation, parameters))
            elif component == "power":
                messages.extend(self._encode_power_command(operation, parameters))
            else:
                logger.warning(f"Unknown component for Firefly encoding: {component}")

        except Exception as e:
            logger.error(f"Error encoding Firefly command: {e}")

        return messages

    def _encode_lighting_command(
        self, operation: str, parameters: dict[str, Any]
    ) -> list[tuple[int, int, bytes]]:
        """Encode Firefly lighting commands."""
        messages = []

        if operation == "set_brightness":
            zone = parameters.get("zone", 0)
            brightness = parameters.get("brightness", 0)
            fade_time = parameters.get("fade_time_ms", 0)

            # Use Firefly custom lighting DGN
            data = bytearray(8)
            data[0] = zone
            data[1] = 2  # Dim command
            data[2] = max(0, min(100, brightness))
            data[3] = 0  # No scene
            data[4] = (fade_time >> 8) & 0xFF
            data[5] = fade_time & 0xFF
            data[6] = 0xFF  # All groups
            data[7] = 0  # Status flags

            messages.append((0x1F100, 0x17, bytes(data)))

        elif operation == "set_scene":
            scene_id = parameters.get("scene_id", 0)

            data = bytearray(8)
            data[0] = 0xFF  # All zones
            data[1] = 3  # Scene command
            data[2] = 0  # No brightness override
            data[3] = scene_id
            data[4:8] = [0] * 4

            messages.append((0x1F100, 0x17, bytes(data)))

        return messages

    def _encode_climate_command(
        self, operation: str, parameters: dict[str, Any]
    ) -> list[tuple[int, int, bytes]]:
        """Encode Firefly climate commands."""
        messages = []

        if operation == "set_temperature":
            zone = parameters.get("zone", 0)
            target_temp = parameters.get("temperature_f", 70)
            mode = parameters.get("mode", "auto")

            mode_map = {"off": 0, "heat": 1, "cool": 2, "auto": 3}
            mode_value = mode_map.get(mode, 3)

            data = bytearray(8)
            data[0] = zone
            data[1] = max(50, min(90, target_temp))
            data[2] = 0  # Current temp (read-only)
            data[3] = mode_value
            data[4] = parameters.get("fan_speed", 50)
            data[5:8] = [0] * 3

            messages.append((0x1F101, 0x17, bytes(data)))

        return messages

    def _encode_slide_awning_command(
        self, component: str, operation: str, parameters: dict[str, Any]
    ) -> list[tuple[int, int, bytes]]:
        """Encode Firefly slide/awning commands."""
        messages = []

        device_id = parameters.get("device_id", 0)
        device_type = 0 if component == "slides" else 1

        if operation in ["extend", "retract", "stop"]:
            target_position = parameters.get("position", 100 if operation == "extend" else 0)
            if operation == "stop":
                target_position = parameters.get("current_position", 0)

            data = bytearray(8)
            data[0] = device_id
            data[1] = device_type
            data[2] = 0  # Current position (read-only)
            data[3] = max(0, min(100, target_position))
            data[4] = 1 if operation == "extend" else (2 if operation == "retract" else 0)
            data[5:8] = [0] * 3

            messages.append((0x1F102, 0x17, bytes(data)))

        return messages

    def _encode_power_command(
        self, operation: str, parameters: dict[str, Any]
    ) -> list[tuple[int, int, bytes]]:
        """Encode Firefly power management commands."""
        messages = []

        if operation == "inverter_control":
            inverter_on = parameters.get("enable", False)

            data = bytearray(8)
            data[0:4] = [0] * 4  # Voltage/current are read-only
            data[4] = 1 if inverter_on else 0
            data[5:8] = [0] * 3

            messages.append((0x1F103, 0x17, bytes(data)))

        return messages


class FireflyCANDetectiveIntegration:
    """
    Optional integration with Firefly's CAN Detective tool.

    This provides enhanced debugging and analysis capabilities when
    CAN Detective is available.
    """

    def __init__(self, settings: FireflySettings | None = None):
        """Initialize CAN Detective integration."""
        self.settings = settings or get_firefly_settings()
        self.enabled = (
            self.settings.enable_can_detective_integration
            and self.settings.can_detective_path is not None
        )

        if self.enabled:
            logger.info("Firefly CAN Detective integration enabled")
        else:
            logger.debug("Firefly CAN Detective integration disabled or not configured")

    def analyze_message_pattern(self, messages: list[FireflyMessage]) -> dict[str, Any]:
        """Analyze message patterns using CAN Detective logic."""
        if not self.enabled:
            return {}

        # This would integrate with actual CAN Detective if available
        # For now, provide basic pattern analysis

        dgn_counts = {}
        source_counts = {}

        for msg in messages:
            dgn_counts[msg.dgn] = dgn_counts.get(msg.dgn, 0) + 1
            source_counts[msg.source_address] = source_counts.get(msg.source_address, 0) + 1

        most_frequent_dgn = None
        most_active_source = None

        if dgn_counts:
            most_frequent_dgn = max(dgn_counts.keys(), key=lambda x: dgn_counts[x])
        if source_counts:
            most_active_source = max(source_counts.keys(), key=lambda x: source_counts[x])

        return {
            "message_count": len(messages),
            "unique_dgns": len(dgn_counts),
            "unique_sources": len(source_counts),
            "most_frequent_dgn": most_frequent_dgn,
            "most_active_source": most_active_source,
            "dgn_distribution": dgn_counts,
            "source_distribution": source_counts,
        }

    def export_can_detective_format(self, messages: list[FireflyMessage]) -> str:
        """Export messages in CAN Detective compatible format."""
        if not self.enabled:
            return ""

        # Export in a format that CAN Detective can import
        lines = ["# Firefly message export for CAN Detective analysis"]
        lines.append("# Timestamp,DGN,Source,Data")

        for msg in messages:
            data_hex = msg.data.hex().upper()
            lines.append(f"{msg.timestamp:.3f},{msg.dgn:04X},{msg.source_address:02X},{data_hex}")

        return "\n".join(lines)
