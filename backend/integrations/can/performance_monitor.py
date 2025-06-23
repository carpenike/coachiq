"""
Performance Monitoring System for CAN Bus Decoder V2

Provides comprehensive performance metrics collection, analysis, and reporting
for the enhanced CAN bus decoder architecture. Includes decoder latency tracking,
BAM completion rates, safety state transitions, and Prometheus endpoint integration.

This module is part of Phase 3.2 of the CAN Bus Decoder architecture improvements.
"""

import asyncio
import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of performance metrics collected."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class ComponentType(Enum):
    """System components being monitored."""

    BAM_HANDLER = "bam_handler"
    PROTOCOL_ROUTER = "protocol_router"
    SAFETY_ENGINE = "safety_engine"
    SECURITY_MANAGER = "security_manager"
    CONFIGURATION_SERVICE = "configuration_service"
    RVC_DECODER = "rvc_decoder"
    J1939_DECODER = "j1939_decoder"


@dataclass
class PerformanceMetric:
    """Individual performance metric with metadata."""

    name: str
    metric_type: MetricType
    component: ComponentType
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: dict[str, str] = field(default_factory=dict)
    unit: str = ""
    description: str = ""

    def to_prometheus_format(self) -> str:
        """Convert metric to Prometheus exposition format."""
        labels_str = ""
        if self.labels:
            label_pairs = [f'{k}="{v}"' for k, v in self.labels.items()]
            labels_str = "{" + ",".join(label_pairs) + "}"

        metric_name = f"canbus_decoder_{self.name}"
        return f"{metric_name}{labels_str} {self.value} {int(self.timestamp * 1000)}"


@dataclass
class ComponentStats:
    """Performance statistics for a specific component."""

    component: ComponentType
    messages_processed: int = 0
    total_processing_time: float = 0.0
    error_count: int = 0
    last_activity: float = field(default_factory=time.time)

    # Timing statistics
    processing_times: deque = field(default_factory=lambda: deque(maxlen=1000))

    def add_processing_time(self, duration: float) -> None:
        """Add a processing time measurement."""
        self.messages_processed += 1
        self.total_processing_time += duration
        self.processing_times.append(duration)
        self.last_activity = time.time()

    def add_error(self) -> None:
        """Record an error occurrence."""
        self.error_count += 1
        self.last_activity = time.time()

    def get_avg_processing_time(self) -> float:
        """Get average processing time in milliseconds."""
        if self.messages_processed == 0:
            return 0.0
        return (self.total_processing_time / self.messages_processed) * 1000

    def get_percentile_processing_time(self, percentile: float = 95.0) -> float:
        """Get percentile processing time in milliseconds."""
        if not self.processing_times:
            return 0.0
        times_ms = [t * 1000 for t in self.processing_times]
        return (
            statistics.quantiles(times_ms, n=100)[int(percentile) - 1]
            if len(times_ms) > 1
            else times_ms[0]
        )

    def get_error_rate(self) -> float:
        """Get error rate as percentage."""
        total_operations = self.messages_processed + self.error_count
        if total_operations == 0:
            return 0.0
        return (self.error_count / total_operations) * 100

    def get_throughput(self, window_seconds: float = 60.0) -> float:
        """Get recent throughput (messages per second)."""
        current_time = time.time()
        if current_time - self.last_activity > window_seconds:
            return 0.0

        # Estimate based on recent activity
        recent_times = [
            t
            for t in self.processing_times
            if current_time - (self.last_activity - t) < window_seconds
        ]

        if not recent_times:
            return 0.0

        return len(recent_times) / window_seconds


