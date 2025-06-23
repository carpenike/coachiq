"""
Enhanced Pattern Recognition Engine for Unknown CAN Messages

This module provides sophisticated analysis of unknown CAN messages to detect:
- Message periodicity and timing patterns
- Event vs periodic classification
- Bit-level change detection
- Message correlation patterns
- Automatic provisional DBC generation
"""

import asyncio
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MessageStatistics:
    """Statistical analysis of a specific CAN message."""

    arbitration_id: int
    first_seen: float
    last_seen: float
    count: int
    data_samples: deque = field(default_factory=lambda: deque(maxlen=1000))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=1000))
    intervals: deque = field(default_factory=lambda: deque(maxlen=999))
    unique_data_values: set[bytes] = field(default_factory=set)

    # Computed properties
    mean_interval: float | None = None
    std_interval: float | None = None
    min_interval: float | None = None
    max_interval: float | None = None
    periodicity_score: float | None = None
    classification: str | None = None  # 'periodic', 'event', 'mixed'

    def add_message(self, data: bytes, timestamp: float) -> None:
        """Add a new message observation."""
        self.data_samples.append(data)
        self.unique_data_values.add(data)

        if self.timestamps:
            interval = timestamp - self.timestamps[-1]
            self.intervals.append(interval)

        self.timestamps.append(timestamp)
        self.last_seen = timestamp
        self.count += 1

        # Recompute statistics if we have enough samples
        if len(self.intervals) >= 10:
            self._compute_statistics()

    def _compute_statistics(self) -> None:
        """Compute statistical measures from interval data."""
        if not self.intervals:
            return

        intervals_list = list(self.intervals)
        self.mean_interval = statistics.mean(intervals_list)
        self.std_interval = statistics.stdev(intervals_list) if len(intervals_list) > 1 else 0.0
        self.min_interval = min(intervals_list)
        self.max_interval = max(intervals_list)

        # Compute periodicity score (lower std relative to mean = more periodic)
        if self.mean_interval > 0:
            coefficient_of_variation = self.std_interval / self.mean_interval
            self.periodicity_score = 1.0 / (1.0 + coefficient_of_variation)
        else:
            self.periodicity_score = 0.0

        # Classify message type based on periodicity
        self._classify_message_type()

    def _classify_message_type(self) -> None:
        """Classify message as periodic, event-driven, or mixed."""
        if self.periodicity_score is None:
            return

        if self.periodicity_score > 0.8:
            self.classification = "periodic"
        elif self.periodicity_score < 0.3:
            self.classification = "event"
        else:
            self.classification = "mixed"


@dataclass
class BitChangePattern:
    """Tracks bit-level changes in message data."""

    arbitration_id: int
    byte_position: int
    bit_position: int
    change_count: int = 0
    last_value: bool | None = None
    change_timestamps: list[float] = field(default_factory=list)

    def add_bit_value(self, value: bool, timestamp: float) -> bool:
        """
        Add a new bit value and detect changes.

        Returns:
            True if this bit changed from the previous value
        """
        changed = False
        if self.last_value is not None and self.last_value != value:
            self.change_count += 1
            self.change_timestamps.append(timestamp)
            changed = True

        self.last_value = value
        return changed


