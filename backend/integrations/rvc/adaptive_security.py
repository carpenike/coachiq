"""
Adaptive Security Manager for CAN Bus Decoder V2

Provides device profiling, learning-based anomaly detection, and adaptive security
policies for RV-C and J1939 networks. Implements machine learning-based threat detection
and behavioral analysis for vehicle control systems.

This module is part of Phase 3.1 of the CAN Bus Decoder architecture improvements.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from cachetools import TTLCache

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of security anomalies that can be detected."""

    UNEXPECTED_PGN = "unexpected_pgn"
    TIMING_ANOMALY = "timing_anomaly"
    BURST_ANOMALY = "burst_anomaly"
    SOURCE_SPOOFING = "source_spoofing"
    DATA_ANOMALY = "data_anomaly"
    PROTOCOL_VIOLATION = "protocol_violation"


class ThreatLevel(Enum):
    """Threat severity levels for anomaly classification."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityEvent:
    """Represents a detected security anomaly or event."""

    event_type: AnomalyType
    threat_level: ThreatLevel
    source_address: int
    pgn: int
    timestamp: float
    description: str
    confidence: float
    raw_data: bytes = b""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            "event_type": self.event_type.value,
            "threat_level": self.threat_level.value,
            "source_address": f"0x{self.source_address:02X}",
            "pgn": f"0x{self.pgn:04X}",
            "timestamp": self.timestamp,
            "description": self.description,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class DeviceProfile:
    """Learning profile for a specific CAN device."""

    source_address: int
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    # PGN behavior patterns
    expected_pgns: set[int] = field(default_factory=set)
    pgn_intervals: dict[int, float] = field(default_factory=dict)  # PGN -> avg interval
    pgn_burst_patterns: dict[int, int] = field(default_factory=dict)  # PGN -> max burst

    # Message patterns
    message_history: deque = field(default_factory=lambda: deque(maxlen=1000))
    data_patterns: dict[int, list[bytes]] = field(default_factory=dict)  # PGN -> data samples

    # Learning state
    learning_phase: bool = True
    learning_start_time: float = field(default_factory=time.time)
    message_count: int = 0

    # Statistics
    total_messages: int = 0
    anomaly_count: int = 0
    last_anomaly_time: float = 0.0

    def update_from_message(self, pgn: int, timestamp: float, data: bytes) -> None:
        """Update profile with new message data."""
        self.last_seen = timestamp
        self.message_count += 1
        self.total_messages += 1

        if self.learning_phase:
            self.expected_pgns.add(pgn)
            self.message_history.append((pgn, timestamp, len(data)))

            # Store data patterns for anomaly detection
            if pgn not in self.data_patterns:
                self.data_patterns[pgn] = []
            if len(self.data_patterns[pgn]) < 50:  # Limit samples per PGN
                self.data_patterns[pgn].append(data)

            self._update_timing_patterns(pgn, timestamp)

    def _update_timing_patterns(self, pgn: int, timestamp: float) -> None:
        """Update timing and burst pattern analysis."""
        # Calculate message intervals for this PGN
        recent_messages = [
            (p, t)
            for p, t, _ in self.message_history
            if p == pgn and timestamp - t < 60.0  # Last minute
        ]

        if len(recent_messages) >= 2:
            intervals = [
                recent_messages[i][1] - recent_messages[i - 1][1]
                for i in range(1, len(recent_messages))
            ]
            if intervals:
                self.pgn_intervals[pgn] = sum(intervals) / len(intervals)

        # Track burst patterns (messages per 10-second window)
        burst_window = [t for p, t, _ in self.message_history if p == pgn and timestamp - t < 10.0]
        self.pgn_burst_patterns[pgn] = max(self.pgn_burst_patterns.get(pgn, 0), len(burst_window))

    def is_message_anomalous(
        self, pgn: int, timestamp: float, data: bytes
    ) -> tuple[bool, str, float]:
        """Check if a message is anomalous based on learned patterns."""
        if self.learning_phase:
            return False, "Learning phase", 0.0

        anomalies = []
        confidence_scores = []

        # Check for unexpected PGN
        if pgn not in self.expected_pgns:
            anomalies.append(f"Unexpected PGN 0x{pgn:04X}")
            confidence_scores.append(0.9)

        # Check timing anomalies
        expected_interval = self.pgn_intervals.get(pgn, 1.0)
        recent_messages = [
            t for p, t, _ in self.message_history if p == pgn and timestamp - t < 60.0
        ]

        if recent_messages:
            last_message_time = max(recent_messages)
            actual_interval = timestamp - last_message_time

            # Detect unusually fast messaging
            if actual_interval < expected_interval * 0.1:  # 10x faster than expected
                anomalies.append(
                    f"Timing anomaly: {actual_interval:.3f}s vs expected {expected_interval:.3f}s"
                )
                confidence_scores.append(0.7)

        # Check burst anomalies
        expected_burst = self.pgn_burst_patterns.get(pgn, 10)
        recent_burst = len(
            [t for p, t, _ in self.message_history if p == pgn and timestamp - t < 10.0]
        )

        if recent_burst > expected_burst * 2:  # 2x more than expected burst
            anomalies.append(
                f"Burst anomaly: {recent_burst} messages vs expected max {expected_burst}"
            )
            confidence_scores.append(0.8)

        # Check data anomalies (basic pattern matching)
        if pgn in self.data_patterns:
            known_patterns = self.data_patterns[pgn]
            if known_patterns and not any(
                self._data_similarity(data, pattern) > 0.8 for pattern in known_patterns
            ):
                anomalies.append("Data pattern anomaly")
                confidence_scores.append(0.6)

        if anomalies:
            self.anomaly_count += 1
            self.last_anomaly_time = timestamp
            overall_confidence = max(confidence_scores) if confidence_scores else 0.5
            return True, "; ".join(anomalies), overall_confidence

        return False, "Normal", 0.0

    def _data_similarity(self, data1: bytes, data2: bytes) -> float:
        """Calculate similarity between two data patterns (0.0 to 1.0)."""
        if len(data1) != len(data2):
            return 0.0

        if len(data1) == 0:
            return 1.0

        matching_bytes = sum(1 for b1, b2 in zip(data1, data2, strict=True) if b1 == b2)
        return matching_bytes / len(data1)

    def get_statistics(self) -> dict:
        """Get profile statistics for monitoring."""
        return {
            "source_address": f"0x{self.source_address:02X}",
            "learning_phase": self.learning_phase,
            "expected_pgns": len(self.expected_pgns),
            "total_messages": self.total_messages,
            "anomaly_count": self.anomaly_count,
            "anomaly_rate": self.anomaly_count / max(self.total_messages, 1),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "age_hours": (time.time() - self.first_seen) / 3600.0,
        }


class AdaptiveSecurityManager:
    """
    Adaptive security manager with machine learning-based anomaly detection.

    Provides device profiling, behavioral learning, and real-time threat detection
    for CAN bus networks with RV-C and J1939 protocols.
    """

    def __init__(
        self,
        learning_duration: float = 3600.0,  # 1 hour learning phase
        max_profiles: int = 256,  # Maximum device profiles
        anomaly_threshold: float = 0.7,  # Confidence threshold for reporting
        cache_ttl: int = 300,  # 5 minutes
    ):
        self.learning_duration = learning_duration
        self.max_profiles = max_profiles
        self.anomaly_threshold = anomaly_threshold

        # Device profiles and caching
        self.device_profiles: dict[int, DeviceProfile] = {}
        self.anomaly_cache = TTLCache(maxsize=1000, ttl=cache_ttl)

        # Statistics and monitoring
        self.total_messages_processed = 0
        self.total_anomalies_detected = 0
        self.start_time = time.time()

        # Security events
        self.security_events: deque = deque(maxlen=1000)
        self.observers: list = []

        # Thread safety
        self._lock = threading.RLock()

        # Known legitimate device ranges for RV systems
        self.legitimate_address_ranges = [
            (0x00, 0x7F),  # Standard device addresses
            (0xE0, 0xEF),  # Gateway and diagnostic tools
            (0xF0, 0xF9),  # OEM-specific addresses
        ]

        logger.info(
            f"Adaptive Security Manager initialized: "
            f"learning_duration={learning_duration}s, "
            f"max_profiles={max_profiles}, "
            f"anomaly_threshold={anomaly_threshold}"
        )

    def add_observer(self, observer_func) -> None:
        """Add observer for security events."""
        with self._lock:
            self.observers.append(observer_func)

    def remove_observer(self, observer_func) -> None:
        """Remove security event observer."""
        with self._lock:
            if observer_func in self.observers:
                self.observers.remove(observer_func)

    def _notify_observers(self, event: SecurityEvent) -> None:
        """Notify all observers of security event."""
        for observer in self.observers:
            try:
                observer(event)
            except Exception as e:
                logger.error(f"Error notifying security observer: {e}")

    def validate_frame(self, frame) -> bool:
        """
        Main validation method - analyzes frame and detects anomalies.

        Args:
            frame: CAN frame object with pgn, source_address, data, timestamp

        Returns:
            bool: True if frame appears legitimate, False if anomalous
        """
        with self._lock:
            self.total_messages_processed += 1
            current_time = time.time()

            # Basic validation first
            if not self._basic_validation(frame):
                return False

            # Get or create device profile
            source_addr = frame.source_address
            if source_addr not in self.device_profiles:
                if len(self.device_profiles) >= self.max_profiles:
                    self._cleanup_old_profiles()

                self.device_profiles[source_addr] = DeviceProfile(source_addr)
                logger.debug(f"Created new device profile for 0x{source_addr:02X}")

            profile = self.device_profiles[source_addr]

            # Update profile with message data
            profile.update_from_message(frame.pgn, current_time, frame.data)

            # Check if learning phase is complete
            if profile.learning_phase:
                learning_elapsed = current_time - profile.learning_start_time
                if learning_elapsed >= self.learning_duration or profile.message_count >= 100:
                    profile.learning_phase = False
                    logger.info(
                        f"Learning phase complete for device 0x{source_addr:02X}: "
                        f"{profile.message_count} messages, {len(profile.expected_pgns)} PGNs"
                    )

                return True  # Allow all messages during learning

            # Perform anomaly detection
            is_anomalous, reason, confidence = profile.is_message_anomalous(
                frame.pgn, current_time, frame.data
            )

            if is_anomalous and confidence >= self.anomaly_threshold:
                # Determine threat level based on anomaly type and confidence
                threat_level = self._assess_threat_level(reason, confidence, frame)

                # Create security event
                event = SecurityEvent(
                    event_type=self._classify_anomaly_type(reason),
                    threat_level=threat_level,
                    source_address=source_addr,
                    pgn=frame.pgn,
                    timestamp=current_time,
                    description=reason,
                    confidence=confidence,
                    raw_data=frame.data,
                    metadata={
                        "frame_id": getattr(frame, "arbitration_id", 0),
                        "profile_stats": profile.get_statistics(),
                    },
                )

                self._handle_security_event(event)

                # For high/critical threats, block the frame
                if threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
                    logger.warning(
                        f"BLOCKING frame from 0x{source_addr:02X}: "
                        f"{threat_level.value} threat - {reason}"
                    )
                    return False

                # For lower threats, log and allow
                logger.info(
                    f"Security anomaly detected (confidence={confidence:.2f}): "
                    f"0x{source_addr:02X} PGN 0x{frame.pgn:04X} - {reason}"
                )

            return True

    def _basic_validation(self, frame) -> bool:
        """Perform basic frame validation checks."""
        # Check if source address is in legitimate ranges
        source_addr = frame.source_address
        is_legitimate = any(
            start <= source_addr <= end for start, end in self.legitimate_address_ranges
        )

        if not is_legitimate:
            logger.warning(f"Suspicious source address: 0x{source_addr:02X}")
            return False

        # Check for obviously invalid PGNs
        if frame.pgn > 0x1FFFF:  # J1939 PGN limit
            logger.warning(f"Invalid PGN: 0x{frame.pgn:06X}")
            return False

        # Check data length reasonableness
        if len(frame.data) > 8:  # Standard CAN frame limit
            logger.warning(f"Oversized frame data: {len(frame.data)} bytes")
            return False

        return True

    def _classify_anomaly_type(self, reason: str) -> AnomalyType:
        """Classify anomaly based on reason string."""
        reason_lower = reason.lower()

        if "unexpected pgn" in reason_lower:
            return AnomalyType.UNEXPECTED_PGN
        if "timing anomaly" in reason_lower:
            return AnomalyType.TIMING_ANOMALY
        if "burst anomaly" in reason_lower:
            return AnomalyType.BURST_ANOMALY
        if "data pattern" in reason_lower:
            return AnomalyType.DATA_ANOMALY
        return AnomalyType.PROTOCOL_VIOLATION

    def _assess_threat_level(self, reason: str, confidence: float, frame) -> ThreatLevel:
        """Assess threat level based on anomaly characteristics."""
        if confidence >= 0.9:
            # High confidence anomalies
            if "unexpected pgn" in reason.lower() and frame.pgn < 0x1FE00:
                return ThreatLevel.HIGH  # Unexpected low PGN could be attack
            if "burst anomaly" in reason.lower():
                return ThreatLevel.MEDIUM  # Could be DoS attempt
            return ThreatLevel.MEDIUM
        if confidence >= 0.7:
            return ThreatLevel.LOW
        return ThreatLevel.INFO

    def _handle_security_event(self, event: SecurityEvent) -> None:
        """Handle detected security event."""
        self.total_anomalies_detected += 1
        self.security_events.append(event)

        # Log the event
        logger.warning(f"Security event: {event.description}")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Security event details: {event.to_dict()}")

        # Notify observers
        self._notify_observers(event)

        # Cache for quick lookup
        cache_key = f"{event.source_address}:{event.pgn}:{event.event_type.value}"
        self.anomaly_cache[cache_key] = event

    def _cleanup_old_profiles(self) -> None:
        """Remove oldest device profiles when limit is reached."""
        if not self.device_profiles:
            return

        # Find oldest profile by first_seen time
        oldest_addr = min(
            self.device_profiles.keys(), key=lambda addr: self.device_profiles[addr].first_seen
        )

        removed_profile = self.device_profiles.pop(oldest_addr)
        logger.debug(
            f"Removed old device profile 0x{oldest_addr:02X} "
            f"(age: {(time.time() - removed_profile.first_seen) / 3600:.1f} hours)"
        )

    def get_device_statistics(self) -> dict:
        """Get statistics for all device profiles."""
        with self._lock:
            return {
                "total_devices": len(self.device_profiles),
                "learning_devices": sum(
                    1 for p in self.device_profiles.values() if p.learning_phase
                ),
                "total_messages_processed": self.total_messages_processed,
                "total_anomalies_detected": self.total_anomalies_detected,
                "anomaly_rate": self.total_anomalies_detected
                / max(self.total_messages_processed, 1),
                "uptime_hours": (time.time() - self.start_time) / 3600.0,
                "devices": {
                    f"0x{addr:02X}": profile.get_statistics()
                    for addr, profile in self.device_profiles.items()
                },
            }

    def get_recent_events(self, limit: int = 50) -> list[dict]:
        """Get recent security events."""
        with self._lock:
            recent_events = list(self.security_events)[-limit:]
            return [event.to_dict() for event in recent_events]

    def force_learning_completion(self, source_address: int | None = None) -> None:
        """Force completion of learning phase for testing."""
        with self._lock:
            if source_address is not None:
                if source_address in self.device_profiles:
                    self.device_profiles[source_address].learning_phase = False
                    logger.info("Forced learning completion for device 0x%02X", source_address)
            else:
                for profile in self.device_profiles.values():
                    profile.learning_phase = False
                logger.info("Forced learning completion for all devices")

    def reset_device_profile(self, source_address: int) -> bool:
        """Reset a specific device profile."""
        with self._lock:
            if source_address in self.device_profiles:
                del self.device_profiles[source_address]
                logger.info("Reset device profile for 0x%02X", source_address)
                return True
            return False

    def get_performance_stats(self) -> dict:
        """Get performance metrics for monitoring."""
        with self._lock:
            total_messages = max(self.total_messages_processed, 1)
            uptime_seconds = max((time.time() - self.start_time), 1)
            return {
                "messages_processed": self.total_messages_processed,
                "anomalies_detected": self.total_anomalies_detected,
                "anomaly_rate": self.total_anomalies_detected / total_messages,
                "active_profiles": len(self.device_profiles),
                "cache_size": len(self.anomaly_cache),
                "uptime_seconds": time.time() - self.start_time,
                "processing_rate": self.total_messages_processed / uptime_seconds,
            }
