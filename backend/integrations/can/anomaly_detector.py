"""
Advanced CAN Bus Anomaly Detection System

This module provides sophisticated anomaly detection for CAN bus traffic, including:
- Token bucket rate limiting per (address, PGN) pair
- Source address ACL validation with whitelist/blacklist support
- Broadcast storm detection with adaptive thresholds
- Multi-layered security alert system
- Real-time monitoring and reporting
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Import security event models for integration
from backend.models.security_events import SecurityEvent, SecurityEventType, SecuritySeverity

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of detected anomalies."""

    RATE_LIMIT_VIOLATION = "rate_limit_violation"
    BROADCAST_STORM = "broadcast_storm"
    SOURCE_ACL_VIOLATION = "source_acl_violation"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    UNKNOWN_SOURCE = "unknown_source"
    MESSAGE_FLOOD = "message_flood"
    PGN_SCANNING = "pgn_scanning"
    RAPID_ADDRESS_CHANGE = "rapid_address_change"


class SeverityLevel(Enum):
    """Security severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""

    capacity: float
    tokens: float
    refill_rate: float
    last_refill: float

    def __post_init__(self):
        """Initialize tokens to full capacity."""
        if self.tokens is None:
            self.tokens = self.capacity

    def consume(self, tokens_needed: float = 1.0) -> bool:
        """
        Try to consume tokens from the bucket.

        Args:
            tokens_needed: Number of tokens to consume

        Returns:
            True if tokens were available and consumed, False otherwise
        """
        now = time.time()

        # Refill tokens based on time elapsed
        time_elapsed = now - self.last_refill
        tokens_to_add = time_elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

        # Check if we have enough tokens
        if self.tokens >= tokens_needed:
            self.tokens -= tokens_needed
            return True

        return False

    def get_status(self) -> dict[str, Any]:
        """Get current bucket status."""
        return {
            "tokens": self.tokens,
            "capacity": self.capacity,
            "refill_rate": self.refill_rate,
            "utilization": 1.0 - (self.tokens / self.capacity),
        }


@dataclass
class SecurityAlert:
    """Security alert with detailed information."""

    timestamp: float
    anomaly_type: AnomalyType
    severity: SeverityLevel
    source_address: int
    pgn: int | None
    description: str
    evidence: dict[str, Any]
    mitigation_action: str | None = None
    alert_id: str = field(default_factory=lambda: f"alert_{int(time.time() * 1000000)}")


@dataclass
class SourceACLEntry:
    """Access Control List entry for source addresses."""

    address: int
    allowed_pgns: set[int] = field(default_factory=set)  # Empty = all allowed
    denied_pgns: set[int] = field(default_factory=set)
    is_whitelisted: bool = True
    description: str = ""
    added_time: float = field(default_factory=time.time)


class BroadcastStormDetector:
    """Detects and tracks broadcast storm patterns."""

    def __init__(
        self,
        window_seconds: float = 5.0,
        threshold_messages: int = 1000,
        adaptive_threshold: bool = True,
    ):
        """
        Initialize broadcast storm detector.

        Args:
            window_seconds: Time window for counting messages
            threshold_messages: Message count threshold for storm detection
            adaptive_threshold: Whether to adapt threshold based on normal traffic
        """
        self.window_seconds = window_seconds
        self.base_threshold = threshold_messages
        self.adaptive_threshold = adaptive_threshold

        # Message tracking
        self.message_times: deque = deque(maxlen=10000)
        self.pgn_message_times: dict[int, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.source_message_times: dict[int, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Adaptive threshold calculation
        self.baseline_rates: deque = deque(maxlen=100)  # Store baseline rates
        self.current_threshold = threshold_messages

        # Storm state tracking
        self.in_storm = False
        self.storm_start_time: float | None = None
        self.storm_pgns: set[int] = set()
        self.storm_sources: set[int] = set()

    def add_message(self, timestamp: float, source_address: int, pgn: int) -> bool:
        """
        Add a message and check for broadcast storm.

        Args:
            timestamp: Message timestamp
            source_address: Source address
            pgn: Protocol Group Number

        Returns:
            True if broadcast storm detected
        """
        # Add to overall tracking
        self.message_times.append(timestamp)
        self.pgn_message_times[pgn].append(timestamp)
        self.source_message_times[source_address].append(timestamp)

        # Clean old messages outside window
        cutoff_time = timestamp - self.window_seconds
        self._cleanup_old_messages(cutoff_time)

        # Check for storm conditions
        return self._check_storm_conditions(timestamp)

    def _cleanup_old_messages(self, cutoff_time: float):
        """Remove messages older than the time window."""
        while self.message_times and self.message_times[0] < cutoff_time:
            self.message_times.popleft()

        for pgn_times in self.pgn_message_times.values():
            while pgn_times and pgn_times[0] < cutoff_time:
                pgn_times.popleft()

        for source_times in self.source_message_times.values():
            while source_times and source_times[0] < cutoff_time:
                source_times.popleft()

    def _check_storm_conditions(self, timestamp: float) -> bool:
        """Check if current conditions indicate a broadcast storm."""
        current_rate = len(self.message_times) / self.window_seconds if self.message_times else 0

        # Update adaptive threshold if enabled
        if self.adaptive_threshold and not self.in_storm:
            self._update_adaptive_threshold(current_rate)

        # Check if we've exceeded the threshold
        storm_detected = current_rate > self.current_threshold

        if storm_detected and not self.in_storm:
            # Storm starting
            self.in_storm = True
            self.storm_start_time = timestamp
            self._identify_storm_sources()
            logger.warning(
                "Broadcast storm detected: %.1f msgs/sec (threshold: %s)",
                current_rate,
                self.current_threshold,
            )
        elif not storm_detected and self.in_storm:
            # Storm ending
            storm_duration = timestamp - (self.storm_start_time or timestamp)
            logger.info("Broadcast storm ended after %.1f seconds", storm_duration)
            self.in_storm = False
            self.storm_start_time = None
            self.storm_pgns.clear()
            self.storm_sources.clear()

        return storm_detected

    def _update_adaptive_threshold(self, current_rate: float):
        """Update the adaptive threshold based on baseline traffic."""
        self.baseline_rates.append(current_rate)

        if len(self.baseline_rates) >= 10:
            # Calculate adaptive threshold as mean + 3 * std deviation
            import statistics

            mean_rate = statistics.mean(self.baseline_rates)
            std_rate = statistics.stdev(self.baseline_rates) if len(self.baseline_rates) > 1 else 0

            # Adaptive threshold is 3 sigma above baseline, but at least the base threshold
            adaptive = mean_rate + (3 * std_rate)
            self.current_threshold = max(adaptive, self.base_threshold)

    def _identify_storm_sources(self):
        """Identify the main contributors to the current storm."""
        # Find PGNs and sources with highest rates
        cutoff_time = time.time() - self.window_seconds

        pgn_rates = {}
        for pgn, times in self.pgn_message_times.items():
            recent_count = sum(1 for t in times if t > cutoff_time)
            if recent_count > 0:
                pgn_rates[pgn] = recent_count / self.window_seconds

        source_rates = {}
        for source, times in self.source_message_times.items():
            recent_count = sum(1 for t in times if t > cutoff_time)
            if recent_count > 0:
                source_rates[source] = recent_count / self.window_seconds

        # Identify top contributors (above 10% of current threshold)
        threshold_10pct = self.current_threshold * 0.1

        self.storm_pgns = {pgn for pgn, rate in pgn_rates.items() if rate > threshold_10pct}
        self.storm_sources = {src for src, rate in source_rates.items() if rate > threshold_10pct}

    def get_status(self) -> dict[str, Any]:
        """Get current storm detector status."""
        current_time = time.time()
        current_rate = len(self.message_times) / self.window_seconds if self.message_times else 0

        return {
            "in_storm": self.in_storm,
            "current_rate": current_rate,
            "threshold": self.current_threshold,
            "storm_duration": (current_time - self.storm_start_time)
            if self.storm_start_time
            else 0,
            "storm_pgns": list(self.storm_pgns),
            "storm_sources": [f"0x{src:02X}" for src in self.storm_sources],
            "window_seconds": self.window_seconds,
            "adaptive_threshold": self.adaptive_threshold,
        }


class CANAnomalyDetector:
    """
    Advanced CAN bus anomaly detection system.

    Provides comprehensive security monitoring including rate limiting,
    ACL validation, broadcast storm detection, and alert management.
    """

    def __init__(self, max_alerts: int = 10000, cleanup_interval: float = 300.0):
        """
        Initialize the anomaly detector.

        Args:
            max_alerts: Maximum number of alerts to keep in memory
            cleanup_interval: How often to clean up old data (seconds)
        """
        self.max_alerts = max_alerts
        self.cleanup_interval = cleanup_interval

        # Token buckets for rate limiting: (source_address, pgn) -> TokenBucket
        self.token_buckets: dict[tuple[int, int], TokenBucket] = {}

        # Source Access Control Lists
        self.source_acl: dict[int, SourceACLEntry] = {}
        self.default_acl_policy = "allow"  # "allow" or "deny"

        # Broadcast storm detection
        self.storm_detector = BroadcastStormDetector()

        # Alert system
        self.alerts: deque = deque(maxlen=max_alerts)
        self.alert_counts_by_type: dict[AnomalyType, int] = defaultdict(int)
        self.alert_counts_by_severity: dict[SeverityLevel, int] = defaultdict(int)

        # Statistics tracking
        self.stats = {
            "messages_processed": 0,
            "rate_limited_messages": 0,
            "acl_violations": 0,
            "storms_detected": 0,
            "start_time": time.time(),
        }

        # Background cleanup task
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

        # Security event integration
        self._security_event_manager = None
        self._enable_event_publishing = True

        logger.info("CAN Anomaly Detector initialized")

    async def start(self):
        """Start the anomaly detector."""
        self._running = True

        # Initialize security event manager connection (with late binding support)
        await self._connect_to_security_event_manager()

        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("CAN Anomaly Detector started")

    async def _connect_to_security_event_manager(self):
        """Connect to SecurityEventManager with support for late binding."""
        if not self._enable_event_publishing:
            return

        try:
            from backend.core.dependencies import get_service_registry

            service_registry = get_service_registry()
            if service_registry.has_service("security_event_manager"):
                self._security_event_manager = service_registry.get_service(
                    "security_event_manager"
                )
                logger.info("Connected to SecurityEventManager for event publishing")
            else:
                logger.info(
                    "SecurityEventManager not yet available - will attempt to connect later"
                )
                self._security_event_manager = None
        except RuntimeError:
            # ServiceRegistry not initialized yet
            logger.info(
                "ServiceRegistry not initialized - will attempt to connect to "
                "SecurityEventManager later"
            )
            self._security_event_manager = None
        except Exception as e:
            logger.warning("Failed to connect to SecurityEventManager: %s", e)
            self._security_event_manager = None

    async def stop(self):
        """Stop the anomaly detector."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("CAN Anomaly Detector stopped")

    async def analyze_message(
        self,
        arbitration_id: int,
        data: bytes,
        timestamp: float,
        source_address: int | None = None,
        pgn: int | None = None,
    ) -> dict[str, Any]:
        """
        Analyze a CAN message for anomalies.

        Args:
            arbitration_id: CAN arbitration ID
            data: Message data
            timestamp: Message timestamp
            source_address: Extracted source address (if None, extract from arbitration_id)
            pgn: Extracted PGN (if None, extract from arbitration_id)

        Returns:
            Analysis results with any detected anomalies
        """
        self.stats["messages_processed"] += 1

        # Extract source and PGN if not provided
        if source_address is None:
            source_address = arbitration_id & 0xFF
        if pgn is None:
            pgn = (arbitration_id >> 8) & 0x3FFFF

        analysis_result = {
            "arbitration_id": arbitration_id,
            "source_address": source_address,
            "pgn": pgn,
            "timestamp": timestamp,
            "anomalies_detected": [],
            "actions_taken": [],
        }

        # 1. Check source ACL
        acl_result = await self._check_source_acl(source_address, pgn)
        if not acl_result["allowed"]:
            alert = await self._create_alert(
                AnomalyType.SOURCE_ACL_VIOLATION,
                SeverityLevel.HIGH,
                source_address,
                pgn,
                f"Source 0x{source_address:02X} not authorized for PGN 0x{pgn:05X}",
                acl_result,
            )
            analysis_result["anomalies_detected"].append(alert)
            analysis_result["actions_taken"].append("message_blocked")
            return analysis_result

        # 2. Check rate limiting
        rate_limit_result = await self._check_rate_limit(source_address, pgn, timestamp)
        if not rate_limit_result["allowed"]:
            self.stats["rate_limited_messages"] += 1
            alert = await self._create_alert(
                AnomalyType.RATE_LIMIT_VIOLATION,
                SeverityLevel.MEDIUM,
                source_address,
                pgn,
                f"Rate limit exceeded for source 0x{source_address:02X}, PGN 0x{pgn:05X}",
                rate_limit_result,
            )
            analysis_result["anomalies_detected"].append(alert)
            analysis_result["actions_taken"].append("rate_limited")

        # 3. Check for broadcast storm
        storm_detected = self.storm_detector.add_message(timestamp, source_address, pgn)
        if storm_detected and not hasattr(self, "_last_storm_alert"):
            self.stats["storms_detected"] += 1
            self._last_storm_alert = timestamp
            storm_status = self.storm_detector.get_status()
            alert = await self._create_alert(
                AnomalyType.BROADCAST_STORM,
                SeverityLevel.HIGH,
                source_address,
                pgn,
                f"Broadcast storm detected: {storm_status['current_rate']:.1f} msg/sec",
                storm_status,
            )
            analysis_result["anomalies_detected"].append(alert)
            analysis_result["actions_taken"].append("storm_detected")
        elif not storm_detected and hasattr(self, "_last_storm_alert"):
            # Storm ended
            delattr(self, "_last_storm_alert")

        # 4. Additional pattern analysis (extend as needed)
        pattern_anomalies = await self._check_suspicious_patterns(
            arbitration_id, data, timestamp, source_address, pgn
        )
        analysis_result["anomalies_detected"].extend(pattern_anomalies)

        return analysis_result

    async def _check_source_acl(self, source_address: int, pgn: int) -> dict[str, Any]:
        """Check if source is authorized for this PGN."""
        # Check if source has specific ACL entry
        if source_address in self.source_acl:
            acl_entry = self.source_acl[source_address]

            # Check denied PGNs first
            if pgn in acl_entry.denied_pgns:
                return {"allowed": False, "reason": "pgn_explicitly_denied", "acl_entry": True}

            # Check allowed PGNs (empty set means all allowed)
            if acl_entry.allowed_pgns and pgn not in acl_entry.allowed_pgns:
                return {"allowed": False, "reason": "pgn_not_in_allowlist", "acl_entry": True}

            return {"allowed": True, "reason": "acl_authorized", "acl_entry": True}

        # No specific ACL entry - use default policy
        if self.default_acl_policy == "deny":
            self.stats["acl_violations"] += 1
            return {"allowed": False, "reason": "default_deny_policy", "acl_entry": False}

        return {"allowed": True, "reason": "default_allow_policy", "acl_entry": False}

    async def _check_rate_limit(
        self, source_address: int, pgn: int, timestamp: float
    ) -> dict[str, Any]:
        """Check rate limiting using token bucket algorithm."""
        bucket_key = (source_address, pgn)

        # Get or create token bucket for this (source, PGN) pair
        if bucket_key not in self.token_buckets:
            # Create bucket with default parameters (can be made configurable)
            capacity = self._get_rate_limit_capacity(pgn)
            refill_rate = self._get_rate_limit_refill_rate(pgn)

            self.token_buckets[bucket_key] = TokenBucket(
                capacity=capacity, tokens=capacity, refill_rate=refill_rate, last_refill=timestamp
            )

        bucket = self.token_buckets[bucket_key]
        allowed = bucket.consume(1.0)

        return {
            "allowed": allowed,
            "bucket_status": bucket.get_status(),
            "source_address": source_address,
            "pgn": pgn,
        }

    def _get_rate_limit_capacity(self, pgn: int) -> float:
        """Get token bucket capacity based on PGN type."""
        # Classify PGN for appropriate rate limits
        if 0x1FEF0 <= pgn <= 0x1FEF7:  # Command PGNs
            return 10.0  # Lower capacity for commands
        if 0x1FFB0 <= pgn <= 0x1FFBF:  # Status PGNs
            return 50.0  # Higher capacity for status
        if 0x1FEC0 <= pgn <= 0x1FECF:  # Diagnostic PGNs
            return 5.0  # Very low for diagnostics
        return 20.0  # Default capacity

    def _get_rate_limit_refill_rate(self, pgn: int) -> float:
        """Get token bucket refill rate based on PGN type."""
        # Refill rate in tokens per second
        if 0x1FEF0 <= pgn <= 0x1FEF7:  # Command PGNs
            return 2.0  # 2 tokens/second
        if 0x1FFB0 <= pgn <= 0x1FFBF:  # Status PGNs
            return 10.0  # 10 tokens/second
        if 0x1FEC0 <= pgn <= 0x1FECF:  # Diagnostic PGNs
            return 0.5  # 0.5 tokens/second
        return 5.0  # Default refill rate

    async def _check_suspicious_patterns(
        self, arbitration_id: int, data: bytes, timestamp: float, source_address: int, pgn: int
    ) -> list[SecurityAlert]:
        """Check for additional suspicious patterns."""
        alerts = []

        # Check for rapid PGN scanning
        if not hasattr(self, "_source_pgn_tracking"):
            self._source_pgn_tracking: dict[int, dict] = defaultdict(
                lambda: {"pgns_seen": set(), "last_reset": time.time()}
            )

        source_info = self._source_pgn_tracking[source_address]
        current_time = time.time()

        # Reset tracking every 60 seconds
        if current_time - source_info["last_reset"] > 60:
            source_info["pgns_seen"] = set()
            source_info["last_reset"] = current_time

        source_info["pgns_seen"].add(pgn)

        # Alert if source is scanning too many PGNs
        if len(source_info["pgns_seen"]) > 50:  # Threshold for PGN scanning
            alert = await self._create_alert(
                AnomalyType.PGN_SCANNING,
                SeverityLevel.MEDIUM,
                source_address,
                pgn,
                f"Source 0x{source_address:02X} scanning {len(source_info['pgns_seen'])} PGNs",
                {
                    "pgn_count": len(source_info["pgns_seen"]),
                    "time_window": 60,
                    "sample_pgns": list(source_info["pgns_seen"])[:10],
                },
            )
            alerts.append(alert)
            # Reset to avoid spam
            source_info["pgns_seen"] = set()

        return alerts

    async def _create_alert(
        self,
        anomaly_type: AnomalyType,
        severity: SeverityLevel,
        source_address: int,
        pgn: int | None,
        description: str,
        evidence: dict[str, Any],
    ) -> SecurityAlert:
        """Create and record a security alert."""
        alert = SecurityAlert(
            timestamp=time.time(),
            anomaly_type=anomaly_type,
            severity=severity,
            source_address=source_address,
            pgn=pgn,
            description=description,
            evidence=evidence,
        )

        # Add to alert queue
        self.alerts.append(alert)

        # Update statistics
        self.alert_counts_by_type[anomaly_type] += 1
        self.alert_counts_by_severity[severity] += 1

        # Log the alert
        log_level = {
            SeverityLevel.LOW: logging.INFO,
            SeverityLevel.MEDIUM: logging.WARNING,
            SeverityLevel.HIGH: logging.ERROR,
            SeverityLevel.CRITICAL: logging.CRITICAL,
        }[severity]

        logger.log(log_level, "Security Alert [%s]: %s", alert.alert_id, description)

        # Publish security event if manager is available
        if self._security_event_manager is not None and self._enable_event_publishing:
            await self._publish_security_event(
                alert, anomaly_type, severity, source_address, pgn, description, evidence
            )

        return alert

    async def _periodic_cleanup(self):
        """Periodic cleanup of old data and reconnection attempts."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_data()

                # Attempt to reconnect to SecurityEventManager if not connected
                if self._security_event_manager is None and self._enable_event_publishing:
                    await self._connect_to_security_event_manager()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")

    async def _cleanup_old_data(self):
        """Clean up old tracking data."""
        current_time = time.time()
        cutoff_time = current_time - 3600  # Keep 1 hour of data

        # Clean up unused token buckets
        active_buckets = {}
        for key, bucket in self.token_buckets.items():
            if current_time - bucket.last_refill < 300:  # Active in last 5 minutes
                active_buckets[key] = bucket

        self.token_buckets = active_buckets

        # Clean up source tracking
        if hasattr(self, "_source_pgn_tracking"):
            active_sources = {}
            for source, info in self._source_pgn_tracking.items():
                if current_time - info["last_reset"] < 300:
                    active_sources[source] = info
            self._source_pgn_tracking = defaultdict(
                lambda: {"pgns_seen": set(), "last_reset": time.time()}
            )
            self._source_pgn_tracking.update(active_sources)

    # ACL Management Methods

    def add_source_to_acl(
        self,
        source_address: int,
        allowed_pgns: set[int] | None = None,
        denied_pgns: set[int] | None = None,
        description: str = "",
    ) -> None:
        """Add or update source in ACL."""
        self.source_acl[source_address] = SourceACLEntry(
            address=source_address,
            allowed_pgns=allowed_pgns or set(),
            denied_pgns=denied_pgns or set(),
            description=description,
        )
        logger.info("Added source 0x%02X to ACL", source_address)

    def remove_source_from_acl(self, source_address: int) -> bool:
        """Remove source from ACL."""
        if source_address in self.source_acl:
            del self.source_acl[source_address]
            logger.info("Removed source 0x%02X from ACL", source_address)
            return True
        return False

    def set_default_acl_policy(self, policy: str) -> None:
        """Set default ACL policy ('allow' or 'deny')."""
        if policy in ["allow", "deny"]:
            self.default_acl_policy = policy
            logger.info("Set default ACL policy to: %s", policy)
        else:
            msg = "Policy must be 'allow' or 'deny'"
            raise ValueError(msg)

    # Status and Reporting Methods

    def get_security_status(self) -> dict[str, Any]:
        """Get comprehensive security status."""
        current_time = time.time()
        uptime = current_time - self.stats["start_time"]

        # Recent alerts (last hour)
        recent_alerts = [alert for alert in self.alerts if current_time - alert.timestamp < 3600]

        return {
            "status": "monitoring",
            "uptime_seconds": uptime,
            "stats": self.stats.copy(),
            "alert_summary": {
                "total_alerts": len(self.alerts),
                "recent_alerts": len(recent_alerts),
                "by_type": {t.value: count for t, count in self.alert_counts_by_type.items()},
                "by_severity": {
                    s.value: count for s, count in self.alert_counts_by_severity.items()
                },
            },
            "storm_detector": self.storm_detector.get_status(),
            "acl_status": {
                "sources_in_acl": len(self.source_acl),
                "default_policy": self.default_acl_policy,
                "total_violations": self.stats["acl_violations"],
            },
            "rate_limiting": {
                "active_buckets": len(self.token_buckets),
                "messages_rate_limited": self.stats["rate_limited_messages"],
            },
        }

    def get_alerts(
        self,
        since: float | None = None,
        severity: SeverityLevel | None = None,
        anomaly_type: AnomalyType | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get alerts matching criteria."""
        alerts = list(self.alerts)

        # Apply filters
        if since is not None:
            alerts = [a for a in alerts if a.timestamp >= since]

        if severity is not None:
            alerts = [a for a in alerts if a.severity == severity]

        if anomaly_type is not None:
            alerts = [a for a in alerts if a.anomaly_type == anomaly_type]

        # Sort by timestamp (newest first) and limit
        alerts.sort(key=lambda a: a.timestamp, reverse=True)
        alerts = alerts[:limit]

        # Convert to dictionaries for JSON serialization
        return [
            {
                "alert_id": alert.alert_id,
                "timestamp": alert.timestamp,
                "anomaly_type": alert.anomaly_type.value,
                "severity": alert.severity.value,
                "source_address": alert.source_address,
                "source_address_hex": f"0x{alert.source_address:02X}",
                "pgn": alert.pgn,
                "pgn_hex": f"0x{alert.pgn:05X}" if alert.pgn else None,
                "description": alert.description,
                "evidence": alert.evidence,
                "mitigation_action": alert.mitigation_action,
            }
            for alert in alerts
        ]

    def reset_statistics(self) -> None:
        """Reset all statistics and tracking data."""
        self.token_buckets.clear()
        self.alerts.clear()
        self.alert_counts_by_type.clear()
        self.alert_counts_by_severity.clear()

        self.stats = {
            "messages_processed": 0,
            "rate_limited_messages": 0,
            "acl_violations": 0,
            "storms_detected": 0,
            "start_time": time.time(),
        }

        if hasattr(self, "_source_pgn_tracking"):
            self._source_pgn_tracking.clear()

        logger.info("Anomaly detector statistics reset")

    async def _publish_security_event(
        self,
        alert: SecurityAlert,
        anomaly_type: AnomalyType,
        severity: SeverityLevel,
        source_address: int,
        pgn: int | None,
        description: str,
        evidence: dict[str, Any],
    ) -> None:
        """Publish a security event via SecurityEventManager."""
        try:
            # Map internal anomaly types to SecurityEventType
            event_type_map = {
                AnomalyType.RATE_LIMIT_VIOLATION: SecurityEventType.CAN_RATE_LIMIT_VIOLATION,
                AnomalyType.BROADCAST_STORM: SecurityEventType.CAN_BROADCAST_STORM,
                AnomalyType.SOURCE_ACL_VIOLATION: SecurityEventType.CAN_SOURCE_ACL_VIOLATION,
                AnomalyType.SUSPICIOUS_PATTERN: SecurityEventType.CAN_SUSPICIOUS_PATTERN,
                AnomalyType.UNKNOWN_SOURCE: SecurityEventType.CAN_UNAUTHORIZED_MESSAGE,
                AnomalyType.MESSAGE_FLOOD: SecurityEventType.CAN_MESSAGE_FLOOD,
                AnomalyType.PGN_SCANNING: SecurityEventType.CAN_PGN_SCANNING,
                AnomalyType.RAPID_ADDRESS_CHANGE: SecurityEventType.CAN_SUSPICIOUS_PATTERN,
            }

            # Map internal severity to SecuritySeverity
            severity_map = {
                SeverityLevel.LOW: SecuritySeverity.LOW,
                SeverityLevel.MEDIUM: SecuritySeverity.MEDIUM,
                SeverityLevel.HIGH: SecuritySeverity.HIGH,
                SeverityLevel.CRITICAL: SecuritySeverity.CRITICAL,
            }

            security_event_type = event_type_map.get(
                anomaly_type, SecurityEventType.CAN_SUSPICIOUS_PATTERN
            )
            security_severity = severity_map.get(severity, SecuritySeverity.MEDIUM)

            # Create title from anomaly type
            title = f"CAN {anomaly_type.value.replace('_', ' ').title()}"

            # Create security event using factory method
            security_event = SecurityEvent.create_can_event(
                event_type=security_event_type,
                severity=security_severity,
                title=title,
                description=description,
                source_address=source_address,
                pgn=pgn,
                alert_id=alert.alert_id,
                evidence=evidence,
                timestamp=alert.timestamp,
            )

            # Publish the event
            await self._security_event_manager.publish(security_event)

            logger.debug("Published security event for alert %s", alert.alert_id)

        except Exception as e:
            logger.error("Failed to publish security event for alert %s: %s", alert.alert_id, e)
            # Don't re-raise - event publishing failure shouldn't break anomaly detection


# Global instance
_anomaly_detector: CANAnomalyDetector | None = None


def get_anomaly_detector() -> CANAnomalyDetector:
    """Get the global anomaly detector instance."""
    global _anomaly_detector
    if _anomaly_detector is None:
        _anomaly_detector = CANAnomalyDetector()
    return _anomaly_detector
