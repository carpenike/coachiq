"""
RV-C to DBC converter utilities.

This module provides utilities to convert between RV-C JSON configurations
and industry-standard DBC files, maintaining backward compatibility.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import cantools
from cantools.database import Database, Message, Signal
from cantools.database.can.database import Node

logger = logging.getLogger(__name__)


class RVCtoDBCConverter:
    """
    Converts RV-C JSON configurations to DBC format and vice versa.

    This maintains backward compatibility with existing RV-C JSON files
    while enabling DBC import/export functionality.
    """

    def __init__(self):
        """Initialize the converter."""
        self.db = Database()
        # Add a default node for RV-C devices
        self.default_node = Node("RVC_Device", comment="Default RV-C device node")
        self.db.nodes.append(self.default_node)

    def rvc_to_dbc(self, rvc_config: dict[str, Any]) -> Database:
        """
        Convert RV-C JSON configuration to DBC database.

        Args:
            rvc_config: RV-C configuration dictionary

        Returns:
            cantools Database object
        """
        self.db = Database()
        self.db.version = "RV-C 1.0"

        # Create nodes for different device types
        nodes = set()
        nodes.add("RVC_Controller")  # Default controller node

        # Process decoders to create messages
        decoders = rvc_config.get("decoders", {})
        for pgn_hex, decoder_info in decoders.items():
            try:
                # Convert hex PGN to integer
                pgn = int(pgn_hex, 16)

                # Create message
                message_name = decoder_info.get("name", f"PGN_{pgn_hex}")
                dlc = decoder_info.get("length", 8)

                # Use extended ID for RV-C (29-bit)
                message = Message(
                    frame_id=pgn,
                    name=message_name.replace(" ", "_").replace("-", "_"),
                    length=dlc,
                    is_extended_frame=True,
                    comment=decoder_info.get("description", ""),
                )

                # Add signals from fields
                fields = decoder_info.get("fields", [])
                for field in fields:
                    signal = self._create_signal_from_field(field)
                    if signal:
                        message.signals.append(signal)

                # Set sender node
                sender_node = decoder_info.get("sender", "RVC_Device")
                nodes.add(sender_node)
                message.senders = [sender_node]

                self.db.messages.append(message)

            except Exception as e:
                logger.warning(f"Failed to convert PGN {pgn_hex}: {e}")

        # Add all unique nodes to database
        for node_name in nodes:
            node = Node(node_name)
            self.db.nodes.append(node)

        return self.db

    def _create_signal_from_field(self, field: dict[str, Any]) -> Signal | None:
        """
        Create a DBC signal from an RV-C field definition.

        Args:
            field: RV-C field dictionary

        Returns:
            cantools Signal object or None
        """
        try:
            name = field.get("name", "Unknown").replace(" ", "_").replace("-", "_")
            start_bit = field.get("start_bit", 0)
            length = field.get("length", 8)

            # RV-C uses Intel byte order (little-endian)
            byte_order = "little_endian"

            # Determine if signed
            is_signed = field.get("signed", False)

            # Get scale and offset
            scale = field.get("scale", 1.0)
            offset = field.get("offset", 0.0)

            # Get min/max values
            minimum = field.get("min")
            maximum = field.get("max")

            # Calculate if not provided
            if minimum is None or maximum is None:
                if is_signed:
                    raw_min = -(2 ** (length - 1))
                    raw_max = (2 ** (length - 1)) - 1
                else:
                    raw_min = 0
                    raw_max = (2**length) - 1

                if minimum is None:
                    minimum = raw_min * scale + offset
                if maximum is None:
                    maximum = raw_max * scale + offset

            # Get unit
            unit = field.get("unit", "")

            # Create signal
            signal = Signal(
                name=name,
                start=start_bit,
                length=length,
                receivers=[],  # Will be populated based on device mappings
                byte_order=byte_order,
                is_signed=is_signed,
                scale=scale,
                offset=offset,
                minimum=minimum,
                maximum=maximum,
                unit=unit,
                comment=field.get("description", ""),
            )

            # Add enumeration values if present
            if "values" in field:
                signal.choices = {}
                for value, description in field["values"].items():
                    try:
                        signal.choices[int(value)] = description
                    except ValueError:
                        pass

            return signal

        except Exception as e:
            logger.warning(f"Failed to create signal from field {field}: {e}")
            return None

    def dbc_to_rvc(self, db: Database) -> dict[str, Any]:
        """
        Convert DBC database to RV-C JSON configuration.

        Args:
            db: cantools Database object

        Returns:
            RV-C configuration dictionary
        """
        rvc_config = {
            "version": db.version or "1.0",
            "decoders": {},
            "device_types": [],
            "nodes": [],
        }

        # Convert nodes
        for node in db.nodes:
            rvc_config["nodes"].append({"name": node.name, "comment": node.comment or ""})

        # Convert messages to decoders
        for message in db.messages:
            pgn_hex = f"{message.frame_id:X}"

            decoder = {
                "name": message.name.replace("_", " "),
                "pgn": message.frame_id,
                "length": message.length,
                "description": message.comment or "",
                "fields": [],
            }

            # Set sender if available
            if message.senders:
                decoder["sender"] = message.senders[0]

            # Convert signals to fields
            for signal in message.signals:
                field = self._create_field_from_signal(signal)
                if field:
                    decoder["fields"].append(field)

            rvc_config["decoders"][pgn_hex] = decoder

        return rvc_config

    def _create_field_from_signal(self, signal: Signal) -> dict[str, Any] | None:
        """
        Create an RV-C field definition from a DBC signal.

        Args:
            signal: cantools Signal object

        Returns:
            RV-C field dictionary or None
        """
        try:
            field = {
                "name": signal.name.replace("_", " "),
                "start_bit": signal.start,
                "length": signal.length,
                "signed": signal.is_signed,
                "scale": signal.scale,
                "offset": signal.offset,
                "unit": signal.unit or "",
                "description": signal.comment or "",
            }

            # Add min/max if different from calculated
            if signal.minimum is not None:
                field["min"] = signal.minimum
            if signal.maximum is not None:
                field["max"] = signal.maximum

            # Add enumeration values
            if signal.choices:
                field["values"] = {}
                for value, description in signal.choices.items():
                    field["values"][str(value)] = description

            return field

        except Exception as e:
            logger.warning(f"Failed to create field from signal {signal}: {e}")
            return None

    async def convert_file(
        self, input_path: str | Path, output_path: str | Path, direction: str = "rvc_to_dbc"
    ) -> None:
        """
        Convert between RV-C JSON and DBC files.

        Args:
            input_path: Path to input file
            output_path: Path to output file
            direction: "rvc_to_dbc" or "dbc_to_rvc"
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if direction == "rvc_to_dbc":
            # Load RV-C JSON
            with open(input_path) as f:
                rvc_config = json.load(f)

            # Convert to DBC
            db = self.rvc_to_dbc(rvc_config)

            # Save DBC file
            db.save(str(output_path))
            logger.info(f"Converted RV-C config to DBC: {output_path}")

        elif direction == "dbc_to_rvc":
            # Load DBC file
            db = cantools.database.load_file(str(input_path))

            # Convert to RV-C
            rvc_config = self.dbc_to_rvc(db)

            # Save JSON file
            with open(output_path, "w") as f:
                json.dump(rvc_config, f, indent=2)

            logger.info(f"Converted DBC to RV-C config: {output_path}")

        else:
            raise ValueError(f"Unknown conversion direction: {direction}")

    def create_sample_dbc(self) -> Database:
        """
        Create a sample DBC database for testing.

        Returns:
            Sample Database object
        """
        db = Database()

        # Add nodes
        controller = Node("RVC_Controller")
        light = Node("RVC_Light")
        temperature = Node("RVC_Temperature")

        db.nodes.extend([controller, light, temperature])

        # Create light control message
        light_msg = Message(
            frame_id=0x1FEED,  # RV-C light command PGN
            name="DC_DIMMER_COMMAND",
            length=8,
            is_extended_frame=True,
            senders=["RVC_Controller"],
        )

        # Add light control signals
        light_msg.signals.append(
            Signal(
                name="Instance",
                start=0,
                length=8,
                receivers=["RVC_Light"],
                byte_order="little_endian",
                is_signed=False,
                scale=1,
                offset=0,
                minimum=0,
                maximum=255,
                unit="",
                comment="Device instance",
            )
        )

        light_msg.signals.append(
            Signal(
                name="Brightness",
                start=8,
                length=8,
                receivers=["RVC_Light"],
                byte_order="little_endian",
                is_signed=False,
                scale=0.5,
                offset=0,
                minimum=0,
                maximum=100,
                unit="%",
                comment="Brightness level (0-100%)",
            )
        )

        db.messages.append(light_msg)

        # Create temperature status message
        temp_msg = Message(
            frame_id=0x1FEA5,  # RV-C temperature status PGN
            name="TEMPERATURE_STATUS",
            length=8,
            is_extended_frame=True,
            senders=["RVC_Temperature"],
        )

        temp_msg.signals.append(
            Signal(
                name="Instance",
                start=0,
                length=8,
                receivers=["RVC_Controller"],
                byte_order="little_endian",
                is_signed=False,
                scale=1,
                offset=0,
                minimum=0,
                maximum=255,
                unit="",
                comment="Sensor instance",
            )
        )

        temp_msg.signals.append(
            Signal(
                name="Temperature",
                start=16,
                length=16,
                receivers=["RVC_Controller"],
                byte_order="little_endian",
                is_signed=False,
                scale=0.03125,
                offset=-273,
                minimum=-273,
                maximum=1735,
                unit="degC",
                comment="Temperature in Celsius",
            )
        )

        db.messages.append(temp_msg)

        return db
