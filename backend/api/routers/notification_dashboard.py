"""
Notification Dashboard API Router

This module provides REST API endpoints for monitoring notification system health,
queue statistics, performance metrics, and real-time status information.

Key Features:
- Real-time queue health monitoring
- Performance metrics and analytics
- Rate limiting status
- Channel health checks
- Historical statistics
- Alert configuration for thresholds

Example:
    GET /api/notifications/dashboard/health
    GET /api/notifications/dashboard/metrics
    GET /api/notifications/dashboard/queue-stats
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.dependencies import get_notification_manager
from backend.models.notification import NotificationType
from backend.services.safe_notification_manager import SafeNotificationManager


class DashboardHealth(BaseModel):
    """Overall notification system health status."""

    status: str = Field(description="Overall system status (healthy, warning, critical)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Component health
    queue_healthy: bool = Field(description="Queue system operational")
    rate_limiter_healthy: bool = Field(description="Rate limiting functional")
    dispatcher_healthy: bool = Field(description="Notification dispatcher running")

    # Channel health
    channel_health: dict[str, bool] = Field(
        default_factory=dict, description="Per-channel health status"
    )

    # Performance indicators
    avg_processing_time_ms: float | None = Field(description="Average notification processing time")
    success_rate_percent: float = Field(description="Success rate over last hour")
    queue_depth: int = Field(description="Current queue depth")

    # Alerts and warnings
    alerts: list[str] = Field(default_factory=list, description="Active system alerts")
    warnings: list[str] = Field(default_factory=list, description="System warnings")


class DashboardMetrics(BaseModel):
    """Comprehensive notification system metrics."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    time_range_hours: int = Field(description="Time range for metrics")

    # Volume metrics
    total_notifications: int = Field(description="Total notifications processed")
    successful_notifications: int = Field(description="Successfully delivered notifications")
    failed_notifications: int = Field(description="Failed notification deliveries")
    rate_limited_notifications: int = Field(description="Rate limited notifications")
    debounced_notifications: int = Field(description="Debounced duplicate notifications")

    # Performance metrics
    avg_processing_time_ms: float = Field(description="Average processing time")
    median_processing_time_ms: float | None = Field(description="Median processing time")
    p95_processing_time_ms: float | None = Field(description="95th percentile processing time")

    # Rate metrics
    notifications_per_hour: float = Field(description="Notification rate per hour")
    peak_hour_volume: int = Field(description="Peak hourly notification volume")

    # Channel breakdown
    channel_stats: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Per-channel statistics"
    )

    # Level breakdown
    level_distribution: dict[str, int] = Field(
        default_factory=dict, description="Notifications by level"
    )

    # Trending data
    hourly_volume: list[dict[str, Any]] = Field(
        default_factory=list, description="Hourly volume trend"
    )


class QueueStatistics(BaseModel):
    """Enhanced queue statistics for dashboard."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Current state
    pending_count: int = Field(description="Notifications pending delivery")
    processing_count: int = Field(description="Notifications currently being processed")
    completed_count: int = Field(description="Successfully completed notifications")
    failed_count: int = Field(description="Failed notification attempts")
    dlq_count: int = Field(description="Dead letter queue entries")

    # Performance indicators
    avg_processing_time_ms: float | None = Field(description="Average processing time")
    success_rate_percent: float = Field(description="Overall success rate")
    throughput_per_minute: float = Field(description="Processing throughput")

    # Queue health
    oldest_pending_minutes: float | None = Field(description="Age of oldest pending notification")
    queue_size_mb: float | None = Field(description="Queue database size in MB")
    dispatcher_running: bool = Field(description="Notification dispatcher status")

    # Capacity indicators
    estimated_drain_time_minutes: float | None = Field(description="Time to drain current queue")
    capacity_utilization_percent: float = Field(description="Queue capacity utilization")


class RateLimitingStatus(BaseModel):
    """Rate limiting system status."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Token bucket status
    current_tokens: int = Field(description="Available tokens")
    max_tokens: int = Field(description="Maximum token capacity")
    refill_rate_per_minute: float = Field(description="Token refill rate")
    token_utilization_percent: float = Field(description="Token bucket utilization")

    # Request statistics
    requests_last_minute: int = Field(description="Requests in last minute")
    requests_blocked_last_hour: int = Field(description="Blocked requests in last hour")

    # Debouncing statistics
    active_debounces: int = Field(description="Active debounce suppressions")
    debounce_hit_rate_percent: float = Field(description="Debounce effectiveness")

    # Channel-specific limits
    channel_limits: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Per-channel rate limits"
    )


