"""
Security Dashboard API

Simple REST endpoints for security monitoring dashboard data.
Provides basic security statistics, events, and system health information.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.models.security_events import SecurityEvent, SecurityEventStats
from backend.services.security_event_manager import get_security_event_manager
from backend.services.security_persistence_service import get_security_persistence_service
from backend.websocket.security_handler import get_security_websocket_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security/dashboard", tags=["security-dashboard"])


class SecurityDashboardData(BaseModel):
    """Complete security dashboard data."""

    stats: Dict[str, Any]
    recent_events: List[Dict[str, Any]]
    system_health: Dict[str, Any]
    websocket_info: Dict[str, Any]


class SystemHealthResponse(BaseModel):
    """System health status response."""

    overall_status: str
    components: Dict[str, Dict[str, Any]]
    last_updated: float


@router.get("/data", response_model=SecurityDashboardData)
async def get_dashboard_data(
    limit: int = Query(default=20, description="Number of recent events to include")
) -> SecurityDashboardData:
    """
    Get complete security dashboard data.

    Returns:
        Complete dashboard data including stats, events, and health
    """
    try:
        # Get SecurityEventManager
        try:
            event_manager = get_security_event_manager()
            manager_stats = event_manager.get_statistics()
            event_stats = event_manager.get_event_stats()
            recent_events = event_manager.get_recent_events(limit=limit)
        except RuntimeError:
            logger.warning("SecurityEventManager not available")
            manager_stats = {"events_published": 0, "events_delivered": 0}
            event_stats = {"total_events": 0, "events_last_hour": 0}
            recent_events = []

        # Get persistence service stats
        try:
            persistence_service = get_security_persistence_service()
            persistence_stats = persistence_service.get_statistics()
            persistence_health = persistence_service.health_details
        except RuntimeError:
            logger.warning("SecurityPersistenceService not available")
            persistence_stats = {"events_persisted": 0, "success_rate": 0.0}
            persistence_health = {"status": "unavailable"}

        # Get WebSocket handler info
        security_handler = get_security_websocket_handler()
        websocket_stats = security_handler.get_handler_stats()

        # Compile complete dashboard data
        dashboard_data = SecurityDashboardData(
            stats={
                "event_manager": manager_stats,
                "event_stats": event_stats.dict() if hasattr(event_stats, 'dict') else event_stats,
                "persistence": persistence_stats,
            },
            recent_events=[
                event.dict() if hasattr(event, 'dict') else event
                for event in recent_events
            ],
            system_health={
                "event_manager": "healthy" if manager_stats.get("events_published", 0) >= 0 else "failed",
                "persistence": persistence_health.get("status", "unknown"),
                "websocket": "healthy" if websocket_stats["connected_clients"] >= 0 else "failed"
            },
            websocket_info=websocket_stats
        )

        return dashboard_data

    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        raise HTTPException(status_code=500, detail="Failed to get dashboard data")


@router.get("/stats", response_model=Dict[str, Any])
async def get_security_stats() -> Dict[str, Any]:
    """
    Get security statistics summary.

    Returns:
        Security statistics and metrics
    """
    try:
        event_manager = get_security_event_manager()
        manager_stats = event_manager.get_statistics()
        event_stats = event_manager.get_event_stats()

        return {
            "manager": manager_stats,
            "events": event_stats.dict() if hasattr(event_stats, 'dict') else event_stats,
            "summary": {
                "total_events": manager_stats.get("events_published", 0),
                "events_per_second": manager_stats.get("performance", {}).get("events_per_second", 0),
                "delivery_success_rate": manager_stats.get("performance", {}).get("delivery_success_rate", 0),
                "active_listeners": len(manager_stats.get("listeners", []))
            }
        }

    except RuntimeError:
        logger.warning("SecurityEventManager not available")
        return {
            "manager": {"events_published": 0},
            "events": {"total_events": 0},
            "summary": {"total_events": 0, "events_per_second": 0}
        }


@router.get("/events/recent")
async def get_recent_events(
    limit: int = Query(default=50, le=500, description="Number of events to return"),
    severity: Optional[str] = Query(default=None, description="Filter by severity")
) -> Dict[str, Any]:
    """
    Get recent security events.

    Args:
        limit: Maximum number of events to return
        severity: Optional severity filter

    Returns:
        Recent security events with metadata
    """
    try:
        event_manager = get_security_event_manager()
        events = event_manager.get_recent_events(limit=limit)

        # Apply severity filter if specified
        if severity:
            events = [e for e in events if e.severity == severity]

        return {
            "events": [event.dict() for event in events],
            "count": len(events),
            "filters_applied": {"severity": severity} if severity else {},
            "available_severities": list(set(e.severity for e in events)) if events else []
        }

    except RuntimeError:
        logger.warning("SecurityEventManager not available")
        return {
            "events": [],
            "count": 0,
            "filters_applied": {},
            "available_severities": []
        }


@router.get("/health", response_model=SystemHealthResponse)
async def get_system_health() -> SystemHealthResponse:
    """
    Get comprehensive system health status.

    Returns:
        System health information for all security components
    """
    import time

    components = {}
    overall_status = "healthy"

    # Check SecurityEventManager
    try:
        event_manager = get_security_event_manager()
        components["event_manager"] = {
            "status": event_manager.health,
            "details": event_manager.health_details
        }
        if event_manager.health in ["degraded", "failed"]:
            overall_status = "degraded" if overall_status == "healthy" else "failed"
    except RuntimeError:
        components["event_manager"] = {
            "status": "unavailable",
            "details": {"reason": "Service not initialized"}
        }
        overall_status = "degraded"

    # Check SecurityPersistenceService
    try:
        persistence_service = get_security_persistence_service()
        components["persistence"] = {
            "status": persistence_service.health,
            "details": persistence_service.health_details
        }
        if persistence_service.health in ["degraded", "failed"]:
            overall_status = "degraded" if overall_status == "healthy" else "failed"
    except RuntimeError:
        components["persistence"] = {
            "status": "unavailable",
            "details": {"reason": "Service not initialized"}
        }
        overall_status = "degraded"

    # Check WebSocket handler
    security_handler = get_security_websocket_handler()
    handler_stats = security_handler.get_handler_stats()
    components["websocket"] = {
        "status": "healthy" if handler_stats["is_registered"] else "degraded",
        "details": handler_stats
    }

    return SystemHealthResponse(
        overall_status=overall_status,
        components=components,
        last_updated=time.time()
    )


@router.post("/test/event")
async def create_test_event(
    event_type: str = "can_rate_limit_violation",
    severity: str = "medium",
    title: str = "Test Security Event"
) -> Dict[str, Any]:
    """
    Create a test security event for dashboard testing.

    Args:
        event_type: Type of security event to create
        severity: Severity level (info, low, medium, high, critical)
        title: Event title

    Returns:
        Information about the created test event
    """
    try:
        from backend.models.security_events import SecurityEvent, SecurityEventType, SecuritySeverity

        # Create test event
        test_event = SecurityEvent.create_can_event(
            event_type=SecurityEventType(event_type),
            severity=SecuritySeverity(severity),
            title=title,
            description=f"Test event generated for dashboard testing at {time.time()}",
            source_address=0x27,
            pgn=0x18FEF100,
            test_data=True
        )

        # Publish through SecurityEventManager
        try:
            event_manager = get_security_event_manager()
            await event_manager.publish(test_event)

            return {
                "status": "success",
                "event_id": test_event.event_id,
                "message": "Test event created and published",
                "event": test_event.dict()
            }

        except RuntimeError:
            return {
                "status": "partial",
                "event_id": test_event.event_id,
                "message": "Test event created but SecurityEventManager not available",
                "event": test_event.dict()
            }

    except Exception as e:
        logger.error(f"Error creating test event: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create test event: {e}")


@router.get("/websocket/info")
async def get_websocket_info() -> Dict[str, Any]:
    """
    Get WebSocket connection information.

    Returns:
        Information about WebSocket connections and status
    """
    security_handler = get_security_websocket_handler()
    handler_stats = security_handler.get_handler_stats()

    return {
        "endpoint": "/ws/security",
        "connected_clients": handler_stats["connected_clients"],
        "is_registered": handler_stats["is_registered"],
        "stats_cache_age": handler_stats["stats_cache_age"],
        "clients_by_view": handler_stats["clients_by_view"],
        "status": "active" if handler_stats["is_registered"] else "inactive"
    }
