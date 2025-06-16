"""
RVC Encoder for creating CAN messages from high-level commands.

This module handles encoding of entity control commands into RV-C compliant
CAN messages, supporting single-frame and multi-frame (BAM) transmissions.
"""

import logging
from typing import Any

from backend.core.config import get_settings
from backend.integrations.rvc.decode import load_config_data
from backend.models.can_message import CANMessage
from backend.models.entity import ControlCommand

logger = logging.getLogger(__name__)


class EncodingError(Exception):
    """Raised when encoding fails."""



class RVCEncoder:
    """
    RVC protocol encoder for converting high-level commands to CAN messages.

    This encoder integrates with the existing configuration management system
    and supports the same coach mapping and RVC spec files used by the decoder.
    """

    def __init__(self, settings: Any = None):
        """
        Initialize the RVC encoder.

        Args:
            settings: Application settings instance (uses get_settings() if None)
        """
        self.settings = settings or get_settings()
        self._config_loaded = False
        self._load_configuration()

    def _load_configuration(self) -> None:
        """Load RVC configuration data using the same system as the decoder."""
        try:
            # Use the same configuration loading as the RVC feature
            spec_path_override = None
            map_path_override = None

            if self.settings.rvc_spec_path:
                spec_path_override = str(self.settings.rvc_spec_path)

            if self.settings.rvc_coach_mapping_path:
                map_path_override = str(self.settings.rvc_coach_mapping_path)

            # Load configuration using the existing decode module
            (
                self.dgn_dict,
                self.spec_meta,
                self.mapping_dict,
                self.entity_map,
                self.entity_ids,
                self.inst_map,
                self.unique_instances,
                self.pgn_hex_to_name_map,
                self.dgn_pairs,
                self.coach_info,
            ) = load_config_data(
                rvc_spec_path_override=spec_path_override,
                device_mapping_path_override=map_path_override,
            )

            self._config_loaded = True
            logger.info(f"RVC encoder configuration loaded - coach: {self.coach_info}")

        except Exception as e:
            logger.error(f"Failed to load RVC encoder configuration: {e}")
            self._config_loaded = False
            msg = f"Configuration loading failed: {e}"
            raise EncodingError(msg) from e

    def is_ready(self) -> bool:
        """Check if the encoder is ready to encode commands."""
        return self._config_loaded

    def encode_entity_command(self, entity_id: str, command: ControlCommand) -> list[CANMessage]:
        """
        Encode a high-level entity command into RV-C CAN messages.

        Args:
            entity_id: The entity ID to control
            command: The control command to execute

        Returns:
            List of CANMessage objects to transmit

        Raises:
            EncodingError: If encoding fails
        """
        if not self.is_ready():
            msg = "Encoder not ready - configuration not loaded"
            raise EncodingError(msg)

        # Look up entity in configuration
        if entity_id not in self.inst_map:
            msg = f"Unknown entity ID: {entity_id}"
            raise EncodingError(msg)

        entity_config = self.inst_map[entity_id]
        dgn_hex = entity_config["dgn_hex"]
        instance = entity_config["instance"]

        # Get the device configuration for this entity
        device_key = (dgn_hex, str(instance))
        if device_key not in self.entity_map:
            msg = f"No device mapping found for entity {entity_id}"
            raise EncodingError(msg)

        device_config = self.entity_map[device_key]

        # Determine command DGN based on the dgn_pairs mapping
        command_dgn_hex = self._get_command_dgn(dgn_hex)
        if not command_dgn_hex:
            msg = f"No command DGN found for status DGN {dgn_hex}"
            raise EncodingError(msg)

        # Get the DGN specification for encoding
        command_dgn_int = int(command_dgn_hex, 16)

        # Find matching DGN in dgn_dict (need to match by PGN portion)
        command_pgn = command_dgn_int & 0x3FFFF
        command_spec = None

        for dgn, spec in self.dgn_dict.items():
            if (dgn & 0x3FFFF) == command_pgn:
                command_spec = spec
                break

        if not command_spec:
            msg = f"No specification found for command DGN {command_dgn_hex}"
            raise EncodingError(msg)

        # Encode the command based on device type and command
        return self._encode_command_payload(command_spec, command, device_config, instance)

    def _get_command_dgn(self, status_dgn_hex: str) -> str | None:
        """
        Get the command DGN for a given status DGN using dgn_pairs mapping.

        Args:
            status_dgn_hex: Status DGN hex string

        Returns:
            Command DGN hex string or None if not found
        """
        # Check direct mapping first
        if status_dgn_hex in self.dgn_pairs:
            return self.dgn_pairs[status_dgn_hex]

        # Check reverse mapping (command -> status)
        for cmd_dgn, stat_dgn in self.dgn_pairs.items():
            if stat_dgn == status_dgn_hex:
                return cmd_dgn

        # Fallback: try to infer based on common RV-C patterns
        # Many command DGNs are status DGN + 0x100
        try:
            status_dgn_int = int(status_dgn_hex, 16)
            command_dgn_int = status_dgn_int + 0x100
            return f"{command_dgn_int:X}"
        except ValueError:
            pass

        return None

    def _encode_command_payload(
        self,
        command_spec: dict[str, Any],
        command: ControlCommand,
        device_config: dict[str, Any],
        instance: str,
    ) -> list[CANMessage]:
        """
        Encode command payload based on specification and device type.

        Args:
            command_spec: DGN specification from RVC spec
            command: Control command to encode
            device_config: Device configuration from mapping
            instance: Device instance number

        Returns:
            List of CANMessage objects
        """
        device_type = device_config.get("device_type", "unknown")

        # Create base payload (8 bytes for standard CAN frame)
        payload = bytearray(8)

        # Set instance field (typically byte 0)
        instance_num = int(instance)
        payload[0] = instance_num & 0xFF

        # Encode based on device type and command
        if device_type in ("light", "dimmer"):
            self._encode_light_command(payload, command, command_spec)
        elif device_type == "switch":
            self._encode_switch_command(payload, command, command_spec)
        elif device_type == "fan":
            self._encode_fan_command(payload, command, command_spec)
        else:
            # Generic encoding - try to map command fields to signals
            self._encode_generic_command(payload, command, command_spec)

        # Create CAN message
        can_id = self._build_can_id(command_spec, instance_num)

        return [CANMessage(can_id=can_id, data=bytes(payload), extended=True)]

    def _encode_light_command(
        self, payload: bytearray, command: ControlCommand, spec: dict[str, Any]
    ) -> None:
        """Encode light/dimmer control command."""
        # Standard RV-C light command encoding
        # Instance is already set in byte 0

        if command.command == "set":
            if command.state == "on":
                # Set light on with brightness
                brightness = command.brightness or 100
                # Convert 0-100% to 0-200 (RV-C standard for some lights)
                rvc_brightness = min(200, int(brightness * 2))
                payload[1] = rvc_brightness & 0xFF
            elif command.state == "off":
                # Set light off
                payload[1] = 0
        elif command.command == "toggle":
            # Toggle command - some systems use specific values
            payload[1] = 0xFE  # Common toggle value in RV-C
        elif command.command == "brightness_up":
            # Brightness up command
            payload[1] = 0xFC  # Common brightness up value
        elif command.command == "brightness_down":
            # Brightness down command
            payload[1] = 0xFD  # Common brightness down value

    def _encode_switch_command(
        self, payload: bytearray, command: ControlCommand, spec: dict[str, Any]
    ) -> None:
        """Encode switch control command."""
        # Standard switch encoding
        if command.command == "set":
            if command.state == "on":
                payload[1] = 1
            elif command.state == "off":
                payload[1] = 0
        elif command.command == "toggle":
            payload[1] = 0xFE  # Toggle command

    def _encode_fan_command(
        self, payload: bytearray, command: ControlCommand, spec: dict[str, Any]
    ) -> None:
        """Encode fan control command."""
        # Fan speed control
        if command.command == "set":
            if command.state == "on":
                # Use brightness field as fan speed (0-100%)
                speed = command.brightness or 100
                payload[1] = min(100, speed) & 0xFF
            elif command.state == "off":
                payload[1] = 0
        elif command.command == "toggle":
            payload[1] = 0xFE

    def _encode_generic_command(
        self, payload: bytearray, command: ControlCommand, spec: dict[str, Any]
    ) -> None:
        """Generic command encoding based on signal specifications."""
        signals = spec.get("signals", [])

        for signal in signals:
            signal_name = signal.get("name", "").lower()

            # Map common signal names to command fields
            if "state" in signal_name or "status" in signal_name:
                if command.state == "on":
                    value = 1
                elif command.state == "off":
                    value = 0
                else:
                    continue

                self._set_signal_value(payload, signal, value)

            elif "brightness" in signal_name or "level" in signal_name:
                if command.brightness is not None:
                    self._set_signal_value(payload, signal, command.brightness)

    def _set_signal_value(self, payload: bytearray, signal: dict[str, Any], value: int) -> None:
        """Set a signal value in the payload."""
        start_bit = signal.get("start_bit", 0)
        length = signal.get("length", 8)

        # Apply scale and offset (reverse of decoding)
        scale = signal.get("scale", 1)
        offset = signal.get("offset", 0)

        # Convert physical value to raw value
        raw_value = int((value - offset) / scale)

        # Ensure value fits in the field
        max_value = (1 << length) - 1
        raw_value = max(0, min(max_value, raw_value))

        # Set bits in payload (little-endian)
        self._set_bits(payload, start_bit, length, raw_value)

    def _set_bits(self, data: bytearray, start_bit: int, length: int, value: int) -> None:
        """Set bits in a bytearray (little-endian)."""
        # Convert to integer, modify, convert back
        current_int = int.from_bytes(data, byteorder="little")

        # Create mask and clear existing bits
        mask = (1 << length) - 1
        clear_mask = ~(mask << start_bit)
        current_int &= clear_mask

        # Set new value
        current_int |= (value & mask) << start_bit

        # Convert back to bytes
        new_bytes = current_int.to_bytes(len(data), byteorder="little")
        data[:] = new_bytes

    def _build_can_id(self, spec: dict[str, Any], instance: int) -> int:
        """
        Build CAN ID for the message.

        Args:
            spec: DGN specification
            instance: Device instance number

        Returns:
            CAN ID (29-bit extended)
        """
        # Extract PGN from spec
        pgn_hex = spec.get("pgn", "0")
        pgn = int(pgn_hex, 16)

        # Default priority (6 for most RV-C commands)
        priority = int(spec.get("priority", "6"), 16)

        # Get source address from settings
        source_addr = int(self.settings.controller_source_addr, 16)

        # Build 29-bit CAN ID
        # Format: [Priority(3)] [Reserved(1)] [Data Page(1)] [PDU Format(8)] [PDU Specific(8)] [Source Address(8)]
        return (priority << 26) | (pgn << 8) | source_addr


    def validate_command(self, entity_id: str, command: ControlCommand) -> tuple[bool, str]:
        """
        Validate a command before encoding.

        Args:
            entity_id: Entity ID to validate
            command: Command to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.is_ready():
            return False, "Encoder not ready - configuration not loaded"

        # Check entity exists
        if entity_id not in self.inst_map:
            return False, f"Unknown entity ID: {entity_id}"

        # Validate command structure
        if not command.command:
            return False, "Command field is required"

        # Validate command types
        valid_commands = {"set", "toggle", "brightness_up", "brightness_down"}
        if command.command not in valid_commands:
            return False, f"Invalid command: {command.command}. Must be one of {valid_commands}"

        # Validate state for 'set' command
        if command.command == "set":
            if command.state not in {"on", "off"}:
                return False, "State must be 'on' or 'off' for 'set' command"

            # Validate brightness
            if command.brightness is not None and not 0 <= command.brightness <= 100:
                return False, "Brightness must be between 0 and 100"

        # Check if entity supports commands
        entity_config = self.inst_map[entity_id]
        dgn_hex = entity_config["dgn_hex"]
        command_dgn = self._get_command_dgn(dgn_hex)

        if not command_dgn:
            return False, f"Entity {entity_id} does not support commands (no command DGN mapping)"

        return True, ""

    def get_supported_entities(self) -> list[str]:
        """
        Get list of entity IDs that support encoding commands.

        Returns:
            List of entity IDs that can be controlled
        """
        if not self.is_ready():
            return []

        supported = []
        for entity_id in self.entity_ids:
            if entity_id in self.inst_map:
                entity_config = self.inst_map[entity_id]
                dgn_hex = entity_config["dgn_hex"]
                command_dgn = self._get_command_dgn(dgn_hex)

                if command_dgn:
                    supported.append(entity_id)

        return supported

    def get_encoder_info(self) -> dict[str, Any]:
        """
        Get information about the encoder configuration.

        Returns:
            Dictionary with encoder status and capabilities
        """
        return {
            "ready": self.is_ready(),
            "coach_info": getattr(self, "coach_info", None),
            "spec_version": getattr(self, "spec_meta", {}).get("version", "unknown"),
            "total_entities": len(getattr(self, "entity_ids", [])),
            "supported_entities": len(self.get_supported_entities()),
            "dgn_pairs_count": len(getattr(self, "dgn_pairs", {})),
        }
