"""
Lightweight Performance Monitoring for Raspberry Pi Deployment

Optimized performance monitoring with minimal memory overhead,
tailored for embedded deployment constraints.
"""

import asyncio
import time
from collections import deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Any, Deque, Dict, Optional, Tuple

from backend.core.structured_logging import get_logger

logger = get_logger(__name__, "RPiPerformanceMonitor")


@dataclass
class QuickMetric:
    """Lightweight metric with minimal memory footprint."""
    latency_ms: float
    timestamp: float
    request_id: str | None = None


class CircularBuffer:
    """Memory-efficient circular buffer for metrics."""

    def __init__(self, maxsize: int = 100):
        self._buffer: deque[QuickMetric] = deque(maxlen=maxsize)
        self._total_count = 0
        self._total_latency = 0.0

    def add(self, metric: QuickMetric) -> None:
        """Add metric to buffer."""
        # Update running totals
        self._total_count += 1
        self._total_latency += metric.latency_ms

        # If buffer is full, subtract the metric being evicted
        if len(self._buffer) == self._buffer.maxlen:
            evicted = self._buffer[0]  # About to be evicted
            self._total_latency -= evicted.latency_ms

        self._buffer.append(metric)

    def get_stats(self) -> dict[str, float]:
        """Get quick statistics."""
        if not self._buffer:
            return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0}

        latencies = [m.latency_ms for m in self._buffer]
        latencies.sort()

        count = len(latencies)
        return {
            "count": count,
            "avg": sum(latencies) / count,
            "min": min(latencies),
            "max": max(latencies),
            "p95": latencies[int(count * 0.95)] if count > 20 else max(latencies),
            "recent_avg": self._total_latency / len(self._buffer)  # Running average
        }


