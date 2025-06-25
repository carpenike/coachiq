"""
Diagnostics API Router

Provides diagnostic endpoints for system health assessment and troubleshooting.
"""

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.core.dependencies import (
    create_optional_service_dependency,
    get_service_registry,
)
from backend.core.service_registry import ServiceStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/diagnostics",
    tags=["diagnostics"],
)


class SystemHealthResponse(BaseModel):
    """System health response model matching frontend expectations."""

    overall_health: float  # 0.0-1.0
    system_scores: dict[str, float]
    status: str  # "healthy" | "warning" | "critical"
    recommendations: list[str]
    last_assessment: float
    active_dtcs: int


@router.get("/health", response_model=SystemHealthResponse)
async def get_system_health(
    service_registry: Annotated[Any, Depends(get_service_registry)],
    system_type: str | None = Query(None, description="Specific system to query"),
) -> SystemHealthResponse:
    """
    Get comprehensive system health status.

    Args:
        system_type: Optional specific system to query, or None for all systems

    Returns:
        System health response with scores and recommendations
    """
    # Get basic service information from registry
    try:
        # Check key services using has_service and get_service
        services_to_check = [
            ("can_facade", "CAN System"),
            ("entity_service", "Entity System"),
            ("persistence_service", "Persistence System"),
            ("websocket_service", "WebSocket System"),
        ]

        system_scores = {}
        healthy_count = 0
        total_count = 0

        for service_name, display_name in services_to_check:
            if service_registry.has_service(service_name):
                try:
                    # Try to get the service - if successful, consider it healthy
                    service = service_registry.get_service(service_name)
                    if service is not None:
                        system_scores[display_name.lower().replace(" ", "_")] = 1.0
                        healthy_count += 1
                    else:
                        system_scores[display_name.lower().replace(" ", "_")] = 0.0
                except Exception:
                    system_scores[display_name.lower().replace(" ", "_")] = 0.5
                total_count += 1
            else:
                # Service not registered
                system_scores[display_name.lower().replace(" ", "_")] = 0.0
                total_count += 1

        # Filter by system_type if provided
        if system_type:
            filtered_scores = {k: v for k, v in system_scores.items() if system_type in k}
            if filtered_scores:
                system_scores = filtered_scores
                healthy_count = sum(1 for v in filtered_scores.values() if v == 1.0)
                total_count = len(filtered_scores)

        # Calculate overall health score
        overall_health = healthy_count / max(total_count, 1)

        # Determine status
        if overall_health >= 0.9:
            status = "healthy"
        elif overall_health >= 0.7:
            status = "warning"
        else:
            status = "critical"

        # Generate recommendations
        recommendations = []
        if overall_health < 0.9:
            if system_scores.get("can_system", 1.0) < 1.0:
                recommendations.append("Check CAN interface connections")
            if system_scores.get("persistence_system", 1.0) < 1.0:
                recommendations.append("Verify database connectivity")
            if not recommendations:
                recommendations.append("Monitor system performance")

        # Count active DTCs (diagnostic trouble codes)
        # In a real system, this would query actual DTCs
        active_dtcs = 0

        return SystemHealthResponse(
            overall_health=overall_health,
            system_scores=system_scores,
            status=status,
            recommendations=recommendations,
            last_assessment=time.time(),
            active_dtcs=active_dtcs,
        )

    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        # Return degraded health on error
        return SystemHealthResponse(
            overall_health=0.0,
            system_scores={},
            status="critical",
            recommendations=["System health check failed", str(e)],
            last_assessment=time.time(),
            active_dtcs=0,
        )
