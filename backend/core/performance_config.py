"""Performance configuration and baselines for v1.0 release.

This module defines performance thresholds and baselines that will be
established during development and used for monitoring in production.
"""

from typing import Any, Dict


class PerformanceBaselines:
    """Performance baselines for v1.0 release.

    These values will be established from actual measurements during development
    and used as targets for production monitoring.
    """

    # Service method baselines (milliseconds)
    SERVICE_METHOD_P50 = 20  # 50th percentile target
    SERVICE_METHOD_P95 = 100  # 95th percentile target
    SERVICE_METHOD_P99 = 200  # 99th percentile target

    # Repository operation baselines (milliseconds)
    REPOSITORY_READ_P95 = 10  # Read operations should be very fast
    REPOSITORY_WRITE_P95 = 30  # Write operations can be slightly slower

    # API endpoint baselines (milliseconds)
    API_GET_P95 = 100  # GET requests target
    API_POST_P95 = 150  # POST requests target
    API_BULK_P95 = 500  # Bulk operations target

    # WebSocket baselines (milliseconds)
    WEBSOCKET_MESSAGE_P95 = 20  # Real-time message handling

    # Alert thresholds (multipliers of baseline)
    ALERT_WARNING_MULTIPLIER = 2.0  # Warn at 2x baseline
    ALERT_CRITICAL_MULTIPLIER = 5.0  # Critical at 5x baseline


class PerformanceThresholds:
    """Performance thresholds for alerting.

    These are absolute thresholds used during development to identify
    operations that need optimization.
    """

    # Service method thresholds (ms)
    SERVICE_METHOD_WARNING = 100
    SERVICE_METHOD_CRITICAL = 500

    # Repository operation thresholds (ms)
    REPOSITORY_READ_WARNING = 50
    REPOSITORY_WRITE_WARNING = 100

    # API endpoint thresholds (ms)
    API_GET_WARNING = 200
    API_POST_WARNING = 300
    API_BULK_WARNING = 1000

    # WebSocket thresholds (ms)
    WEBSOCKET_MESSAGE_WARNING = 50
    WEBSOCKET_BROADCAST_WARNING = 100

    # Error rate thresholds (per minute)
    ERROR_RATE_WARNING = 10
    ERROR_RATE_CRITICAL = 50


def get_threshold_for_operation(operation_type: str, operation_name: str) -> float:
    """Get the appropriate threshold for a given operation.

    Args:
        operation_type: Type of operation (service, repository, api, websocket)
        operation_name: Name of the specific operation

    Returns:
        Threshold in milliseconds
    """
    thresholds = PerformanceThresholds()

    if operation_type == "repository":
        if "read" in operation_name.lower() or "get" in operation_name.lower():
            return thresholds.REPOSITORY_READ_WARNING
        return thresholds.REPOSITORY_WRITE_WARNING

    if operation_type == "api":
        if "GET" in operation_name:
            return thresholds.API_GET_WARNING
        if "POST" in operation_name:
            return thresholds.API_POST_WARNING
        if "bulk" in operation_name.lower():
            return thresholds.API_BULK_WARNING
        return thresholds.API_POST_WARNING

    if operation_type == "websocket":
        if "broadcast" in operation_name.lower():
            return thresholds.WEBSOCKET_BROADCAST_WARNING
        return thresholds.WEBSOCKET_MESSAGE_WARNING

    # Default to service thresholds
    return thresholds.SERVICE_METHOD_WARNING


def calculate_baseline_from_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    """Calculate performance baselines from collected metrics.

    Args:
        metrics: Dictionary of collected metrics with latency data

    Returns:
        Dictionary of calculated baselines
    """
    baselines = {}

    for operation, data in metrics.items():
        if data.get("latencies"):
            sorted_latencies = sorted(data["latencies"])
            count = len(sorted_latencies)

            baselines[operation] = {
                "p50": sorted_latencies[int(count * 0.50)],
                "p95": sorted_latencies[int(count * 0.95)],
                "p99": sorted_latencies[int(count * 0.99)],
                "avg": sum(sorted_latencies) / count,
                "min": sorted_latencies[0],
                "max": sorted_latencies[-1],
                "count": count,
            }

    return baselines