class LightweightPerformanceMonitor:
    """
    Lightweight performance monitor optimized for Raspberry Pi 4.
    
    Features:
    - Minimal memory usage with circular buffers
    - Fast metric collection with deque operations
    - Configurable alert thresholds
    - Efficient statistics calculation
    """

    def __init__(self, buffer_size: int = 100, enable_detailed_logging: bool = False):
        self._buffers: dict[str, CircularBuffer] = {}
        self._buffer_size = buffer_size
        self._enable_detailed_logging = enable_detailed_logging

        # Alert thresholds optimized for RPi
        self._alert_thresholds = {
            "api": 200.0,      # API calls should be under 200ms
            "service": 100.0,  # Service methods under 100ms
            "database": 50.0,  # Database operations under 50ms
            "cache": 10.0,     # Cache operations under 10ms
            "can": 5.0,        # CAN operations under 5ms (safety-critical)
        }

        # Performance baseline tracking
        self._baselines: dict[str, float] = {}
        self._baseline_window = 50  # Establish baseline after 50 measurements

        logger.info(f"Initialized lightweight performance monitor (buffer_size={buffer_size})")

    def _get_buffer(self, operation_key: str) -> CircularBuffer:
        """Get or create buffer for operation."""
        if operation_key not in self._buffers:
            self._buffers[operation_key] = CircularBuffer(self._buffer_size)
        return self._buffers[operation_key]

    def _determine_category(self, operation_key: str) -> str:
        """Determine alert category from operation key."""
        key_lower = operation_key.lower()
        if "api" in key_lower or "endpoint" in key_lower:
            return "api"
        if "cache" in key_lower:
            return "cache"
        if "database" in key_lower or "db" in key_lower or "repository" in key_lower:
            return "database"
        if "can" in key_lower or "rvc" in key_lower:
            return "can"
        return "service"

    def record_operation(
        self,
        operation_key: str,
        latency_ms: float,
        request_id: str | None = None
    ) -> None:
        """Record operation latency with minimal overhead."""
        metric = QuickMetric(
            latency_ms=latency_ms,
            timestamp=time.time(),
            request_id=request_id
        )

        buffer = self._get_buffer(operation_key)
        buffer.add(metric)

        # Check for alerts
        category = self._determine_category(operation_key)
        threshold = self._alert_thresholds.get(category, 100.0)

        if latency_ms > threshold:
            logger.warning(
                f"Slow operation: {operation_key} took {latency_ms:.2f}ms "
                f"(threshold: {threshold}ms, request_id: {request_id})"
            )

        # Update baseline if we have enough data
        if buffer._total_count >= self._baseline_window:
            stats = buffer.get_stats()
            self._baselines[operation_key] = stats["avg"]

            if self._enable_detailed_logging and buffer._total_count == self._baseline_window:
                logger.info(f"Established baseline for {operation_key}: {stats['avg']:.2f}ms")

    @asynccontextmanager
    async def monitor_async_operation(self, operation_key: str, request_id: str | None = None):
        """Async context manager for monitoring operations."""
        start_time = time.perf_counter()
        try:
            yield
        finally:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.record_operation(operation_key, latency_ms, request_id)

    def monitor_method(self, operation_key: str, alert_threshold_ms: float | None = None):
        """Decorator for monitoring async methods."""
        def decorator(func: Callable) -> Callable:
            if not asyncio.iscoroutinefunction(func):
                logger.warning(f"{operation_key} is sync - limited monitoring available")
                return func

            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    latency_ms = (time.perf_counter() - start_time) * 1000

                    # Use custom threshold if provided
                    if alert_threshold_ms:
                        category = self._determine_category(operation_key)
                        self._alert_thresholds[category] = alert_threshold_ms

                    self.record_operation(operation_key, latency_ms)
                    return result
                except Exception as e:
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    logger.error(f"Error in {operation_key} after {latency_ms:.2f}ms: {e}")
                    raise

            return async_wrapper
        return decorator

    def get_operation_stats(self, operation_key: str) -> dict[str, Any]:
        """Get statistics for specific operation."""
        if operation_key not in self._buffers:
            return {"error": "Operation not found"}

        buffer = self._buffers[operation_key]
        stats = buffer.get_stats()

        # Add baseline comparison if available
        if operation_key in self._baselines:
            baseline = self._baselines[operation_key]
            if stats["avg"] > 0:
                stats["baseline_ms"] = baseline
                stats["deviation_percent"] = ((stats["avg"] - baseline) / baseline) * 100

        return stats

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all monitored operations."""
        return {
            operation_key: self.get_operation_stats(operation_key)
            for operation_key in self._buffers.keys()
        }

    def get_health_summary(self) -> dict[str, Any]:
        """Get health summary optimized for RPi dashboard."""
        all_stats = self.get_all_stats()

        # Categorize operations
        categories = {
            "api": [],
            "service": [],
            "database": [],
            "cache": [],
            "can": []
        }

        for operation_key, stats in all_stats.items():
            category = self._determine_category(operation_key)
            categories[category].append({
                "operation": operation_key,
                "avg_ms": stats.get("avg", 0),
                "count": stats.get("count", 0),
                "p95_ms": stats.get("p95", 0)
            })

        # Calculate category health scores
        health_scores = {}
        for category, operations in categories.items():
            if not operations:
                health_scores[category] = {"score": 100, "status": "healthy"}
                continue

            threshold = self._alert_thresholds[category]
            avg_latency = sum(op["avg_ms"] for op in operations) / len(operations)

            # Simple health score: 100 when at threshold, 0 when 3x threshold
            score = max(0, 100 - (avg_latency / threshold) * 33.33)

            if score >= 80:
                status = "healthy"
            elif score >= 60:
                status = "warning"
            else:
                status = "critical"

            health_scores[category] = {
                "score": round(score, 1),
                "status": status,
                "avg_latency_ms": round(avg_latency, 2),
                "threshold_ms": threshold
            }

        return {
            "overall_health": min(score["score"] for score in health_scores.values()),
            "categories": health_scores,
            "total_operations": len(all_stats),
            "memory_usage_kb": self._estimate_memory_usage()
        }

    def _estimate_memory_usage(self) -> float:
        """Estimate memory usage in KB."""
        # Rough estimate: QuickMetric ~40 bytes, buffer overhead ~100 bytes
        total_metrics = sum(len(buffer._buffer) for buffer in self._buffers.values())
        estimated_bytes = total_metrics * 40 + len(self._buffers) * 100
        return round(estimated_bytes / 1024, 2)

    def reset_buffers(self) -> None:
        """Reset all buffers - useful for testing."""
        self._buffers.clear()
        self._baselines.clear()
        logger.info("Performance monitor buffers reset")

    def set_alert_threshold(self, category: str, threshold_ms: float) -> None:
        """Update alert threshold for category."""
        if category in self._alert_thresholds:
            old_threshold = self._alert_thresholds[category]
            self._alert_thresholds[category] = threshold_ms
            logger.info(f"Updated {category} threshold: {old_threshold}ms -> {threshold_ms}ms")
        else:
            logger.warning(f"Unknown category: {category}")


# Global instance for easy access
_rpi_monitor: LightweightPerformanceMonitor | None = None


def get_rpi_performance_monitor() -> LightweightPerformanceMonitor:
    """Get global RPi performance monitor instance."""
    global _rpi_monitor
    if _rpi_monitor is None:
        _rpi_monitor = LightweightPerformanceMonitor()
    return _rpi_monitor


def initialize_rpi_performance_monitor(
    buffer_size: int = 100,
    enable_detailed_logging: bool = False
) -> LightweightPerformanceMonitor:
    """Initialize global RPi performance monitor."""
    global _rpi_monitor
    _rpi_monitor = LightweightPerformanceMonitor(
        buffer_size=buffer_size,
        enable_detailed_logging=enable_detailed_logging
    )
    logger.info("RPi performance monitor initialized")
    return _rpi_monitor


# Convenience decorators
def monitor_rpi_operation(operation_key: str, alert_threshold_ms: float | None = None):
    """Decorator for monitoring operations on RPi."""
    monitor = get_rpi_performance_monitor()
    return monitor.monitor_method(operation_key, alert_threshold_ms)


async def record_rpi_operation(operation_key: str, latency_ms: float, request_id: str | None = None):
    """Record operation for RPi monitoring."""
    monitor = get_rpi_performance_monitor()
    monitor.record_operation(operation_key, latency_ms, request_id)
