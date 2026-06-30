"""
Spartan K2 Chassis Integration Extensions

This module provides comprehensive Spartan K2 chassis-specific protocol extensions
for enhanced RV integration, including advanced diagnostics, safety systems,
and OEM-specific control capabilities.

Key features:
- Spartan K2-specific J1939 PGN extensions
- Chassis safety interlock systems
- Advanced diagnostic capabilities
- Air brake system integration
- Suspension and leveling control
- Power steering and stability systems
- Integration with existing J1939 and RV-C frameworks

Architecture:
- Follows proven patterns from Firefly and J1939 implementations
- Seamless integration with feature management system
- Comprehensive configuration via Pydantic settings
- Type-safe implementation with full test coverage
"""

import logging
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple

from backend.core.config import Settings

logger = logging.getLogger(__name__)


class SpartanK2Priority(Enum):
    """Spartan K2-specific message priority levels."""

    CRITICAL = 1  # Brake system failures, steering faults
    HIGH = 2  # Suspension alerts, power steering status
    NORMAL = 3  # Chassis diagnostics, leveling status
    LOW = 4  # Maintenance indicators
    BACKGROUND = 5  # System statistics, configuration data


class SpartanK2SystemType(Enum):
    """Spartan K2 chassis system types."""

    BRAKES = "brakes"
    SUSPENSION = "suspension"
    STEERING = "steering"
    LEVELING = "leveling"
    ELECTRICAL = "electrical"
    DIAGNOSTICS = "diagnostics"
    SAFETY = "safety"
    UNKNOWN = "unknown"


@dataclass
class SpartanK2Message:
    """Decoded Spartan K2 chassis message structure."""

    pgn: int
    source_address: int
    data: bytes
    priority: int
    system_type: SpartanK2SystemType
    decoded_signals: dict[str, Any]
    raw_signals: dict[str, int]
    safety_interlocks: list[str]
    diagnostic_codes: list[int]
    timestamp: float | None = None


class SpartanK2SignalDefinition(NamedTuple):
    """Spartan K2-specific signal definition structure."""

    name: str
    start_bit: int
    length: int
    scale: float
    offset: float
    units: str
    min_value: float | None = None
    max_value: float | None = None
    safety_critical: bool = False
    interlock_condition: str | None = None


class SpartanK2PGNDefinition(NamedTuple):
    """Spartan K2 PGN definition structure."""

    pgn: int
    name: str
    system_type: SpartanK2SystemType
    priority: SpartanK2Priority
    data_length: int
    signals: list[SpartanK2SignalDefinition]
    safety_interlocks: list[str]
    diagnostic_support: bool = True


