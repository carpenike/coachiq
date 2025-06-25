"""
CAN Bus Recorder for recording and replaying CAN traffic.

This module provides comprehensive CAN traffic recording with:
- High-performance recording with minimal impact
- Flexible filtering options
- Multiple storage formats (JSON, CSV, binary)
- Replay with timing preservation
- Session management and metadata
"""

import asyncio
import json
import logging
import struct
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from backend.core.safety_interfaces import (
    SafeStateAction,
    SafetyAware,
    SafetyClassification,
    SafetyStatus,
)

logger = logging.getLogger(__name__)


class RecordingFormat(str, Enum):
    """Supported recording formats."""

    JSON = "json"
    CSV = "csv"
    BINARY = "binary"
    CANDUMP = "candump"  # socketcan candump compatible format


class RecordingState(str, Enum):
    """Recording session states."""

    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    REPLAYING = "replaying"


@dataclass
class RecordedMessage:
    """Recorded CAN message with metadata."""

    timestamp: float  # Unix timestamp with microsecond precision
    can_id: int
    data: bytes
    interface: str
    is_extended: bool = False
    is_error: bool = False
    is_remote: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "timestamp": self.timestamp,
            "can_id": self.can_id,
            "data": self.data.hex(),
            "interface": self.interface,
            "is_extended": self.is_extended,
            "is_error": self.is_error,
            "is_remote": self.is_remote,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecordedMessage":
        """Create from dictionary format."""
        return cls(
            timestamp=data["timestamp"],
            can_id=data["can_id"],
            data=bytes.fromhex(data["data"]),
            interface=data["interface"],
            is_extended=data.get("is_extended", False),
            is_error=data.get("is_error", False),
            is_remote=data.get("is_remote", False),
        )


@dataclass
class RecordingSession:
    """Recording session metadata."""

    session_id: str
    name: str
    description: str
    start_time: datetime
    end_time: datetime | None
    message_count: int
    interfaces: list[str]
    filters: dict[str, Any]
    format: RecordingFormat
    file_path: Path | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "message_count": self.message_count,
            "interfaces": self.interfaces,
            "filters": self.filters,
            "format": self.format.value,
            "file_path": str(self.file_path) if self.file_path else None,
        }


@dataclass
class ReplayOptions:
    """Options for replay operation."""

    speed_factor: float = 1.0  # 1.0 = real-time, 2.0 = 2x speed, 0.5 = half speed
    loop: bool = False
    start_offset: float = 0.0  # Start replay from offset seconds
    end_offset: float | None = None  # End replay at offset seconds
    interface_mapping: dict[str, str] | None = None  # Map recorded -> replay interfaces
    filter_can_ids: set[int] | None = None  # Only replay specific CAN IDs
    modify_callback: Callable[[RecordedMessage], RecordedMessage | None] | None = None


