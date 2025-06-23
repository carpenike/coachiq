"""
Async wrapper for cantools DBC operations.

This module provides an asynchronous interface to cantools' synchronous
DBC database operations, preventing blocking of the asyncio event loop.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import cantools
from cantools.database import Database, Message, Signal

logger = logging.getLogger(__name__)


class DBCDecodingError(Exception):
    """Raised when DBC decoding fails."""


class DBCDatabase:
    """
    Async wrapper for cantools DBC database operations.

    This class provides thread-safe async methods for loading and using
    DBC files without blocking the event loop.
    """

    def __init__(self, max_workers: int = 2):
        """
        Initialize the async DBC database handler.

        Args:
            max_workers: Maximum number of threads for decode operations
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.db: Database | None = None
        self.filepath: Path | None = None
        self._lock = asyncio.Lock()

    async def load_file(self, filepath: str | Path) -> None:
        """
        Load a DBC file asynchronously.

        Args:
            filepath: Path to the DBC file

        Raises:
            FileNotFoundError: If the DBC file doesn't exist
            ValueError: If the DBC file is invalid
        """
        async with self._lock:
            filepath = Path(filepath)
            if not filepath.exists():
                raise FileNotFoundError(f"DBC file not found: {filepath}")

            try:
                loop = asyncio.get_running_loop()
                self.db = await loop.run_in_executor(
                    self.executor, self._load_file_sync, str(filepath)
                )
                self.filepath = filepath
                logger.info(f"Loaded DBC file: {filepath} with {len(self.db.messages)} messages")
            except Exception as e:
                raise ValueError(f"Failed to load DBC file: {e}")

    def _load_file_sync(self, filepath: str) -> Database:
        """
        Load DBC file synchronously with proper encoding handling.

        This method handles encoding issues by trying multiple encodings
        and using string parsing which is more robust than file parsing.
        """
        encodings = ["utf-8", "iso-8859-1", "cp1252", "ascii"]

        for encoding in encodings:
            try:
                with open(filepath, encoding=encoding) as f:
                    content = f.read()

                # Use string parsing instead of file parsing
                return cantools.database.load_string(content)

            except UnicodeDecodeError:
                continue
            except Exception as e:
                if encoding == encodings[-1]:
                    # Last encoding attempt failed
                    raise ValueError(f"Failed to parse DBC file with any encoding: {e}")
                continue

        raise ValueError("Could not decode DBC file with any supported encoding")

    async def decode_message(
        self,
        arbitration_id: int,
        data: bytes,
        decode_choices: bool = True,
        scaling: bool = True,
        is_extended: bool = False,
    ) -> dict[str, Any]:
        """
        Decode a CAN message using the loaded DBC.

        Args:
            arbitration_id: CAN message ID
            data: Message data bytes
            decode_choices: Decode enumeration values
            scaling: Apply signal scaling
            is_extended: Whether this is an extended CAN ID

        Returns:
            Dictionary of signal names to values

        Raises:
            DBCDecodingError: If decoding fails
            RuntimeError: If no DBC is loaded
        """
        if not self.db:
            raise RuntimeError("No DBC file loaded")

        try:
            loop = asyncio.get_running_loop()
            decoded = await loop.run_in_executor(
                self.executor,
                self._decode_message_sync,
                arbitration_id,
                data,
                decode_choices,
                scaling,
                is_extended,
            )
            return decoded
        except Exception as e:
            raise DBCDecodingError(f"Failed to decode message {arbitration_id:08X}: {e}")

    def _decode_message_sync(
        self,
        arbitration_id: int,
        data: bytes,
        decode_choices: bool,
        scaling: bool,
        is_extended: bool,
    ) -> dict[str, Any]:
        """Synchronous message decode operation."""
        if not self.db:
            raise RuntimeError("No DBC loaded")

        # Get the message definition
        message = self.db.get_message_by_frame_id(arbitration_id)

        # Decode the message
        return message.decode(data, decode_choices=decode_choices, scaling=scaling)

    async def encode_message(
        self,
        name_or_id: str | int,
        data: dict[str, Any],
        scaling: bool = True,
        padding: bool = True,
        strict: bool = False,
    ) -> tuple[int, bytes]:
        """
        Encode data into a CAN message.

        Args:
            name_or_id: Message name or ID
            data: Dictionary of signal names to values
            scaling: Apply signal scaling
            padding: Pad message to DLC length
            strict: Require all signals to be specified

        Returns:
            Tuple of (arbitration_id, data_bytes)

        Raises:
            DBCDecodingError: If encoding fails
            RuntimeError: If no DBC is loaded
        """
        if not self.db:
            raise RuntimeError("No DBC file loaded")

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                self.executor, self._encode_message_sync, name_or_id, data, scaling, padding, strict
            )
            return result
        except Exception as e:
            raise DBCDecodingError(f"Failed to encode message: {e}")

    def _encode_message_sync(
        self,
        name_or_id: str | int,
        data: dict[str, Any],
        scaling: bool,
        padding: bool,
        strict: bool,
    ) -> tuple[int, bytes]:
        """Synchronous message encode operation."""
        if not self.db:
            raise RuntimeError("No DBC loaded")

        # Get message by name or ID
        if isinstance(name_or_id, str):
            message = self.db.get_message_by_name(name_or_id)
        else:
            message = self.db.get_message_by_frame_id(name_or_id)

        # Encode the data
        data_bytes = message.encode(data, scaling=scaling, padding=padding, strict=strict)

        return message.frame_id, data_bytes

    async def get_message_list(self) -> list[dict[str, Any]]:
        """
        Get a list of all messages in the DBC.

        Returns:
            List of message definitions with their signals
        """
        if not self.db:
            raise RuntimeError("No DBC file loaded")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._get_message_list_sync)

    def _get_message_list_sync(self) -> list[dict[str, Any]]:
        """Get message list synchronously."""
        if not self.db:
            return []

        messages = []
        for msg in self.db.messages:
            message_info = {
                "name": msg.name,
                "id": msg.frame_id,
                "id_hex": f"{msg.frame_id:08X}",
                "is_extended": msg.is_extended_frame,
                "length": msg.length,
                "cycle_time": msg.cycle_time,
                "comment": msg.comment,
                "signals": [],
            }

            for signal in msg.signals:
                signal_info = {
                    "name": signal.name,
                    "start_bit": signal.start,
                    "length": signal.length,
                    "byte_order": signal.byte_order,
                    "signed": signal.is_signed,
                    "scale": signal.scale,
                    "offset": signal.offset,
                    "minimum": signal.minimum,
                    "maximum": signal.maximum,
                    "unit": signal.unit,
                    "comment": signal.comment,
                    "choices": signal.choices if hasattr(signal, "choices") else {},
                }
                message_info["signals"].append(signal_info)

            messages.append(message_info)

        return messages

    async def find_signal(self, signal_name: str) -> dict[str, Any] | None:
        """
        Find a signal by name across all messages.

        Args:
            signal_name: Name of the signal to find

        Returns:
            Signal info with parent message, or None if not found
        """
        if not self.db:
            raise RuntimeError("No DBC file loaded")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._find_signal_sync, signal_name)

    def _find_signal_sync(self, signal_name: str) -> dict[str, Any] | None:
        """Find signal synchronously."""
        if not self.db:
            return None

        for msg in self.db.messages:
            for signal in msg.signals:
                if signal.name == signal_name:
                    return {
                        "signal_name": signal.name,
                        "message_name": msg.name,
                        "message_id": msg.frame_id,
                        "message_id_hex": f"{msg.frame_id:08X}",
                        "start_bit": signal.start,
                        "length": signal.length,
                        "scale": signal.scale,
                        "offset": signal.offset,
                        "unit": signal.unit,
                    }
        return None

    async def export_to_dict(self) -> dict[str, Any]:
        """
        Export the DBC database to a dictionary format.

        This can be used for JSON serialization or conversion
        to other formats.
        """
        if not self.db:
            raise RuntimeError("No DBC file loaded")

        return {
            "version": getattr(self.db, "version", ""),
            "messages": await self.get_message_list(),
            "nodes": [node.name for node in getattr(self.db, "nodes", [])],
            "filepath": str(self.filepath) if self.filepath else None,
        }

    def __del__(self):
        """Cleanup thread pool on deletion."""
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)


