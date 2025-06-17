"""
Dashboard API Router

FastAPI router for aggregated dashboard data and enhanced frontend endpoints.
This router provides optimized endpoints for dashboard components with
intelligent caching and real-time data aggregation.

Routes:
- GET /dashboard/summary: Get complete dashboard data in one request
- GET /dashboard/entities: Get entity summary statistics
- GET /dashboard/system: Get system performance metrics
- GET /dashboard/activity: Get recent activity feed
- POST /dashboard/bulk-control: Perform bulk entity control operations
- GET /dashboard/analytics: Get system analytics and alerts
- POST /dashboard/alerts/{alert_id}/acknowledge: Acknowledge an alert
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.core.dependencies_v2 import (
    get_can_service,
    get_entity_service,
    get_feature_manager,
    get_websocket_manager,
)
from backend.models.dashboard import (
    ActivityFeed,
    BulkControlRequest,
    BulkControlResponse,
    CANBusSummary,
    DashboardSummary,
    EntitySummary,
    SystemAnalytics,
    SystemMetrics,
)
from backend.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Global dashboard service instance (will be initialized on first use)
_dashboard_service: DashboardService | None = None


def _check_dashboard_aggregation_enabled(request: Request) -> None:
    """Check if dashboard_aggregation feature is enabled, raise 404 if disabled."""
    feature_manager = get_feature_manager(request)
    if not feature_manager.is_enabled("dashboard_aggregation"):
        raise HTTPException(status_code=404, detail="dashboard_aggregation feature is disabled")


def _get_dashboard_service(
    request: Request,
    entity_service: Annotated[Any, Depends(get_entity_service)],
    can_service: Annotated[Any, Depends(get_can_service)],
    websocket_manager: Annotated[Any, Depends(get_websocket_manager)],
) -> DashboardService:
    """Get or create dashboard service instance."""
    global _dashboard_service

    if _dashboard_service is None:
        _dashboard_service = DashboardService(
            entity_service=entity_service,
            can_service=can_service,
            websocket_manager=websocket_manager,
        )

    return _dashboard_service


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Get dashboard summary",
    description="Get complete aggregated dashboard data in a single optimized request.",
    response_description="Complete dashboard data including entities, system metrics, and activity feed",
)
async def get_dashboard_summary(
    request: Request,
    dashboard_service: Annotated[DashboardService, Depends(_get_dashboard_service)],
) -> DashboardSummary:
    """
    Get complete aggregated dashboard data in a single request.

    This endpoint provides all the data needed for the main dashboard page,
    optimized for performance with intelligent caching.
    """
    logger.info("GET /dashboard/summary - Retrieving complete dashboard data")
    _check_dashboard_aggregation_enabled(request)

    try:
        summary = await dashboard_service.get_dashboard_summary()
        logger.info(
            f"Dashboard summary retrieved: {summary.entities.total_entities} entities, "
            f"{len(summary.activity.entries)} activities, {len(summary.alerts)} alerts"
        )
        return summary

    except Exception as e:
        logger.error(f"Error retrieving dashboard summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboard summary") from e


@router.get(
    "/entities",
    response_model=EntitySummary,
    summary="Get entity statistics",
    description="Get aggregated entity statistics and health information.",
    response_description="Entity summary with counts, health scores, and device type breakdown",
)
async def get_entity_summary(
    request: Request,
    dashboard_service: Annotated[DashboardService, Depends(_get_dashboard_service)],
) -> EntitySummary:
    """Get aggregated entity statistics."""
    logger.debug("GET /dashboard/entities - Retrieving entity summary")
    _check_dashboard_aggregation_enabled(request)

    try:
        summary = await dashboard_service.get_entity_summary()
        logger.info(
            f"Entity summary: {summary.total_entities} total, {summary.online_entities} online"
        )
        return summary

    except Exception as e:
        logger.error(f"Error retrieving entity summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve entity summary") from e


@router.get(
    "/system",
    response_model=SystemMetrics,
    summary="Get system metrics",
    description="Get system performance metrics and health indicators.",
    response_description="System metrics including uptime, performance, and resource usage",
)
async def get_system_metrics(
    request: Request,
    dashboard_service: Annotated[DashboardService, Depends(_get_dashboard_service)],
) -> SystemMetrics:
    """Get system performance metrics."""
    logger.debug("GET /dashboard/system - Retrieving system metrics")
    _check_dashboard_aggregation_enabled(request)

    try:
        metrics = await dashboard_service.get_system_metrics()
        logger.info(
            f"System metrics: {metrics.uptime_seconds}s uptime, {metrics.message_rate:.1f} msg/s"
        )
        return metrics

    except Exception as e:
        logger.error(f"Error retrieving system metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve system metrics") from e


@router.get(
    "/can-bus",
    response_model=CANBusSummary,
    summary="Get CAN bus summary",
    description="Get CAN bus status and performance summary.",
    response_description="CAN bus summary with interface count, message rates, and health status",
)
async def get_can_bus_summary(
    request: Request,
    dashboard_service: Annotated[DashboardService, Depends(_get_dashboard_service)],
) -> CANBusSummary:
    """Get CAN bus status summary."""
    logger.debug("GET /dashboard/can-bus - Retrieving CAN bus summary")
    _check_dashboard_aggregation_enabled(request)

    try:
        summary = await dashboard_service.get_can_bus_summary()
        logger.info(
            f"CAN summary: {summary.interfaces_count} interfaces, {summary.total_messages} messages"
        )
        return summary

    except Exception as e:
        logger.error(f"Error retrieving CAN bus summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve CAN bus summary") from e


@router.get(
    "/activity",
    response_model=ActivityFeed,
    summary="Get activity feed",
    description="Get recent system activity and event feed.",
    response_description="Activity feed with recent events, entity changes, and system notifications",
)
async def get_activity_feed(
    request: Request,
    dashboard_service: Annotated[DashboardService, Depends(_get_dashboard_service)],
    limit: int = Query(50, description="Maximum number of activities to return", ge=1, le=200),
    since: Annotated[
        datetime | None, Query(description="Return activities since this timestamp")
    ] = None,
) -> ActivityFeed:
    """Get recent system activity feed."""
    logger.debug(f"GET /dashboard/activity - Retrieving activity feed (limit={limit})")
    _check_dashboard_aggregation_enabled(request)

    try:
        activity_feed = await dashboard_service.get_activity_feed(limit=limit, since=since)
        logger.info(
            f"Activity feed: {len(activity_feed.entries)} entries, has_more={activity_feed.has_more}"
        )
        return activity_feed

    except Exception as e:
        logger.error(f"Error retrieving activity feed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve activity feed") from e


@router.post(
    "/bulk-control",
    response_model=BulkControlResponse,
    summary="Bulk entity control",
    description="Perform control operations on multiple entities in a single request.",
    response_description="Results of bulk control operation with individual entity status",
)
async def bulk_control_entities(
    request: Request,
    bulk_request: BulkControlRequest,
    dashboard_service: Annotated[DashboardService, Depends(_get_dashboard_service)],
) -> BulkControlResponse:
    """Perform bulk control operations on multiple entities."""
    logger.info(
        f"POST /dashboard/bulk-control - Bulk {bulk_request.command} on {len(bulk_request.entity_ids)} entities"
    )

    # Check if bulk operations feature is enabled
    feature_manager = get_feature_manager(request)
    if not feature_manager.is_enabled("bulk_operations"):
        raise HTTPException(status_code=404, detail="bulk_operations feature is disabled")

    if not bulk_request.entity_ids:
        raise HTTPException(status_code=400, detail="No entity IDs provided")

    try:
        response = await dashboard_service.bulk_control_entities(bulk_request)
        logger.info(
            f"Bulk control completed: {response.successful} successful, {response.failed} failed"
        )
        return response

    except ValueError as e:
        logger.warning(f"Invalid bulk control request: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e

    except Exception as e:
        logger.error(f"Error performing bulk control: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to perform bulk control operation"
        ) from e


@router.get(
    "/analytics",
    response_model=SystemAnalytics,
    summary="Get system analytics",
    description="Get system analytics, alerts, and performance monitoring data.",
    response_description="System analytics with active alerts, trends, and recommendations",
)
async def get_system_analytics(
    request: Request,
    dashboard_service: Annotated[DashboardService, Depends(_get_dashboard_service)],
) -> SystemAnalytics:
    """Get system analytics and monitoring data."""
    logger.debug("GET /dashboard/analytics - Retrieving system analytics")

    # Check if system analytics feature is enabled
    feature_manager = get_feature_manager(request)
    if not feature_manager.is_enabled("system_analytics"):
        raise HTTPException(status_code=404, detail="system_analytics feature is disabled")

    try:
        analytics = await dashboard_service.get_system_analytics()
        logger.info(
            f"System analytics: {len(analytics.alerts)} active alerts, {len(analytics.recommendations)} recommendations"
        )
        return analytics

    except Exception as e:
        logger.error(f"Error retrieving system analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve system analytics") from e


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=dict[str, Any],
    summary="Acknowledge alert",
    description="Acknowledge an active system alert.",
    response_description="Acknowledgment status and confirmation",
)
async def acknowledge_alert(
    alert_id: str,
    request: Request,
    dashboard_service: Annotated[DashboardService, Depends(_get_dashboard_service)],
) -> dict[str, Any]:
    """Acknowledge an active system alert."""
    logger.info(f"POST /dashboard/alerts/{alert_id}/acknowledge - Acknowledging alert")

    # Check if system analytics feature is enabled
    feature_manager = get_feature_manager(request)
    if not feature_manager.is_enabled("system_analytics"):
        raise HTTPException(status_code=404, detail="system_analytics feature is disabled")

    try:
        success = await dashboard_service.acknowledge_alert(alert_id)

        if success:
            logger.info(f"Alert {alert_id} acknowledged successfully")
            return {
                "success": True,
                "message": f"Alert {alert_id} acknowledged",
                "alert_id": alert_id,
                "acknowledged_at": datetime.now().isoformat(),
            }
        logger.warning(f"Alert {alert_id} not found or already acknowledged")
        raise HTTPException(status_code=404, detail="Alert not found or already acknowledged")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to acknowledge alert") from e
