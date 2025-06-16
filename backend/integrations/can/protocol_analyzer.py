"""
CAN Protocol Analyzer for deep packet inspection and protocol analysis.

This module provides comprehensive protocol analysis capabilities:
- Automatic protocol detection (RV-C, J1939, CANopen, etc.)
- Deep packet inspection with payload decoding
- Pattern analysis and sequence detection
- Protocol compliance validation
- Real-time statistics and metrics
"""

import asyncio
import time
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import logging
import struct

from backend.services.feature_base import Feature

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
    unique_ids: Set[int] = field(default_factory=set)
    message_types: Dict[str, int] = field(default_factory=dict)


@dataclass
class DecodedField:
    """Decoded message field."""
    name: str
    value: Any
    unit: Optional[str] = None
    raw_value: Optional[int] = None
    scale: float = 1.0
    offset: float = 0.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
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
    source_address: Optional[int] = None
    destination_address: Optional[int] = None
    pgn: Optional[int] = None  # For J1939/RV-C
    function_code: Optional[int] = None  # For CANopen
    decoded_fields: List[DecodedField] = field(default_factory=list)
    description: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class CommunicationPattern:
    """Detected communication pattern."""
    pattern_type: str  # "request_response", "periodic", "event", "broadcast"
    participants: List[int]  # CAN IDs involved
    message_sequence: List[Tuple[int, bytes]]  # Sequence of messages
    interval_ms: Optional[float] = None
    confidence: float = 0.0


