"""
Health Probe Metrics Collection

Comprehensive monitoring for health endpoint performance and reliability.
Provides Prometheus metrics and alerting for production monitoring.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProbeMetric:
    """Individual health probe execution metric"""

    endpoint: str
    timestamp: float
    response_time_ms: float
    status_code: int
    status: str  # pass, warn, fail
    error: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class ProbeStatistics:
    """Aggregated statistics for a health probe endpoint"""

    endpoint: str
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    warning_count: int = 0
    avg_response_time_ms: float = 0.0
    min_response_time_ms: float = float("inf")
    max_response_time_ms: float = 0.0
    success_rate: float = 0.0
    last_success_time: float | None = None
    last_failure_time: float | None = None
    consecutive_failures: int = 0
    recent_metrics: deque = field(default_factory=lambda: deque(maxlen=100))


class HealthProbeMonitor:
    """
    Monitors health probe performance and provides metrics for alerting.

    Tracks response times, success rates, and failure patterns across
    all health endpoints (/healthz, /readyz, /startupz).
    """

    def __init__(self, metric_retention_seconds: int = 3600):
        self.metric_retention_seconds = metric_retention_seconds
        self.statistics: dict[str, ProbeStatistics] = {}
        self.recent_metrics: deque = deque(maxlen=10000)  # Last 10k metrics
        self._lock = Lock()

        # Performance thresholds for alerting
        self.thresholds = {
            "healthz": {
                "target_response_time_ms": 5.0,  # <5ms target for liveness
                "warning_response_time_ms": 10.0,  # Warning at 10ms
                "critical_response_time_ms": 50.0,  # Critical at 50ms
                "min_success_rate": 0.99,  # 99% success rate minimum
            },
            "readyz": {
                "target_response_time_ms": 50.0,  # <50ms target for readiness
                "warning_response_time_ms": 100.0,  # Warning at 100ms
                "critical_response_time_ms": 500.0,  # Critical at 500ms
                "min_success_rate": 0.95,  # 95% success rate minimum
            },
            "startupz": {
                "target_response_time_ms": 100.0,  # <100ms target for startup
                "warning_response_time_ms": 200.0,  # Warning at 200ms
                "critical_response_time_ms": 1000.0,  # Critical at 1s
                "min_success_rate": 0.90,  # 90% success rate minimum
            },
        }

        logger.info("Health probe monitor initialized")

    def record_probe_execution(
        self,
        endpoint: str,
        response_time_ms: float,
        status_code: int,
        status: str,
        error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> ProbeMetric:
        """Record a health probe execution result"""

        metric = ProbeMetric(
            endpoint=endpoint,
            timestamp=time.time(),
            response_time_ms=response_time_ms,
            status_code=status_code,
            status=status,
            error=error,
            details=details,
        )

        with self._lock:
            # Add to recent metrics
            self.recent_metrics.append(metric)

            # Update endpoint statistics
            if endpoint not in self.statistics:
                self.statistics[endpoint] = ProbeStatistics(endpoint=endpoint)

            stats = self.statistics[endpoint]
            stats.total_requests += 1
            stats.recent_metrics.append(metric)

            # Update success/failure counts
            if status == "pass" and 200 <= status_code < 300:
                stats.success_count += 1
                stats.last_success_time = metric.timestamp
                stats.consecutive_failures = 0
            elif status == "warn":
                stats.warning_count += 1
                stats.consecutive_failures = 0
            else:
                stats.failure_count += 1
                stats.last_failure_time = metric.timestamp
                stats.consecutive_failures += 1

            # Update response time statistics
            stats.min_response_time_ms = min(stats.min_response_time_ms, response_time_ms)
            stats.max_response_time_ms = max(stats.max_response_time_ms, response_time_ms)

            # Calculate running average
            if stats.total_requests == 1:
                stats.avg_response_time_ms = response_time_ms
            else:
                # Weighted average favoring recent measurements
                weight = 0.1  # 10% weight to new measurement
                stats.avg_response_time_ms = (
                    1 - weight
                ) * stats.avg_response_time_ms + weight * response_time_ms

            # Calculate success rate
            stats.success_rate = stats.success_count / stats.total_requests

        # Check for threshold violations and log warnings
        self._check_thresholds(endpoint, metric, stats)

        return metric

    def _check_thresholds(self, endpoint: str, metric: ProbeMetric, stats: ProbeStatistics):
        """Check if metric violates performance thresholds"""
        thresholds = self.thresholds.get(endpoint, {})

        # Check response time thresholds
        if metric.response_time_ms > thresholds.get("critical_response_time_ms", float("inf")):
            logger.critical(
                f"CRITICAL: {endpoint} response time {metric.response_time_ms:.2f}ms "
                f"exceeds critical threshold {thresholds['critical_response_time_ms']}ms"
            )
        elif metric.response_time_ms > thresholds.get("warning_response_time_ms", float("inf")):
            logger.warning(
                f"WARNING: {endpoint} response time {metric.response_time_ms:.2f}ms "
                f"exceeds warning threshold {thresholds['warning_response_time_ms']}ms"
            )

        # Check success rate thresholds (only after sufficient samples)
        if stats.total_requests >= 10:
            min_success_rate = thresholds.get("min_success_rate", 0.0)
            if stats.success_rate < min_success_rate:
                logger.error(
                    f"ERROR: {endpoint} success rate {stats.success_rate:.2%} "
                    f"below minimum {min_success_rate:.2%}"
                )

        # Check consecutive failures
        if stats.consecutive_failures >= 5:
            logger.critical(
                f"CRITICAL: {endpoint} has {stats.consecutive_failures} consecutive failures"
            )
        elif stats.consecutive_failures >= 3:
            logger.error(f"ERROR: {endpoint} has {stats.consecutive_failures} consecutive failures")

    def get_endpoint_statistics(self, endpoint: str) -> ProbeStatistics | None:
        """Get statistics for a specific endpoint"""
        with self._lock:
            return self.statistics.get(endpoint)

    def get_all_statistics(self) -> dict[str, ProbeStatistics]:
        """Get statistics for all endpoints"""
        with self._lock:
            return dict(self.statistics)

    def get_recent_metrics(
        self, endpoint: str | None = None, limit: int = 100
    ) -> list[ProbeMetric]:
        """Get recent metrics for an endpoint or all endpoints"""
        with self._lock:
            if endpoint:
                return [m for m in list(self.recent_metrics)[-limit:] if m.endpoint == endpoint]
            return list(self.recent_metrics)[-limit:]

    def get_prometheus_metrics(self) -> dict[str, Any]:
        """Generate Prometheus-compatible metrics"""
        metrics = {
            "health_probe_requests_total": {},
            "health_probe_request_duration_seconds": {},
            "health_probe_success_rate": {},
            "health_probe_consecutive_failures": {},
            "health_probe_last_success_timestamp": {},
            "health_probe_last_failure_timestamp": {},
        }

        with self._lock:
            for endpoint, stats in self.statistics.items():
                labels = f'endpoint="{endpoint}"'

                metrics["health_probe_requests_total"][labels] = stats.total_requests
                metrics["health_probe_request_duration_seconds"][f'{labels},quantile="avg"'] = (
                    stats.avg_response_time_ms / 1000
                )
                metrics["health_probe_request_duration_seconds"][f'{labels},quantile="min"'] = (
                    stats.min_response_time_ms / 1000
                )
                metrics["health_probe_request_duration_seconds"][f'{labels},quantile="max"'] = (
                    stats.max_response_time_ms / 1000
                )
                metrics["health_probe_success_rate"][labels] = stats.success_rate
                metrics["health_probe_consecutive_failures"][labels] = stats.consecutive_failures

                if stats.last_success_time:
                    metrics["health_probe_last_success_timestamp"][labels] = stats.last_success_time
                if stats.last_failure_time:
                    metrics["health_probe_last_failure_timestamp"][labels] = stats.last_failure_time

        return metrics

    def get_health_summary(self) -> dict[str, Any]:
        """Get overall health monitoring summary"""
        summary = {
            "endpoints": {},
            "overall_health": "healthy",
            "total_requests": 0,
            "global_success_rate": 0.0,
            "alerts": [],
        }

        total_success = 0
        total_requests = 0
        critical_issues = []
        warning_issues = []

        with self._lock:
            for endpoint, stats in self.statistics.items():
                endpoint_summary = {
                    "total_requests": stats.total_requests,
                    "success_rate": stats.success_rate,
                    "avg_response_time_ms": stats.avg_response_time_ms,
                    "consecutive_failures": stats.consecutive_failures,
                    "health_status": "healthy",
                }

                # Determine endpoint health status
                thresholds = self.thresholds.get(endpoint, {})
                if stats.consecutive_failures >= 5:
                    endpoint_summary["health_status"] = "critical"
                    critical_issues.append(
                        f"{endpoint}: {stats.consecutive_failures} consecutive failures"
                    )
                elif stats.success_rate < thresholds.get("min_success_rate", 0.95):
                    endpoint_summary["health_status"] = "warning"
                    warning_issues.append(f"{endpoint}: {stats.success_rate:.2%} success rate")
                elif stats.avg_response_time_ms > thresholds.get(
                    "warning_response_time_ms", float("inf")
                ):
                    endpoint_summary["health_status"] = "warning"
                    warning_issues.append(
                        f"{endpoint}: {stats.avg_response_time_ms:.1f}ms avg response"
                    )

                summary["endpoints"][endpoint] = endpoint_summary
                total_success += stats.success_count
                total_requests += stats.total_requests

        # Calculate global metrics
        if total_requests > 0:
            summary["global_success_rate"] = total_success / total_requests
            summary["total_requests"] = total_requests

        # Determine overall health
        if critical_issues:
            summary["overall_health"] = "critical"
            summary["alerts"] = critical_issues + warning_issues
        elif warning_issues:
            summary["overall_health"] = "warning"
            summary["alerts"] = warning_issues

        return summary

    def cleanup_old_metrics(self):
        """Remove metrics older than retention period"""
        cutoff_time = time.time() - self.metric_retention_seconds

        with self._lock:
            # Clean up recent_metrics deque
            while self.recent_metrics and self.recent_metrics[0].timestamp < cutoff_time:
                self.recent_metrics.popleft()

            # Clean up per-endpoint recent metrics
            for stats in self.statistics.values():
                while stats.recent_metrics and stats.recent_metrics[0].timestamp < cutoff_time:
                    stats.recent_metrics.popleft()

    async def start_cleanup_task(self):
        """Start background task to clean up old metrics"""
        while True:
            try:
                await asyncio.sleep(300)  # Clean up every 5 minutes
                self.cleanup_old_metrics()
            except Exception as e:
                logger.error(f"Error in metrics cleanup task: {e}")


# Global health probe monitor instance
health_probe_monitor = HealthProbeMonitor()


def record_health_probe(
    endpoint: str, response_time_ms: float, status_code: int, status: str, **kwargs
):
    """Convenience function to record health probe execution"""
    return health_probe_monitor.record_probe_execution(
        endpoint=endpoint,
        response_time_ms=response_time_ms,
        status_code=status_code,
        status=status,
        **kwargs,
    )


def get_health_monitoring_summary() -> dict[str, Any]:
    """Get current health monitoring summary"""
    return health_probe_monitor.get_health_summary()
