"""
Advanced Analytics Dashboard API Router

FastAPI router providing comprehensive analytics dashboard endpoints including
performance trends, system insights, historical analysis, and metrics aggregation.
"""

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.core.dependencies import get_feature_manager_from_request
from backend.services.analytics_dashboard_service import AnalyticsDashboardService

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter(prefix="/api/analytics", tags=["analytics_dashboard"])


# Request/Response Models


class CustomMetricRequest(BaseModel):
    """Request model for recording custom metrics."""

    metric_name: str = Field(..., description="Name of the metric")
    value: float = Field(..., description="Metric value")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")


class TrendsQueryParams(BaseModel):
    """Query parameters for performance trends."""

    time_window_hours: int = Field(default=24, ge=1, le=168, description="Time window in hours")
    metrics: list[str] | None = Field(default=None, description="Specific metrics to include")
    resolution: str = Field(
        default="1h", pattern=r"^(1m|5m|15m|1h|6h|1d)$", description="Data resolution"
    )


class InsightsQueryParams(BaseModel):
    """Query parameters for system insights."""

    categories: list[str] | None = Field(default=None, description="Insight categories")
    min_severity: str = Field(
        default="low",
        pattern=r"^(low|medium|high|critical)$",
        description="Minimum severity",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Maximum number of insights")


class HistoricalAnalysisParams(BaseModel):
    """Parameters for historical analysis."""

    analysis_type: str = Field(
        default="pattern_detection",
        pattern=r"^(pattern_detection|anomaly_detection|correlation|all)$",
    )
    time_window_hours: int = Field(default=168, ge=24, le=720, description="Time window in hours")
    include_predictions: bool = Field(default=True, description="Include predictive analysis")


class MetricsAggregationParams(BaseModel):
    """Parameters for metrics aggregation."""

    aggregation_windows: list[str] | None = Field(
        default=None, description="Time windows for aggregation"
    )
    metric_groups: list[str] | None = Field(default=None, description="Metric groups to include")


def _check_analytics_enabled(request: Request) -> None:
    """Check if analytics features are enabled, raise 404 if disabled."""
    feature_manager = get_feature_manager_from_request(request)
    if not feature_manager.is_enabled("performance_analytics"):
        raise HTTPException(status_code=404, detail="Analytics features are disabled")


def get_analytics_dashboard_service(request: Request) -> AnalyticsDashboardService:
    """Get the analytics dashboard service from app state."""
    if not hasattr(request.app.state, "analytics_dashboard_service"):
        raise HTTPException(status_code=500, detail="Analytics dashboard service not available")
    return request.app.state.analytics_dashboard_service


@router.get(
    "/trends",
    response_model=dict[str, Any],
    summary="Get performance trends",
    description="Retrieve performance trends and analysis for specified metrics and time window.",
    response_description="Performance trend data with analysis and insights",
)
async def get_performance_trends(
    request: Request,
    service: Annotated[AnalyticsDashboardService, Depends(get_analytics_dashboard_service)],
    time_window_hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    metrics: str | None = Query(None, description="Comma-separated list of metrics"),
    resolution: str = Query("1h", regex=r"^(1m|5m|15m|1h|6h|1d)$", description="Data resolution"),
) -> dict[str, Any]:
    """
    Get performance trends for specified metrics and time window.

    This endpoint provides comprehensive performance trend analysis including:
    - Time-series data for selected metrics
    - Trend direction and change percentages
    - Anomaly detection and alerts
    - Performance insights and recommendations

    Args:
        time_window_hours: Time window for trend analysis (1-168 hours)
        metrics: Comma-separated list of specific metrics (None for all)
        resolution: Data resolution (1m, 5m, 15m, 1h, 6h, 1d)

    Returns:
        Performance trend data with comprehensive analysis
    """
    logger.debug(
        f"GET /analytics/trends - time_window={time_window_hours}h, resolution={resolution}"
    )
    _check_analytics_enabled(request)

    try:
        # Parse metrics parameter
        metrics_list = None
        if metrics:
            metrics_list = [m.strip() for m in metrics.split(",") if m.strip()]

        trends = await service.get_performance_trends(
            time_window_hours=time_window_hours,
            metrics=metrics_list,
            resolution=resolution,
        )

        logger.info(f"Generated performance trends for {len(trends.get('metrics', {}))} metrics")
        return trends

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving performance trends: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/insights",
    response_model=dict[str, Any],
    summary="Get system insights",
    description="Retrieve intelligent system insights and recommendations based on analytics data.",
    response_description="System insights with actionable recommendations",
)
async def get_system_insights(
    request: Request,
    service: Annotated[AnalyticsDashboardService, Depends(get_analytics_dashboard_service)],
    categories: str | None = Query(None, description="Comma-separated list of categories"),
    min_severity: str = Query(
        "low",
        regex=r"^(low|medium|high|critical)$",
        description="Minimum severity level",
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of insights"),
) -> dict[str, Any]:
    """
    Get system insights and intelligent recommendations.

    This endpoint provides AI-powered insights including:
    - Performance optimization recommendations
    - System health alerts and warnings
    - Operational efficiency suggestions
    - Predictive maintenance recommendations

    Args:
        categories: Comma-separated categories (performance, reliability, efficiency, cost)
        min_severity: Minimum severity level (low, medium, high, critical)
        limit: Maximum number of insights to return

    Returns:
        System insights with actionable recommendations
    """
    logger.debug(f"GET /analytics/insights - categories={categories}, min_severity={min_severity}")
    _check_analytics_enabled(request)

    try:
        # Parse categories parameter
        categories_list = None
        if categories:
            categories_list = [c.strip() for c in categories.split(",") if c.strip()]

        insights = await service.get_system_insights(
            categories=categories_list, min_severity=min_severity, limit=limit
        )

        logger.info(f"Retrieved {insights.get('total_insights', 0)} system insights")
        return insights

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving system insights: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/historical",
    response_model=dict[str, Any],
    summary="Get historical analysis",
    description="Perform historical data analysis including pattern detection and anomaly analysis.",
    response_description="Historical analysis results with patterns and predictions",
)
async def get_historical_analysis(
    request: Request,
    service: Annotated[AnalyticsDashboardService, Depends(get_analytics_dashboard_service)],
    analysis_type: str = Query(
        "pattern_detection",
        regex=r"^(pattern_detection|anomaly_detection|correlation|all)$",
    ),
    time_window_hours: int = Query(168, ge=24, le=720, description="Time window in hours"),
    include_predictions: bool = Query(True, description="Include predictive analysis"),
) -> dict[str, Any]:
    """
    Get historical data analysis including pattern detection.

    This endpoint provides advanced historical analysis including:
    - Pattern detection and cyclical behavior analysis
    - Anomaly detection and outlier identification
    - Correlation analysis between metrics
    - Predictive analytics and forecasting

    Args:
        analysis_type: Type of analysis (pattern_detection, anomaly_detection, correlation, all)
        time_window_hours: Time window for analysis (24-720 hours)
        include_predictions: Whether to include predictive analysis

    Returns:
        Historical analysis results with patterns and predictions
    """
    logger.debug(
        f"GET /analytics/historical - analysis_type={analysis_type}, time_window={time_window_hours}h"
    )
    _check_analytics_enabled(request)

    try:
        analysis = await service.get_historical_analysis(
            analysis_type=analysis_type,
            time_window_hours=time_window_hours,
            include_predictions=include_predictions,
        )

        patterns_count = len(analysis.get("patterns", []))
        anomalies_count = len(analysis.get("anomalies", []))
        logger.info(
            f"Historical analysis completed: {patterns_count} patterns, {anomalies_count} anomalies"
        )
        return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in historical analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/aggregation",
    response_model=dict[str, Any],
    summary="Get metrics aggregation",
    description="Get comprehensive metrics aggregation and reporting across multiple time windows.",
    response_description="Aggregated metrics with KPIs and benchmarks",
)
async def get_metrics_aggregation(
    request: Request,
    service: Annotated[AnalyticsDashboardService, Depends(get_analytics_dashboard_service)],
    aggregation_windows: str | None = Query(
        None, description="Comma-separated aggregation windows"
    ),
    metric_groups: str | None = Query(None, description="Comma-separated metric groups"),
) -> dict[str, Any]:
    """
    Get comprehensive metrics aggregation and reporting.

    This endpoint provides enterprise-level metrics aggregation including:
    - Multi-window time aggregations (hourly, daily, weekly)
    - Key Performance Indicators (KPIs)
    - Performance benchmarks and comparisons
    - Optimization recommendations

    Args:
        aggregation_windows: Comma-separated windows (1h, 6h, 1d, 1w)
        metric_groups: Comma-separated groups (system_performance, protocol_efficiency, etc.)

    Returns:
        Comprehensive metrics aggregation with reporting data
    """
    logger.debug(
        f"GET /analytics/aggregation - windows={aggregation_windows}, groups={metric_groups}"
    )
    _check_analytics_enabled(request)

    try:
        # Parse parameters
        windows_list = None
        if aggregation_windows:
            windows_list = [w.strip() for w in aggregation_windows.split(",") if w.strip()]

        groups_list = None
        if metric_groups:
            groups_list = [g.strip() for g in metric_groups.split(",") if g.strip()]

        aggregation = await service.get_metrics_aggregation(
            aggregation_windows=windows_list, metric_groups=groups_list
        )

        windows_count = len(aggregation.get("windows", {}))
        kpis_count = len(aggregation.get("kpis", {}))
        logger.info(f"Metrics aggregation completed: {windows_count} windows, {kpis_count} KPIs")
        return aggregation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in metrics aggregation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/metrics",
    response_model=dict[str, bool],
    summary="Record custom metric",
    description="Record a custom metric for analytics tracking and analysis.",
    response_description="Success status of metric recording",
)
async def record_custom_metric(
    request: Request,
    metric_request: CustomMetricRequest,
    service: Annotated[AnalyticsDashboardService, Depends(get_analytics_dashboard_service)],
) -> dict[str, bool]:
    """
    Record a custom metric for analytics.

    This endpoint allows recording custom metrics that will be included in:
    - Performance trend analysis
    - Historical pattern detection
    - System insights generation
    - Metrics aggregation and reporting

    Args:
        metric_request: Custom metric data including name, value, and metadata

    Returns:
        Success status of metric recording
    """
    logger.debug(
        f"POST /analytics/metrics - metric={metric_request.metric_name}, value={metric_request.value}"
    )
    _check_analytics_enabled(request)

    try:
        success = await service.record_custom_metric(
            metric_name=metric_request.metric_name,
            value=metric_request.value,
            metadata=metric_request.metadata,
        )

        if success:
            logger.info(
                f"Recorded custom metric: {metric_request.metric_name}={metric_request.value}"
            )
        else:
            logger.warning(f"Failed to record custom metric: {metric_request.metric_name}")

        return {"success": success}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording custom metric: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/status",
    response_model=dict[str, Any],
    summary="Get analytics dashboard status",
    description="Get the current status and configuration of the analytics dashboard.",
    response_description="Analytics dashboard status and configuration",
)
async def get_analytics_status(
    request: Request,
    service: Annotated[AnalyticsDashboardService, Depends(get_analytics_dashboard_service)],
) -> dict[str, Any]:
    """
    Get analytics dashboard status and configuration.

    This endpoint provides information about:
    - Service status and health
    - Available metrics and data retention
    - Configuration parameters
    - Data quality metrics

    Returns:
        Analytics dashboard status and configuration
    """
    logger.debug("GET /analytics/status - Retrieving analytics dashboard status")
    _check_analytics_enabled(request)

    try:
        # Get storage statistics from the storage service
        storage_stats = await service.storage.get_storage_stats()

        # Get basic status information
        status = {
            "service_status": "operational",
            "feature_enabled": True,
            "data_retention_hours": service.analytics_settings.memory_retention_hours,
            "insight_generation_interval": service.insight_generation_interval,
            "pattern_analysis_interval": service.pattern_analysis_interval,
            "metrics_tracked": storage_stats.get("metric_types", 0),
            "insights_cached": storage_stats.get("insights_stored", 0),
            "patterns_detected": storage_stats.get("patterns_stored", 0),
            "background_tasks": {
                "insight_generation": service._insight_task is not None
                and not service._insight_task.done(),
                "pattern_analysis": service._pattern_task is not None
                and not service._pattern_task.done(),
            },
            "capabilities": [
                "performance_trends",
                "system_insights",
                "historical_analysis",
                "metrics_aggregation",
                "custom_metrics",
                "pattern_detection",
                "anomaly_detection",
            ],
        }

        logger.info("Retrieved analytics dashboard status")
        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving analytics status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/health",
    response_model=dict[str, Any],
    summary="Analytics health check",
    description="Health check endpoint for analytics dashboard service.",
    response_description="Health status of analytics components",
)
async def analytics_health_check(
    request: Request,
    service: Annotated[AnalyticsDashboardService, Depends(get_analytics_dashboard_service)],
) -> dict[str, Any]:
    """
    Analytics dashboard health check.

    Returns:
        Health status of all analytics components
    """
    logger.debug("GET /analytics/health - Analytics health check")

    try:
        # Get storage statistics
        storage_stats = await service.storage.get_storage_stats()

        # Get recent insights count
        recent_insights = await service.storage.get_insights(
            categories=None, min_severity="low", limit=100
        )
        recent_count = len([i for i in recent_insights if (time.time() - i.created_at) < 3600])

        health = {
            "status": "healthy",
            "service_running": service._running,
            "components": {
                "metric_collection": "operational",
                "insight_generation": (
                    "operational"
                    if service._insight_task and not service._insight_task.done()
                    else "inactive"
                ),
                "pattern_analysis": (
                    "operational"
                    if service._pattern_task and not service._pattern_task.done()
                    else "inactive"
                ),
                "data_storage": "operational",
            },
            "data_quality": {
                "metrics_available": storage_stats.get("metric_types", 0) > 0,
                "insights_recent": recent_count > 0,
                "patterns_detected": storage_stats.get("patterns_stored", 0) > 0,
            },
        }

        # Determine overall health
        if not service._running:
            health["status"] = "degraded"
        elif storage_stats.get("metric_types", 0) == 0:
            health["status"] = "limited"

        return health

    except Exception as e:
        logger.error(f"Error in analytics health check: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
