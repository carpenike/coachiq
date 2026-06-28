"""
BAM (Broadcast Announce Message) handler for multi-packet RV-C messages.

This module handles the reassembly of multi-packet messages sent via the
J1939/RV-C transport protocol. BAM is used for messages larger than 8 bytes
that need to be split across multiple CAN frames.

Transport Protocol PGNs:
- 0xEC00 (60416): Transport Protocol Control (TP.CM) - BAM announcement
- 0xEB00 (60160): Transport Protocol Data Transfer (TP.DT) - Data packets
"""

# ruff: noqa: G004

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BAMSession:
    """Represents an active BAM message reassembly session."""

    source_address: int
    target_pgn: int
    total_size: int
    total_packets: int
    received_packets: dict[int, bytes] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    complete: bool = False
    reassembled_data: bytes | None = None


class BAMHandler:
    """
    Handles reassembly of multi-packet BAM messages.

    The BAM protocol is used for broadcasting messages larger than 8 bytes
    to all nodes on the network. Unlike the peer-to-peer protocol, BAM
    doesn't require acknowledgments from receivers.
    """

    # Transport Protocol PGNs
    TP_CM_PGN = 0xEC00  # Transport Protocol Control
    TP_DT_PGN = 0xEB00  # Transport Protocol Data Transfer
    TP_CM_PF = 0xEC
    TP_DT_PF = 0xEB
    BAM_CONTROL_BYTE = 0x20  # Identifies a BAM start message

    # CAN frame constants
    CAN_FRAME_SIZE = 8  # Standard CAN frame data size

    def __init__(self, session_timeout: float = 30.0, max_concurrent_sessions: int = 100):
        """
        Initialize the BAM handler.

        Args:
            session_timeout: Maximum time in seconds to wait for a complete message
            max_concurrent_sessions: Maximum number of concurrent BAM sessions to track
        """
        self.sessions: dict[tuple[int, int], BAMSession] = {}
        self.source_to_sessions: dict[int, list[int]] = {}  # source -> [target_pgns]
        self.session_timeout = session_timeout
        self.max_concurrent_sessions = max_concurrent_sessions
        self._last_cleanup = time.time()
        self._cleanup_interval = 10.0  # Run cleanup every 10 seconds

    @classmethod
    def normalize_transport_pgn(cls, pgn: int) -> int:
        """Normalize PDU1 TP PGNs by clearing the destination-address byte."""
        protocol_format = (pgn >> 8) & 0xFF
        if protocol_format in {cls.TP_CM_PF, cls.TP_DT_PF}:
            return pgn & 0x3FF00
        return pgn

    def process_frame(self, pgn: int, data: bytes, source_address: int) -> tuple[int, bytes] | None:
        """
        Process a CAN frame that might be part of a BAM transfer.

        Args:
            pgn: The Parameter Group Number of the message
            data: The 8-byte data payload
            source_address: The source address of the message

        Returns:
            Tuple of (target_pgn, reassembled_data) if a complete message is available,
            None otherwise
        """
        # Periodic cleanup of stale sessions
        cleanup_after = min(self._cleanup_interval, self.session_timeout)
        if time.time() - self._last_cleanup > cleanup_after:
            self._cleanup_stale_sessions()

        normalized_pgn = self.normalize_transport_pgn(pgn)

        if normalized_pgn == self.TP_CM_PGN:
            return self._handle_control_message(data, source_address)
        if normalized_pgn == self.TP_DT_PGN:
            return self._handle_data_transfer(data, source_address)

        return None

    def _handle_control_message(self, data: bytes, source_address: int) -> tuple[int, bytes] | None:
        """Handle a Transport Protocol Control message."""
        if len(data) < self.CAN_FRAME_SIZE:
            logger.warning(f"TP.CM message too short: {len(data)} bytes")
            return None

        control_byte = data[0]

        # Check if this is a BAM start message
        if control_byte != self.BAM_CONTROL_BYTE:
            # Not a BAM message, might be RTS/CTS
            return None

        # Extract BAM header information
        total_size = int.from_bytes(data[1:3], "little")
        total_packets = data[3]
        # data[4] is reserved (0xFF)
        pgn_bytes = data[5:8]
        # PGN is stored in J1939 format (3 bytes, little-endian)
        target_pgn = int.from_bytes(pgn_bytes, "little")

        # Limit concurrent sessions to prevent memory issues
        if len(self.sessions) >= self.max_concurrent_sessions:
            self._cleanup_oldest_session()

        # Create new session
        session_key = (source_address, target_pgn)

        if session_key in self.sessions:
            logger.warning(
                "Overwriting existing BAM session for source=%02X, PGN=%05X",
                source_address,
                target_pgn,
            )

        self.sessions[session_key] = BAMSession(
            source_address=source_address,
            target_pgn=target_pgn,
            total_size=total_size,
            total_packets=total_packets,
        )

        # Update source-to-sessions mapping for O(1) lookup
        if source_address not in self.source_to_sessions:
            self.source_to_sessions[source_address] = []
        if target_pgn not in self.source_to_sessions[source_address]:
            self.source_to_sessions[source_address].append(target_pgn)

        logger.debug(
            "Started BAM session: source=%02X, PGN=%05X, size=%d, packets=%d",
            source_address,
            target_pgn,
            total_size,
            total_packets,
        )

        return None

    def _handle_data_transfer(self, data: bytes, source_address: int) -> tuple[int, bytes] | None:
        """Handle a Transport Protocol Data Transfer message."""
        if len(data) < self.CAN_FRAME_SIZE:
            logger.warning(f"TP.DT message too short: {len(data)} bytes")
            return None

        sequence_number = data[0]
        payload = data[1:8]  # 7 bytes of actual data per packet

        # Find the active session for this source using O(1) lookup
        session = None
        session_key = None

        # Use O(1) lookup to source's active sessions
        target_pgns = self.source_to_sessions.get(source_address, [])
        for target_pgn in target_pgns:
            potential_key = (source_address, target_pgn)
            potential_session = self.sessions.get(potential_key)
            if potential_session and not potential_session.complete:
                session = potential_session
                session_key = potential_key
                break

        if not session:
            logger.debug(f"Received TP.DT from source={source_address:02X} with no active session")
            return None

        # Validate sequence number
        if sequence_number < 1 or sequence_number > session.total_packets:
            logger.warning(
                "Invalid sequence number %d for session with %d packets",
                sequence_number,
                session.total_packets,
            )
            return None

        # Store the packet
        session.received_packets[sequence_number] = payload

        # Check if we have all packets
        if len(session.received_packets) >= session.total_packets:
            # Reassemble the message
            reassembled = self._reassemble_message(session)

            if reassembled:
                session.complete = True
                session.reassembled_data = reassembled

                # Clean up the completed session
                if session_key:
                    self._remove_session(session_key)

                logger.debug(
                    "Completed BAM message: PGN=%05X, size=%d bytes",
                    session.target_pgn,
                    len(reassembled),
                )

                return (session.target_pgn, reassembled)

        return None

    def _reassemble_message(self, session: BAMSession) -> bytes | None:
        """Reassemble a complete message from received packets."""
        try:
            reassembled = bytearray()

            # Combine packets in sequence order
            for seq_num in range(1, session.total_packets + 1):
                if seq_num not in session.received_packets:
                    logger.error(
                        "Missing packet %d in BAM reassembly for PGN=%05X",
                        seq_num,
                        session.target_pgn,
                    )
                    return None

                reassembled.extend(session.received_packets[seq_num])

            # Trim to the expected size
            reassembled = reassembled[: session.total_size]

            return bytes(reassembled)

        except Exception as e:
            logger.error(f"Error reassembling BAM message: {e}")
            return None

    def _cleanup_stale_sessions(self) -> None:
        """Remove sessions that have timed out."""
        current_time = time.time()
        keys_to_remove = []

        for key, session in self.sessions.items():
            if current_time - session.timestamp > self.session_timeout:
                logger.warning(
                    "BAM session timeout: source=%02X, PGN=%05X, received %d/%d packets",
                    session.source_address,
                    session.target_pgn,
                    len(session.received_packets),
                    session.total_packets,
                )
                keys_to_remove.append(key)

        for key in keys_to_remove:
            self._remove_session(key)

        self._last_cleanup = current_time

    def _cleanup_oldest_session(self) -> None:
        """Remove the oldest session when at capacity."""
        if not self.sessions:
            return

        oldest_key = min(self.sessions.keys(), key=lambda k: self.sessions[k].timestamp)
        oldest_session = self.sessions[oldest_key]

        logger.warning(
            "Removing oldest BAM session due to capacity: source=%02X, PGN=%05X",
            oldest_session.source_address,
            oldest_session.target_pgn,
        )

        self._remove_session(oldest_key)

    def _remove_session(self, session_key: tuple[int, int]) -> None:
        """Remove a session and update source-to-sessions mapping."""
        source_address, target_pgn = session_key

        # Remove from main sessions dict
        if session_key in self.sessions:
            del self.sessions[session_key]

        # Update source-to-sessions mapping
        if source_address in self.source_to_sessions:
            if target_pgn in self.source_to_sessions[source_address]:
                self.source_to_sessions[source_address].remove(target_pgn)

            # Clean up empty source entries
            if not self.source_to_sessions[source_address]:
                del self.source_to_sessions[source_address]

    def get_active_session_count(self) -> int:
        """Get the number of active BAM sessions."""
        return len(self.sessions)

    def get_session_info(self) -> list[dict[str, Any]]:
        """Get information about all active sessions for debugging."""
        info = []
        current_time = time.time()

        for (source, pgn), session in self.sessions.items():
            info.append(
                {
                    "source_address": f"{source:02X}",
                    "target_pgn": f"{pgn:05X}",
                    "total_packets": session.total_packets,
                    "received_packets": len(session.received_packets),
                    "total_size": session.total_size,
                    "age_seconds": current_time - session.timestamp,
                    "complete": session.complete,
                }
            )

        return info