class PeriodicityAnalyzer:
    """Analyzes message timing patterns to detect periodicity."""

    def __init__(self, min_samples: int = 10, max_samples: int = 1000):
        self.min_samples = min_samples
        self.max_samples = max_samples

    def analyze_intervals(self, intervals: list[float]) -> dict[str, Any]:
        """
        Analyze timing intervals to determine periodicity characteristics.

        Args:
            intervals: List of time intervals between messages

        Returns:
            Dictionary with analysis results
        """
        if len(intervals) < self.min_samples:
            return {"status": "insufficient_data", "sample_count": len(intervals)}

        # Basic statistics
        mean_interval = statistics.mean(intervals)
        std_interval = statistics.stdev(intervals) if len(intervals) > 1 else 0.0
        median_interval = statistics.median(intervals)

        # Coefficient of variation (std/mean) - lower values indicate more periodic
        cv = std_interval / mean_interval if mean_interval > 0 else float("inf")

        # Periodicity score (0-1, higher = more periodic)
        periodicity_score = 1.0 / (1.0 + cv)

        # Detect potential multiple periodicities using histogram analysis
        hist, bin_edges = np.histogram(intervals, bins=min(50, len(intervals) // 10))
        peak_bins = self._find_peaks(hist, bin_edges)

        # Classification
        if periodicity_score > 0.8:
            classification = "highly_periodic"
        elif periodicity_score > 0.6:
            classification = "moderately_periodic"
        elif periodicity_score > 0.3:
            classification = "mixed"
        else:
            classification = "event_driven"

        return {
            "status": "analyzed",
            "sample_count": len(intervals),
            "mean_interval": mean_interval,
            "std_interval": std_interval,
            "median_interval": median_interval,
            "coefficient_of_variation": cv,
            "periodicity_score": periodicity_score,
            "classification": classification,
            "potential_periods": peak_bins,
            "frequency_hz": 1.0 / mean_interval if mean_interval > 0 else 0.0,
        }

    def _find_peaks(self, hist: np.ndarray, bin_edges: np.ndarray) -> list[float]:
        """Find peaks in the interval histogram to detect multiple periodicities."""
        peaks = []

        # Simple peak detection - values higher than neighbors
        for i in range(1, len(hist) - 1):
            if hist[i] > hist[i - 1] and hist[i] > hist[i + 1]:
                # Use bin center as the peak value
                peak_value = (bin_edges[i] + bin_edges[i + 1]) / 2
                peaks.append(peak_value)

        return sorted(peaks)


class BitChangeDetector:
    """Detects and analyzes bit-level changes in CAN message data."""

    def __init__(self, track_bytes: int = 8):
        self.track_bytes = track_bytes
        self.bit_patterns: dict[int, dict[tuple[int, int], BitChangePattern]] = defaultdict(dict)

    def analyze_message(
        self, arbitration_id: int, data: bytes, timestamp: float
    ) -> list[BitChangePattern]:
        """
        Analyze a message for bit-level changes.

        Args:
            arbitration_id: CAN message ID
            data: Message data bytes
            timestamp: Message timestamp

        Returns:
            List of bit patterns that changed in this message
        """
        changed_patterns = []

        # Analyze each byte up to track_bytes limit
        for byte_pos in range(min(len(data), self.track_bytes)):
            byte_value = data[byte_pos]

            # Analyze each bit in the byte
            for bit_pos in range(8):
                bit_value = bool(byte_value & (1 << bit_pos))
                pattern_key = (byte_pos, bit_pos)

                # Get or create bit pattern tracker
                if pattern_key not in self.bit_patterns[arbitration_id]:
                    self.bit_patterns[arbitration_id][pattern_key] = BitChangePattern(
                        arbitration_id=arbitration_id, byte_position=byte_pos, bit_position=bit_pos
                    )

                pattern = self.bit_patterns[arbitration_id][pattern_key]

                # Check for change
                if pattern.add_bit_value(bit_value, timestamp):
                    changed_patterns.append(pattern)

        return changed_patterns

    def get_active_bits(self, arbitration_id: int, min_changes: int = 5) -> list[BitChangePattern]:
        """Get bits that have changed at least min_changes times."""
        if arbitration_id not in self.bit_patterns:
            return []

        return [
            pattern
            for pattern in self.bit_patterns[arbitration_id].values()
            if pattern.change_count >= min_changes
        ]


class CorrelationMatrix:
    """Analyzes correlations between different CAN messages."""

    def __init__(self, window_seconds: float = 1.0):
        self.window_seconds = window_seconds
        self.message_events: dict[int, list[float]] = defaultdict(list)
        self.correlation_cache: dict[tuple[int, int], float] = {}

    def add_message_event(self, arbitration_id: int, timestamp: float) -> None:
        """Record a message event for correlation analysis."""
        self.message_events[arbitration_id].append(timestamp)

        # Keep only recent events (last 1000 or 1 hour)
        cutoff_time = timestamp - 3600  # 1 hour
        self.message_events[arbitration_id] = [
            t for t in self.message_events[arbitration_id] if t > cutoff_time
        ][-1000:]  # Keep last 1000 events

    def compute_correlation(self, id1: int, id2: int) -> float:
        """
        Compute temporal correlation between two message types.

        Returns correlation score between 0.0 and 1.0.
        """
        cache_key = (min(id1, id2), max(id1, id2))
        if cache_key in self.correlation_cache:
            return self.correlation_cache[cache_key]

        events1 = self.message_events.get(id1, [])
        events2 = self.message_events.get(id2, [])

        if not events1 or not events2:
            return 0.0

        # Count co-occurrences within the time window
        co_occurrences = 0
        total_events = len(events1)

        for t1 in events1:
            # Check if any event2 occurred within window
            for t2 in events2:
                if abs(t1 - t2) <= self.window_seconds:
                    co_occurrences += 1
                    break

        correlation = co_occurrences / total_events if total_events > 0 else 0.0
        self.correlation_cache[cache_key] = correlation

        return correlation

    def find_correlated_messages(
        self, target_id: int, min_correlation: float = 0.5
    ) -> list[tuple[int, float]]:
        """Find messages that correlate with the target message."""
        correlations = []

        for other_id in self.message_events:
            if other_id != target_id:
                correlation = self.compute_correlation(target_id, other_id)
                if correlation >= min_correlation:
                    correlations.append((other_id, correlation))

        return sorted(correlations, key=lambda x: x[1], reverse=True)


class PatternRecognitionEngine:
    """
    Main engine for analyzing unknown CAN message patterns.

    Integrates periodicity analysis, bit change detection, and correlation analysis
    to provide comprehensive insights into unknown CAN traffic.
    """

    def __init__(self, max_tracked_messages: int = 10000, analysis_interval: float = 30.0):
        """
        Initialize the pattern recognition engine.

        Args:
            max_tracked_messages: Maximum number of different message IDs to track
            analysis_interval: How often to run comprehensive analysis (seconds)
        """
        self.max_tracked_messages = max_tracked_messages
        self.analysis_interval = analysis_interval

        # Core analyzers
        self.periodicity_analyzer = PeriodicityAnalyzer()
        self.bit_change_detector = BitChangeDetector()
        self.correlation_matrix = CorrelationMatrix()

        # Message tracking
        self.message_stats: dict[int, MessageStatistics] = {}
        self.last_analysis_time = time.time()

        # Background analysis task
        self._analysis_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the pattern recognition engine."""
        self._running = True
        self._analysis_task = asyncio.create_task(self._periodic_analysis())
        logger.info("Pattern Recognition Engine started")

    async def stop(self) -> None:
        """Stop the pattern recognition engine."""
        self._running = False
        if self._analysis_task:
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass
        logger.info("Pattern Recognition Engine stopped")

    async def analyze_message(
        self, arbitration_id: int, data: bytes, timestamp: float
    ) -> dict[str, Any]:
        """
        Analyze a new CAN message for patterns.

        Args:
            arbitration_id: CAN message ID
            data: Message data bytes
            timestamp: Message timestamp

        Returns:
            Dictionary with immediate analysis results
        """
        # Update message statistics
        if arbitration_id not in self.message_stats:
            if len(self.message_stats) >= self.max_tracked_messages:
                # Remove oldest message (simple LRU)
                oldest_id = min(
                    self.message_stats.keys(), key=lambda x: self.message_stats[x].last_seen
                )
                del self.message_stats[oldest_id]

            self.message_stats[arbitration_id] = MessageStatistics(
                arbitration_id=arbitration_id, first_seen=timestamp, last_seen=timestamp, count=0
            )

        stats = self.message_stats[arbitration_id]
        stats.add_message(data, timestamp)

        # Analyze bit changes
        changed_bits = self.bit_change_detector.analyze_message(arbitration_id, data, timestamp)

        # Update correlation matrix
        self.correlation_matrix.add_message_event(arbitration_id, timestamp)

        # Return immediate analysis
        return {
            "arbitration_id": arbitration_id,
            "message_count": stats.count,
            "classification": stats.classification,
            "periodicity_score": stats.periodicity_score,
            "mean_interval": stats.mean_interval,
            "unique_data_count": len(stats.unique_data_values),
            "changed_bits": len(changed_bits),
            "bit_changes": [
                {
                    "byte": bit.byte_position,
                    "bit": bit.bit_position,
                    "total_changes": bit.change_count,
                }
                for bit in changed_bits
            ],
        }

    async def _periodic_analysis(self) -> None:
        """Background task for comprehensive pattern analysis."""
        while self._running:
            try:
                await asyncio.sleep(self.analysis_interval)
                await self._run_comprehensive_analysis()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic analysis: {e}")

    async def _run_comprehensive_analysis(self) -> None:
        """Run comprehensive analysis on all tracked messages."""
        current_time = time.time()

        logger.debug(f"Running comprehensive analysis on {len(self.message_stats)} messages")

        # Analyze correlations between messages
        correlation_findings = []
        for arbitration_id in self.message_stats:
            correlations = self.correlation_matrix.find_correlated_messages(arbitration_id)
            if correlations:
                correlation_findings.append(
                    {
                        "message_id": arbitration_id,
                        "correlations": correlations[:5],  # Top 5 correlations
                    }
                )

        # Log interesting findings
        if correlation_findings:
            logger.info(f"Found {len(correlation_findings)} messages with correlations")

        self.last_analysis_time = current_time

    def get_message_analysis(self, arbitration_id: int) -> dict[str, Any] | None:
        """Get detailed analysis for a specific message ID."""
        if arbitration_id not in self.message_stats:
            return None

        stats = self.message_stats[arbitration_id]
        active_bits = self.bit_change_detector.get_active_bits(arbitration_id)
        correlations = self.correlation_matrix.find_correlated_messages(arbitration_id)

        return {
            "arbitration_id": arbitration_id,
            "arbitration_id_hex": f"0x{arbitration_id:08X}",
            "first_seen": stats.first_seen,
            "last_seen": stats.last_seen,
            "message_count": stats.count,
            "classification": stats.classification,
            "periodicity_score": stats.periodicity_score,
            "timing_analysis": {
                "mean_interval": stats.mean_interval,
                "std_interval": stats.std_interval,
                "min_interval": stats.min_interval,
                "max_interval": stats.max_interval,
                "frequency_hz": 1.0 / stats.mean_interval if stats.mean_interval else 0.0,
            },
            "data_analysis": {
                "unique_data_count": len(stats.unique_data_values),
                "data_variability": len(stats.unique_data_values) / stats.count
                if stats.count > 0
                else 0.0,
            },
            "bit_analysis": {
                "active_bits": [
                    {
                        "byte_position": bit.byte_position,
                        "bit_position": bit.bit_position,
                        "change_count": bit.change_count,
                        "change_rate": bit.change_count / stats.count if stats.count > 0 else 0.0,
                    }
                    for bit in active_bits
                ],
                "total_active_bits": len(active_bits),
            },
            "correlations": correlations[:10],  # Top 10 correlations
        }

    def get_all_messages_summary(self) -> dict[str, Any]:
        """Get summary of all tracked messages."""
        total_messages = len(self.message_stats)

        classifications = defaultdict(int)
        for stats in self.message_stats.values():
            if stats.classification:
                classifications[stats.classification] += 1

        return {
            "total_tracked_messages": total_messages,
            "classifications": dict(classifications),
            "last_analysis_time": self.last_analysis_time,
            "engine_status": "running" if self._running else "stopped",
        }

    def export_provisional_dbc(self) -> str:
        """
        Export discovered patterns as a provisional DBC file.

        Returns:
            DBC file content as string
        """
        dbc_lines = [
            'VERSION ""',
            "",
            "NS_ :",
            "\tNS_DESC_",
            "\tCM_",
            "\tBA_DEF_",
            "\tBA_",
            "\tVAL_",
            "\tCAT_DEF_",
            "\tCAT_",
            "\tFILTER",
            "\tBA_DEF_DEF_",
            "\tEV_DATA_",
            "\tENVVAR_DATA_",
            "\tSGTYPE_",
            "\tSGTYPE_VAL_",
            "\tBA_DEF_SGTYPE_",
            "\tBA_SGTYPE_",
            "\tSIG_TYPE_REF_",
            "\tVAL_TABLE_",
            "\tSIG_GROUP_",
            "\tSIG_VALTYPE_",
            "\tSIGTYPE_VALTYPE_",
            "\tBO_TX_BU_",
            "\tBA_DEF_REL_",
            "\tBA_REL_",
            "\tBA_DEF_DEF_REL_",
            "\tBU_SG_REL_",
            "\tBU_EV_REL_",
            "\tBU_BO_REL_",
            "\tSG_MUL_VAL_",
            "",
            "BS_:",
            "",
            "BU_: UnknownECU",
            "",
        ]

        # Add messages based on discovered patterns
        for arbitration_id, stats in self.message_stats.items():
            if stats.count < 10:  # Skip messages with too few observations
                continue

            message_name = f"Unknown_{arbitration_id:08X}"

            # Determine message length from data samples
            max_length = max(len(data) for data in stats.data_samples) if stats.data_samples else 8

            dbc_lines.append(f"BO_ {arbitration_id} {message_name}: {max_length} UnknownECU")

            # Add signals for active bits
            active_bits = self.bit_change_detector.get_active_bits(arbitration_id, min_changes=5)

            if active_bits:
                for i, bit_pattern in enumerate(active_bits[:8]):  # Limit to 8 signals per message
                    signal_name = f"Signal_{bit_pattern.byte_position}_{bit_pattern.bit_position}"
                    start_bit = bit_pattern.byte_position * 8 + bit_pattern.bit_position

                    dbc_lines.append(
                        f' SG_ {signal_name} : {start_bit}|1@1+ (1,0) [0|1] "" UnknownECU'
                    )
            else:
                # Add a generic data signal if no active bits detected
                dbc_lines.append(f' SG_ Data : 0|{max_length * 8}@1+ (1,0) [0|0] "" UnknownECU')

            dbc_lines.append("")

        return "\n".join(dbc_lines)


# Global instance
_pattern_engine: PatternRecognitionEngine | None = None


def get_pattern_recognition_engine() -> PatternRecognitionEngine:
    """Get the global pattern recognition engine instance."""
    global _pattern_engine
    if _pattern_engine is None:
        _pattern_engine = PatternRecognitionEngine()
    return _pattern_engine
