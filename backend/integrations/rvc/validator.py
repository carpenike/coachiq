"""
Enhanced message validation for RV-C protocol.

This module provides comprehensive validation of CAN messages, signals,
and commands beyond basic structure validation.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

from backend.core.config import get_settings
from backend.integrations.rvc.decode import load_config_data_v2

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]

    def add_error(self, error: str) -> None:
        """Add an error to the result."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        """Add a warning to the result."""
        self.warnings.append(warning)


@dataclass
class SignalValidationRule:
    """Validation rule for a signal."""

    signal_name: str
    min_value: float | None = None
    max_value: float | None = None
    valid_values: list[Any] | None = None
    required: bool = False
    depends_on: str | None = None  # Signal dependency
    engineering_limits: dict[str, float] | None = None


@dataclass
class SecurityEvent:
    """Security-related event for logging."""

    timestamp: float
    event_type: str
    source_address: int
    dgn: int
    severity: str  # "low", "medium", "high", "critical"
    description: str
    raw_data: bytes | None = None


class MessageValidator:
    """
    Enhanced message validator for RV-C protocol.

    Provides multi-layer validation including:
    - Signal range validation
    - Dependency checking
    - Engineering limits
    - Security validation
    """

    def __init__(self, settings: Any = None):
        """
        Initialize the message validator.

        Args:
            settings: Application settings instance (uses get_settings() if None)
        """
        self.settings = settings or get_settings()
        self._config_loaded = False
        self._validation_rules: dict[str, list[SignalValidationRule]] = {}
        self._security_events: list[SecurityEvent] = []
        self._max_security_events = 1000  # Ring buffer for security events
        self._load_configuration()
        self._load_validation_rules()

    def _load_configuration(self) -> None:
        """Load RV-C configuration data."""
        try:
            # Use the same configuration loading as other RVC components
            spec_path_override = None
            map_path_override = None

            if self.settings.rvc_spec_path:
                spec_path_override = str(self.settings.rvc_spec_path)

            if self.settings.rvc_coach_mapping_path:
                map_path_override = str(self.settings.rvc_coach_mapping_path)

            # Load configuration using the new structured version
            self.rvc_config = load_config_data_v2(
                rvc_spec_path_override=spec_path_override,
                device_mapping_path_override=map_path_override,
            )

            # For backward compatibility with existing methods
            self.dgn_dict = self.rvc_config.dgn_dict
            self.spec_meta = self.rvc_config.spec_meta
            self.mapping_dict = self.rvc_config.mapping_dict
            self.entity_map = self.rvc_config.entity_map
            self.entity_ids = self.rvc_config.entity_ids
            self.inst_map = self.rvc_config.inst_map
            self.unique_instances = self.rvc_config.unique_instances
            self.pgn_hex_to_name_map = self.rvc_config.pgn_hex_to_name_map
            self.dgn_pairs = self.rvc_config.dgn_pairs
            self.coach_info = self.rvc_config.coach_info

            self._config_loaded = True
            logger.info("Message validator configuration loaded")

        except Exception as e:
            logger.error(f"Failed to load validator configuration: {e}")
            self._config_loaded = False

    def _load_validation_rules(self) -> None:
        """Load validation rules from configuration."""
        if not self._config_loaded:
            return

        # Define common validation rules based on RV-C specifications
        common_rules = {
            # Light/dimmer rules
            "brightness": SignalValidationRule(
                signal_name="brightness",
                min_value=0,
                max_value=100,
                engineering_limits={"max_continuous": 100, "max_peak": 100},
            ),
            "light_level": SignalValidationRule(
                signal_name="light_level",
                min_value=0,
                max_value=200,  # RV-C often uses 0-200 range
            ),
            # Temperature rules
            "temperature": SignalValidationRule(
                signal_name="temperature",
                min_value=-40,
                max_value=150,  # Celsius
                engineering_limits={"min_operating": -20, "max_operating": 80},
            ),
            # Voltage rules
            "voltage": SignalValidationRule(
                signal_name="voltage",
                min_value=0,
                max_value=50,  # Typical RV voltage range
                engineering_limits={"min_operating": 10.5, "max_operating": 15.5},
            ),
            # Current rules
            "current": SignalValidationRule(
                signal_name="current",
                min_value=0,
                max_value=1000,  # Amps
                engineering_limits={"max_continuous": 100, "max_peak": 200},
            ),
            # Pressure rules
            "pressure": SignalValidationRule(
                signal_name="pressure",
                min_value=0,
                max_value=1000,  # PSI or kPa depending on signal
                engineering_limits={"max_operating": 150},
            ),
            # Instance rules
            "instance": SignalValidationRule(
                signal_name="instance",
                min_value=0,
                max_value=253,  # RV-C standard range
                required=True,
            ),
            # State/status rules
            "state": SignalValidationRule(
                signal_name="state",
                valid_values=[0, 1, 2, 3],  # Common state values
            ),
        }

        # Apply rules to DGNs based on signal names
        for dgn, spec in self.dgn_dict.items():
            dgn_hex = spec.get("pgn", f"{dgn:X}")
            rules = []

            for signal in spec.get("signals", []):
                signal_name = signal.get("name", "").lower()

                # Find matching rules
                for rule_pattern, rule in common_rules.items():
                    if rule_pattern in signal_name:
                        # Create a copy with signal-specific settings
                        signal_rule = SignalValidationRule(
                            signal_name=signal.get("name", ""),
                            min_value=rule.min_value,
                            max_value=rule.max_value,
                            valid_values=rule.valid_values,
                            required=rule.required,
                            engineering_limits=rule.engineering_limits,
                        )
                        rules.append(signal_rule)
                        break

            if rules:
                self._validation_rules[dgn_hex] = rules

    def validate_signal_range(self, signal: dict[str, Any], value: Any) -> ValidationResult:
        """
        Validate a signal value against specification ranges.

        Args:
            signal: Signal specification from RVC spec
            value: Raw signal value to validate

        Returns:
            ValidationResult with any errors or warnings
        """
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        signal_name = signal.get("name", "unknown")

        # Check basic type
        if not isinstance(value, int | float):
            result.add_error(f"Signal '{signal_name}' value must be numeric, got {type(value)}")
            return result

        # Check bit field limits
        length = signal.get("length", 8)
        max_raw_value = (1 << length) - 1

        if value < 0:
            result.add_error(f"Signal '{signal_name}' value {value} is negative")
        elif value > max_raw_value:
            result.add_error(
                f"Signal '{signal_name}' value {value} exceeds maximum {max_raw_value}"
            )

        # Apply scale and offset to get physical value
        scale = signal.get("scale", 1)
        offset = signal.get("offset", 0)
        physical_value = value * scale + offset

        # Check enumerated values
        if "enum" in signal:
            enum_map = signal["enum"]
            if str(value) not in enum_map:
                result.add_warning(f"Signal '{signal_name}' value {value} not in enumeration")

        # Check custom validation rules
        dgn_hex = signal.get("dgn_hex")
        if dgn_hex and dgn_hex in self._validation_rules:
            for rule in self._validation_rules[dgn_hex]:
                if rule.signal_name.lower() in signal_name.lower():
                    self._apply_validation_rule(rule, physical_value, result)

        return result

    def _apply_validation_rule(
        self, rule: SignalValidationRule, value: float, result: ValidationResult
    ) -> None:
        """Apply a validation rule to a value."""
        # Range checks
        if rule.min_value is not None and value < rule.min_value:
            result.add_error(
                f"Signal '{rule.signal_name}' value {value} below minimum {rule.min_value}"
            )

        if rule.max_value is not None and value > rule.max_value:
            result.add_error(
                f"Signal '{rule.signal_name}' value {value} above maximum {rule.max_value}"
            )

        # Valid values check
        if rule.valid_values is not None and value not in rule.valid_values:
            result.add_error(
                f"Signal '{rule.signal_name}' value {value} not in valid values {rule.valid_values}"
            )

        # Engineering limits (warnings, not errors)
        if rule.engineering_limits:
            limits = rule.engineering_limits

            if "min_operating" in limits and value < limits["min_operating"]:
                result.add_warning(
                    f"Signal '{rule.signal_name}' value {value} below recommended operating minimum {limits['min_operating']}"
                )

            if "max_operating" in limits and value > limits["max_operating"]:
                result.add_warning(
                    f"Signal '{rule.signal_name}' value {value} above recommended operating maximum {limits['max_operating']}"
                )

            if "max_continuous" in limits and value > limits["max_continuous"]:
                result.add_warning(
                    f"Signal '{rule.signal_name}' value {value} above continuous operating limit {limits['max_continuous']}"
                )

    def validate_dependencies(self, decoded_signals: dict[str, Any]) -> list[str]:
        """
        Check signal dependencies and constraints.

        Args:
            decoded_signals: Dictionary of decoded signal values

        Returns:
            List of dependency violation error messages
        """
        errors = []

        # Common RV-C dependency rules
        dependency_rules = [
            # Light brightness depends on state being "on"
            ("brightness", "state", lambda brightness, state: state == "on" or brightness == 0),
            ("light_level", "state", lambda level, state: state == "on" or level == 0),
            # Fan speed depends on state
            ("fan_speed", "state", lambda speed, state: state == "on" or speed == 0),
            # Current should be 0 when voltage is 0
            ("current", "voltage", lambda current, voltage: voltage > 0 or current == 0),
        ]

        for signal1, signal2, rule_func in dependency_rules:
            # Find signals that match the patterns
            signal1_value = None
            signal2_value = None

            for signal_name, value in decoded_signals.items():
                if signal1.lower() in signal_name.lower():
                    signal1_value = value
                elif signal2.lower() in signal_name.lower():
                    signal2_value = value

            # Apply rule if both signals are present
            if signal1_value is not None and signal2_value is not None:
                try:
                    # Convert string values to numeric where possible
                    if isinstance(signal1_value, str) and signal1_value.replace(".", "").isdigit():
                        signal1_value = float(signal1_value)
                    if isinstance(signal2_value, str) and signal2_value.replace(".", "").isdigit():
                        signal2_value = float(signal2_value)

                    if not rule_func(signal1_value, signal2_value):
                        errors.append(
                            f"Dependency violation: {signal1}={signal1_value} conflicts with {signal2}={signal2_value}"
                        )

                except (ValueError, TypeError) as e:
                    # Skip rules that can't be applied due to type issues
                    logger.debug(f"Could not apply dependency rule {signal1}/{signal2}: {e}")

        return errors

    def check_engineering_limits(self, dgn: int, signals: dict[str, Any]) -> list[str]:
        """
        Validate against engineering limits and safety constraints.

        Args:
            dgn: DGN ID
            signals: Dictionary of signal names to raw values

        Returns:
            List of engineering limit violation warnings
        """
        warnings = []

        # Safety-critical limits for different systems
        safety_limits = {
            # Battery/electrical systems
            "voltage": {"min_safe": 10.0, "max_safe": 16.0},
            "current": {"max_safe": 200.0},
            "temperature": {"max_safe": 85.0},  # Electronics temperature
            # Pressure systems
            "pressure": {"max_safe": 150.0},  # PSI
            "water_pressure": {"max_safe": 60.0},
            # Tank levels
            "tank_level": {"max_safe": 95.0},  # Percent
        }

        for signal_name, raw_value in signals.items():
            # Apply scale/offset if available
            if dgn in self.dgn_dict:
                spec = self.dgn_dict[dgn]
                for signal_spec in spec.get("signals", []):
                    if signal_spec.get("name") == signal_name:
                        scale = signal_spec.get("scale", 1)
                        offset = signal_spec.get("offset", 0)
                        physical_value = raw_value * scale + offset

                        # Check against safety limits
                        for limit_pattern, limits in safety_limits.items():
                            if limit_pattern.lower() in signal_name.lower():
                                if "min_safe" in limits and physical_value < limits["min_safe"]:
                                    warnings.append(
                                        f"Signal '{signal_name}' value {physical_value} below safety minimum {limits['min_safe']}"
                                    )

                                if "max_safe" in limits and physical_value > limits["max_safe"]:
                                    warnings.append(
                                        f"Signal '{signal_name}' value {physical_value} above safety maximum {limits['max_safe']}"
                                    )
                                break
                        break

        return warnings

    def validate_source_permissions(self, source: int, dgn: int) -> bool:
        """
        Check if source is authorized for this DGN.

        Args:
            source: Source address
            dgn: DGN ID

        Returns:
            True if authorized, False otherwise
        """
        # Get controller source address from settings
        try:
            controller_addr = int(self.settings.controller_source_addr, 16)
        except (ValueError, AttributeError):
            controller_addr = 0xF9  # Default controller address

        # Allow our own controller
        if source == controller_addr:
            return True

        # Define authorization rules
        # For now, be permissive but log unusual sources
        authorized_ranges = [
            (0x80, 0xF7),  # Normal device range
            (0x00, 0x7F),  # Additional device range
        ]

        for min_addr, max_addr in authorized_ranges:
            if min_addr <= source <= max_addr:
                return True

        # Log suspicious source addresses
        if source not in (0xFE, 0xFF):  # Exclude broadcast addresses
            logger.warning(f"Unusual source address {source:02X} for DGN {dgn:X}")

        return False

    def record_security_event(
        self,
        event_type: str,
        source_address: int,
        dgn: int,
        severity: str = "medium",
        description: str = "",
        raw_data: bytes | None = None,
    ) -> None:
        """
        Record a security-related event.

        Args:
            event_type: Type of security event
            source_address: Source address of the message
            dgn: DGN ID
            severity: Event severity level
            description: Human-readable description
            raw_data: Optional raw message data
        """
        event = SecurityEvent(
            timestamp=time.time(),
            event_type=event_type,
            source_address=source_address,
            dgn=dgn,
            severity=severity,
            description=description,
            raw_data=raw_data,
        )

        # Add to ring buffer
        self._security_events.append(event)
        if len(self._security_events) > self._max_security_events:
            self._security_events.pop(0)

        # Log based on severity
        log_msg = (
            f"Security event: {event_type} from {source_address:02X} DGN {dgn:X} - {description}"
        )

        if severity == "critical":
            logger.critical(log_msg)
        elif severity == "high":
            logger.error(log_msg)
        elif severity == "medium":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

    def get_security_events(self, since: float | None = None) -> list[SecurityEvent]:
        """
        Get security events since a timestamp.

        Args:
            since: Timestamp to filter from (None for all events)

        Returns:
            List of security events
        """
        if since is None:
            return self._security_events.copy()

        return [event for event in self._security_events if event.timestamp >= since]

    def validate_message_complete(
        self, dgn: int, source: int, decoded_signals: dict[str, Any], raw_data: bytes
    ) -> ValidationResult:
        """
        Perform complete message validation.

        Args:
            dgn: DGN ID
            source: Source address
            decoded_signals: Decoded signal values
            raw_data: Raw message data

        Returns:
            Complete validation result
        """
        result = ValidationResult(is_valid=True, errors=[], warnings=[])

        # 1. Source permission check
        if not self.validate_source_permissions(source, dgn):
            result.add_warning(f"Unusual source address {source:02X} for DGN {dgn:X}")
            self.record_security_event(
                "unauthorized_source",
                source,
                dgn,
                "medium",
                f"Unusual source address {source:02X}",
                raw_data,
            )

        # 2. Signal range validation
        if dgn in self.dgn_dict:
            spec = self.dgn_dict[dgn]
            for signal_spec in spec.get("signals", []):
                signal_name = signal_spec.get("name")
                if signal_name in decoded_signals:
                    signal_result = self.validate_signal_range(
                        signal_spec, decoded_signals[signal_name]
                    )
                    result.errors.extend(signal_result.errors)
                    result.warnings.extend(signal_result.warnings)
                    if not signal_result.is_valid:
                        result.is_valid = False

        # 3. Dependency validation
        dependency_errors = self.validate_dependencies(decoded_signals)
        result.errors.extend(dependency_errors)
        if dependency_errors:
            result.is_valid = False

        # 4. Engineering limits
        engineering_warnings = self.check_engineering_limits(dgn, decoded_signals)
        result.warnings.extend(engineering_warnings)

        return result

    def get_validation_stats(self) -> dict[str, Any]:
        """
        Get validation statistics.

        Returns:
            Dictionary with validation statistics
        """
        return {
            "config_loaded": self._config_loaded,
            "validation_rules_count": sum(len(rules) for rules in self._validation_rules.values()),
            "dgns_with_rules": len(self._validation_rules),
            "security_events_count": len(self._security_events),
            "recent_security_events": len(
                [
                    e
                    for e in self._security_events
                    if time.time() - e.timestamp < 3600  # Last hour
                ]
            ),
        }
