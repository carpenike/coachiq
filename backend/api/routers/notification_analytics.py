"""
Notification Analytics API Router

This module provides API endpoints for notification analytics, metrics,
and reporting functionality.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.core.dependencies_v2 import (
    get_analytics_service,
    get_reporting_service,
)
from backend.middleware.auth import require_authentication
from backend.models.notification import NotificationChannel, NotificationType
from backend.models.notification_analytics import (
    AggregationPeriod,
    MetricType,
    NotificationMetric,
)
from backend.services.notification_analytics_service import NotificationAnalyticsService
from backend.services.notification_reporting_service import NotificationReportingService

# Request/Response Models

class MetricsRequest(BaseModel):
    """Request model for metrics queries."""

    metric_type: MetricType = Field(..., description="Type of metric to retrieve")
    aggregation_period: AggregationPeriod = Field(
        AggregationPeriod.HOURLY,
        description="Aggregation period"
    )
    start_date: datetime = Field(..., description="Start of period")
    end_date: datetime | None = Field(None, description="End of period")
    channel: NotificationChannel | None = Field(None, description="Filter by channel")
    notification_type: NotificationType | None = Field(None, description="Filter by type")


class ChannelMetricsResponse(BaseModel):
    """Response model for channel metrics."""

    channels: list[dict[str, Any]] = Field(..., description="Channel metrics")
    period: dict[str, str] = Field(..., description="Period information")
    total_sent: int = Field(..., description="Total notifications sent")
    overall_success_rate: float = Field(..., description="Overall success rate")


class ErrorAnalysisResponse(BaseModel):
    """Response model for error analysis."""

    errors: list[dict[str, Any]] = Field(..., description="Error analysis results")
    total_errors: int = Field(..., description="Total errors in period")
    recommendations: list[str] = Field(..., description="General recommendations")


class QueueHealthResponse(BaseModel):
    """Response model for queue health."""

    health_score: float = Field(..., description="Overall health score (0-1)")
    queue_depth: int = Field(..., description="Current queue depth")
    processing_rate: float = Field(..., description="Messages per second")
    success_rate: float = Field(..., description="Recent success rate")
    status: str = Field(..., description="Health status")
    recommendations: list[str] = Field(..., description="Health recommendations")


class ReportRequest(BaseModel):
    """Request model for report generation."""

    template: str = Field(..., description="Report template name")
    start_date: datetime = Field(..., description="Report period start")
    end_date: datetime = Field(..., description="Report period end")
    format: str = Field("json", description="Output format (json, csv, pdf, html)")
    parameters: dict[str, Any] | None = Field(None, description="Additional parameters")


class ReportScheduleRequest(BaseModel):
    """Request model for report scheduling."""

    schedule_id: str = Field(..., description="Unique schedule ID")
    template: str = Field(..., description="Report template name")
    schedule: dict[str, Any] = Field(..., description="Schedule configuration")
    format: str = Field("json", description="Output format")
    parameters: dict[str, Any] | None = Field(None, description="Additional parameters")
    recipients: list[str] | None = Field(None, description="Email recipients")


class DashboardMetrics(BaseModel):
    """Response model for dashboard metrics."""

    summary: dict[str, Any] = Field(..., description="Summary metrics")
    channels: list[dict[str, Any]] = Field(..., description="Channel breakdown")
    recent_activity: list[dict[str, Any]] = Field(..., description="Recent activity")
    queue_health: dict[str, Any] = Field(..., description="Queue health status")
    trending: dict[str, Any] = Field(..., description="Trending metrics")


# Create router
router = APIRouter(
    prefix="/api/notification-analytics",
    tags=["notification-analytics"],
    dependencies=[Depends(require_authentication)],
)


@router.get("/metrics", response_model=list[NotificationMetric])
async def get_metrics(
    metric_type: MetricType = Query(..., description="Type of metric"),
    aggregation_period: AggregationPeriod = Query(
        AggregationPeriod.HOURLY,
        description="Aggregation period"
    ),
    start_date: datetime = Query(..., description="Start date"),
    end_date: datetime | None = Query(None, description="End date"),
    channel: NotificationChannel | None = Query(None, description="Filter by channel"),
    notification_type: NotificationType | None = Query(None, description="Filter by type"),
    analytics_service: NotificationAnalyticsService = Depends(get_analytics_service),
) -> list[NotificationMetric]:
    """
    Get aggregated notification metrics.

    Returns time-series data for the specified metric type and period.
    """
    if end_date is None:
        end_date = datetime.now(UTC)

    return await analytics_service.get_aggregated_metrics(
        metric_type=metric_type,
        aggregation_period=aggregation_period,
        start_date=start_date,
        end_date=end_date,
        channel=channel,
        notification_type=notification_type,
    )


@router.get("/channels", response_model=ChannelMetricsResponse)
async def get_channel_metrics(
    start_date: datetime | None = Query(None, description="Start date"),
    end_date: datetime | None = Query(None, description="End date"),
    channel: NotificationChannel | None = Query(None, description="Specific channel"),
    analytics_service: NotificationAnalyticsService = Depends(get_analytics_service),
) -> ChannelMetricsResponse:
    """
    Get performance metrics for notification channels.

    Returns detailed metrics for each channel including success rates,
    delivery times, and error breakdowns.
    """
    if end_date is None:
        end_date = datetime.now(UTC)
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    metrics = await analytics_service.get_channel_metrics(
        channel=channel,
        start_date=start_date,
        end_date=end_date,
    )

    # Calculate summary
    total_sent = sum(m.total_sent for m in metrics)
    total_delivered = sum(m.total_delivered for m in metrics)
    overall_success_rate = total_delivered / max(total_sent, 1)

    return ChannelMetricsResponse(
        channels=[
            {
                "channel": m.channel.value,
                "total_sent": m.total_sent,
                "total_delivered": m.total_delivered,
                "total_failed": m.total_failed,
                "success_rate": m.success_rate,
                "average_delivery_time": m.average_delivery_time,
                "last_success": m.last_success.isoformat() if m.last_success else None,
                "last_failure": m.last_failure.isoformat() if m.last_failure else None,
                "error_breakdown": m.error_breakdown,
            }
            for m in metrics
        ],
        period={
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        total_sent=total_sent,
        overall_success_rate=overall_success_rate,
    )


@router.get("/errors", response_model=ErrorAnalysisResponse)
async def analyze_errors(
    start_date: datetime | None = Query(None, description="Start date"),
    end_date: datetime | None = Query(None, description="End date"),
    min_occurrences: int = Query(5, description="Minimum occurrences"),
    analytics_service: NotificationAnalyticsService = Depends(get_analytics_service),
) -> ErrorAnalysisResponse:
    """
    Analyze notification delivery errors.

    Returns error patterns, frequencies, and recommendations for
    improving delivery success rates.
    """
    if end_date is None:
        end_date = datetime.now(UTC)
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    errors = await analytics_service.analyze_errors(
        start_date=start_date,
        end_date=end_date,
        min_occurrences=min_occurrences,
    )

    # Generate recommendations
    recommendations = []

    # Check for persistent errors
    persistent_errors = [e for e in errors if not e.is_resolved]
    if persistent_errors:
        recommendations.append(
            f"Address {len(persistent_errors)} persistent error patterns that are still occurring"
        )

    # Check for low retry success rates
    low_retry_success = [e for e in errors if e.retry_success_rate < 0.2]
    if low_retry_success:
        recommendations.append(
            f"Investigate {len(low_retry_success)} error types with low retry success rates"
        )

    # Channel-specific issues
    channel_errors = {}
    for error in errors:
        if error.channel not in channel_errors:
            channel_errors[error.channel] = 0
        channel_errors[error.channel] += error.occurrence_count

    for channel, count in channel_errors.items():
        if count > 100:
            recommendations.append(f"Review {channel} channel configuration - {count} errors")

    return ErrorAnalysisResponse(
        errors=[
            {
                "error_code": e.error_code,
                "error_message": e.error_message,
                "channel": e.channel,
                "occurrences": e.occurrence_count,
                "first_seen": e.first_seen.isoformat(),
                "last_seen": e.last_seen.isoformat(),
                "affected_recipients": e.affected_recipients,
                "retry_success_rate": e.retry_success_rate,
                "recommendation": e.recommended_action,
                "is_resolved": e.is_resolved,
            }
            for e in errors
        ],
        total_errors=sum(e.occurrence_count for e in errors),
        recommendations=recommendations,
    )


@router.get("/queue/health", response_model=QueueHealthResponse)
async def get_queue_health(
    analytics_service: NotificationAnalyticsService = Depends(get_analytics_service),
) -> QueueHealthResponse:
    """
    Get current notification queue health status.

    Returns real-time metrics about queue performance and health indicators.
    """
    health = await analytics_service.get_queue_health()

    # Determine status
    if health.health_score >= 0.9:
        status = "healthy"
    elif health.health_score >= 0.7:
        status = "degraded"
    elif health.health_score >= 0.5:
        status = "warning"
    else:
        status = "critical"

    # Generate recommendations
    recommendations = []

    if health.queue_depth > 1000:
        recommendations.append("High queue depth - consider scaling workers")

    if health.processing_rate < 1.0:
        recommendations.append("Low processing rate - check worker performance")

    if health.success_rate < 0.8:
        recommendations.append("Low success rate - investigate delivery failures")

    if health.average_wait_time > 300:
        recommendations.append("High queue wait times - increase processing capacity")

    if health.dlq_size > 100:
        recommendations.append("Large dead letter queue - review failed notifications")

    return QueueHealthResponse(
        health_score=health.health_score,
        queue_depth=health.queue_depth,
        processing_rate=health.processing_rate,
        success_rate=health.success_rate,
        status=status,
        recommendations=recommendations,
    )


@router.post("/reports/generate", response_model=dict)
async def generate_report(
    request: ReportRequest,
    current_user: Any = Depends(require_authentication),
    reporting_service: NotificationReportingService = Depends(get_reporting_service),
) -> dict:
    """
    Generate a notification analytics report.

    Creates a report using the specified template and returns the report ID
    for downloading.
    """
    try:
        report = await reporting_service.generate_report(
            template_name=request.template,
            start_date=request.start_date,
            end_date=request.end_date,
            format=request.format,
            parameters=request.parameters,
            generated_by=current_user.email if hasattr(current_user, "email") else None,
        )

        return {
            "report_id": report.report_id,
            "status": "completed",
            "download_url": f"/api/notification-analytics/reports/{report.report_id}/download",
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e!s}")


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str,
    reporting_service: NotificationReportingService = Depends(get_reporting_service),
) -> dict:
    """
    Get report metadata by ID.

    Returns information about a generated report including its status
    and download URL.
    """
    report = await reporting_service.get_report(report_id)

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "report_id": report.report_id,
        "report_type": report.report_type,
        "report_name": report.report_name,
        "start_date": report.start_date.isoformat(),
        "end_date": report.end_date.isoformat(),
        "generated_at": report.created_at.isoformat(),
        "generated_by": report.generated_by,
        "format": report.format,
        "file_size": report.file_size_bytes,
        "download_url": f"/api/notification-analytics/reports/{report.report_id}/download",
    }


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: str,
    reporting_service: NotificationReportingService = Depends(get_reporting_service),
) -> FileResponse:
    """
    Download a generated report.

    Returns the report file in the format it was generated.
    """
    result = await reporting_service.get_report_file(report_id)

    if not result:
        raise HTTPException(status_code=404, detail="Report file not found")

    file_path, format = result

    # Set appropriate content type
    content_types = {
        "json": "application/json",
        "csv": "text/csv",
        "pdf": "application/pdf",
        "html": "text/html",
    }

    return FileResponse(
        path=file_path,
        media_type=content_types.get(format, "application/octet-stream"),
        filename=file_path.name,
    )


@router.get("/reports")
async def list_reports(
    report_type: str | None = Query(None, description="Filter by report type"),
    start_date: datetime | None = Query(None, description="Filter by generation date start"),
    end_date: datetime | None = Query(None, description="Filter by generation date end"),
    limit: int = Query(100, description="Maximum results", le=1000),
    reporting_service: NotificationReportingService = Depends(get_reporting_service),
    current_user: Any = Depends(require_authentication),
) -> dict:
    """
    List generated reports.

    Returns a list of reports with optional filtering.
    """
    reports = await reporting_service.list_reports(
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        generated_by=current_user.email if hasattr(current_user, "email") else None,
        limit=limit,
    )

    return {
        "reports": [
            {
                "report_id": r.report_id,
                "report_type": r.report_type,
                "report_name": r.report_name,
                "generated_at": r.created_at.isoformat(),
                "format": r.format,
                "file_size": r.file_size_bytes,
            }
            for r in reports
        ],
        "total": len(reports),
    }


@router.post("/reports/schedule")
async def schedule_report(
    request: ReportScheduleRequest,
    reporting_service: NotificationReportingService = Depends(get_reporting_service),
    current_user: Any = Depends(require_authentication),
) -> dict:
    """
    Schedule a recurring report.

    Creates a scheduled report that will be generated automatically
    based on the specified schedule.
    """
    try:
        await reporting_service.schedule_report(
            schedule_id=request.schedule_id,
            template_name=request.template,
            schedule=request.schedule,
            format=request.format,
            parameters=request.parameters,
            recipients=request.recipients,
        )

        return {
            "schedule_id": request.schedule_id,
            "status": "scheduled",
            "next_run": reporting_service._calculate_next_run(request.schedule).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to schedule report: {e!s}")


@router.delete("/reports/schedule/{schedule_id}")
async def unschedule_report(
    schedule_id: str,
    reporting_service: NotificationReportingService = Depends(get_reporting_service),
) -> dict:
    """
    Remove a scheduled report.

    Cancels a scheduled report by ID.
    """
    await reporting_service.unschedule_report(schedule_id)

    return {
        "schedule_id": schedule_id,
        "status": "unscheduled",
    }


@router.get("/dashboard", response_model=DashboardMetrics)
async def get_dashboard_metrics(
    analytics_service: NotificationAnalyticsService = Depends(get_analytics_service),
) -> DashboardMetrics:
    """
    Get dashboard metrics for real-time monitoring.

    Returns a comprehensive set of metrics suitable for dashboard display.
    """
    now = datetime.now(UTC)

    # Get last 24 hours metrics
    day_ago = now - timedelta(days=1)
    channel_metrics = await analytics_service.get_channel_metrics(
        start_date=day_ago,
        end_date=now,
    )

    # Get hourly metrics for last 12 hours
    twelve_hours_ago = now - timedelta(hours=12)
    hourly_metrics = await analytics_service.get_aggregated_metrics(
        MetricType.DELIVERY_COUNT,
        AggregationPeriod.HOURLY,
        twelve_hours_ago,
        now,
    )

    # Get queue health
    queue_health = await analytics_service.get_queue_health()

    # Calculate trending
    # Compare last hour to previous hour
    last_hour = now - timedelta(hours=1)
    prev_hour = now - timedelta(hours=2)

    last_hour_metrics = await analytics_service.get_channel_metrics(
        start_date=last_hour,
        end_date=now,
    )

    prev_hour_metrics = await analytics_service.get_channel_metrics(
        start_date=prev_hour,
        end_date=last_hour,
    )

    last_hour_total = sum(m.total_sent for m in last_hour_metrics)
    prev_hour_total = sum(m.total_sent for m in prev_hour_metrics)

    volume_trend = ((last_hour_total - prev_hour_total) / max(prev_hour_total, 1)) * 100

    return DashboardMetrics(
        summary={
            "total_24h": sum(m.total_sent for m in channel_metrics),
            "delivered_24h": sum(m.total_delivered for m in channel_metrics),
            "failed_24h": sum(m.total_failed for m in channel_metrics),
            "success_rate_24h": sum(m.total_delivered for m in channel_metrics) /
                               max(sum(m.total_sent for m in channel_metrics), 1),
            "active_channels": len([m for m in channel_metrics if m.total_sent > 0]),
        },
        channels=[
            {
                "channel": m.channel.value,
                "sent": m.total_sent,
                "success_rate": m.success_rate,
                "status": "healthy" if m.success_rate >= 0.9 else "degraded",
            }
            for m in channel_metrics
        ],
        recent_activity=[
            {
                "timestamp": m.timestamp.isoformat(),
                "count": int(m.value),
            }
            for m in hourly_metrics
        ],
        queue_health={
            "score": queue_health.health_score,
            "depth": queue_health.queue_depth,
            "processing_rate": queue_health.processing_rate,
            "status": "healthy" if queue_health.health_score >= 0.9 else "degraded",
        },
        trending={
            "volume_trend_percent": volume_trend,
            "last_hour_count": last_hour_total,
            "trend_direction": "up" if volume_trend > 0 else "down" if volume_trend < 0 else "stable",
        },
    )


@router.post("/engagement/{notification_id}")
async def track_engagement(
    notification_id: str,
    action: str = Query(..., description="Action type: opened, clicked, dismissed"),
    analytics_service: NotificationAnalyticsService = Depends(get_analytics_service),
) -> dict:
    """
    Track user engagement with a notification.

    Records when a notification is opened, clicked, or dismissed.
    """
    if action not in ["opened", "clicked", "dismissed"]:
        raise HTTPException(status_code=400, detail="Invalid action type")

    await analytics_service.track_engagement(
        notification_id=notification_id,
        action=action,
    )

    return {
        "notification_id": notification_id,
        "action": action,
        "tracked": True,
    }