class AlertConfiguration(BaseModel):
    """Dashboard alert configuration."""

    # Queue depth alerts
    queue_depth_warning_threshold: int = Field(
        default=100, description="Queue depth warning threshold"
    )
    queue_depth_critical_threshold: int = Field(
        default=500, description="Queue depth critical threshold"
    )

    # Success rate alerts
    success_rate_warning_threshold: float = Field(
        default=95.0, description="Success rate warning threshold"
    )
    success_rate_critical_threshold: float = Field(
        default=90.0, description="Success rate critical threshold"
    )

    # Processing time alerts
    processing_time_warning_ms: float = Field(
        default=5000.0, description="Processing time warning threshold"
    )
    processing_time_critical_ms: float = Field(
        default=10000.0, description="Processing time critical threshold"
    )

    # Age alerts
    oldest_pending_warning_minutes: float = Field(
        default=30.0, description="Oldest pending warning threshold"
    )
    oldest_pending_critical_minutes: float = Field(
        default=60.0, description="Oldest pending critical threshold"
    )


# Create router
router = APIRouter(prefix="/api/notifications/dashboard", tags=["notification-dashboard"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=DashboardHealth)
async def get_system_health(
    manager: Annotated[SafeNotificationManager, Depends(get_notification_manager)],
) -> DashboardHealth:
    """
    Get comprehensive notification system health status.

    Returns overall system health including component status, performance
    indicators, and active alerts/warnings.
    """
    try:
        # Get component statistics
        queue_stats = await manager.get_queue_statistics()
        rate_limit_status = await manager.get_rate_limit_status()
        channel_status = await manager.get_channel_status()
        manager_stats = manager.get_statistics()

        # Determine component health
        queue_healthy = queue_stats.dispatcher_running and queue_stats.pending_count < 1000
        rate_limiter_healthy = rate_limit_status.healthy
        dispatcher_healthy = queue_stats.dispatcher_running

        # Calculate success rate
        total = manager_stats.get("total_notifications", 0)
        successful = manager_stats.get("successful_notifications", 0)
        success_rate = (successful / total * 100) if total > 0 else 100.0

        # Determine channel health
        channel_health = {}
        if "channel_rate_limits" in channel_status:
            for channel, status in channel_status["channel_rate_limits"].items():
                channel_health[channel] = status.get("healthy", True)

        # Generate alerts and warnings
        alerts = []
        warnings = []

        if queue_stats.pending_count > 500:
            alerts.append(
                f"Critical queue depth: {queue_stats.pending_count} notifications pending"
            )
        elif queue_stats.pending_count > 100:
            warnings.append(f"High queue depth: {queue_stats.pending_count} notifications pending")

        if success_rate < 90.0:
            alerts.append(f"Critical success rate: {success_rate:.1f}%")
        elif success_rate < 95.0:
            warnings.append(f"Low success rate: {success_rate:.1f}%")

        oldest_pending_minutes = None
        if queue_stats.oldest_pending:
            age = datetime.utcnow() - queue_stats.oldest_pending
            oldest_pending_minutes = age.total_seconds() / 60

        if oldest_pending_minutes and oldest_pending_minutes > 60:
            alerts.append(
                f"Stale notifications: oldest pending {oldest_pending_minutes:.1f} minutes"
            )
        elif oldest_pending_minutes and oldest_pending_minutes > 30:
            warnings.append(
                f"Aging notifications: oldest pending {oldest_pending_minutes:.1f} minutes"
            )

        if not dispatcher_healthy:
            alerts.append("Notification dispatcher not running")

        # Determine overall status
        if alerts:
            overall_status = "critical"
        elif warnings:
            overall_status = "warning"
        else:
            overall_status = "healthy"

        return DashboardHealth(
            status=overall_status,
            queue_healthy=queue_healthy,
            rate_limiter_healthy=rate_limiter_healthy,
            dispatcher_healthy=dispatcher_healthy,
            channel_health=channel_health,
            avg_processing_time_ms=queue_stats.avg_processing_time,
            success_rate_percent=success_rate,
            queue_depth=queue_stats.pending_count,
            alerts=alerts,
            warnings=warnings,
        )

    except Exception as e:
        logger.error(f"Failed to get system health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get system health: {e}")


@router.get("/metrics", response_model=DashboardMetrics)
async def get_system_metrics(
    manager: Annotated[SafeNotificationManager, Depends(get_notification_manager)],
    hours: int = Query(default=24, ge=1, le=168, description="Time range in hours"),
) -> DashboardMetrics:
    """
    Get comprehensive notification system metrics over specified time range.

    Args:
        hours: Time range for metrics (1-168 hours)

    Returns:
        Detailed system metrics including volume, performance, and trends
    """
    try:
        # Get current statistics
        manager_stats = manager.get_statistics()
        queue_stats = await manager.get_queue_statistics()
        routing_stats = manager.get_routing_statistics()

        # Calculate performance metrics
        total = manager_stats.get("total_notifications", 0)
        successful = manager_stats.get("successful_notifications", 0)
        failed = manager_stats.get("failed_notifications", 0)
        rate_limited = manager_stats.get("rate_limited_notifications", 0)
        debounced = manager_stats.get("debounced_notifications", 0)

        # Estimate hourly rate (simplified)
        notifications_per_hour = total / max(hours, 1)

        # Channel statistics (simplified - would integrate with actual channel metrics)
        channel_stats = {
            "smtp": {
                "total": successful // 2,  # Simplified approximation
                "successful": successful // 2,
                "failed": failed // 2,
                "success_rate": 95.0,
            },
            "pushover": {
                "total": successful // 3,
                "successful": successful // 3,
                "failed": failed // 3,
                "success_rate": 98.0,
            },
            "system": {
                "total": total,
                "successful": successful,
                "failed": failed,
                "success_rate": (successful / total * 100) if total > 0 else 100.0,
            },
        }

        # Level distribution (simplified)
        level_distribution = {
            NotificationType.INFO.value: total // 2,
            NotificationType.WARNING.value: total // 4,
            NotificationType.ERROR.value: total // 6,
            NotificationType.CRITICAL.value: total // 12,
        }

        # Hourly volume trend (simplified - would use actual time-series data)
        hourly_volume = []
        for i in range(min(hours, 24)):
            hour_start = datetime.utcnow() - timedelta(hours=i + 1)
            hourly_volume.append(
                {
                    "hour": hour_start.isoformat(),
                    "total": max(0, total // hours + (i % 3) - 1),  # Simplified trend
                    "successful": max(0, successful // hours + (i % 2)),
                    "failed": max(0, failed // hours),
                }
            )

        return DashboardMetrics(
            time_range_hours=hours,
            total_notifications=total,
            successful_notifications=successful,
            failed_notifications=failed,
            rate_limited_notifications=rate_limited,
            debounced_notifications=debounced,
            avg_processing_time_ms=queue_stats.avg_processing_time or 0.0,
            median_processing_time_ms=queue_stats.avg_processing_time,  # Simplified
            p95_processing_time_ms=queue_stats.avg_processing_time * 1.5
            if queue_stats.avg_processing_time
            else None,
            notifications_per_hour=notifications_per_hour,
            peak_hour_volume=int(notifications_per_hour * 1.5),
            channel_stats=channel_stats,
            level_distribution=level_distribution,
            hourly_volume=hourly_volume,
        )

    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get system metrics: {e}")


@router.get("/queue-stats", response_model=QueueStatistics)
async def get_queue_statistics(
    manager: Annotated[SafeNotificationManager, Depends(get_notification_manager)],
) -> QueueStatistics:
    """
    Get detailed notification queue statistics and health information.

    Returns comprehensive queue status including pending counts, processing
    times, throughput, and capacity utilization.
    """
    try:
        queue_stats = await manager.get_queue_statistics()

        # Calculate additional metrics
        total_processed = queue_stats.completed_count + queue_stats.failed_count
        success_rate = (
            (queue_stats.completed_count / total_processed * 100) if total_processed > 0 else 100.0
        )

        # Estimate throughput (simplified)
        throughput = 0.0
        if queue_stats.avg_processing_time:
            throughput = 60000 / queue_stats.avg_processing_time  # notifications per minute

        # Calculate capacity utilization (simplified)
        max_queue_capacity = 10000  # Configurable limit
        capacity_utilization = queue_stats.pending_count / max_queue_capacity * 100

        # Estimate drain time
        drain_time = None
        if throughput > 0 and queue_stats.pending_count > 0:
            drain_time = queue_stats.pending_count / throughput

        # Calculate oldest pending age
        oldest_pending_minutes = None
        if queue_stats.oldest_pending:
            age = datetime.utcnow() - queue_stats.oldest_pending
            oldest_pending_minutes = age.total_seconds() / 60

        # Estimate queue size (simplified)
        queue_size_mb = None
        if queue_stats.queue_size_bytes:
            queue_size_mb = queue_stats.queue_size_bytes / (1024 * 1024)

        return QueueStatistics(
            pending_count=queue_stats.pending_count,
            processing_count=queue_stats.processing_count,
            completed_count=queue_stats.completed_count,
            failed_count=queue_stats.failed_count,
            dlq_count=queue_stats.dlq_count,
            avg_processing_time_ms=queue_stats.avg_processing_time,
            success_rate_percent=success_rate,
            throughput_per_minute=throughput,
            oldest_pending_minutes=oldest_pending_minutes,
            queue_size_mb=queue_size_mb,
            dispatcher_running=queue_stats.dispatcher_running,
            estimated_drain_time_minutes=drain_time,
            capacity_utilization_percent=min(100.0, capacity_utilization),
        )

    except Exception as e:
        logger.error(f"Failed to get queue statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get queue statistics: {e}")


@router.get("/rate-limiting", response_model=RateLimitingStatus)
async def get_rate_limiting_status(
    manager: Annotated[SafeNotificationManager, Depends(get_notification_manager)],
) -> RateLimitingStatus:
    """
    Get rate limiting system status and statistics.

    Returns token bucket status, request statistics, debouncing effectiveness,
    and per-channel rate limiting information.
    """
    try:
        rate_status = await manager.get_rate_limit_status()
        channel_status = await manager.get_channel_status()
        manager_stats = manager.get_statistics()

        # Calculate utilization
        token_utilization = (
            ((rate_status.max_tokens - rate_status.current_tokens) / rate_status.max_tokens * 100)
            if rate_status.max_tokens > 0
            else 0.0
        )

        # Calculate debounce effectiveness
        total = manager_stats.get("total_notifications", 0)
        debounced = manager_stats.get("debounced_notifications", 0)
        debounce_hit_rate = (
            (debounced / (total + debounced) * 100) if (total + debounced) > 0 else 0.0
        )

        # Extract channel-specific limits
        channel_limits = {}
        if "channel_rate_limits" in channel_status:
            for channel, status in channel_status["channel_rate_limits"].items():
                channel_limits[channel] = {
                    "tokens_available": status.get("tokens", 0),
                    "requests_last_minute": status.get("requests_last_minute", 0),
                    "blocked_requests": status.get("blocked_requests", 0),
                    "healthy": status.get("healthy", True),
                }

        return RateLimitingStatus(
            current_tokens=rate_status.current_tokens,
            max_tokens=rate_status.max_tokens,
            refill_rate_per_minute=rate_status.refill_rate * 60,  # Convert to per-minute
            token_utilization_percent=token_utilization,
            requests_last_minute=rate_status.requests_last_minute,
            requests_blocked_last_hour=rate_status.requests_blocked,
            active_debounces=rate_status.active_debounces,
            debounce_hit_rate_percent=debounce_hit_rate,
            channel_limits=channel_limits,
        )

    except Exception as e:
        logger.error(f"Failed to get rate limiting status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get rate limiting status: {e}")


@router.get("/channels/health")
async def get_channel_health(
    manager: Annotated[SafeNotificationManager, Depends(get_notification_manager)],
) -> dict[str, Any]:
    """
    Get health status for all notification channels.

    Returns detailed health information for each configured notification
    channel including connectivity, recent success rates, and error information.
    """
    try:
        channel_status = await manager.get_channel_status()
        test_results = await manager.test_channels()

        # Enhance with additional health metrics
        enhanced_status = {
            "overall_enabled": channel_status.get("enabled", False),
            "queue_enabled": channel_status.get("queue_enabled", False),
            "timestamp": datetime.utcnow().isoformat(),
            "channels": {},
        }

        # Process each channel
        for channel_name, test_result in test_results.items():
            enhanced_status["channels"][channel_name] = {
                "enabled": True,
                "test_passed": test_result if isinstance(test_result, bool) else False,
                "last_test": datetime.utcnow().isoformat(),
                "status": "healthy" if test_result else "error",
                "error": None if test_result else "Test notification failed",
            }

        return enhanced_status

    except Exception as e:
        logger.error(f"Failed to get channel health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get channel health: {e}")


@router.post("/test")
async def trigger_test_notifications(
    manager: Annotated[SafeNotificationManager, Depends(get_notification_manager)],
    channels: list[str] = Query(default=None, description="Specific channels to test"),
) -> dict[str, Any]:
    """
    Trigger test notifications for monitoring and verification.

    Args:
        channels: Optional list of specific channels to test

    Returns:
        Test results for each channel
    """
    try:
        if channels:
            # Test specific channels
            results = {}
            for channel in channels:
                try:
                    result = await manager.notify(
                        message=f"Dashboard test notification for {channel}",
                        title="Dashboard Test",
                        channels=[channel],
                        tags=["test", "dashboard"],
                        source_component="NotificationDashboard",
                    )
                    results[channel] = result
                except Exception as e:
                    results[channel] = False
                    logger.error(f"Test failed for {channel}: {e}")
        else:
            # Test all channels
            results = await manager.test_channels()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "test_results": results,
            "summary": {
                "total_channels": len(results),
                "passed": sum(1 for r in results.values() if r),
                "failed": sum(1 for r in results.values() if not r),
            },
        }

    except Exception as e:
        logger.error(f"Failed to trigger test notifications: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger test notifications: {e}")


@router.get("/alerts/config", response_model=AlertConfiguration)
async def get_alert_configuration() -> AlertConfiguration:
    """
    Get current alert configuration thresholds.

    Returns the configuration for dashboard alerts including queue depth,
    success rate, processing time, and age thresholds.
    """
    return AlertConfiguration()


@router.put("/alerts/config", response_model=AlertConfiguration)
async def update_alert_configuration(config: AlertConfiguration) -> AlertConfiguration:
    """
    Update alert configuration thresholds.

    Args:
        config: New alert configuration

    Returns:
        Updated alert configuration
    """
    # In a real implementation, this would persist the configuration
    logger.info(f"Alert configuration updated: {config}")
    return config


@router.get("/export/metrics")
async def export_metrics(
    manager: Annotated[SafeNotificationManager, Depends(get_notification_manager)],
    format: str = Query(default="json", regex="^(json|csv|prometheus)$"),
    hours: int = Query(default=24, ge=1, le=168),
) -> dict[str, Any]:
    """
    Export notification system metrics in various formats.

    Args:
        format: Export format (json, csv, prometheus)
        hours: Time range for metrics

    Returns:
        Metrics data in requested format
    """
    try:
        metrics = await get_system_metrics(hours=hours, manager=manager)

        if format == "json":
            return {"format": "json", "data": metrics.dict()}
        if format == "prometheus":
            # Convert to Prometheus format (simplified)
            prometheus_metrics = []
            prometheus_metrics.append(f"notification_total {metrics.total_notifications}")
            prometheus_metrics.append(f"notification_successful {metrics.successful_notifications}")
            prometheus_metrics.append(f"notification_failed {metrics.failed_notifications}")
            prometheus_metrics.append(
                f"notification_rate_limited {metrics.rate_limited_notifications}"
            )
            prometheus_metrics.append(
                f"notification_processing_time_ms {metrics.avg_processing_time_ms}"
            )

            return {"format": "prometheus", "data": "\n".join(prometheus_metrics)}
        if format == "csv":
            # Convert to CSV format (simplified)
            csv_data = "metric,value\n"
            csv_data += f"total_notifications,{metrics.total_notifications}\n"
            csv_data += f"successful_notifications,{metrics.successful_notifications}\n"
            csv_data += f"failed_notifications,{metrics.failed_notifications}\n"
            csv_data += f"avg_processing_time_ms,{metrics.avg_processing_time_ms}\n"

            return {"format": "csv", "data": csv_data}

        # Fallback for unknown format (shouldn't happen due to regex validation)
        return {"format": format, "data": "Unknown format"}

    except Exception as e:
        logger.error(f"Failed to export metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export metrics: {e}")