class ProtocolAnalyzer(Feature):
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
        name: str = "can_protocol_analyzer",
        enabled: bool = True,
        core: bool = False,
        buffer_size: int = 10000,
        pattern_window_ms: float = 5000.0,
        **kwargs,
    ):
        super().__init__(name=name, enabled=enabled, core=core, **kwargs)
        self.buffer_size = buffer_size
        self.pattern_window_ms = pattern_window_ms

        # Message buffer for pattern analysis
        self.message_buffer: deque[AnalyzedMessage] = deque(maxlen=buffer_size)

        # Protocol detection state
        self.protocol_hints: Dict[int, Dict[CANProtocol, int]] = defaultdict(lambda: defaultdict(int))
        self.detected_protocols: Dict[int, CANProtocol] = {}

        # Metrics by protocol
        self.protocol_metrics: Dict[CANProtocol, ProtocolMetrics] = defaultdict(ProtocolMetrics)

        # Pattern detection
        self.detected_patterns: List[CommunicationPattern] = []
        self.sequence_tracker: Dict[int, List[Tuple[float, bytes]]] = defaultdict(list)

        # Callbacks
        self.message_callback: Optional[Callable[[AnalyzedMessage], None]] = None
        self.pattern_callback: Optional[Callable[[CommunicationPattern], None]] = None

        # Statistics
        self.start_time = time.time()
        self.total_messages = 0
        self.total_bytes = 0

    async def startup(self) -> None:
        """Initialize the analyzer."""
        await super().startup()
        logger.info("CAN Protocol Analyzer initialized")

    async def shutdown(self) -> None:
        """Cleanup analyzer resources."""
        await super().shutdown()

    async def analyze_message(
        self,
        can_id: int,
        data: bytes,
        interface: str,
        timestamp: Optional[float] = None,
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
                self.detected_protocols[can_id] = max(hint_counts, key=hint_counts.get)

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
        metrics.message_types[message.message_type.value] = metrics.message_types.get(message.message_type.value, 0) + 1

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
            elif pgn in [0xFECA, 0xFEDA, 0xFEDB, 0xFEE6, 0xFEE7, 0xFEE8, 0xFEE9]:
                # Common J1939 diagnostic PGNs
                return CANProtocol.J1939
            elif 0xF000 <= pgn <= 0xFFFF:
                # J1939 PDU2 format
                return CANProtocol.J1939
            else:
                # Could be RVC or J1939
                return CANProtocol.J1939
        else:
            # Standard 11-bit ID
            # CANopen uses specific ID ranges
            node_id = can_id & 0x7F
            function_code = (can_id >> 7) & 0x0F

            if function_code in [0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8, 0x9, 0xA, 0xB]:
                return CANProtocol.CANOPEN
            elif 0x700 <= can_id <= 0x7FF:
                # CANopen NMT/SDO range
                return CANProtocol.CANOPEN
            else:
                return CANProtocol.UNKNOWN

    def _classify_message_type(self, can_id: int, data: bytes, protocol: CANProtocol) -> MessageType:
        """Classify message type based on protocol and content."""
        if protocol == CANProtocol.J1939:
            pgn = (can_id >> 8) & 0x3FFFF
            if pgn == 0xFECA:  # DM1 - Diagnostic Message 1
                return MessageType.DIAGNOSTIC
            elif pgn in [0xFECC, 0xFECB]:  # Vehicle speed, engine speed
                return MessageType.STATUS
            elif pgn >= 0xEF00 and pgn <= 0xEFFF:  # Proprietary B
                return MessageType.DATA
            else:
                return MessageType.BROADCAST
        elif protocol == CANProtocol.CANOPEN:
            function_code = (can_id >> 7) & 0x0F
            if function_code == 0x0:  # NMT
                return MessageType.COMMAND
            elif function_code == 0x1:  # SYNC
                return MessageType.BROADCAST
            elif function_code in [0x3, 0x4, 0x5, 0x6]:  # PDO
                return MessageType.DATA
            elif function_code in [0xB, 0xC]:  # SDO
                return MessageType.PEER_TO_PEER
            else:
                return MessageType.STATUS
        else:
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
                    valid=temp_raw != 0xFFFF
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

            message.decoded_fields.extend([
                DecodedField(name="Instance", value=instance),
                DecodedField(
                    name="Brightness 1",
                    value=brightness1 * 0.4 if brightness1 != 0xFF else None,
                    unit="%",
                    raw_value=brightness1,
                    scale=0.4,
                    valid=brightness1 != 0xFF
                ),
                DecodedField(
                    name="Brightness 2",
                    value=brightness2 * 0.4 if brightness2 != 0xFF else None,
                    unit="%",
                    raw_value=brightness2,
                    scale=0.4,
                    valid=brightness2 != 0xFF
                ),
            ])
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
                message.description = f"NMT: {commands.get(command, f'Unknown ({command})')} - Node {target_node}"

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
                    interval = (messages[i].timestamp - messages[i-1].timestamp) * 1000
                    intervals.append(interval)

                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    std_dev = (sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)) ** 0.5

                    # Check if periodic (low standard deviation)
                    if std_dev < avg_interval * 0.1:  # 10% tolerance
                        pattern = CommunicationPattern(
                            pattern_type="periodic",
                            participants=[can_id],
                            message_sequence=[(msg.can_id, msg.data) for msg in messages[-3:]],
                            interval_ms=avg_interval,
                            confidence=1.0 - (std_dev / avg_interval) if avg_interval > 0 else 0.0
                        )

                        # Check if pattern already detected
                        existing = False
                        for existing_pattern in self.detected_patterns:
                            if (existing_pattern.pattern_type == "periodic" and
                                existing_pattern.participants == [can_id] and
                                abs(existing_pattern.interval_ms - avg_interval) < 10):
                                existing = True
                                break

                        if not existing:
                            self.detected_patterns.append(pattern)
                            if self.pattern_callback:
                                try:
                                    self.pattern_callback(pattern)
                                except Exception as e:
                                    logger.error(f"Error in pattern callback: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get analyzer statistics."""
        runtime = time.time() - self.start_time

        # Calculate message rates
        overall_rate = self.total_messages / runtime if runtime > 0 else 0

        # Calculate bus utilization (assuming 500kbps CAN bus)
        # Each message has 64 bits overhead + data
        bits_per_message = 64 + (self.total_bytes / self.total_messages * 8) if self.total_messages > 0 else 0
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
                    "percentage": (metrics.message_count / self.total_messages * 100) if self.total_messages > 0 else 0
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

    def get_protocol_report(self) -> Dict[str, Any]:
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
                "confidence": "high" if len(ids) > 10 else "medium" if len(ids) > 5 else "low"
            }

        # Communication patterns
        for pattern in self.detected_patterns[-20:]:  # Last 20 patterns
            report["communication_patterns"].append({
                "type": pattern.pattern_type,
                "participants": pattern.participants,
                "interval_ms": pattern.interval_ms,
                "confidence": pattern.confidence,
            })

        # Protocol compliance (basic checks)
        for protocol, metrics in self.protocol_metrics.items():
            if metrics.message_count > 0:
                compliance = {
                    "error_rate": (metrics.error_count / metrics.message_count * 100) if metrics.message_count > 0 else 0,
                    "issues": [],
                }

                if compliance["error_rate"] > 5:
                    compliance["issues"].append("High error rate detected")

                report["protocol_compliance"][protocol.value] = compliance

        # Recommendations
        if self.total_messages > 0:
            bus_util = self.get_statistics()["bus_utilization_percent"]
            if bus_util > 80:
                report["recommendations"].append("Bus utilization is high. Consider reducing message frequency.")
            if bus_util < 10:
                report["recommendations"].append("Bus utilization is very low. System may be idle or disconnected.")

        return report
