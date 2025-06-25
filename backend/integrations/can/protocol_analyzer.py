"""
CAN Protocol Analyzer for deep packet inspection and protocol analysis.

This module provides comprehensive protocol analysis capabilities:
- Automatic protocol detection (RV-C, J1939, CANopen, etc.)
- Deep packet inspection with payload decoding
- Pattern analysis and sequence detection
- Protocol compliance validation
- Real-time statistics and metrics
"""

import logging
import struct
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.safety_interfaces import (
    SafeStateAction,
    SafetyAware,
    SafetyClassification,
    SafetyStatus,
)

logger = logging.getLogger(__name__)


class CANProtocol(str, Enum):
    """Supported CAN protocols."""

    UNKNOWN = "unknown"
    RVC = "rvc"
    J1939 = "j1939"
    CANOPEN = "canopen"
    DEVICENET = "devicenet"
    NMEA2000 = "nmea2000"
    ISO14229 = "iso14229"  # UDS
    ISO11783 = "iso11783"  # ISOBUS
    CUSTOM = "custom"


class MessageType(str, Enum):
    """Message type classification."""

    DATA = "data"
    REMOTE = "remote"
    ERROR = "error"
    OVERLOAD = "overload"
    DIAGNOSTIC = "diagnostic"
    COMMAND = "command"
    STATUS = "status"
    BROADCAST = "broadcast"
    PEER_TO_PEER = "peer_to_peer"


@dataclass
class ProtocolMetrics:
    """Protocol-specific metrics."""

    message_count: int = 0
    byte_count: int = 0
    error_count: int = 0
    avg_message_rate: float = 0.0
    peak_message_rate: float = 0.0
    bus_utilization: float = 0.0
    unique_ids: set[int] = field(default_factory=set)
    message_types: dict[str, int] = field(default_factory=dict)


@dataclass
class DecodedField:
    """Decoded message field."""

    name: str
    value: Any
    unit: str | None = None
    raw_value: int | None = None
    scale: float = 1.0
    offset: float = 0.0
    min_value: float | None = None
    max_value: float | None = None
    valid: bool = True


@dataclass
class AnalyzedMessage:
    """Analyzed CAN message with protocol information."""

    timestamp: float
    can_id: int
    data: bytes
    interface: str
    protocol: CANProtocol
    message_type: MessageType
    source_address: int | None = None
    destination_address: int | None = None
    pgn: int | None = None  # For J1939/RV-C
    function_code: int | None = None  # For CANopen
    decoded_fields: list[DecodedField] = field(default_factory=list)
    description: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class CommunicationPattern:
    """Detected communication pattern."""

    pattern_type: str  # "request_response", "periodic", "event", "broadcast"
    participants: list[int]  # CAN IDs involved
    message_sequence: list[tuple[int, bytes]]  # Sequence of messages
    interval_ms: float | None = None
    confidence: float = 0.0