class PerformanceMonitor:
    """
    Comprehensive performance monitoring system for CAN bus decoder components.

    Collects metrics, analyzes performance trends, and provides Prometheus endpoints
    for integration with monitoring systems.
    """

    def __init__(self, collection_interval: float = 10.0, retention_hours: int = 24):
        self.collection_interval = collection_interval
        self.retention_hours = retention_hours

        # Metrics storage
        self.metrics: deque = deque(maxlen=int(retention_hours * 3600 / collection_interval))
        self.component_stats: dict[ComponentType, ComponentStats] = {
            component: ComponentStats(component) for component in ComponentType
        }

        # BAM-specific metrics
        self.bam_session_stats = {
            "sessions_started": 0,
            "sessions_completed": 0,
            "sessions_timeout": 0,
            "sessions_failed": 0,
            "avg_completion_time": 0.0,
            "completion_times": deque(maxlen=1000),
        }

        # Safety engine metrics
        self.safety_stats = {
            "state_transitions": 0,
            "safety_commands_issued": 0,
            "operations_blocked": 0,
            "emergency_stops": 0,
            "state_transition_times": deque(maxlen=1000),
        }

        # Security manager metrics
        self.security_stats = {
            "frames_validated": 0,
            "anomalies_detected": 0,
            "threats_blocked": 0,
            "learning_devices": 0,
            "active_profiles": 0,
        }

        # System metrics
        self.system_stats = {
            "total_messages_processed": 0,
            "total_errors": 0,
            "uptime_start": time.time(),
            "last_activity": time.time(),
        }

        # Threading
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._collection_task = None

        # Performance thresholds
        self.thresholds = {
            "max_processing_time_ms": 10.0,
            "max_error_rate_percent": 5.0,
            "min_throughput_msg_sec": 100.0,
            "max_bam_completion_time_ms": 50.0,
            "max_safety_response_time_ms": 5.0,
        }

        logger.info(
            "Performance Monitor initialized: "
            f"collection_interval={collection_interval}s, "
            f"retention_hours={retention_hours}h"
        )

    def start_monitoring(self) -> None:
        """Start background metrics collection."""
        if self._collection_task is None or self._collection_task.done():
            self._stop_event.clear()
            self._collection_task = asyncio.create_task(self._collection_loop())
            logger.info("Performance monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop background metrics collection."""
        if self._collection_task and not self._collection_task.done():
            self._stop_event.set()
            try:
                await asyncio.wait_for(self._collection_task, timeout=5.0)
            except TimeoutError:
                self._collection_task.cancel()
            logger.info("Performance monitoring stopped")

    async def _collection_loop(self) -> None:
        """Main metrics collection loop."""
        while not self._stop_event.is_set():
            try:
                await self._collect_metrics()
                await asyncio.sleep(self.collection_interval)
            except Exception as e:
                logger.error("Error in metrics collection: %s", e)
                await asyncio.sleep(self.collection_interval)

    async def _collect_metrics(self) -> None:
        """Collect current performance metrics."""
        current_time = time.time()

        with self._lock:
            # Collect component metrics
            for component, stats in self.component_stats.items():
                # Processing time metrics
                if stats.messages_processed > 0:
                    self._add_metric(
                        f"{component.value}_avg_processing_time_ms",
                        MetricType.GAUGE,
                        component,
                        stats.get_avg_processing_time(),
                        {"component": component.value},
                    )

                    self._add_metric(
                        f"{component.value}_p95_processing_time_ms",
                        MetricType.GAUGE,
                        component,
                        stats.get_percentile_processing_time(95.0),
                        {"component": component.value},
                    )

                # Throughput metrics
                self._add_metric(
                    f"{component.value}_throughput_msg_sec",
                    MetricType.GAUGE,
                    component,
                    stats.get_throughput(),
                    {"component": component.value},
                )

                # Error rate metrics
                self._add_metric(
                    f"{component.value}_error_rate_percent",
                    MetricType.GAUGE,
                    component,
                    stats.get_error_rate(),
                    {"component": component.value},
                )

                # Message count metrics
                self._add_metric(
                    f"{component.value}_messages_total",
                    MetricType.COUNTER,
                    component,
                    stats.messages_processed,
                    {"component": component.value},
                )

            # BAM-specific metrics
            self._collect_bam_metrics()

            # Safety engine metrics
            self._collect_safety_metrics()

            # Security manager metrics
            self._collect_security_metrics()

            # System-wide metrics
            self._collect_system_metrics()

    def _collect_bam_metrics(self) -> None:
        """Collect BAM handler specific metrics."""
        stats = self.bam_session_stats

        if stats["sessions_completed"] > 0:
            completion_rate = (
                stats["sessions_completed"] / max(stats["sessions_started"], 1)
            ) * 100

            self._add_metric(
                "bam_session_completion_rate_percent",
                MetricType.GAUGE,
                ComponentType.BAM_HANDLER,
                completion_rate,
            )

        if stats["completion_times"]:
            avg_time = statistics.mean(stats["completion_times"]) * 1000
            self._add_metric(
                "bam_avg_completion_time_ms", MetricType.GAUGE, ComponentType.BAM_HANDLER, avg_time
            )

        # Counter metrics
        for metric_name, value in [
            ("bam_sessions_started_total", stats["sessions_started"]),
            ("bam_sessions_completed_total", stats["sessions_completed"]),
            ("bam_sessions_timeout_total", stats["sessions_timeout"]),
            ("bam_sessions_failed_total", stats["sessions_failed"]),
        ]:
            self._add_metric(metric_name, MetricType.COUNTER, ComponentType.BAM_HANDLER, value)

    def _collect_safety_metrics(self) -> None:
        """Collect safety engine specific metrics."""
        stats = self.safety_stats

        if stats["state_transition_times"]:
            avg_time = statistics.mean(stats["state_transition_times"]) * 1000
            self._add_metric(
                "safety_avg_transition_time_ms",
                MetricType.GAUGE,
                ComponentType.SAFETY_ENGINE,
                avg_time,
            )

        # Counter metrics
        for metric_name, value in [
            ("safety_state_transitions_total", stats["state_transitions"]),
            ("safety_commands_issued_total", stats["safety_commands_issued"]),
            ("safety_operations_blocked_total", stats["operations_blocked"]),
            ("safety_emergency_stops_total", stats["emergency_stops"]),
        ]:
            self._add_metric(metric_name, MetricType.COUNTER, ComponentType.SAFETY_ENGINE, value)

    def _collect_security_metrics(self) -> None:
        """Collect security manager specific metrics."""
        stats = self.security_stats

        # Gauge metrics
        for metric_name, value in [
            ("security_learning_devices", stats["learning_devices"]),
            ("security_active_profiles", stats["active_profiles"]),
        ]:
            self._add_metric(metric_name, MetricType.GAUGE, ComponentType.SECURITY_MANAGER, value)

        # Counter metrics
        for metric_name, value in [
            ("security_frames_validated_total", stats["frames_validated"]),
            ("security_anomalies_detected_total", stats["anomalies_detected"]),
            ("security_threats_blocked_total", stats["threats_blocked"]),
        ]:
            self._add_metric(metric_name, MetricType.COUNTER, ComponentType.SECURITY_MANAGER, value)

        # Calculate security metrics
        if stats["frames_validated"] > 0:
            anomaly_rate = (stats["anomalies_detected"] / stats["frames_validated"]) * 100
            self._add_metric(
                "security_anomaly_rate_percent",
                MetricType.GAUGE,
                ComponentType.SECURITY_MANAGER,
                anomaly_rate,
            )

    def _collect_system_metrics(self) -> None:
        """Collect system-wide metrics."""
        current_time = time.time()
        uptime_hours = (current_time - self.system_stats["uptime_start"]) / 3600.0

        self._add_metric(
            "system_uptime_hours", MetricType.GAUGE, ComponentType.PROTOCOL_ROUTER, uptime_hours
        )

        self._add_metric(
            "system_messages_processed_total",
            MetricType.COUNTER,
            ComponentType.PROTOCOL_ROUTER,
            self.system_stats["total_messages_processed"],
        )

        if self.system_stats["total_messages_processed"] > 0:
            error_rate = (
                self.system_stats["total_errors"] / self.system_stats["total_messages_processed"]
            ) * 100
            self._add_metric(
                "system_error_rate_percent",
                MetricType.GAUGE,
                ComponentType.PROTOCOL_ROUTER,
                error_rate,
            )

    def _add_metric(
        self,
        name: str,
        metric_type: MetricType,
        component: ComponentType,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Add a metric to the collection."""
        metric = PerformanceMetric(
            name=name,
            metric_type=metric_type,
            component=component,
            value=value,
            labels=labels or {},
        )
        self.metrics.append(metric)

    # Public API methods for recording events

    def record_processing_time(self, component: ComponentType, duration: float) -> None:
        """Record processing time for a component."""
        with self._lock:
            self.component_stats[component].add_processing_time(duration)
            self.system_stats["total_messages_processed"] += 1
            self.system_stats["last_activity"] = time.time()

    def record_error(self, component: ComponentType) -> None:
        """Record an error for a component."""
        with self._lock:
            self.component_stats[component].add_error()
            self.system_stats["total_errors"] += 1

    def record_bam_session_start(self) -> None:
        """Record BAM session start."""
        with self._lock:
            self.bam_session_stats["sessions_started"] += 1

    def record_bam_session_complete(self, duration: float) -> None:
        """Record BAM session completion."""
        with self._lock:
            self.bam_session_stats["sessions_completed"] += 1
            self.bam_session_stats["completion_times"].append(duration)

    def record_bam_session_timeout(self) -> None:
        """Record BAM session timeout."""
        with self._lock:
            self.bam_session_stats["sessions_timeout"] += 1

    def record_bam_session_failed(self) -> None:
        """Record BAM session failure."""
        with self._lock:
            self.bam_session_stats["sessions_failed"] += 1

    def record_safety_state_transition(self, duration: float) -> None:
        """Record safety state transition."""
        with self._lock:
            self.safety_stats["state_transitions"] += 1
            self.safety_stats["state_transition_times"].append(duration)

    def record_safety_command_issued(self) -> None:
        """Record safety command issued."""
        with self._lock:
            self.safety_stats["safety_commands_issued"] += 1

    def record_safety_operation_blocked(self) -> None:
        """Record safety operation blocked."""
        with self._lock:
            self.safety_stats["operations_blocked"] += 1

    def record_safety_emergency_stop(self) -> None:
        """Record emergency stop activation."""
        with self._lock:
            self.safety_stats["emergency_stops"] += 1

    def record_security_frame_validated(self) -> None:
        """Record security frame validation."""
        with self._lock:
            self.security_stats["frames_validated"] += 1

    def record_security_anomaly_detected(self) -> None:
        """Record security anomaly detection."""
        with self._lock:
            self.security_stats["anomalies_detected"] += 1

    def record_security_threat_blocked(self) -> None:
        """Record security threat blocked."""
        with self._lock:
            self.security_stats["threats_blocked"] += 1

    def update_security_device_counts(self, learning: int, active: int) -> None:
        """Update security manager device counts."""
        with self._lock:
            self.security_stats["learning_devices"] = learning
            self.security_stats["active_profiles"] = active

    # Monitoring and alerting

    def check_performance_thresholds(self) -> list[dict[str, Any]]:
        """Check for performance threshold violations."""
        violations = []

        with self._lock:
            for component, stats in self.component_stats.items():
                # Check processing time
                avg_time = stats.get_avg_processing_time()
                if avg_time > self.thresholds["max_processing_time_ms"]:
                    violations.append(
                        {
                            "component": component.value,
                            "metric": "processing_time",
                            "value": avg_time,
                            "threshold": self.thresholds["max_processing_time_ms"],
                            "severity": "warning",
                        }
                    )

                # Check error rate
                error_rate = stats.get_error_rate()
                if error_rate > self.thresholds["max_error_rate_percent"]:
                    violations.append(
                        {
                            "component": component.value,
                            "metric": "error_rate",
                            "value": error_rate,
                            "threshold": self.thresholds["max_error_rate_percent"],
                            "severity": "critical",
                        }
                    )

                # Check throughput
                throughput = stats.get_throughput()
                if throughput < self.thresholds["min_throughput_msg_sec"] and throughput > 0:
                    violations.append(
                        {
                            "component": component.value,
                            "metric": "throughput",
                            "value": throughput,
                            "threshold": self.thresholds["min_throughput_msg_sec"],
                            "severity": "warning",
                        }
                    )

            # Check BAM completion time
            if self.bam_session_stats["completion_times"]:
                avg_bam_time = statistics.mean(self.bam_session_stats["completion_times"]) * 1000
                if avg_bam_time > self.thresholds["max_bam_completion_time_ms"]:
                    violations.append(
                        {
                            "component": "bam_handler",
                            "metric": "completion_time",
                            "value": avg_bam_time,
                            "threshold": self.thresholds["max_bam_completion_time_ms"],
                            "severity": "warning",
                        }
                    )

            # Check safety response time
            if self.safety_stats["state_transition_times"]:
                avg_safety_time = (
                    statistics.mean(self.safety_stats["state_transition_times"]) * 1000
                )
                if avg_safety_time > self.thresholds["max_safety_response_time_ms"]:
                    violations.append(
                        {
                            "component": "safety_engine",
                            "metric": "response_time",
                            "value": avg_safety_time,
                            "threshold": self.thresholds["max_safety_response_time_ms"],
                            "severity": "critical",
                        }
                    )

        return violations

    def get_prometheus_metrics(self) -> str:
        """Generate Prometheus exposition format metrics."""
        lines = []

        # Add help and type information
        metric_groups = defaultdict(list)

        with self._lock:
            # Group metrics by name
            for metric in self.metrics:
                metric_groups[metric.name].append(metric)

            # Generate Prometheus format
            for metric_name, metric_list in metric_groups.items():
                if metric_list:
                    latest_metric = metric_list[-1]  # Use latest value

                    # Add HELP and TYPE
                    full_name = f"canbus_decoder_{metric_name}"
                    lines.append(f"# HELP {full_name} {latest_metric.description}")
                    lines.append(f"# TYPE {full_name} {latest_metric.metric_type.value}")

                    # Add metric
                    lines.append(latest_metric.to_prometheus_format())

        return "\n".join(lines)

    def get_performance_summary(self) -> dict[str, Any]:
        """Get comprehensive performance summary."""
        with self._lock:
            summary = {
                "timestamp": time.time(),
                "uptime_hours": (time.time() - self.system_stats["uptime_start"]) / 3600.0,
                "system": {
                    "total_messages": self.system_stats["total_messages_processed"],
                    "total_errors": self.system_stats["total_errors"],
                    "overall_error_rate": (
                        self.system_stats["total_errors"]
                        / max(self.system_stats["total_messages_processed"], 1)
                    )
                    * 100,
                },
                "components": {},
                "bam_handler": {
                    "sessions_started": self.bam_session_stats["sessions_started"],
                    "sessions_completed": self.bam_session_stats["sessions_completed"],
                    "completion_rate": (
                        self.bam_session_stats["sessions_completed"]
                        / max(self.bam_session_stats["sessions_started"], 1)
                    )
                    * 100,
                    "avg_completion_time_ms": (
                        statistics.mean(self.bam_session_stats["completion_times"]) * 1000
                        if self.bam_session_stats["completion_times"]
                        else 0.0
                    ),
                },
                "safety_engine": {
                    "state_transitions": self.safety_stats["state_transitions"],
                    "commands_issued": self.safety_stats["safety_commands_issued"],
                    "operations_blocked": self.safety_stats["operations_blocked"],
                    "emergency_stops": self.safety_stats["emergency_stops"],
                    "avg_response_time_ms": (
                        statistics.mean(self.safety_stats["state_transition_times"]) * 1000
                        if self.safety_stats["state_transition_times"]
                        else 0.0
                    ),
                },
                "security_manager": {
                    "frames_validated": self.security_stats["frames_validated"],
                    "anomalies_detected": self.security_stats["anomalies_detected"],
                    "threats_blocked": self.security_stats["threats_blocked"],
                    "learning_devices": self.security_stats["learning_devices"],
                    "active_profiles": self.security_stats["active_profiles"],
                    "anomaly_rate": (
                        self.security_stats["anomalies_detected"]
                        / max(self.security_stats["frames_validated"], 1)
                    )
                    * 100,
                },
                "threshold_violations": self.check_performance_thresholds(),
            }

            # Add component statistics
            for component, stats in self.component_stats.items():
                summary["components"][component.value] = {
                    "messages_processed": stats.messages_processed,
                    "avg_processing_time_ms": stats.get_avg_processing_time(),
                    "p95_processing_time_ms": stats.get_percentile_processing_time(95.0),
                    "error_rate_percent": stats.get_error_rate(),
                    "throughput_msg_sec": stats.get_throughput(),
                }

            return summary

    def reset_metrics(self) -> None:
        """Reset all metrics (for testing purposes)."""
        with self._lock:
            self.metrics.clear()
            self.component_stats = {
                component: ComponentStats(component) for component in ComponentType
            }
            self.bam_session_stats = {
                "sessions_started": 0,
                "sessions_completed": 0,
                "sessions_timeout": 0,
                "sessions_failed": 0,
                "avg_completion_time": 0.0,
                "completion_times": deque(maxlen=1000),
            }
            self.safety_stats = {
                "state_transitions": 0,
                "safety_commands_issued": 0,
                "operations_blocked": 0,
                "emergency_stops": 0,
                "state_transition_times": deque(maxlen=1000),
            }
            self.security_stats = {
                "frames_validated": 0,
                "anomalies_detected": 0,
                "threats_blocked": 0,
                "learning_devices": 0,
                "active_profiles": 0,
            }
            self.system_stats = {
                "total_messages_processed": 0,
                "total_errors": 0,
                "uptime_start": time.time(),
                "last_activity": time.time(),
            }
            logger.info("Performance metrics reset")
