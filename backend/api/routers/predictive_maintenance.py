"""
Predictive Maintenance API Router

FastAPI router for predictive maintenance with component health tracking,
trend analysis, and proactive maintenance recommendations.

Routes:
- GET /health/overview: Get overall RV health score and status
- GET /health/components: Get health scores for all components
- GET /health/components/{component_id}: Get detailed component health
- GET /recommendations: Get maintenance recommendations
- POST /recommendations/{recommendation_id}/acknowledge: Acknowledge recommendation
- GET /trends/{component_id}: Get trend data for component
- POST /maintenance/log: Log maintenance activity
- GET /maintenance/history: Get maintenance history
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.core.dependencies_v2 import (
    get_feature_manager,
    get_predictive_maintenance_service,
)

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter(prefix="/api/predictive-maintenance", tags=["predictive-maintenance"])


def _check_predictive_maintenance_feature_enabled(request: Request) -> None:
    """
    Check if the predictive_maintenance feature is enabled.

    Raises HTTPException with 404 status if the feature is disabled.
    """
    feature_manager = get_feature_manager(request)
    if not feature_manager.is_enabled("predictive_maintenance"):
        raise HTTPException(
            status_code=404,
            detail="predictive_maintenance feature is disabled",
        )


# Pydantic Models
class ComponentHealth(BaseModel):
    """Component health status model."""

    component_id: str = Field(..., description="Component identifier")
    component_type: str = Field(..., description="Type of component")
    component_name: str = Field(..., description="Human-readable component name")
    health_score: float = Field(..., ge=0, le=100, description="Health score (0-100%)")
    status: str = Field(..., description="Health status (healthy, watch, advise, alert)")
    remaining_useful_life_days: int | None = Field(
        None, description="Estimated days until replacement needed"
    )
    last_maintenance: datetime | None = Field(None, description="Last maintenance date")
    next_maintenance_due: datetime | None = Field(None, description="Next scheduled maintenance")
    usage_hours: float | None = Field(None, description="Total usage hours")
    usage_cycles: int | None = Field(None, description="Total usage cycles")
    anomaly_count: int = Field(default=0, description="Recent anomaly count")
    trend_direction: str = Field(
        default="stable", description="Trend direction (improving, stable, degrading)"
    )


class RVHealthOverview(BaseModel):
    """Overall RV health overview model."""

    overall_health_score: float = Field(..., ge=0, le=100, description="Overall health score")
    status: str = Field(..., description="Overall status (healthy, watch, advise, alert)")
    critical_alerts: int = Field(default=0, description="Number of critical alerts")
    active_recommendations: int = Field(default=0, description="Number of active recommendations")
    components_monitored: int = Field(default=0, description="Total components being monitored")
    last_updated: datetime = Field(..., description="Last update timestamp")
    system_health_breakdown: dict[str, float] = Field(
        default_factory=dict, description="Health by system type"
    )


class MaintenanceRecommendation(BaseModel):
    """Maintenance recommendation model."""

    recommendation_id: str = Field(..., description="Unique recommendation identifier")
    component_id: str = Field(..., description="Component identifier")
    component_name: str = Field(..., description="Human-readable component name")
    level: str = Field(..., description="Recommendation level (watch, advise, alert)")
    title: str = Field(..., description="Recommendation title")
    message: str = Field(..., description="Detailed recommendation message")
    priority: int = Field(..., ge=1, le=5, description="Priority level (1=highest, 5=lowest)")
    estimated_cost: float | None = Field(None, description="Estimated maintenance cost")
    estimated_time_hours: float | None = Field(None, description="Estimated time required")
    urgency_days: int | None = Field(None, description="Days until urgent")
    created_at: datetime = Field(..., description="Recommendation creation time")
    acknowledged_at: datetime | None = Field(None, description="Acknowledgment timestamp")
    dismissed: bool = Field(default=False, description="Whether recommendation was dismissed")
    maintenance_type: str = Field(
        default="inspection",
        description="Type of maintenance (inspection, service, replacement)",
    )


class ComponentTrendData(BaseModel):
    """Component trend analysis data."""

    component_id: str = Field(..., description="Component identifier")
    metric_name: str = Field(..., description="Metric being tracked")
    trend_points: list[dict[str, Any]] = Field(..., description="Trend data points")
    normal_range: dict[str, float] = Field(..., description="Normal operating range")
    anomalies: list[dict[str, Any]] = Field(default_factory=list, description="Detected anomalies")
    prediction_confidence: float = Field(..., ge=0, le=1, description="Prediction confidence")
    trend_analysis: str = Field(..., description="Trend analysis summary")


class MaintenanceLogEntry(BaseModel):
    """Maintenance activity log entry."""

    component_id: str = Field(..., description="Component identifier")
    maintenance_type: str = Field(..., description="Type of maintenance performed")
    description: str = Field(..., description="Maintenance description")
    cost: float | None = Field(None, description="Maintenance cost")
    performed_by: str | None = Field(None, description="Who performed the maintenance")
    location: str | None = Field(None, description="Where maintenance was performed")
    notes: str | None = Field(None, description="Additional notes")


class MaintenanceHistory(BaseModel):
    """Maintenance history model."""

    entry_id: str = Field(..., description="History entry identifier")
    component_id: str = Field(..., description="Component identifier")
    component_name: str = Field(..., description="Component name")
    maintenance_type: str = Field(..., description="Type of maintenance")
    description: str = Field(..., description="Maintenance description")
    performed_at: datetime = Field(..., description="When maintenance was performed")
    cost: float | None = Field(None, description="Maintenance cost")
    performed_by: str | None = Field(None, description="Who performed maintenance")
    location: str | None = Field(None, description="Maintenance location")
    notes: str | None = Field(None, description="Additional notes")


@router.get(
    "/health/overview",
    response_model=RVHealthOverview,
    summary="Get RV health overview",
    description="Get overall RV health score and system status summary.",
)
async def get_health_overview(
    request: Request,
    pm_service: Annotated[Any, Depends(get_predictive_maintenance_service)],
) -> RVHealthOverview:
    """Get overall RV health overview."""
    logger.debug("GET /health/overview - Retrieving RV health overview")
    _check_predictive_maintenance_feature_enabled(request)

    try:
        return await pm_service.get_health_overview()

    except Exception as e:
        logger.error(f"Error retrieving health overview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve health overview") from e


@router.get(
    "/health/components",
    response_model=list[ComponentHealth],
    summary="Get component health status",
    description="Get health status for all monitored components.",
)
async def get_component_health(
    request: Request,
    pm_service: Annotated[Any, Depends(get_predictive_maintenance_service)],
    system_type: str | None = Query(None, description="Filter by system type"),
    status: str | None = Query(None, description="Filter by health status"),
) -> list[ComponentHealth]:
    """Get health status for all components."""
    logger.debug(
        f"GET /health/components - Retrieving component health (system_type={system_type}, status={status})"
    )
    _check_predictive_maintenance_feature_enabled(request)

    try:
        return await pm_service.get_component_health(
            system_type=system_type,
            status=status,
        )

    except Exception as e:
        logger.error(f"Error retrieving component health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve component health") from e


@router.get(
    "/health/components/{component_id}",
    response_model=ComponentHealth,
    summary="Get specific component health",
    description="Get detailed health information for a specific component.",
)
async def get_component_health_detail(
    request: Request,
    component_id: str,
    pm_service: Annotated[Any, Depends(get_predictive_maintenance_service)],
) -> ComponentHealth:
    """Get detailed health information for a specific component."""
    logger.debug(f"GET /health/components/{component_id} - Retrieving component health detail")
    _check_predictive_maintenance_feature_enabled(request)

    try:
        component = await pm_service.get_component_health_detail(component_id)
        if not component:
            raise HTTPException(status_code=404, detail="Component not found")
        return component

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving component health detail for {component_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Failed to retrieve component health detail"
        ) from e


@router.get(
    "/recommendations",
    response_model=list[MaintenanceRecommendation],
    summary="Get maintenance recommendations",
    description="Get active maintenance recommendations prioritized by urgency.",
)
async def get_maintenance_recommendations(
    request: Request,
    pm_service: Annotated[Any, Depends(get_predictive_maintenance_service)],
    level: str | None = Query(None, description="Filter by recommendation level"),
    component_id: str | None = Query(None, description="Filter by component"),
    acknowledged: bool | None = Query(None, description="Filter by acknowledgment status"),
) -> list[MaintenanceRecommendation]:
    """Get maintenance recommendations."""
    logger.debug("GET /recommendations - Retrieving maintenance recommendations")
    _check_predictive_maintenance_feature_enabled(request)

    try:
        return await pm_service.get_maintenance_recommendations(
            level=level,
            component_id=component_id,
            acknowledged=acknowledged,
        )

    except Exception as e:
        logger.error(f"Error retrieving maintenance recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve maintenance recommendations"
        ) from e


@router.post(
    "/recommendations/{recommendation_id}/acknowledge",
    summary="Acknowledge recommendation",
    description="Acknowledge a maintenance recommendation.",
)
async def acknowledge_recommendation(
    request: Request,
    recommendation_id: str,
    pm_service: Annotated[Any, Depends(get_predictive_maintenance_service)],
) -> dict[str, str]:
    """Acknowledge a maintenance recommendation."""
    logger.info(
        f"POST /recommendations/{recommendation_id}/acknowledge - Acknowledging recommendation"
    )
    _check_predictive_maintenance_feature_enabled(request)

    try:
        success = await pm_service.acknowledge_recommendation(recommendation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Recommendation not found")

        return {"message": "Recommendation acknowledged successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error acknowledging recommendation {recommendation_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to acknowledge recommendation") from e


@router.get(
    "/trends/{component_id}",
    response_model=ComponentTrendData,
    summary="Get component trend data",
    description="Get trend analysis data for a specific component.",
)
async def get_component_trends(
    request: Request,
    component_id: str,
    pm_service: Annotated[Any, Depends(get_predictive_maintenance_service)],
    metric: str | None = Query(None, description="Specific metric to analyze"),
    days: int = Query(30, description="Number of days of data", ge=1, le=365),
) -> ComponentTrendData:
    """Get trend analysis data for a component."""
    logger.debug(f"GET /trends/{component_id} - Retrieving component trend data")
    _check_predictive_maintenance_feature_enabled(request)

    try:
        trend_data = await pm_service.get_component_trends(
            component_id=component_id,
            metric=metric,
            days=days,
        )
        if not trend_data:
            raise HTTPException(status_code=404, detail="Component trend data not found")
        return trend_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving trend data for component {component_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Failed to retrieve component trend data"
        ) from e


@router.post(
    "/maintenance/log",
    summary="Log maintenance activity",
    description="Log a maintenance activity for a component.",
)
async def log_maintenance_activity(
    request: Request,
    maintenance_entry: MaintenanceLogEntry,
    pm_service: Annotated[Any, Depends(get_predictive_maintenance_service)],
) -> dict[str, str]:
    """Log a maintenance activity."""
    logger.info(
        f"POST /maintenance/log - Logging maintenance for component {maintenance_entry.component_id}"
    )
    _check_predictive_maintenance_feature_enabled(request)

    try:
        entry_id = await pm_service.log_maintenance_activity(maintenance_entry)
        return {
            "message": "Maintenance activity logged successfully",
            "entry_id": entry_id,
        }

    except Exception as e:
        logger.error(f"Error logging maintenance activity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to log maintenance activity") from e


@router.get(
    "/maintenance/history",
    response_model=list[MaintenanceHistory],
    summary="Get maintenance history",
    description="Get maintenance history for components.",
)
async def get_maintenance_history(
    request: Request,
    pm_service: Annotated[Any, Depends(get_predictive_maintenance_service)],
    component_id: str | None = Query(None, description="Filter by component"),
    maintenance_type: str | None = Query(None, description="Filter by maintenance type"),
    days: int = Query(90, description="Number of days to retrieve", ge=1, le=365),
) -> list[MaintenanceHistory]:
    """Get maintenance history."""
    logger.debug("GET /maintenance/history - Retrieving maintenance history")
    _check_predictive_maintenance_feature_enabled(request)

    try:
        return await pm_service.get_maintenance_history(
            component_id=component_id,
            maintenance_type=maintenance_type,
            days=days,
        )

    except Exception as e:
        logger.error(f"Error retrieving maintenance history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve maintenance history") from e