class ProtocolAnalyzer(SafetyAware):
    """
    CAN protocol analyzer for deep packet inspection.

    Features:
    - Automatic protocol detection
    - Message decoding based on protocol
    - Pattern recognition
    - Statistics and metrics
    - Protocol compliance validation
    """

    def __init__(
        self,
        buffer_size: int = 10000,
        pattern_window_ms: float = 5000.0,
    ):
        # Initialize as safety-aware service
        super().__init__(
            safety_classification=SafetyClassification.OPERATIONAL,
            safe_state_action=SafeStateAction.DISABLE,
        )

        self.buffer_size = buffer_size
        self.pattern_window_ms = pattern_window_ms

        # Message buffer for pattern analysis
        self.message_buffer: deque[AnalyzedMessage] = deque(maxlen=buffer_size)

        # Service state
        self._is_running = False

        # Broadcasting state
        self._last_stats_broadcast = time.time()
        self._stats_broadcast_interval = 5.0  # Broadcast stats every 5 seconds
        self._message_broadcast_buffer: list[AnalyzedMessage] = []
        self._message_broadcast_interval = 2.0  # Broadcast messages every 2 seconds
        self._last_message_broadcast = time.time()

        # Protocol detection state
        self.protocol_hints: dict[int, dict[CANProtocol, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.detected_protocols: dict[int, CANProtocol] = {}

        # Metrics by protocol
        self.protocol_metrics: dict[CANProtocol, ProtocolMetrics] = defaultdict(ProtocolMetrics)

        # Pattern detection
        self.detected_patterns: list[CommunicationPattern] = []
        self.sequence_tracker: dict[int, list[tuple[float, bytes]]] = defaultdict(list)

        # Callbacks
        self.message_callback: Callable[[AnalyzedMessage], None] | None = None
        self.pattern_callback: Callable[[CommunicationPattern], None] | None = None

        # Statistics
        self.start_time = time.time()
        self.total_messages = 0
        self.total_bytes = 0

        # WebSocket manager for broadcasting updates (injected by main.py)
        self._websocket_manager = None

        logger.info(
            "ProtocolAnalyzer initialized: buffer_size=%d, pattern_window_ms=%.1f",
            buffer_size,
            pattern_window_ms,
        )

    async def start(self) -> None:
        """Start the analyzer."""
        logger.info("Starting CAN protocol analyzer")
        self._is_running = True
        self.start_time = time.time()
        self._set_safety_status(SafetyStatus.SAFE)

    async def stop(self) -> None:
        """Stop the analyzer."""
        logger.info("Stopping CAN protocol analyzer")
        self._is_running = False

    async def emergency_stop(self, reason: str) -> None:
        """
        Emergency stop all protocol analysis operations.

        This method implements the SafetyAware emergency stop interface
        for immediate cessation of analysis activities.

        Args:
            reason: Reason for emergency stop (for audit logging)
        """
        logger.critical("CAN protocol analyzer emergency stop: %s", reason)

        # Set emergency stop state
        self._set_emergency_stop_active(True)

        # Immediately stop all operations
        self._is_running = False

        # Clear all analysis data to prevent stale information
        self.message_buffer.clear()
        self.protocol_hints.clear()
        self.detected_protocols.clear()
        self.detected_patterns.clear()
        self.sequence_tracker.clear()

        # Reset statistics
        self.total_messages = 0
        self.total_bytes = 0
        self.start_time = time.time()

        # Clear protocol metrics
        for metrics in self.protocol_metrics.values():
            metrics.message_count = 0
            metrics.byte_count = 0
            metrics.error_count = 0
            metrics.unique_ids.clear()
            metrics.message_types.clear()

        logger.critical("CAN protocol analyzer emergency stop completed")

    async def get_safety_status(self) -> SafetyStatus:
        """Get current safety status of the analyzer."""
        if self._emergency_stop_active:
            return SafetyStatus.EMERGENCY_STOP
        if not self._is_running:
            return SafetyStatus.SAFE
        # Check buffer usage
        buffer_usage = len(self.message_buffer) / self.buffer_size
        if buffer_usage > 0.9:
            return SafetyStatus.DEGRADED
        return SafetyStatus.SAFE

    async def validate_safety_interlock(self, operation: str) -> bool:
        """
        Validate if analyzer operation is safe to perform.

        Args:
            operation: Operation being validated (e.g., "analyze_message")

        Returns:
            True if operation is safe to perform
        """
        # Check basic safety status
        safety_status = await self.get_safety_status()
        if safety_status == SafetyStatus.EMERGENCY_STOP:
            logger.warning("Analyzer operation %s blocked: emergency stop active", operation)
            return False

        if not self._is_running and operation != "start":
            logger.warning("Analyzer operation %s blocked: service not running", operation)
            return False

        return True

    # Legacy methods for backward compatibility
    async def startup(self) -> None:
        """Legacy startup method - delegates to start()."""
        await self.start()

    async def shutdown(self) -> None:
        """Legacy shutdown method - delegates to stop()."""
        await self.stop()

    async def analyze_message(
        self,
        can_id: int,
        data: bytes,
        interface: str,
        timestamp: float | None = None,
    ) -> AnalyzedMessage:
        """
        Analyze a CAN message and detect protocol.

        Args:
            can_id: CAN identifier
            data: Message data
            interface: Interface name
            timestamp: Message timestamp

        Returns:
            Analyzed message with protocol information
        """
        # Check safety interlock
        if not await self.validate_safety_interlock("analyze_message"):
            # Return minimal analyzed message if safety check fails
            return AnalyzedMessage(
                timestamp=timestamp or time.time(),
                can_id=can_id,
                data=data,
                interface=interface,
                protocol=CANProtocol.UNKNOWN,
                message_type=MessageType.DATA,
                warnings=["Analysis blocked by safety interlock"],
            )

        if timestamp is None:
            timestamp = time.time()

        # Update statistics
        self.total_messages += 1
        self.total_bytes += len(data)

        # Detect protocol
        protocol = self._detect_protocol(can_id, data)

        # Update protocol detection confidence
        self.protocol_hints[can_id][protocol] += 1

        # Determine most likely protocol for this ID
        if can_id not in self.detected_protocols:
            hint_counts = self.protocol_hints[can_id]
            if sum(hint_counts.values()) >= 5:  # Need at least 5 messages
                best_protocol = max(hint_counts.keys(), key=lambda k: hint_counts[k])
                self.detected_protocols[can_id] = best_protocol

        # Use detected protocol if available
        if can_id in self.detected_protocols:
            protocol = self.detected_protocols[can_id]

        # Create analyzed message
        message = AnalyzedMessage(
            timestamp=timestamp,
            can_id=can_id,
            data=data,
            interface=interface,
            protocol=protocol,
            message_type=self._classify_message_type(can_id, data, protocol),
        )

        # Protocol-specific analysis
        if protocol == CANProtocol.J1939:
            self._analyze_j1939(message)
        elif protocol == CANProtocol.RVC:
            self._analyze_rvc(message)
        elif protocol == CANProtocol.CANOPEN:
            self._analyze_canopen(message)

        # Update metrics
        metrics = self.protocol_metrics[protocol]
        metrics.message_count += 1
        metrics.byte_count += len(data)
        metrics.unique_ids.add(can_id)
        metrics.message_types[message.message_type.value] = (
            metrics.message_types.get(message.message_type.value, 0) + 1
        )

        # Add to buffer
        self.message_buffer.append(message)

        # Track for pattern detection
        self.sequence_tracker[can_id].append((timestamp, data))

        # Detect patterns periodically
        if len(self.message_buffer) % 100 == 0:
            await self._detect_patterns()

        # Call callback if registered
        if self.message_callback:
            try:
                self.message_callback(message)
            except Exception as e:
                logger.error(f"Error in message callback: {e}")

        # Add to broadcast buffer for WebSocket
        if self._websocket_manager:
            self._message_broadcast_buffer.append(message)

            # Check if it's time to broadcast messages
            current_time = time.time()
            if current_time - self._last_message_broadcast >= self._message_broadcast_interval:
                await self._broadcast_messages()
                self._last_message_broadcast = current_time

            # Check if it's time to broadcast statistics
            if current_time - self._last_stats_broadcast >= self._stats_broadcast_interval:
                await self._broadcast_statistics()
                self._last_stats_broadcast = current_time

        return message

    def _detect_protocol(self, can_id: int, data: bytes) -> CANProtocol:
        """
        Detect protocol based on CAN ID and data patterns.

        Args:
            can_id: CAN identifier
            data: Message data

        Returns:
            Detected protocol
        """
        # Check if extended ID (29-bit)
        is_extended = can_id > 0x7FF

        if is_extended:
            # J1939/RVC use extended IDs
            priority = (can_id >> 26) & 0x07
            pgn = (can_id >> 8) & 0x3FFFF
            source_addr = can_id & 0xFF

            # RVC typically uses specific PGN ranges
            if 0x1FE00 <= pgn <= 0x1FEFF:
                return CANProtocol.RVC
            if pgn in [0xFECA, 0xFEDA, 0xFEDB, 0xFEE6, 0xFEE7, 0xFEE8, 0xFEE9]:
                # Common J1939 diagnostic PGNs
                return CANProtocol.J1939
            if 0xF000 <= pgn <= 0xFFFF:
                # J1939 PDU2 format
                return CANProtocol.J1939
            # Could be RVC or J1939
            return CANProtocol.J1939
        # Standard 11-bit ID
        # CANopen uses specific ID ranges
        node_id = can_id & 0x7F
        function_code = (can_id >> 7) & 0x0F

        if function_code in [0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8, 0x9, 0xA, 0xB]:
            return CANProtocol.CANOPEN
        if 0x700 <= can_id <= 0x7FF:
            # CANopen NMT/SDO range
            return CANProtocol.CANOPEN
        return CANProtocol.UNKNOWN

    def _classify_message_type(
        self, can_id: int, data: bytes, protocol: CANProtocol
    ) -> MessageType:
        """Classify message type based on protocol and content."""
        if protocol == CANProtocol.J1939:
            pgn = (can_id >> 8) & 0x3FFFF
            if pgn == 0xFECA:  # DM1 - Diagnostic Message 1
                return MessageType.DIAGNOSTIC
            if pgn in [0xFECC, 0xFECB]:  # Vehicle speed, engine speed
                return MessageType.STATUS
            if pgn >= 0xEF00 and pgn <= 0xEFFF:  # Proprietary B
                return MessageType.DATA
            return MessageType.BROADCAST
        if protocol == CANProtocol.CANOPEN:
            function_code = (can_id >> 7) & 0x0F
            if function_code == 0x0:  # NMT
                return MessageType.COMMAND
            if function_code == 0x1:  # SYNC
                return MessageType.BROADCAST
            if function_code in [0x3, 0x4, 0x5, 0x6]:  # PDO
                return MessageType.DATA
            if function_code in [0xB, 0xC]:  # SDO
                return MessageType.PEER_TO_PEER
            return MessageType.STATUS
        return MessageType.DATA

    def _analyze_j1939(self, message: AnalyzedMessage) -> None:
        """Analyze J1939 message."""
        can_id = message.can_id

        # Extract J1939 fields
        priority = (can_id >> 26) & 0x07
        pgn = (can_id >> 8) & 0x3FFFF
        source_addr = can_id & 0xFF

        # PDU format
        pdu_format = (pgn >> 8) & 0xFF
        pdu_specific = pgn & 0xFF

        message.pgn = pgn
        message.source_address = source_addr

        if pdu_format < 240:
            # PDU1 format - peer-to-peer
            message.destination_address = pdu_specific
            message.message_type = MessageType.PEER_TO_PEER
        else:
            # PDU2 format - broadcast
            message.destination_address = 0xFF
            message.message_type = MessageType.BROADCAST

        # Decode common PGNs
        if pgn == 0xFEE8 and len(message.data) >= 8:  # Engine Temperature
            temp_raw = struct.unpack("<H", message.data[0:2])[0]
            temp_c = temp_raw * 0.03125 - 273.15
            message.decoded_fields.append(
                DecodedField(
                    name="Engine Coolant Temperature",
                    value=temp_c,
                    unit="°C",
                    raw_value=temp_raw,
                    scale=0.03125,
                    offset=-273.15,
                    min_value=-273.15,
                    max_value=1734.96875,
                    valid=temp_raw != 0xFFFF,
                )
            )
            message.description = "Engine Temperature"

    def _analyze_rvc(self, message: AnalyzedMessage) -> None:
        """Analyze RV-C message."""
        # RV-C is based on J1939, so extract same fields
        self._analyze_j1939(message)

        # Additional RV-C specific decoding
        pgn = message.pgn

        if pgn == 0x1FE79 and len(message.data) >= 8:  # DC Dimmer Status
            instance = message.data[0]
            brightness1 = message.data[1]
            brightness2 = message.data[2]

            message.decoded_fields.extend(
                [
                    DecodedField(name="Instance", value=instance),
                    DecodedField(
                        name="Brightness 1",
                        value=brightness1 * 0.4 if brightness1 != 0xFF else None,
                        unit="%",
                        raw_value=brightness1,
                        scale=0.4,
                        valid=brightness1 != 0xFF,
                    ),
                    DecodedField(
                        name="Brightness 2",
                        value=brightness2 * 0.4 if brightness2 != 0xFF else None,
                        unit="%",
                        raw_value=brightness2,
                        scale=0.4,
                        valid=brightness2 != 0xFF,
                    ),
                ]
            )
            message.description = "DC Dimmer Status"

    def _analyze_canopen(self, message: AnalyzedMessage) -> None:
        """Analyze CANopen message."""
        can_id = message.can_id

        # Extract CANopen fields
        node_id = can_id & 0x7F
        function_code = (can_id >> 7) & 0x0F

        message.source_address = node_id
        message.function_code = function_code

        # Decode based on function code
        if function_code == 0x0:  # NMT
            if len(message.data) >= 2:
                command = message.data[0]
                target_node = message.data[1]
                commands = {
                    0x01: "Start Remote Node",
                    0x02: "Stop Remote Node",
                    0x80: "Enter Pre-Operational",
                    0x81: "Reset Node",
                    0x82: "Reset Communication",
                }
                message.description = (
                    f"NMT: {commands.get(command, f'Unknown ({command})')} - Node {target_node}"
                )

    async def _detect_patterns(self) -> None:
        """Detect communication patterns in message buffer."""
        current_time = time.time()
        window_start = current_time - (self.pattern_window_ms / 1000.0)

        # Get recent messages
        recent_messages = [msg for msg in self.message_buffer if msg.timestamp >= window_start]

        if len(recent_messages) < 10:
            return

        # Group by CAN ID
        by_id = defaultdict(list)
        for msg in recent_messages:
            by_id[msg.can_id].append(msg)

        # Detect periodic patterns
        for can_id, messages in by_id.items():
            if len(messages) >= 3:
                intervals = []
                for i in range(1, len(messages)):
                    interval = (messages[i].timestamp - messages[i - 1].timestamp) * 1000
                    intervals.append(interval)

                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    std_dev = (
                        sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
                    ) ** 0.5

                    # Check if periodic (low standard deviation)
                    if std_dev < avg_interval * 0.1:  # 10% tolerance
                        pattern = CommunicationPattern(
                            pattern_type="periodic",
                            participants=[can_id],
                            message_sequence=[(msg.can_id, msg.data) for msg in messages[-3:]],
                            interval_ms=avg_interval,
                            confidence=1.0 - (std_dev / avg_interval) if avg_interval > 0 else 0.0,
                        )

                        # Check if pattern already detected
                        existing = False
                        for existing_pattern in self.detected_patterns:
                            if (
                                existing_pattern.pattern_type == "periodic"
                                and existing_pattern.participants == [can_id]
                                and existing_pattern.interval_ms is not None
                                and abs(existing_pattern.interval_ms - avg_interval) < 10
                            ):
                                existing = True
                                break

                        if not existing:
                            self.detected_patterns.append(pattern)
                            if self.pattern_callback:
                                try:
                                    self.pattern_callback(pattern)
                                except Exception as e:
                                    logger.error(f"Error in pattern callback: {e}")

    async def _broadcast_statistics(self) -> None:
        """Broadcast current statistics via WebSocket if available."""
        if self._websocket_manager:
            try:
                stats = self.get_statistics()
                await self._websocket_manager.broadcast_can_analyzer_update("statistics", stats)
            except Exception as e:
                logger.debug(f"Failed to broadcast analyzer statistics: {e}")

    async def _broadcast_messages(self) -> None:
        """Broadcast buffered messages via WebSocket if available."""
        if self._websocket_manager and self._message_broadcast_buffer:
            try:
                # Convert messages to dict format for JSON serialization
                messages = []
                for msg in self._message_broadcast_buffer[-100:]:  # Send last 100 messages max
                    messages.append(
                        {
                            "timestamp": msg.timestamp,
                            "can_id": msg.can_id,
                            "data": msg.data.hex(),
                            "interface": msg.interface,
                            "protocol": msg.protocol.value,
                            "message_type": msg.message_type.value,
                            "source_address": msg.source_address,
                            "destination_address": msg.destination_address,
                            "pgn": msg.pgn,
                            "decoded_fields": [
                                {
                                    "name": field.name,
                                    "value": field.value,
                                    "unit": field.unit,
                                    "valid": field.valid,
                                }
                                for field in (msg.decoded_fields or [])
                            ]
                            if msg.decoded_fields
                            else None,
                        }
                    )

                await self._websocket_manager.broadcast_can_analyzer_update("messages", messages)

                # Clear the buffer after broadcasting
                self._message_broadcast_buffer.clear()
            except Exception as e:
                logger.debug(f"Failed to broadcast analyzer messages: {e}")

    def get_statistics(self) -> dict[str, Any]:
        """Get analyzer statistics."""
        runtime = time.time() - self.start_time

        # Calculate message rates
        overall_rate = self.total_messages / runtime if runtime > 0 else 0

        # Calculate bus utilization (assuming 500kbps CAN bus)
        # Each message has 64 bits overhead + data
        bits_per_message = (
            64 + (self.total_bytes / self.total_messages * 8) if self.total_messages > 0 else 0
        )
        bus_utilization = (bits_per_message * overall_rate) / 500000.0 * 100

        # Protocol breakdown
        protocol_stats = {}
        for protocol, metrics in self.protocol_metrics.items():
            if metrics.message_count > 0:
                protocol_stats[protocol.value] = {
                    "message_count": metrics.message_count,
                    "byte_count": metrics.byte_count,
                    "error_count": metrics.error_count,
                    "unique_ids": len(metrics.unique_ids),
                    "message_types": dict(metrics.message_types),
                    "percentage": (metrics.message_count / self.total_messages * 100)
                    if self.total_messages > 0
                    else 0,
                }

        return {
            "runtime_seconds": runtime,
            "total_messages": self.total_messages,
            "total_bytes": self.total_bytes,
            "overall_message_rate": overall_rate,
            "bus_utilization_percent": bus_utilization,
            "protocols": protocol_stats,
            "detected_patterns": len(self.detected_patterns),
            "buffer_usage": len(self.message_buffer),
            "buffer_capacity": self.buffer_size,
        }

    def get_protocol_report(self) -> dict[str, Any]:
        """Generate detailed protocol analysis report."""
        report = {
            "detected_protocols": {},
            "communication_patterns": [],
            "protocol_compliance": {},
            "recommendations": [],
        }

        # Detected protocols by ID
        id_protocols = defaultdict(list)
        for can_id, protocol in self.detected_protocols.items():
            id_protocols[protocol].append(can_id)

        for protocol, ids in id_protocols.items():
            report["detected_protocols"][protocol.value] = {
                "can_ids": sorted(ids),
                "count": len(ids),
                "confidence": "high" if len(ids) > 10 else "medium" if len(ids) > 5 else "low",
            }

        # Communication patterns
        for pattern in self.detected_patterns[-20:]:  # Last 20 patterns
            report["communication_patterns"].append(
                {
                    "type": pattern.pattern_type,
                    "participants": pattern.participants,
                    "interval_ms": pattern.interval_ms,
                    "confidence": pattern.confidence,
                }
            )

        # Protocol compliance (basic checks)
        for protocol, metrics in self.protocol_metrics.items():
            if metrics.message_count > 0:
                compliance = {
                    "error_rate": (metrics.error_count / metrics.message_count * 100)
                    if metrics.message_count > 0
                    else 0,
                    "issues": [],
                }

                if compliance["error_rate"] > 5:
                    compliance["issues"].append("High error rate detected")

                report["protocol_compliance"][protocol.value] = compliance

        # Recommendations
        if self.total_messages > 0:
            bus_util = self.get_statistics()["bus_utilization_percent"]
            if bus_util > 80:
                report["recommendations"].append(
                    "Bus utilization is high. Consider reducing message frequency."
                )
            if bus_util < 10:
                report["recommendations"].append(
                    "Bus utilization is very low. System may be idle or disconnected."
                )

        return report