class CANBusRecorder(SafetyAware):
    """
    CAN bus traffic recorder with replay capabilities.

    Features:
    - High-performance recording with ring buffer
    - Multiple format support (JSON, CSV, binary, candump)
    - Flexible filtering and triggering
    - Replay with timing preservation
    - Session management
    """

    def __init__(
        self,
        buffer_size: int = 100000,  # Maximum messages in memory buffer
        storage_path: Path = Path("./recordings"),
        auto_save_interval: float = 60.0,  # Auto-save every 60 seconds
        max_file_size_mb: float = 100.0,  # Max file size before rotation
    ):
        # Initialize as safety-aware service
        super().__init__(
            safety_classification=SafetyClassification.OPERATIONAL,
            safe_state_action=SafeStateAction.DISABLE,
        )

        self.buffer_size = buffer_size
        self.storage_path = storage_path
        self.auto_save_interval = auto_save_interval
        self.max_file_size_mb = max_file_size_mb

        # Recording state
        self.recording_state = RecordingState.IDLE
        self.current_session: RecordingSession | None = None
        self.message_buffer: deque[RecordedMessage] = deque(maxlen=buffer_size)
        self.recording_task: asyncio.Task | None = None
        self.replay_task: asyncio.Task | None = None

        # Service state
        self._is_running = False

        # Filters
        self.can_id_filter: set[int] | None = None
        self.interface_filter: set[str] | None = None
        self.pgn_filter: set[int] | None = None  # For J1939

        # Statistics
        self.messages_recorded = 0
        self.messages_dropped = 0
        self.bytes_recorded = 0

        # Callbacks
        self.message_callback: Callable[[RecordedMessage], None] | None = None

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # WebSocket manager for broadcasting updates (injected by main.py)
        self._websocket_manager = None

        logger.info(
            "CANBusRecorder initialized: buffer_size=%d, storage=%s", buffer_size, storage_path
        )

    async def start(self) -> None:
        """Start the recorder."""
        logger.info("Starting CAN bus recorder")
        self._is_running = True
        self._set_safety_status(SafetyStatus.SAFE)

    async def stop(self) -> None:
        """Stop the recorder."""
        logger.info("Stopping CAN bus recorder")
        self._is_running = False

        # Stop any active recording
        if self.recording_state == RecordingState.RECORDING:
            await self.stop_recording()

        # Stop any active replay
        if self.recording_state == RecordingState.REPLAYING:
            await self.stop_replay()

    async def emergency_stop(self, reason: str) -> None:
        """
        Emergency stop all recording and replay operations.

        This method implements the SafetyAware emergency stop interface
        for immediate cessation of all recorder activities.

        Args:
            reason: Reason for emergency stop (for audit logging)
        """
        logger.critical("CAN bus recorder emergency stop: %s", reason)

        # Set emergency stop state
        self._set_emergency_stop_active(True)

        # Immediately stop all operations
        self._is_running = False
        self.recording_state = RecordingState.IDLE

        # Cancel recording task
        if self.recording_task:
            self.recording_task.cancel()
            try:
                await self.recording_task
            except asyncio.CancelledError:
                pass

        # Cancel replay task
        if self.replay_task:
            self.replay_task.cancel()
            try:
                await self.replay_task
            except asyncio.CancelledError:
                pass

        # Save current session if recording
        if self.current_session:
            try:
                self.current_session.end_time = datetime.now(UTC)
                await self._save_recording(self.current_session)
                logger.info(
                    "Emergency saved recording session: %s", self.current_session.session_id
                )
            except Exception as e:
                logger.error("Error saving recording during emergency stop: %s", e)
            finally:
                self.current_session = None

        logger.critical("CAN bus recorder emergency stop completed")

    async def get_safety_status(self) -> SafetyStatus:
        """Get current safety status of the recorder."""
        if self._emergency_stop_active:
            return SafetyStatus.EMERGENCY_STOP
        if not self._is_running:
            return SafetyStatus.SAFE
        if self.recording_state in [RecordingState.RECORDING, RecordingState.REPLAYING]:
            # Check buffer usage
            buffer_usage = len(self.message_buffer) / self.buffer_size
            if buffer_usage > 0.9:
                return SafetyStatus.DEGRADED
            return SafetyStatus.SAFE
        return SafetyStatus.SAFE

    async def validate_safety_interlock(self, operation: str) -> bool:
        """
        Validate if recorder operation is safe to perform.

        Args:
            operation: Operation being validated (e.g., "start_recording", "start_replay")

        Returns:
            True if operation is safe to perform
        """
        # Check basic safety status
        safety_status = await self.get_safety_status()
        if safety_status == SafetyStatus.EMERGENCY_STOP:
            logger.warning("Recorder operation %s blocked: emergency stop active", operation)
            return False

        if not self._is_running and operation not in ["start"]:
            logger.warning("Recorder operation %s blocked: service not running", operation)
            return False

        # Additional operation-specific validations
        if operation == "start_recording" and self.recording_state != RecordingState.IDLE:
            logger.warning(
                "Start recording blocked: recorder not idle (state: %s)", self.recording_state.value
            )
            return False

        if operation == "start_replay" and self.recording_state != RecordingState.IDLE:
            logger.warning(
                "Start replay blocked: recorder not idle (state: %s)", self.recording_state.value
            )
            return False

        return True

    # Legacy methods for backward compatibility
    async def startup(self) -> None:
        """Legacy startup method - delegates to start()."""
        await self.start()

    async def shutdown(self) -> None:
        """Legacy shutdown method - delegates to stop()."""
        await self.stop()

    def set_filters(
        self,
        can_ids: set[int] | None = None,
        interfaces: set[str] | None = None,
        pgns: set[int] | None = None,
    ) -> None:
        """Set recording filters."""
        self.can_id_filter = can_ids
        self.interface_filter = interfaces
        self.pgn_filter = pgns
        logger.info(
            f"Recording filters updated - CAN IDs: {can_ids}, Interfaces: {interfaces}, PGNs: {pgns}"
        )

    def should_record_message(self, can_id: int, interface: str) -> bool:
        """Check if a message should be recorded based on filters."""
        # Check interface filter
        if self.interface_filter and interface not in self.interface_filter:
            return False

        # Check CAN ID filter
        if self.can_id_filter and can_id not in self.can_id_filter:
            return False

        # Check PGN filter for J1939 (29-bit extended IDs)
        if self.pgn_filter and (can_id & 0x80000000):  # Extended ID
            pgn = (can_id >> 8) & 0x3FFFF  # Extract PGN from J1939 ID
            if pgn not in self.pgn_filter:
                return False

        return True

    async def record_message(
        self,
        can_id: int,
        data: bytes,
        interface: str,
        is_extended: bool = False,
        is_error: bool = False,
        is_remote: bool = False,
    ) -> None:
        """Record a CAN message."""
        if self.recording_state != RecordingState.RECORDING:
            return

        if not self.should_record_message(can_id, interface):
            return

        message = RecordedMessage(
            timestamp=time.time(),
            can_id=can_id,
            data=data,
            interface=interface,
            is_extended=is_extended,
            is_error=is_error,
            is_remote=is_remote,
        )

        self.message_buffer.append(message)
        self.messages_recorded += 1
        self.bytes_recorded += len(data)

        if self.current_session:
            self.current_session.message_count += 1

        # Call callback if registered
        if self.message_callback:
            try:
                self.message_callback(message)
            except Exception as e:
                logger.error(f"Error in message callback: {e}")

    async def start_recording(
        self,
        name: str,
        description: str = "",
        format: RecordingFormat = RecordingFormat.JSON,
    ) -> RecordingSession:
        """Start a new recording session."""
        # Check safety interlock
        if not await self.validate_safety_interlock("start_recording"):
            raise RuntimeError("Start recording blocked by safety interlock")

        if self.recording_state != RecordingState.IDLE:
            raise RuntimeError(f"Cannot start recording in state {self.recording_state.value}")

        # Create session
        session_id = f"rec_{int(time.time() * 1000)}"
        self.current_session = RecordingSession(
            session_id=session_id,
            name=name,
            description=description,
            start_time=datetime.now(UTC),
            end_time=None,
            message_count=0,
            interfaces=list(self.interface_filter) if self.interface_filter else ["all"],
            filters={
                "can_ids": list(self.can_id_filter) if self.can_id_filter else None,
                "pgns": list(self.pgn_filter) if self.pgn_filter else None,
            },
            format=format,
            file_path=None,
        )

        # Clear buffer
        self.message_buffer.clear()
        self.messages_recorded = 0
        self.messages_dropped = 0
        self.bytes_recorded = 0

        # Start recording
        self.recording_state = RecordingState.RECORDING
        self.recording_task = asyncio.create_task(self._auto_save_task())

        logger.info(f"Started recording session {session_id}: {name}")

        # Broadcast status update
        await self._broadcast_status()

        return self.current_session

    async def stop_recording(self) -> RecordingSession | None:
        """Stop the current recording session."""
        if self.recording_state != RecordingState.RECORDING:
            return None

        self.recording_state = RecordingState.IDLE

        # Broadcast status update
        await self._broadcast_status()

        if self.recording_task:
            self.recording_task.cancel()
            try:
                await self.recording_task
            except asyncio.CancelledError:
                pass

        if self.current_session:
            self.current_session.end_time = datetime.now(UTC)

            # Save final data
            file_path = await self._save_recording(self.current_session)
            self.current_session.file_path = file_path

            session = self.current_session
            self.current_session = None

            logger.info(
                f"Stopped recording session {session.session_id}: {session.message_count} messages"
            )
            return session

        return None

    async def pause_recording(self) -> None:
        """Pause the current recording."""
        if self.recording_state == RecordingState.RECORDING:
            self.recording_state = RecordingState.PAUSED
            logger.info("Recording paused")
            await self._broadcast_status()

    async def resume_recording(self) -> None:
        """Resume a paused recording."""
        if self.recording_state == RecordingState.PAUSED:
            self.recording_state = RecordingState.RECORDING
            logger.info("Recording resumed")
            await self._broadcast_status()

    async def _auto_save_task(self) -> None:
        """Periodically save recorded data."""
        try:
            while self.recording_state in (RecordingState.RECORDING, RecordingState.PAUSED):
                await asyncio.sleep(self.auto_save_interval)

                if self.current_session and len(self.message_buffer) > 0:
                    await self._save_recording(self.current_session, incremental=True)

        except asyncio.CancelledError:
            pass

    async def _save_recording(
        self,
        session: RecordingSession,
        incremental: bool = False,
    ) -> Path:
        """Save recording to file."""
        # Generate filename
        timestamp = session.start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"{session.name}_{timestamp}.{session.format.value}"
        file_path = self.storage_path / filename

        # Copy messages to avoid modification during iteration
        messages = list(self.message_buffer)

        if session.format == RecordingFormat.JSON:
            await self._save_json(file_path, session, messages, incremental)
        elif session.format == RecordingFormat.CSV:
            await self._save_csv(file_path, session, messages, incremental)
        elif session.format == RecordingFormat.BINARY:
            await self._save_binary(file_path, session, messages, incremental)
        elif session.format == RecordingFormat.CANDUMP:
            await self._save_candump(file_path, session, messages, incremental)

        return file_path

    async def _save_json(
        self,
        file_path: Path,
        session: RecordingSession,
        messages: list[RecordedMessage],
        incremental: bool,
    ) -> None:
        """Save in JSON format."""
        data = {
            "session": session.to_dict(),
            "messages": [msg.to_dict() for msg in messages],
        }

        # Use async file I/O
        import aiofiles

        async with aiofiles.open(file_path, "w") as f:
            await f.write(json.dumps(data, indent=2))

    async def _save_csv(
        self,
        file_path: Path,
        session: RecordingSession,
        messages: list[RecordedMessage],
        incremental: bool,
    ) -> None:
        """Save in CSV format."""
        import aiofiles

        mode = "a" if incremental and file_path.exists() else "w"
        async with aiofiles.open(file_path, mode) as f:
            if mode == "w":
                # Write header
                await f.write("timestamp,can_id,data,interface,is_extended,is_error,is_remote\n")

            for msg in messages:
                row = f"{msg.timestamp},{msg.can_id:08X},{msg.data.hex()},{msg.interface},"
                row += f"{msg.is_extended},{msg.is_error},{msg.is_remote}\n"
                await f.write(row)

    async def _save_binary(
        self,
        file_path: Path,
        session: RecordingSession,
        messages: list[RecordedMessage],
        incremental: bool,
    ) -> None:
        """Save in binary format for space efficiency."""
        import aiofiles

        mode = "ab" if incremental and file_path.exists() else "wb"
        async with aiofiles.open(file_path, mode) as f:
            if mode == "wb":
                # Write header: magic number + version
                await f.write(b"CANR\x01\x00\x00\x00")

            for msg in messages:
                # Format: timestamp(8) + can_id(4) + flags(1) + data_len(1) + data(N)
                flags = (msg.is_extended << 0) | (msg.is_error << 1) | (msg.is_remote << 2)
                packed = struct.pack(
                    "<dIBB",
                    msg.timestamp,
                    msg.can_id,
                    flags,
                    len(msg.data),
                )
                await f.write(packed + msg.data)

    async def _save_candump(
        self,
        file_path: Path,
        session: RecordingSession,
        messages: list[RecordedMessage],
        incremental: bool,
    ) -> None:
        """Save in candump format (socketcan compatible)."""
        import aiofiles

        mode = "a" if incremental and file_path.exists() else "w"
        async with aiofiles.open(file_path, mode) as f:
            for msg in messages:
                # Format: (timestamp) interface can_id#data
                can_id_str = f"{msg.can_id:08X}" if msg.is_extended else f"{msg.can_id:03X}"
                line = f"({msg.timestamp:.6f}) {msg.interface} {can_id_str}#{msg.data.hex()}\n"
                await f.write(line)

    async def load_recording(self, file_path: str | Path) -> RecordingSession:
        """Load a recording from file."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Recording file not found: {file_path}")

        # Determine format from extension
        extension = file_path.suffix.lower()[1:]  # Remove dot
        format = RecordingFormat(extension)

        if format == RecordingFormat.JSON:
            return await self._load_json(file_path)
        if format == RecordingFormat.CSV:
            return await self._load_csv(file_path)
        if format == RecordingFormat.BINARY:
            return await self._load_binary(file_path)
        if format == RecordingFormat.CANDUMP:
            return await self._load_candump(file_path)
        raise ValueError(f"Unsupported format: {format}")

    async def _load_json(self, file_path: Path) -> RecordingSession:
        """Load JSON format recording."""
        import aiofiles

        async with aiofiles.open(file_path) as f:
            data = json.loads(await f.read())

        # Load session metadata
        session_data = data["session"]
        session = RecordingSession(
            session_id=session_data["session_id"],
            name=session_data["name"],
            description=session_data["description"],
            start_time=datetime.fromisoformat(session_data["start_time"]),
            end_time=datetime.fromisoformat(session_data["end_time"])
            if session_data["end_time"]
            else None,
            message_count=session_data["message_count"],
            interfaces=session_data["interfaces"],
            filters=session_data["filters"],
            format=RecordingFormat(session_data["format"]),
            file_path=file_path,
        )

        # Load messages into buffer
        self.message_buffer.clear()
        for msg_data in data["messages"]:
            self.message_buffer.append(RecordedMessage.from_dict(msg_data))

        return session

    async def _load_csv(self, file_path: Path) -> RecordingSession:
        """Load CSV format recording."""
        # TODO: Implement CSV loading
        raise NotImplementedError("CSV loading not yet implemented")

    async def _load_binary(self, file_path: Path) -> RecordingSession:
        """Load binary format recording."""
        # TODO: Implement binary loading
        raise NotImplementedError("Binary loading not yet implemented")

    async def _load_candump(self, file_path: Path) -> RecordingSession:
        """Load candump format recording."""
        # TODO: Implement candump loading
        raise NotImplementedError("Candump loading not yet implemented")

    async def start_replay(
        self,
        session_or_file: RecordingSession | str | Path,
        options: ReplayOptions | None = None,
        can_sender: Callable[[int, bytes, str], asyncio.Task] | None = None,
    ) -> None:
        """Start replaying a recording."""
        if self.recording_state != RecordingState.IDLE:
            raise RuntimeError(f"Cannot start replay in state {self.recording_state}")

        if not can_sender:
            raise ValueError("CAN sender callback required for replay")

        # Load recording if file path provided
        if isinstance(session_or_file, (str, Path)):
            session = await self.load_recording(session_or_file)
        else:
            session = session_or_file

        options = options or ReplayOptions()

        self.recording_state = RecordingState.REPLAYING
        self.replay_task = asyncio.create_task(self._replay_messages(session, options, can_sender))

    async def stop_replay(self) -> None:
        """Stop the current replay."""
        if self.recording_state != RecordingState.REPLAYING:
            return

        self.recording_state = RecordingState.IDLE

        if self.replay_task:
            self.replay_task.cancel()
            try:
                await self.replay_task
            except asyncio.CancelledError:
                pass

        logger.info("Replay stopped")

    async def _replay_messages(
        self,
        session: RecordingSession,
        options: ReplayOptions,
        can_sender: Callable[[int, bytes, str], asyncio.Task],
    ) -> None:
        """Replay recorded messages with timing preservation."""
        try:
            messages = list(self.message_buffer)
            if not messages:
                logger.warning("No messages to replay")
                return

            # Apply time range filtering
            start_time = messages[0].timestamp + options.start_offset
            end_time = messages[-1].timestamp
            if options.end_offset is not None:
                end_time = messages[0].timestamp + options.end_offset

            # Filter messages by time range
            messages = [msg for msg in messages if start_time <= msg.timestamp <= end_time]

            # Apply CAN ID filtering
            if options.filter_can_ids:
                messages = [msg for msg in messages if msg.can_id in options.filter_can_ids]

            logger.info(
                f"Starting replay of {len(messages)} messages at {options.speed_factor}x speed"
            )

            while self.recording_state == RecordingState.REPLAYING:
                replay_start_time = time.time()
                base_timestamp = messages[0].timestamp

                for i, msg in enumerate(messages):
                    if self.recording_state != RecordingState.REPLAYING:
                        break

                    # Apply modification callback if provided
                    if options.modify_callback:
                        modified_msg = options.modify_callback(msg)
                        if modified_msg is None:
                            continue  # Skip this message
                        msg = modified_msg

                    # Calculate timing
                    relative_time = (msg.timestamp - base_timestamp) / options.speed_factor
                    target_time = replay_start_time + relative_time
                    current_time = time.time()

                    # Wait for the right time
                    if current_time < target_time:
                        await asyncio.sleep(target_time - current_time)

                    # Map interface if needed
                    interface = msg.interface
                    if options.interface_mapping and msg.interface in options.interface_mapping:
                        interface = options.interface_mapping[msg.interface]

                    # Send the message
                    try:
                        await can_sender(msg.can_id, msg.data, interface)
                    except Exception as e:
                        logger.error(f"Error sending replay message: {e}")

                    # Log progress periodically
                    if i % 1000 == 0:
                        progress = (i / len(messages)) * 100
                        logger.debug(f"Replay progress: {progress:.1f}%")

                if not options.loop:
                    break

                logger.info("Replay loop completed, restarting...")

        except asyncio.CancelledError:
            logger.info("Replay cancelled")
        except Exception as e:
            logger.error(f"Replay error: {e}")
        finally:
            self.recording_state = RecordingState.IDLE

    async def _broadcast_status(self) -> None:
        """Broadcast current status via WebSocket if available."""
        if self._websocket_manager:
            try:
                status = self.get_status()
                await self._websocket_manager.broadcast_can_recorder_update("status", status)
            except Exception as e:
                logger.debug(f"Failed to broadcast recorder status: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get current recorder status."""
        return {
            "state": self.recording_state.value,
            "current_session": self.current_session.to_dict() if self.current_session else None,
            "buffer_size": len(self.message_buffer),
            "buffer_capacity": self.buffer_size,
            "messages_recorded": self.messages_recorded,
            "messages_dropped": self.messages_dropped,
            "bytes_recorded": self.bytes_recorded,
            "filters": {
                "can_ids": list(self.can_id_filter) if self.can_id_filter else None,
                "interfaces": list(self.interface_filter) if self.interface_filter else None,
                "pgns": list(self.pgn_filter) if self.pgn_filter else None,
            },
        }

    async def list_recordings(self) -> list[dict[str, Any]]:
        """List all available recordings."""
        recordings = []

        for file_path in self.storage_path.glob("*"):
            if file_path.is_file() and file_path.suffix[1:] in [f.value for f in RecordingFormat]:
                try:
                    # Get file info
                    stat = file_path.stat()
                    recordings.append(
                        {
                            "filename": file_path.name,
                            "path": str(file_path),
                            "size_bytes": stat.st_size,
                            "size_mb": round(stat.st_size / (1024 * 1024), 2),
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "format": file_path.suffix[1:],
                        }
                    )
                except Exception as e:
                    logger.error(f"Error listing recording {file_path}: {e}")

        return sorted(recordings, key=lambda x: x["modified"], reverse=True)

    async def delete_recording(self, filename: str) -> bool:
        """Delete a recording file."""
        file_path = self.storage_path / filename

        if not file_path.exists():
            return False

        try:
            file_path.unlink()
            logger.info(f"Deleted recording: {filename}")
            return True
        except Exception as e:
            logger.error(f"Error deleting recording {filename}: {e}")
            return False
