"""
RVC Encoder for creating CAN messages from high-level commands.

This module handles encoding of entity control commands into RV-C compliant
CAN messages, supporting single-frame and multi-frame (BAM) transmissions.
"""

import logging
from typing import Any

from backend.core.config import get_settings
from backend.integrations.rvc.decode import load_config_data_v2
from backend.models.can_message import CANMessage
from backend.models.entity import ControlCommand
from backend.models.rvc_config import RVCConfiguration

logger = logging.getLogger(__name__)
MAX_BRIGHTNESS = 100


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
        self.rvc_config = self._load_configuration()

        # Backward-compatible aliases used by existing callers and methods.
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

    def _load_configuration(self) -> RVCConfiguration:
        """Load RVC configuration data using the same system as the decoder."""
        try:
            # Use the same configuration loading as the RVC feature
            spec_path_override = None
            map_path_override = None

            if self.settings.rvc_spec_path:
                spec_path_override = str(self.settings.rvc_spec_path)

            if self.settings.rvc_coach_mapping_path:
                map_path_override = str(self.settings.rvc_coach_mapping_path)

            # Load configuration using the new structured version
            rvc_config = load_config_data_v2(
                rvc_spec_path_override=spec_path_override,
                device_mapping_path_override=map_path_override,
            )
            logger.info("RVC encoder configuration loaded - coach: %s", rvc_config.coach_info)
            return rvc_config

        except Exception as e:
            logger.error("Failed to load RVC encoder configuration: %s", e)
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

        # Some physical entities map to more than one dimmer output that must
        # all be commanded together (e.g. the bedroom ceiling light is driven by
        # instances 25 and 26 -- the physical Mira button commands both). The
        # coach mapping may express this via an optional `command_instances`
        # list; fall back to the single primary instance otherwise.
        command_instances = self._resolve_command_instances(entity_config, instance)

        # entity_map contains status routes only; command DGNs are deliberately
        # excluded so command intent cannot mutate RX state. Resolve metadata
        # by entity identity instead of looking up the command DGN as an RX key.
        device_config = next(
            (config for config in self.entity_map.values() if config.get("entity_id") == entity_id),
            None,
        )
        if device_config is None:
            msg = f"No device mapping found for entity {entity_id}"
            raise EncodingError(msg)

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

        # Encode the command based on device type and command, fanning out over
        # every command instance the entity maps to.
        return self._encode_command_payload(command_spec, command, device_config, command_instances)

    @staticmethod
    def _resolve_command_instances(
        entity_config: dict[str, Any], primary_instance: Any
    ) -> list[int]:
        """Resolve the list of dimmer instances a command should fan out to.

        Reads an optional ``command_instances`` list from the entity's inst_map
        entry (sourced from the coach mapping). Non-integer values are dropped.
        Falls back to ``[primary_instance]`` when no list is present.
        """
        raw_instances = entity_config.get("command_instances")
        resolved: list[int] = []
        if isinstance(raw_instances, list | tuple):
            for value in raw_instances:
                try:
                    resolved.append(int(value))
                except (TypeError, ValueError):
                    continue

        if not resolved:
            try:
                resolved = [int(primary_instance)]
            except (TypeError, ValueError):
                resolved = []

        # De-duplicate while preserving order.
        seen: set[int] = set()
        unique: list[int] = []
        for inst in resolved:
            if inst not in seen:
                seen.add(inst)
                unique.append(inst)
        return unique

    def _get_command_dgn(self, dgn_hex: str) -> str | None:
        """
        Resolve the command DGN for a given entity DGN using dgn_pairs mapping.

        ``dgn_pairs`` is keyed command_dgn -> status_dgn (e.g. "1FEDB": "1FEDA").
        An entity may be registered under either its status DGN or its command
        DGN, so handle both directions.

        Args:
            dgn_hex: The entity's DGN hex string (status or command)

        Returns:
            Command DGN hex string or None if not found
        """
        # If the entity's DGN is already a command DGN (a key in dgn_pairs),
        # then it *is* the command DGN -- return it unchanged. This is the case
        # for lights, whose inst_map entry carries the command DGN 1FEDB.
        if dgn_hex in self.dgn_pairs:
            return dgn_hex

        # Otherwise treat the input as a status DGN and find the command DGN
        # whose paired status matches it.
        for cmd_dgn, stat_dgn in self.dgn_pairs.items():
            if stat_dgn == dgn_hex:
                return cmd_dgn

        # Fallback: try to infer based on common RV-C patterns
        # Many command DGNs are status DGN + 0x100
        try:
            status_dgn_int = int(dgn_hex, 16)
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
        instances: int | str | list[int],
    ) -> list[CANMessage]:
        """
        Encode command payload based on specification and device type.

        Args:
            command_spec: DGN specification from RVC spec
            command: Control command to encode
            device_config: Device configuration from mapping
            instances: One instance number, or a list of instances to fan out
                over (one CANMessage is emitted per instance)

        Returns:
            List of CANMessage objects (one per instance)
        """
        device_type = device_config.get("device_type", "unknown")

        # Normalize to a list so single- and multi-instance callers share a path.
        if isinstance(instances, list):
            instance_list = [int(i) for i in instances]
        else:
            instance_list = [int(instances)]

        messages: list[CANMessage] = []
        for instance_num in instance_list:
            # Create base payload (8 bytes for standard CAN frame)
            payload = bytearray(8)

            # Set instance field (typically byte 0)
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
            messages.append(CANMessage(can_id=can_id, data=bytes(payload), extended=True))

        return messages

    def _encode_light_command(
        self, payload: bytearray, command: ControlCommand, _spec: dict[str, Any]
    ) -> None:
        """Encode a DC_DIMMER_COMMAND_2 (DGN 0x1FEDB) light control command.

        Byte layout verified on the live coach bus (see docs/can-re-findings.md):
            byte0 = instance      (set by caller, left untouched here)
            byte1 = 0xFF          group = none
            byte2 = level         0-200 scale (0xC8 = 100%, 0x00 = off)
            byte3 = 0x00          command = set brightness/level
            byte4 = 0xFF          duration = instant
            byte5 = 0x00
            byte6 = 0xFF
            byte7 = 0xFF

        Confirmed on the wire: 19FEDBF9#19FF6400FF00FFFF set instance 0x19 to
        op_status 0x64, and 19FF0000FF00FFFF turned it off; DC_DIMMER_STATUS_3
        (0x1FEDA) byte2 echoed the commanded level exactly.
        """
        # byte0 (instance) is already populated by the caller.
        # Establish the fixed fields common to every set-level command.
        payload[1] = 0xFF  # group = none
        payload[3] = 0x00  # command = set brightness/level
        payload[4] = 0xFF  # duration = instant
        payload[5] = 0x00
        payload[6] = 0xFF
        payload[7] = 0xFF

        # Compute the desired level (0-200 scale) into byte2.
        if command.command == "set":
            if command.state == "off":
                level = 0x00
            elif command.brightness is not None:
                # 0-100% -> 0-200; clamp to the valid range.
                level = max(0, min(200, round(command.brightness * 2)))
            else:
                # Default "on" with no explicit brightness => full.
                level = 0xC8
        else:
            # toggle / brightness_up / brightness_down are not part of the
            # verified dialect; default to full-on so callers still emit a
            # well-formed frame rather than a malformed no-op.
            level = 0xC8

        payload[2] = level & 0xFF

    def _encode_switch_command(
        self, payload: bytearray, command: ControlCommand, _spec: dict[str, Any]
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
        self, payload: bytearray, command: ControlCommand, _spec: dict[str, Any]
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

    def _build_can_id(self, spec: dict[str, Any], _instance: int) -> int:
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
        # Format: priority, reserved, data page, PDU format/specific, source address.
        return (priority << 26) | (pgn << 8) | source_addr

    @staticmethod
    def _validate_command_fields(command: ControlCommand) -> str | None:
        """Return a validation error for command fields, if any."""
        if not command.command:
            return "Command field is required"

        valid_commands = {"set", "toggle", "brightness_up", "brightness_down"}
        if command.command not in valid_commands:
            return f"Invalid command: {command.command}. Must be one of {valid_commands}"

        if command.command != "set":
            return None
        if command.state not in {"on", "off"}:
            return "State must be 'on' or 'off' for 'set' command"
        if command.brightness is not None and not 0 <= command.brightness <= MAX_BRIGHTNESS:
            return f"Brightness must be between 0 and {MAX_BRIGHTNESS}"
        return None

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

        field_error = self._validate_command_fields(command)
        if field_error:
            return False, field_error

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