class DBCManager:
    """
    Manager for multiple DBC databases.

    Allows loading and switching between multiple DBC files for
    different protocols or vehicle configurations.
    """

    def __init__(self):
        """Initialize the DBC manager."""
        self.databases: dict[str, DBCDatabase] = {}
        self.active_db: str | None = None

    async def load_dbc(self, name: str, filepath: str | Path) -> None:
        """
        Load a DBC file with a given name.

        Args:
            name: Name to reference this DBC
            filepath: Path to the DBC file
        """
        db = DBCDatabase()
        await db.load_file(filepath)
        self.databases[name] = db

        # Set as active if it's the first one
        if self.active_db is None:
            self.active_db = name

        logger.info(f"Loaded DBC '{name}' from {filepath}")

    def set_active(self, name: str) -> None:
        """
        Set the active DBC database.

        Args:
            name: Name of the DBC to make active

        Raises:
            KeyError: If the named DBC doesn't exist
        """
        if name not in self.databases:
            raise KeyError(f"DBC '{name}' not loaded")
        self.active_db = name

    def get_active(self) -> DBCDatabase | None:
        """Get the currently active DBC database."""
        if self.active_db:
            return self.databases.get(self.active_db)
        return None

    def get(self, name: str) -> DBCDatabase | None:
        """Get a specific DBC database by name."""
        return self.databases.get(name)

    async def decode_with_fallback(
        self, arbitration_id: int, data: bytes, **kwargs
    ) -> dict[str, Any] | None:
        """
        Try to decode a message using all loaded DBCs.

        First tries the active DBC, then falls back to others.

        Returns:
            Decoded signals or None if no DBC could decode it
        """
        # Try active DB first
        if self.active_db:
            try:
                db = self.databases[self.active_db]
                return await db.decode_message(arbitration_id, data, **kwargs)
            except DBCDecodingError:
                pass

        # Try other DBCs
        for name, db in self.databases.items():
            if name != self.active_db:
                try:
                    return await db.decode_message(arbitration_id, data, **kwargs)
                except DBCDecodingError:
                    continue

        return None


# Singleton instance
_dbc_manager = DBCManager()


def get_dbc_manager() -> DBCManager:
    """Get the global DBC manager instance."""
    return _dbc_manager
