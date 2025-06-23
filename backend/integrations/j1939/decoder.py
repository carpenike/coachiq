"""
J1939 protocol decoder implementation.

This module provides comprehensive J1939 message decoding functionality
for engine, transmission, and chassis systems, with manufacturer-specific
extensions for Cummins engines and Allison transmissions.

Key features:
- Standard J1939 PGN decoding
- Multi-manufacturer support (Cummins, Allison, Spartan)
- Real-time performance optimization
- Security validation and monitoring
- Protocol bridging capabilities
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple

from backend.core.config import Settings

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    """J1939 message priority levels for processing optimization."""

    CRITICAL = 1  # Engine critical alarms, transmission faults
    HIGH = 2  # Engine speed, transmission status
    NORMAL = 3  # General engine parameters
    LOW = 4  # Diagnostic readiness
    BACKGROUND = 5  # Statistics, trip data


class SystemType(Enum):
    """J1939 system types for message classification."""

    ENGINE = "engine"
    TRANSMISSION = "transmission"
    CHASSIS = "chassis"
    BRAKES = "brakes"
    EXHAUST = "exhaust"
    FUEL = "fuel"
    DIAGNOSTICS = "diagnostics"
    UNKNOWN = "unknown"


@dataclass
class J1939Message:
    """Decoded J1939 message structure."""

    pgn: int
    source_address: int
    data: bytes
    priority: int
    system_type: SystemType
    decoded_signals: dict[str, Any]
    raw_signals: dict[str, int]
    manufacturer: str | None = None
    timestamp: float | None = None


class SignalDefinition(NamedTuple):
    """J1939 signal definition structure."""

    name: str
    start_bit: int
    length: int
    scale: float
    offset: float
    units: str
    min_value: float | None = None
    max_value: float | None = None


class PGNDefinition(NamedTuple):
    """J1939 PGN definition structure."""

    pgn: int
    name: str
    system_type: SystemType
    priority: MessagePriority
    data_length: int
    signals: list[SignalDefinition]
    manufacturer: str | None = None


class J1939Decoder:
    """
    J1939 protocol decoder with manufacturer extensions.

    Provides comprehensive decoding of J1939 messages including:
    - Standard SAE J1939 PGNs
    - Cummins engine-specific PGNs
    - Allison transmission PGNs
    - Chassis system PGNs (Spartan K2, etc.)
    """

    def __init__(self, settings: Settings):
        """
        Initialize the J1939 decoder.

        Args:
            settings: Application settings containing J1939 configuration
        """
        self.settings = settings
        self.j1939_config = settings.j1939
        self._pgn_definitions: dict[int, PGNDefinition] = {}
        self._manufacturer_extensions: dict[str, dict[int, PGNDefinition]] = {}
        self._load_standard_pgns()
        if self.j1939_config.enable_cummins_extensions:
            self._load_cummins_extensions()
        if self.j1939_config.enable_allison_extensions:
            self._load_allison_extensions()
        if self.j1939_config.enable_chassis_extensions:
            self._load_chassis_extensions()

        logger.info(f"J1939 decoder initialized with {len(self._pgn_definitions)} PGN definitions")

    def decode_message(
        self,
        pgn: int,
        source_address: int,
        data: bytes,
        priority: int = 6,
        timestamp: float | None = None,
    ) -> J1939Message | None:
        """
        Decode a J1939 CAN message.

        Args:
            pgn: Parameter Group Number
            source_address: Source address of the message
            data: Message data bytes
            priority: Message priority (0-7, lower is higher priority)
            timestamp: Optional timestamp

        Returns:
            Decoded J1939Message or None if PGN not recognized
        """
        # Look up PGN definition
        pgn_def = self._get_pgn_definition(pgn)
        if not pgn_def:
            logger.debug(f"Unknown J1939 PGN: 0x{pgn:04X}")
            return None

        # Validate data length
        if len(data) < pgn_def.data_length:
            logger.warning(
                f"Insufficient data for PGN 0x{pgn:04X}: got {len(data)}, need {pgn_def.data_length}"
            )
            return None

        # Decode signals
        try:
            decoded_signals, raw_signals = self._decode_signals(pgn_def, data)
        except Exception as e:
            logger.error(f"Error decoding PGN 0x{pgn:04X}: {e}")
            return None

        return J1939Message(
            pgn=pgn,
            source_address=source_address,
            data=data,
            priority=priority,
            system_type=pgn_def.system_type,
            decoded_signals=decoded_signals,
            raw_signals=raw_signals,
            manufacturer=pgn_def.manufacturer,
            timestamp=timestamp,
        )

    def get_message_priority(self, pgn: int) -> MessagePriority:
        """
        Get the processing priority for a PGN.

        Args:
            pgn: Parameter Group Number

        Returns:
            MessagePriority enum value
        """
        pgn_def = self._get_pgn_definition(pgn)
        if pgn_def:
            return pgn_def.priority

        # Default priority based on PGN ranges
        if pgn in self.j1939_config.priority_critical_pgns:
            return MessagePriority.CRITICAL
        if pgn in self.j1939_config.priority_high_pgns:
            return MessagePriority.HIGH
        return MessagePriority.NORMAL

    def get_system_type(self, pgn: int) -> SystemType:
        """
        Get the system type for a PGN.

        Args:
            pgn: Parameter Group Number

        Returns:
            SystemType enum value
        """
        pgn_def = self._get_pgn_definition(pgn)
        if pgn_def:
            return pgn_def.system_type
        return SystemType.UNKNOWN

    def get_supported_pgns(self) -> list[int]:
        """
        Get list of all supported PGNs.

        Returns:
            List of supported PGN numbers
        """
        return list(self._pgn_definitions.keys())

    def get_pgn_info(self, pgn: int) -> dict[str, Any] | None:
        """
        Get detailed information about a PGN.

        Args:
            pgn: Parameter Group Number

        Returns:
            Dictionary with PGN information or None if not found
        """
        pgn_def = self._get_pgn_definition(pgn)
        if not pgn_def:
            return None

        return {
            "pgn": pgn_def.pgn,
            "name": pgn_def.name,
            "system_type": pgn_def.system_type.value,
            "priority": pgn_def.priority.value,
            "data_length": pgn_def.data_length,
            "manufacturer": pgn_def.manufacturer,
            "signals": [
                {
                    "name": sig.name,
                    "start_bit": sig.start_bit,
                    "length": sig.length,
                    "scale": sig.scale,
                    "offset": sig.offset,
                    "units": sig.units,
                    "min_value": sig.min_value,
                    "max_value": sig.max_value,
                }
                for sig in pgn_def.signals
            ],
        }

    def validate_source_address(self, source_address: int) -> bool:
        """
        Validate J1939 source address against allowed ranges.

        Args:
            source_address: Source address to validate

        Returns:
            True if address is valid, False otherwise
        """
        if not self.j1939_config.enable_address_validation:
            return True

        # J1939 standard address ranges:
        # 0-127: Preferred addresses for specific functions
        # 128-247: Available for arbitrary assignment
        # 248-253: Reserved
        # 254: NULL address
        # 255: Global address

        return 0 <= source_address <= 247

    def _get_pgn_definition(self, pgn: int) -> PGNDefinition | None:
        """Get PGN definition from standard or manufacturer-specific definitions."""
        return self._pgn_definitions.get(pgn)

    def _decode_signals(
        self, pgn_def: PGNDefinition, data: bytes
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """
        Decode all signals from a PGN definition.

        Args:
            pgn_def: PGN definition containing signal information
            data: Message data bytes

        Returns:
            Tuple of (decoded_signals, raw_signals)
        """
        decoded_signals = {}
        raw_signals = {}

        for signal in pgn_def.signals:
            try:
                # Extract raw value using bit manipulation
                raw_value = self._extract_signal_bits(data, signal.start_bit, signal.length)
                raw_signals[signal.name] = raw_value

                # Apply scaling and offset
                scaled_value = (raw_value * signal.scale) + signal.offset

                # Apply range validation if specified
                if signal.min_value is not None and scaled_value < signal.min_value:
                    scaled_value = signal.min_value
                if signal.max_value is not None and scaled_value > signal.max_value:
                    scaled_value = signal.max_value

                decoded_signals[signal.name] = scaled_value

            except Exception as e:
                logger.warning(f"Error decoding signal {signal.name}: {e}")
                raw_signals[signal.name] = 0
                decoded_signals[signal.name] = 0.0

        return decoded_signals, raw_signals

    def _extract_signal_bits(self, data: bytes, start_bit: int, length: int) -> int:
        """
        Extract a signal from CAN data using bit manipulation.

        Args:
            data: Message data bytes
            start_bit: Starting bit position (LSB = 0)
            length: Number of bits to extract

        Returns:
            Extracted integer value
        """
        if start_bit + length > len(data) * 8:
            msg = f"Signal extends beyond data: start={start_bit}, length={length}, data_bits={len(data) * 8}"
            raise ValueError(msg)

        # Convert bytes to integer for bit manipulation
        data_int = int.from_bytes(data, byteorder="little")

        # Create mask and extract bits
        mask = (1 << length) - 1
        return (data_int >> start_bit) & mask

    def _load_standard_pgns(self) -> None:
        """Load standard SAE J1939 PGN definitions."""
        # Engine Speed (RPM) - PGN 61444 (0xF004)
        self._pgn_definitions[61444] = PGNDefinition(
            pgn=61444,
            name="Electronic Engine Controller 1",
            system_type=SystemType.ENGINE,
            priority=MessagePriority.HIGH,
            data_length=8,
            signals=[
                SignalDefinition("engine_torque_mode", 0, 4, 1, 0, "state"),
                SignalDefinition("actual_engine_torque_percent", 8, 8, 1, -125, "%"),
                SignalDefinition("engine_speed", 24, 16, 0.125, 0, "rpm", 0, 8031.875),
                SignalDefinition("source_address_engine", 40, 8, 1, 0, "address"),
                SignalDefinition("engine_starter_mode", 48, 4, 1, 0, "state"),
                SignalDefinition("engine_demand_torque_percent", 56, 8, 1, -125, "%"),
            ],
        )

        # Engine Temperature 1 - PGN 65262 (0xFEEE)
        self._pgn_definitions[65262] = PGNDefinition(
            pgn=65262,
            name="Engine Temperature 1",
            system_type=SystemType.ENGINE,
            priority=MessagePriority.CRITICAL,
            data_length=8,
            signals=[
                SignalDefinition("engine_coolant_temp", 0, 8, 1, -40, "°C", -40, 210),
                SignalDefinition("fuel_temp", 8, 8, 1, -40, "°C", -40, 210),
                SignalDefinition("engine_oil_temp", 16, 16, 0.03125, -273, "°C", -273, 1735),
                SignalDefinition("turbo_oil_temp", 32, 16, 0.03125, -273, "°C", -273, 1735),
                SignalDefinition("engine_intercooler_temp", 48, 8, 1, -40, "°C", -40, 210),
                SignalDefinition(
                    "engine_intercooler_thermostat_opening", 56, 8, 0.4, 0, "%", 0, 100
                ),
            ],
        )

        # Vehicle Speed - PGN 65265 (0xFEF1)
        self._pgn_definitions[65265] = PGNDefinition(
            pgn=65265,
            name="Cruise Control/Vehicle Speed",
            system_type=SystemType.CHASSIS,
            priority=MessagePriority.HIGH,
            data_length=8,
            signals=[
                SignalDefinition("two_speed_axle_switch", 0, 2, 1, 0, "state"),
                SignalDefinition("parking_brake_switch", 2, 2, 1, 0, "state"),
                SignalDefinition("cruise_control_pause_switch", 4, 2, 1, 0, "state"),
                SignalDefinition("park_brake_release_inhibit_req", 6, 2, 1, 0, "state"),
                SignalDefinition(
                    "wheel_based_vehicle_speed", 8, 16, 1 / 256, 0, "km/h", 0, 250.996
                ),
                SignalDefinition("cruise_control_active", 24, 2, 1, 0, "state"),
                SignalDefinition("cruise_control_enable_switch", 26, 2, 1, 0, "state"),
                SignalDefinition("brake_switch", 28, 2, 1, 0, "state"),
                SignalDefinition("clutch_switch", 30, 2, 1, 0, "state"),
                SignalDefinition("cruise_control_set_switch", 32, 2, 1, 0, "state"),
                SignalDefinition("cruise_control_coast_switch", 34, 2, 1, 0, "state"),
                SignalDefinition("cruise_control_resume_switch", 36, 2, 1, 0, "state"),
                SignalDefinition("cruise_control_accelerate_switch", 38, 2, 1, 0, "state"),
                SignalDefinition("cruise_control_set_speed", 40, 8, 1, 0, "km/h", 0, 250),
                SignalDefinition(
                    "cruise_control_high_set_limit_speed", 48, 8, 1, 0, "km/h", 0, 250
                ),
                SignalDefinition("cruise_control_low_set_limit_speed", 56, 8, 1, 0, "km/h", 0, 250),
            ],
        )

        # Fuel Economy - PGN 65266 (0xFEF2)
        self._pgn_definitions[65266] = PGNDefinition(
            pgn=65266,
            name="Fuel Economy",
            system_type=SystemType.FUEL,
            priority=MessagePriority.HIGH,
            data_length=8,
            signals=[
                SignalDefinition("fuel_rate", 0, 16, 0.05, 0, "L/h", 0, 3212.75),
                SignalDefinition(
                    "instantaneous_fuel_economy", 16, 16, 1 / 512, 0, "km/L", 0, 125.5
                ),
                SignalDefinition("average_fuel_economy", 32, 16, 1 / 512, 0, "km/L", 0, 125.5),
                SignalDefinition("throttle_position", 48, 8, 0.4, 0, "%", 0, 100),
            ],
        )

        logger.info("Standard J1939 PGNs loaded")

    def _load_cummins_extensions(self) -> None:
        """Load Cummins engine-specific PGN definitions."""
        # Cummins Electronic Engine Controller 3 - Custom PGN
        self._pgn_definitions[61445] = PGNDefinition(
            pgn=61445,
            name="Cummins Electronic Engine Controller 3",
            system_type=SystemType.ENGINE,
            priority=MessagePriority.HIGH,
            data_length=8,
            manufacturer="Cummins",
            signals=[
                SignalDefinition("nominal_friction_torque", 0, 8, 1, -125, "%"),
                SignalDefinition("engine_desired_operating_speed", 8, 16, 0.125, 0, "rpm"),
                SignalDefinition(
                    "engine_operating_speed_asymmetry_adjustment", 24, 8, 1, -125, "%"
                ),
                SignalDefinition("estimated_engine_parasitic_losses", 32, 16, 0.125, 0, "kW"),
            ],
        )

        # Cummins Aftertreatment 1 Diesel Exhaust Fluid Tank Information
        self._pgn_definitions[65110] = PGNDefinition(
            pgn=65110,
            name="Cummins Aftertreatment 1 Diesel Exhaust Fluid Tank Information",
            system_type=SystemType.EXHAUST,
            priority=MessagePriority.NORMAL,
            data_length=8,
            manufacturer="Cummins",
            signals=[
                SignalDefinition("diesel_exhaust_fluid_tank_level", 0, 8, 0.4, 0, "%", 0, 100),
                SignalDefinition("diesel_exhaust_fluid_tank_temp", 8, 16, 0.03125, -273, "°C"),
                SignalDefinition("diesel_exhaust_fluid_concentration", 24, 8, 0.4, 0, "%", 0, 100),
                SignalDefinition("diesel_exhaust_fluid_conductivity", 32, 16, 1, 0, "µS/cm"),
            ],
        )

        logger.info("Cummins J1939 extensions loaded")

    def _load_allison_extensions(self) -> None:
        """Load Allison transmission-specific PGN definitions."""
        # Allison Electronic Transmission Controller 1
        self._pgn_definitions[61443] = PGNDefinition(
            pgn=61443,
            name="Allison Electronic Transmission Controller 1",
            system_type=SystemType.TRANSMISSION,
            priority=MessagePriority.HIGH,
            data_length=8,
            manufacturer="Allison",
            signals=[
                SignalDefinition("clutch_pressure", 0, 8, 4, 0, "kPa", 0, 1000),
                SignalDefinition("transmission_oil_level_high_low", 8, 2, 1, 0, "state"),
                SignalDefinition("transmission_oil_level_countdown_timer", 10, 6, 1, 0, "s"),
                SignalDefinition("transmission_oil_level_measurement_status", 16, 4, 1, 0, "state"),
                SignalDefinition("transmission_shift_in_process", 20, 2, 1, 0, "state"),
                SignalDefinition("transmission_current_gear", 24, 8, 1, -125, "gear"),
                SignalDefinition("transmission_selected_gear", 32, 8, 1, -125, "gear"),
                SignalDefinition("transmission_actual_gear_ratio", 40, 16, 0.001, 0, "ratio"),
            ],
        )

        # Allison Electronic Transmission Controller 2
        self._pgn_definitions[65272] = PGNDefinition(
            pgn=65272,
            name="Allison Electronic Transmission Controller 2",
            system_type=SystemType.TRANSMISSION,
            priority=MessagePriority.NORMAL,
            data_length=8,
            manufacturer="Allison",
            signals=[
                SignalDefinition("transmission_fluid_temp", 0, 16, 0.03125, -273, "°C"),
                SignalDefinition("transmission_oil_pressure", 16, 8, 4, 0, "kPa", 0, 1000),
                SignalDefinition("transmission_output_shaft_speed", 24, 16, 0.125, 0, "rpm"),
                SignalDefinition("transmission_input_shaft_speed", 40, 16, 0.125, 0, "rpm"),
            ],
        )

        logger.info("Allison J1939 extensions loaded")

    def _load_chassis_extensions(self) -> None:
        """Load chassis-specific PGN definitions (Spartan K2, etc.)."""
        # Chassis Electronic Control Unit
        self._pgn_definitions[65098] = PGNDefinition(
            pgn=65098,
            name="Chassis Electronic Control Unit",
            system_type=SystemType.CHASSIS,
            priority=MessagePriority.NORMAL,
            data_length=8,
            manufacturer="Spartan",
            signals=[
                SignalDefinition("chassis_system_status", 0, 8, 1, 0, "status"),
                SignalDefinition("front_axle_weight", 8, 16, 0.5, 0, "kg"),
                SignalDefinition("rear_axle_weight", 24, 16, 0.5, 0, "kg"),
                SignalDefinition("chassis_level_front", 40, 8, 0.4, 0, "%"),
                SignalDefinition("chassis_level_rear", 48, 8, 0.4, 0, "%"),
            ],
        )

        # Anti-lock Braking System Information
        self._pgn_definitions[65097] = PGNDefinition(
            pgn=65097,
            name="Anti-lock Braking System Information",
            system_type=SystemType.BRAKES,
            priority=MessagePriority.CRITICAL,
            data_length=8,
            signals=[
                SignalDefinition("abs_active", 0, 2, 1, 0, "state"),
                SignalDefinition("abs_off_road_switch", 2, 2, 1, 0, "state"),
                SignalDefinition("antilock_braking_active", 4, 2, 1, 0, "state"),
                SignalDefinition("engine_retarder_selection", 6, 8, 1, 0, "level"),
                SignalDefinition("abs_full_function", 16, 2, 1, 0, "state"),
                SignalDefinition("ebs_red_warning_signal", 18, 2, 1, 0, "state"),
                SignalDefinition("abs_ebs_amber_warning_signal", 20, 2, 1, 0, "state"),
            ],
        )

        logger.info("Chassis J1939 extensions loaded")