class SpartanK2CommandPrecondition:
    """Safety interlock validation for Spartan K2 chassis systems."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.spartan_config = getattr(settings, "spartan_k2", None)
        self._active_interlocks: set[str] = set()
        self._safety_violations: list[dict] = []

    def validate_brake_interlock(self, brake_data: dict) -> tuple[bool, list[str]]:
        """Validate brake system safety interlocks."""
        violations = []

        # Critical brake pressure validation
        brake_pressure = brake_data.get("brake_pressure", 0)
        if brake_pressure < 80:  # psi
            violations.append("Low brake pressure detected - system safety compromised")

        # ABS system validation
        abs_active = brake_data.get("abs_active", False)
        if not abs_active and brake_data.get("vehicle_speed", 0) > 5:
            violations.append("ABS system inactive at speed - safety concern")

        # Parking brake validation
        parking_brake = brake_data.get("parking_brake_active", False)
        engine_running = brake_data.get("engine_running", False)
        if not parking_brake and not engine_running:
            violations.append("Parking brake not engaged with engine off")

        return len(violations) == 0, violations

    def validate_suspension_interlock(self, suspension_data: dict) -> tuple[bool, list[str]]:
        """Validate suspension system safety interlocks."""
        violations = []

        # Level sensor validation
        front_level = suspension_data.get("front_level_sensor", 50)
        rear_level = suspension_data.get("rear_level_sensor", 50)

        level_diff = abs(front_level - rear_level)
        if level_diff > 15:  # More than 15% difference
            violations.append("Chassis level differential exceeds safe limits")

        # Air pressure validation
        air_pressure = suspension_data.get("air_pressure", 0)
        if air_pressure < 100:  # psi
            violations.append("Insufficient air pressure for suspension operation")

        # Movement safety check
        vehicle_speed = suspension_data.get("vehicle_speed", 0)
        leveling_active = suspension_data.get("leveling_active", False)
        if leveling_active and vehicle_speed > 0.5:
            violations.append("Leveling system active while vehicle in motion")

        return len(violations) == 0, violations

    def validate_steering_interlock(self, steering_data: dict) -> tuple[bool, list[str]]:
        """Validate power steering safety interlocks."""
        violations = []

        # Power steering pressure
        ps_pressure = steering_data.get("power_steering_pressure", 0)
        if ps_pressure < 1000:  # psi
            violations.append("Low power steering pressure - steering assistance compromised")

        # Steering angle validation
        steering_angle = steering_data.get("steering_wheel_angle", 0)
        if abs(steering_angle) > 720:  # More than 2 full turns
            violations.append("Excessive steering angle detected")

        # Speed-dependent validation
        vehicle_speed = steering_data.get("vehicle_speed", 0)
        if vehicle_speed > 50 and abs(steering_angle) > 180:
            violations.append("High-speed operation with significant steering input")

        return len(violations) == 0, violations


class SpartanK2Decoder:
    """
    Spartan K2 chassis-specific J1939 decoder and safety system integration.

    Provides comprehensive decoding and safety validation for Spartan K2 chassis systems
    including advanced brake, suspension, steering, and diagnostic capabilities.
    """

    def __init__(self, settings: Settings):
        """
        Initialize the Spartan K2 decoder.

        Args:
            settings: Application settings containing Spartan K2 configuration
        """
        self.settings = settings
        self.spartan_config = getattr(settings, "spartan_k2", None)
        self.safety_interlock = SpartanK2CommandPrecondition(settings)
        self._pgn_definitions: dict[int, SpartanK2PGNDefinition] = {}
        self._message_cache: dict[int, SpartanK2Message] = {}
        self._load_spartan_k2_pgns()

        logger.info(
            f"Spartan K2 decoder initialized with {len(self._pgn_definitions)} PGN definitions"
        )

    def decode_message(
        self,
        pgn: int,
        source_address: int,
        data: bytes,
        priority: int = 6,
        timestamp: float | None = None,
    ) -> SpartanK2Message | None:
        """
        Decode a Spartan K2 chassis message.

        Args:
            pgn: Parameter Group Number
            source_address: Source address of the message
            data: Message data bytes
            priority: Message priority (0-7, lower is higher priority)
            timestamp: Optional timestamp

        Returns:
            Decoded SpartanK2Message or None if PGN not recognized
        """
        # Look up PGN definition
        pgn_def = self._get_pgn_definition(pgn)
        if not pgn_def:
            logger.debug(f"Unknown Spartan K2 PGN: 0x{pgn:04X}")
            return None

        # Validate data length
        if len(data) < pgn_def.data_length:
            logger.warning(
                f"Insufficient data for Spartan K2 PGN 0x{pgn:04X}: got {len(data)}, need {pgn_def.data_length}"
            )
            return None

        # Decode signals
        try:
            decoded_signals, raw_signals = self._decode_signals(pgn_def, data)
        except Exception as e:
            logger.error(f"Error decoding Spartan K2 PGN 0x{pgn:04X}: {e}")
            return None

        # Validate safety interlocks
        safety_violations = self._validate_command_preconditions(pgn_def, decoded_signals)

        # Extract diagnostic codes
        diagnostic_codes = self._extract_diagnostic_codes(pgn_def, decoded_signals)

        # Create message
        message = SpartanK2Message(
            pgn=pgn,
            source_address=source_address,
            data=data,
            priority=priority,
            system_type=pgn_def.system_type,
            decoded_signals=decoded_signals,
            raw_signals=raw_signals,
            safety_interlocks=safety_violations,
            diagnostic_codes=diagnostic_codes,
            timestamp=timestamp,
        )

        # Cache for cross-reference validation
        self._message_cache[pgn] = message

        return message

    def get_system_status(self, system_type: SpartanK2SystemType) -> dict[str, Any]:
        """Get comprehensive status for a specific Spartan K2 system."""
        status = {
            "system_type": system_type.value,
            "messages_received": 0,
            "last_update": None,
            "guardrail_status": "unknown",
            "diagnostic_codes": [],
            "interlock_violations": [],
        }

        # Analyze cached messages for this system
        system_messages = [
            msg for msg in self._message_cache.values() if msg.system_type == system_type
        ]

        if system_messages:
            latest_msg = max(system_messages, key=lambda m: m.timestamp or 0)
            status.update(
                {
                    "messages_received": len(system_messages),
                    "last_update": latest_msg.timestamp,
                    "guardrail_status": "ok" if not latest_msg.safety_interlocks else "violation",
                    "diagnostic_codes": latest_msg.diagnostic_codes,
                    "interlock_violations": latest_msg.safety_interlocks,
                }
            )

        return status

    def get_decoder_info(self) -> dict[str, Any]:
        """Get comprehensive decoder status and capabilities."""
        return {
            "decoder_type": "spartan_k2",
            "manufacturer": "Spartan Chassis",
            "chassis_model": "K2",
            "pgn_definitions": len(self._pgn_definitions),
            "supported_systems": [system.value for system in SpartanK2SystemType],
            "safety_interlocks_enabled": True,
            "diagnostic_support": True,
            "message_cache_size": len(self._message_cache),
            "configuration": {
                "enabled": getattr(self.spartan_config, "enabled", False)
                if self.spartan_config
                else False,
                "safety_interlocks": getattr(self.spartan_config, "enable_safety_interlocks", True)
                if self.spartan_config
                else True,
                "advanced_diagnostics": getattr(
                    self.spartan_config, "enable_advanced_diagnostics", True
                )
                if self.spartan_config
                else True,
            },
        }

    def _load_spartan_k2_pgns(self) -> None:
        """Load Spartan K2-specific PGN definitions."""

        # Advanced Brake System Controller (Spartan K2-specific)
        self._pgn_definitions[65280] = SpartanK2PGNDefinition(
            pgn=65280,
            name="Spartan K2 Advanced Brake System Controller",
            system_type=SpartanK2SystemType.BRAKES,
            priority=SpartanK2Priority.CRITICAL,
            data_length=8,
            safety_interlocks=["brake_pressure_low", "abs_malfunction", "parking_brake_disengaged"],
            signals=[
                SpartanK2SignalDefinition(
                    "brake_pressure", 0, 16, 0.5, 0, "psi", 0, 200, safety_critical=True
                ),
                SpartanK2SignalDefinition("abs_active", 16, 2, 1, 0, "state", safety_critical=True),
                SpartanK2SignalDefinition(
                    "parking_brake_active", 18, 2, 1, 0, "state", safety_critical=True
                ),
                SpartanK2SignalDefinition("brake_fluid_level", 20, 4, 1, 0, "level"),
                SpartanK2SignalDefinition("brake_temp_front", 24, 8, 1, -40, "°C", -40, 200),
                SpartanK2SignalDefinition("brake_temp_rear", 32, 8, 1, -40, "°C", -40, 200),
                SpartanK2SignalDefinition("brake_wear_front", 40, 8, 0.4, 0, "%", 0, 100),
                SpartanK2SignalDefinition("brake_wear_rear", 48, 8, 0.4, 0, "%", 0, 100),
            ],
        )

        # Suspension and Leveling System (Spartan K2-specific)
        self._pgn_definitions[65281] = SpartanK2PGNDefinition(
            pgn=65281,
            name="Spartan K2 Suspension and Leveling System",
            system_type=SpartanK2SystemType.SUSPENSION,
            priority=SpartanK2Priority.HIGH,
            data_length=8,
            safety_interlocks=[
                "level_differential_high",
                "air_pressure_low",
                "leveling_while_moving",
            ],
            signals=[
                SpartanK2SignalDefinition(
                    "front_level_sensor", 0, 8, 0.4, 0, "%", 0, 100, safety_critical=True
                ),
                SpartanK2SignalDefinition(
                    "rear_level_sensor", 8, 8, 0.4, 0, "%", 0, 100, safety_critical=True
                ),
                SpartanK2SignalDefinition(
                    "air_pressure", 16, 8, 2, 0, "psi", 0, 200, safety_critical=True
                ),
                SpartanK2SignalDefinition("leveling_active", 24, 2, 1, 0, "state"),
                SpartanK2SignalDefinition("suspension_mode", 26, 3, 1, 0, "mode"),
                SpartanK2SignalDefinition("ride_height_front", 32, 8, 0.5, 0, "inches"),
                SpartanK2SignalDefinition("ride_height_rear", 40, 8, 0.5, 0, "inches"),
                SpartanK2SignalDefinition("shock_position", 48, 8, 0.4, 0, "%"),
            ],
        )

        # Power Steering and Stability System (Spartan K2-specific)
        self._pgn_definitions[65282] = SpartanK2PGNDefinition(
            pgn=65282,
            name="Spartan K2 Power Steering and Stability System",
            system_type=SpartanK2SystemType.STEERING,
            priority=SpartanK2Priority.HIGH,
            data_length=8,
            safety_interlocks=["steering_pressure_low", "steering_angle_excessive"],
            signals=[
                SpartanK2SignalDefinition(
                    "power_steering_pressure", 0, 16, 4, 0, "psi", 0, 2000, safety_critical=True
                ),
                SpartanK2SignalDefinition(
                    "steering_wheel_angle", 16, 16, 0.0625, -2000, "degrees", safety_critical=True
                ),
                SpartanK2SignalDefinition("steering_effort", 32, 8, 1, 0, "%", 0, 100),
                SpartanK2SignalDefinition("stability_control_active", 40, 2, 1, 0, "state"),
                SpartanK2SignalDefinition("lane_keep_assist", 42, 2, 1, 0, "state"),
                SpartanK2SignalDefinition("steering_temp", 48, 8, 1, -40, "°C"),
            ],
        )

        # Chassis Electrical and Power Management (Spartan K2-specific)
        self._pgn_definitions[65283] = SpartanK2PGNDefinition(
            pgn=65283,
            name="Spartan K2 Chassis Electrical and Power Management",
            system_type=SpartanK2SystemType.ELECTRICAL,
            priority=SpartanK2Priority.NORMAL,
            data_length=8,
            safety_interlocks=["battery_voltage_low", "alternator_failure"],
            signals=[
                SpartanK2SignalDefinition("chassis_battery_voltage", 0, 16, 0.05, 0, "V", 10, 16),
                SpartanK2SignalDefinition("alternator_output", 16, 8, 1, 0, "A", 0, 200),
                SpartanK2SignalDefinition("power_distribution_status", 24, 8, 1, 0, "status"),
                SpartanK2SignalDefinition("auxiliary_power_active", 32, 2, 1, 0, "state"),
                SpartanK2SignalDefinition("engine_block_heater", 34, 2, 1, 0, "state"),
                SpartanK2SignalDefinition("chassis_ground_fault", 36, 2, 1, 0, "state"),
            ],
        )

        # Advanced Diagnostics and Maintenance (Spartan K2-specific)
        self._pgn_definitions[65284] = SpartanK2PGNDefinition(
            pgn=65284,
            name="Spartan K2 Advanced Diagnostics and Maintenance",
            system_type=SpartanK2SystemType.DIAGNOSTICS,
            priority=SpartanK2Priority.LOW,
            data_length=8,
            safety_interlocks=[],
            diagnostic_support=True,
            signals=[
                SpartanK2SignalDefinition("diagnostic_trouble_code", 0, 16, 1, 0, "code"),
                SpartanK2SignalDefinition("maintenance_due_indicator", 16, 8, 1, 0, "days"),
                SpartanK2SignalDefinition("system_health_score", 24, 8, 1, 0, "%", 0, 100),
                SpartanK2SignalDefinition("operating_hours", 32, 16, 0.1, 0, "hours"),
                SpartanK2SignalDefinition("mileage_counter", 48, 16, 0.1, 0, "miles"),
            ],
        )

        logger.info("Spartan K2 PGN definitions loaded")

    def _get_pgn_definition(self, pgn: int) -> SpartanK2PGNDefinition | None:
        """Get PGN definition for the given PGN."""
        return self._pgn_definitions.get(pgn)

    def _decode_signals(
        self, pgn_def: SpartanK2PGNDefinition, data: bytes
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Decode signals from message data."""
        decoded_signals = {}
        raw_signals = {}

        for signal in pgn_def.signals:
            try:
                # Extract raw value
                byte_offset = signal.start_bit // 8
                bit_offset = signal.start_bit % 8

                if signal.length <= 8:
                    # Single byte signal
                    raw_value = data[byte_offset]
                    mask = (1 << signal.length) - 1
                    raw_value = (raw_value >> bit_offset) & mask
                elif signal.length <= 16:
                    # Two-byte signal
                    raw_value = struct.unpack("<H", data[byte_offset : byte_offset + 2])[0]
                    mask = (1 << signal.length) - 1
                    raw_value = (raw_value >> bit_offset) & mask
                else:
                    # Multi-byte signal
                    raw_value = int.from_bytes(
                        data[byte_offset : byte_offset + 4], byteorder="little"
                    )
                    mask = (1 << signal.length) - 1
                    raw_value = (raw_value >> bit_offset) & mask

                # Apply scaling and offset
                decoded_value = raw_value * signal.scale + signal.offset

                # Validate ranges
                if signal.min_value is not None and decoded_value < signal.min_value:
                    logger.warning(
                        f"Signal {signal.name} below minimum: {decoded_value} < {signal.min_value}"
                    )
                if signal.max_value is not None and decoded_value > signal.max_value:
                    logger.warning(
                        f"Signal {signal.name} above maximum: {decoded_value} > {signal.max_value}"
                    )

                decoded_signals[signal.name] = decoded_value
                raw_signals[signal.name] = raw_value

            except Exception as e:
                logger.error(f"Error decoding signal {signal.name}: {e}")
                decoded_signals[signal.name] = None
                raw_signals[signal.name] = 0

        return decoded_signals, raw_signals

    def _validate_command_preconditions(
        self, pgn_def: SpartanK2PGNDefinition, decoded_signals: dict
    ) -> list[str]:
        """Validate safety interlocks for the message."""
        violations = []

        if pgn_def.system_type == SpartanK2SystemType.BRAKES:
            valid, brake_violations = self.safety_interlock.validate_brake_interlock(
                decoded_signals
            )
            if not valid:
                violations.extend(brake_violations)

        elif pgn_def.system_type == SpartanK2SystemType.SUSPENSION:
            valid, suspension_violations = self.safety_interlock.validate_suspension_interlock(
                decoded_signals
            )
            if not valid:
                violations.extend(suspension_violations)

        elif pgn_def.system_type == SpartanK2SystemType.STEERING:
            valid, steering_violations = self.safety_interlock.validate_steering_interlock(
                decoded_signals
            )
            if not valid:
                violations.extend(steering_violations)

        return violations

    def _extract_diagnostic_codes(
        self, pgn_def: SpartanK2PGNDefinition, decoded_signals: dict
    ) -> list[int]:
        """Extract diagnostic trouble codes from the message."""
        codes = []

        if pgn_def.diagnostic_support:
            # Look for diagnostic trouble code signals
            dtc_value = decoded_signals.get("diagnostic_trouble_code")
            if dtc_value and dtc_value != 0:
                codes.append(int(dtc_value))

        return codes
