"""Performance monitoring framework for service methods and operations.

This module provides decorators and utilities for monitoring the performance
of services, repositories, and API endpoints with request tracing support.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, Dict, List, Optional

from prometheus_client import Counter, Gauge, Histogram

from backend.core.context import get_request_id
from backend.core.metrics import _safe_create_metric

logger = logging.getLogger(__name__)


# Prometheus metrics for performance monitoring
SERVICE_METHOD_LATENCY = _safe_create_metric(
    Histogram,
    "coachiq_service_method_latency_seconds",
    "Service method execution latency",
    labelnames=["service", "method"],
)

SERVICE_METHOD_ERRORS = _safe_create_metric(
    Counter,
    "coachiq_service_method_errors_total",
    "Total service method errors",
    labelnames=["service", "method", "error_type"],
)

REPOSITORY_OPERATION_LATENCY = _safe_create_metric(
    Histogram,
    "coachiq_repository_operation_latency_seconds",
    "Repository operation execution latency",
    labelnames=["repository", "operation"],
)

SLOW_OPERATIONS = _safe_create_metric(
    Counter,
    "coachiq_slow_operations_total",
    "Total slow operations detected",
    labelnames=["service", "method"],
)


class MetricsCollector:
    """Collects and stores performance metrics using Prometheus and in-memory storage."""

    def __init__(self):
        self._metrics: dict[str, list[dict]] = {}

    def record_service_latency(
        self,
        service_name: str,
        method_name: str,
        latency_ms: float,
        request_id: str | None = None,
    ) -> None:
        """Record service method latency."""
        # Record to Prometheus
        if SERVICE_METHOD_LATENCY:
            SERVICE_METHOD_LATENCY.labels(service=service_name, method=method_name).observe(
                latency_ms / 1000.0
            )  # Convert to seconds

        # Also store in memory for detailed analysis
        metric = {
            "service": service_name,
            "method": method_name,
            "latency_ms": latency_ms,
            "request_id": request_id,
            "timestamp": time.time(),
        }
        key = f"{service_name}.{method_name}"
        if key not in self._metrics:
            self._metrics[key] = []
        self._metrics[key].append(metric)

    def record_slow_operation(
        self,
        service_name: str,
        method_name: str,
        latency_ms: float,
        request_id: str | None = None,
    ) -> None:
        """Record a slow operation for alerting."""
        # Record to Prometheus
        if SLOW_OPERATIONS:
            SLOW_OPERATIONS.labels(service=service_name, method=method_name).inc()

        logger.warning(
            f"Slow operation detected: {service_name}.{method_name} "
            f"took {latency_ms:.2f}ms (request_id: {request_id})"
        )

    def record_service_error(
        self, service_name: str, method_name: str, error: str, request_id: str | None = None
    ) -> None:
        """Record service method error."""
        # Record to Prometheus
        if SERVICE_METHOD_ERRORS:
            # Extract error type from error string
            error_type = type(error).__name__ if hasattr(error, "__class__") else "Unknown"
            SERVICE_METHOD_ERRORS.labels(
                service=service_name, method=method_name, error_type=error_type
            ).inc()

        logger.error(
            f"Service error in {service_name}.{method_name}: {error} (request_id: {request_id})"
        )

    def record_api_latency(
        self,
        method: str,
        path: str,
        latency_ms: float,
        request_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        """Record API endpoint latency."""
        # Use existing HTTP metrics from backend.core.metrics
        from backend.core.metrics import get_http_latency, get_http_requests

        try:
            # Record to Prometheus HTTP latency
            http_latency = get_http_latency()
            if http_latency:
                http_latency.labels(method=method, endpoint=path).observe(
                    latency_ms / 1000.0
                )  # Convert to seconds

            # Record to Prometheus HTTP requests counter
            if status_code:
                http_requests = get_http_requests()
                if http_requests:
                    http_requests.labels(
                        method=method, endpoint=path, status_code=str(status_code)
                    ).inc()
        except Exception as e:
            logger.warning(f"Failed to record HTTP metrics: {e}")

        # Also store in memory for detailed analysis
        metric = {
            "method": method,
            "path": path,
            "latency_ms": latency_ms,
            "request_id": request_id,
            "status_code": status_code,
            "timestamp": time.time(),
        }
        key = f"api.{method}.{path}"
        if key not in self._metrics:
            self._metrics[key] = []
        self._metrics[key].append(metric)

    async def get_service_metrics(self, time_range: str) -> dict:
        """Get service metrics for the specified time range."""
        # TODO: Implement time range filtering
        return {"metrics": self._metrics, "summary": self._calculate_summary()}

    def _calculate_summary(self) -> dict:
        """Calculate summary statistics for metrics."""
        summary = {}
        for key, metrics in self._metrics.items():
            if not metrics:
                continue

            latencies = [m.get("latency_ms", 0) for m in metrics]
            latencies.sort()

            summary[key] = {
                "count": len(metrics),
                "min": min(latencies),
                "max": max(latencies),
                "avg": sum(latencies) / len(latencies),
                "p50": latencies[len(latencies) // 2],
                "p95": latencies[int(len(latencies) * 0.95)]
                if len(latencies) > 20
                else max(latencies),
                "p99": latencies[int(len(latencies) * 0.99)]
                if len(latencies) > 100
                else max(latencies),
            }

        return summary


class PerformanceMonitor:
    """Central performance monitoring system."""

    def __init__(self, metrics_collector: MetricsCollector | None = None):
        self._metrics = metrics_collector or MetricsCollector()

    def monitor_service_method(
        self, service_name: str, method_name: str, alert_threshold_ms: float = 100
    ):
        """Decorator for monitoring async service methods.

        Args:
            service_name: Name of the service
            method_name: Name of the method being monitored
            alert_threshold_ms: Threshold in milliseconds for slow operation alerts

        Returns:
            Decorated function with performance monitoring
        """

        def decorator(func: Callable) -> Callable:
            if not asyncio.iscoroutinefunction(func):
                # Log warning but don't fail for sync methods
                logger.warning(
                    f"{service_name}.{method_name} is sync - "
                    "consider converting to async for monitoring"
                )
                return func

            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                start_time = time.perf_counter()
                request_id = get_request_id()

                try:
                    result = await func(*args, **kwargs)
                    elapsed_ms = (time.perf_counter() - start_time) * 1000

                    # Record metrics with request ID for tracing
                    self._metrics.record_service_latency(
                        service_name, method_name, elapsed_ms, request_id=request_id
                    )

                    if elapsed_ms > alert_threshold_ms:
                        self._metrics.record_slow_operation(
                            service_name, method_name, elapsed_ms, request_id=request_id
                        )

                    return result
                except Exception as e:
                    self._metrics.record_service_error(
                        service_name, method_name, str(e), request_id=request_id
                    )
                    raise

            return async_wrapper

        return decorator

    def monitor_repository_operation(
        self, repository_name: str, operation_name: str, alert_threshold_ms: float = 50
    ):
        """Decorator for monitoring repository operations.

        Args:
            repository_name: Name of the repository
            operation_name: Name of the operation being monitored
            alert_threshold_ms: Threshold in milliseconds for slow operation alerts

        Returns:
            Decorated function
        """

        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                request_id = get_request_id()

                try:
                    result = await func(*args, **kwargs)
                    latency_ms = (time.time() - start_time) * 1000

                    # Record to Prometheus
                    if REPOSITORY_OPERATION_LATENCY:
                        REPOSITORY_OPERATION_LATENCY.labels(
                            repository=repository_name, operation=operation_name
                        ).observe(latency_ms / 1000.0)

                    # Record to metrics collector
                    self._metrics.record_service_latency(
                        repository_name, operation_name, latency_ms, request_id=request_id
                    )

                    # Alert on slow operations
                    if latency_ms > alert_threshold_ms:
                        self._metrics.record_slow_operation(
                            repository_name, operation_name, latency_ms, request_id=request_id
                        )

                    return result
                except Exception as e:
                    self._metrics.record_service_error(
                        repository_name, operation_name, str(e), request_id=request_id
                    )
                    raise

            return async_wrapper

        return decorator

    def record_api_latency(self, **kwargs) -> None:
        """Record API endpoint latency."""
        self._metrics.record_api_latency(**kwargs)

    async def get_service_metrics(self, time_range: str = "1h") -> dict:
        """Get service performance metrics."""
        return await self._metrics.get_service_metrics(time_range)

    async def get_repository_metrics(self, time_range: str = "1h") -> dict:
        """Get repository performance metrics."""
        # Filter metrics for repository operations
        all_metrics = await self._metrics.get_service_metrics(time_range)
        repo_metrics = {k: v for k, v in all_metrics["metrics"].items() if "Repository" in k}
        return {"metrics": repo_metrics}

    async def get_api_metrics(self, time_range: str = "1h") -> dict:
        """Get API endpoint performance metrics."""
        # Filter metrics for API operations
        all_metrics = await self._metrics.get_service_metrics(time_range)
        api_metrics = {k: v for k, v in all_metrics["metrics"].items() if k.startswith("api.")}
        return {"metrics": api_metrics}

    async def get_websocket_metrics(self, time_range: str = "1h") -> dict:
        """Get WebSocket performance metrics."""
        # TODO: Implement WebSocket metrics collection
        return {"metrics": {}}

    async def get_performance_baselines(self) -> dict:
        """Get current performance baselines."""
        summary = self._metrics._calculate_summary()

        baselines = {"service_methods": {}, "repository_operations": {}, "api_endpoints": {}}

        for key, stats in summary.items():
            if "Repository" in key:
                baselines["repository_operations"][key] = stats
            elif key.startswith("api."):
                baselines["api_endpoints"][key] = stats
            else:
                baselines["service_methods"][key] = stats

        return baselines

    async def establish_baselines(self) -> dict:
        """Establish performance baselines from current metrics."""
        baselines = await self.get_performance_baselines()

        # TODO: Save baselines to configuration
        logger.info(f"Established performance baselines: {baselines}")

        return {"status": "baselines_established", "baselines": baselines}


class MonitoredRepository:
    """Base class for repositories with performance monitoring."""

    def __init__(self, performance_monitor: PerformanceMonitor):
        self._monitor = performance_monitor
        self._repository_name = self.__class__.__name__

    def _monitored_operation(self, operation_name: str):
        """Decorator for monitoring repository operations."""
        return self._monitor.monitor_service_method(
            self._repository_name,
            operation_name,
            alert_threshold_ms=50,  # Repositories should be fast
        )
