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

from backend.core.dependencies import (
    get_predictive_maintenance_service,
)
from backend.models.predictive_maintenance import MaintenanceHistoryModel

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter(prefix="/api/predictive-maintenance", tags=["predictive-maintenance"])


@router.get(
    "/maintenance/history",
    response_model=list[MaintenanceHistoryModel],
    summary="Get maintenance history",
    description="Get maintenance history for components.",
)
async def get_maintenance_history(
    request: Request,
    pm_service: Annotated[Any, Depends(get_predictive_maintenance_service)],
    component_id: str | None = Query(None, description="Filter by component"),
    maintenance_type: str | None = Query(None, description="Filter by maintenance type"),
    days: int = Query(90, description="Number of days to retrieve", ge=1, le=365),
) -> list[MaintenanceHistoryModel]:
    """Get maintenance history."""
    logger.debug("GET /maintenance/history - Retrieving maintenance history")

    try:
        return await pm_service.get_maintenance_history(
            component_id=component_id,
            maintenance_type=maintenance_type,
            days=days,
        )

    except Exception as e:
        logger.error(f"Error retrieving maintenance history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve maintenance history") from e
