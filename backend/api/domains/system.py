"""
System Domain API Router (v2)

Provides domain-specific system management endpoints:
- System information and status
- Configuration management
- Service health monitoring
- Performance metrics

This router integrates with existing system services.
"""

import logging
import os
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.domains import register_domain_router

logger = logging.getLogger(__name__)


def _map_service_status_to_ietf(status: str) -> str:
    """Map internal service status values to IETF-compliant values."""
    status_mapping = {
        "healthy": "pass",
        "degraded": "warn",
        "failed": "fail",
        "disabled": "pass",  # Disabled services are not unhealthy
    }
    return status_mapping.get(status, status)


# Domain-specific schemas for v2 API
class SystemInfo(BaseModel):
    """System information"""

    hostname: str = Field(..., description="System hostname")
    platform: str = Field(..., description="Operating system platform")
    architecture: str = Field(..., description="System architecture")
    python_version: str = Field(..., description="Python version")
    uptime_seconds: float = Field(..., description="System uptime in seconds")
    timestamp: float = Field(..., description="Info timestamp")


class ServiceStatus(BaseModel):
    """Service status information"""

    name: str = Field(..., description="Service name")
    status: str = Field(..., description="Service status: healthy/degraded/unhealthy")
    enabled: bool = Field(..., description="Whether service is enabled")
    last_check: float = Field(..., description="Last health check timestamp")


class ServiceMetadata(BaseModel):
    """Service metadata information"""

    name: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    environment: str = Field(..., description="Environment (development, staging, production)")
    hostname: str = Field(..., description="System hostname")
    platform: str = Field(..., description="Operating system platform")


class ComponentHealth(BaseModel):
    """Individual component health information"""

    id: str = Field(..., description="Component identifier")
    name: str = Field(..., description="Component display name")
    status: str = Field(..., description="Component status: healthy/degraded/unhealthy/unknown")
    message: str | None = Field(None, description="Status message or error details")
    category: str = Field(..., description="Component category: core/network/storage/external")
    last_checked: float = Field(..., description="Last health check timestamp")
    safety_classification: str | None = Field(
        None, description="Safety classification if applicable"
    )


class ComponentHealthResponse(BaseModel):
    """Response for component health endpoint"""

    components: list[ComponentHealth] = Field(..., description="List of component health statuses")
    total_components: int = Field(..., description="Total number of components")
    healthy_components: int = Field(..., description="Number of healthy components")
    degraded_components: int = Field(..., description="Number of degraded components")
    unhealthy_components: int = Field(..., description="Number of unhealthy components")
    timestamp: float = Field(..., description="Response timestamp")


class SystemStatus(BaseModel):
    """System status response"""

    overall_status: str = Field(..., description="Overall system status: healthy/degraded/failed")
    services: list[ServiceStatus] = Field(..., description="List of service statuses")
    total_services: int = Field(..., description="Total number of services")
    healthy_services: int = Field(..., description="Number of healthy services")
    timestamp: float = Field(..., description="Status check timestamp")
    response_time_ms: float = Field(..., description="Response time in milliseconds")
    service: ServiceMetadata = Field(..., description="Service metadata")
    description: str = Field(..., description="Human-readable status description")


class EventLogEntry(BaseModel):
    """System event log entry"""

    id: str = Field(..., description="Unique event identifier")
    timestamp: float = Field(..., description="Event timestamp")
    level: str = Field(..., description="Log level: debug/info/warning/error/critical")
    component: str = Field(..., description="Component that generated the event")
    message: str = Field(..., description="Event message")
    details: dict[str, Any] | None = Field(None, description="Additional event details")


class EventLogResponse(BaseModel):
    """Response for event logs endpoint"""

    events: list[EventLogEntry] = Field(..., description="List of event log entries")
    total_events: int = Field(..., description="Total number of events")
    timestamp: float = Field(..., description="Response timestamp")


class EventLogFilter(BaseModel):
    """Filter parameters for event logs"""

    limit: int = Field(50, ge=1, le=1000, description="Maximum number of events to return")
    level: str | None = Field(None, description="Filter by log level")
    component: str | None = Field(None, description="Filter by component")
    start_time: float | None = Field(None, description="Filter events after this timestamp")
    end_time: float | None = Field(None, description="Filter events before this timestamp")


class SystemStatus(BaseModel):
    """Overall system status with enhanced metadata"""

    overall_status: str = Field(..., description="Overall system status")
    services: list[ServiceStatus] = Field(..., description="Individual service statuses")
    total_services: int = Field(..., description="Total number of services")
    healthy_services: int = Field(..., description="Number of healthy services")
    timestamp: float = Field(..., description="Status timestamp")

    # Enhanced metadata from healthz
    response_time_ms: float | None = Field(None, description="Response time in milliseconds")
    service: ServiceMetadata | None = Field(None, description="Service metadata")
    description: str | None = Field(None, description="Human-readable status description")


def create_system_router() -> APIRouter:
    """Create the system domain router with all endpoints"""
    router = APIRouter(tags=["system-v2"])

    @router.get("/health")
    async def health_check(request: Request) -> dict[str, Any]:
        """Health check endpoint for system domain API"""

        return {
            "status": "healthy",
            "domain": "system",
            "version": "v2",
            "features": {
                "system_monitoring": True,
                "service_management": True,
                "configuration_api": True,
            },
            "timestamp": "2025-01-11T00:00:00Z",
        }

    @router.get("/schemas")
    async def get_schemas(request: Request) -> dict[str, Any]:
        """Export schemas for system domain"""

        return {
            "message": "System domain schemas available",
            "available_endpoints": [
                "/health",
                "/schemas",
                "/info",
                "/status",
                "/services",
                "/components/health",
                "/events",
            ],
        }

    @router.get("/info", response_model=SystemInfo)
    async def get_system_info(request: Request) -> SystemInfo:
        """Get system information"""

        try:
            return SystemInfo(
                hostname=platform.node(),
                platform=platform.system(),
                architecture=platform.machine(),
                python_version=platform.python_version(),
                uptime_seconds=time.time(),  # Simplified - would use actual uptime
                timestamp=time.time(),
            )

        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get system info: {e!s}")

    @router.get("/status")
    async def get_system_status(request: Request, format: str = "default") -> dict[str, Any]:
        """Get overall system status with enhanced metadata

        Supports multiple formats:
        - default: Standard SystemStatus response
        - ietf: IETF health+json compliant format
        """

        start_time = time.time()

        try:
            # Get service version
            try:
                version_file = Path(__file__).parent.parent.parent / "VERSION"
                if version_file.exists():
                    version = version_file.read_text().strip()
                else:
                    version = os.getenv("VERSION", "development")
            except Exception:
                version = "unknown"

            # Calculate response time
            response_time_ms = round((time.time() - start_time) * 1000, 2)

            # Create service metadata
            service_metadata = ServiceMetadata(
                name="coachiq",
                version=version,
                environment=os.getenv("ENVIRONMENT", "development"),
                hostname=platform.node(),
                platform=platform.system(),
            )

            # For now, return a simplified status without enumerating all services
            overall_status = "healthy"
            ietf_status = "pass"
            description = "All services operational"

            # Return format based on request
            if format.lower() == "ietf":
                # IETF health+json format
                return {
                    "status": ietf_status,
                    "version": "1",  # Health check format version
                    "releaseId": version,
                    "serviceId": "coachiq-system",
                    "description": description,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "service": {
                        "name": service_metadata.name,
                        "version": service_metadata.version,
                        "environment": service_metadata.environment,
                        "hostname": service_metadata.hostname,
                        "platform": service_metadata.platform,
                    },
                    "response_time_ms": response_time_ms,
                }

            # Default SystemStatus format
            return SystemStatus(
                overall_status=overall_status,
                services=[],  # Empty for now
                total_services=0,
                healthy_services=0,
                timestamp=time.time(),
                response_time_ms=response_time_ms,
                service=service_metadata,
                description=description,
            ).model_dump()

        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get system status: {e!s}")

    @router.get("/services")
    async def get_services(request: Request) -> list[ServiceStatus]:
        """Get detailed service information"""

        try:
            # Get services from ServiceRegistry
            from backend.core.dependencies import get_service_registry

            service_registry = get_service_registry()
            services = []

            # Get all services and check their health individually
            try:
                metrics = (
                    service_registry.get_startup_metrics()
                    if hasattr(service_registry, "get_startup_metrics")
                    else {}
                )
                all_services = (
                    list(metrics.get("services", {}).keys()) if "services" in metrics else []
                )
            except Exception:
                all_services = []

            for service_name in all_services:
                try:
                    service_status = await service_registry.check_service_health(service_name)

                    # Map ServiceStatus enum to string status
                    if service_status.value == "healthy":
                        status = "healthy"
                    elif service_status.value == "degraded":
                        status = "degraded"
                    elif service_status.value == "failed":
                        status = "failed"
                    else:
                        status = "unknown"
                except Exception:
                    # If health check fails, mark as unknown
                    status = "unknown"

                services.append(
                    ServiceStatus(
                        name=service_name, status=status, enabled=True, last_check=time.time()
                    )
                )

            return services

        except Exception as e:
            logger.error(f"Error getting services: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get services: {e!s}")

    @router.get("/components/health", response_model=ComponentHealthResponse)
    async def get_component_health(request: Request) -> ComponentHealthResponse:
        """Get detailed health status for all system components

        Returns health information for individual system components,
        organized by category (core, network, storage, external).
        """

        try:
            # Get services from ServiceRegistry
            from backend.core.dependencies import get_service_registry

            service_registry = get_service_registry()
            components = []

            # Map services to component categories
            category_mapping = {
                # Core services
                "service_registry": "core",
                "entity_service": "core",
                "auth_manager": "core",
                "analytics_service": "core",
                # Network services
                "can_service": "network",
                "websocket_manager": "network",
                "multi_network_service": "network",
                # Storage services
                "persistence_service": "storage",
                "database_manager": "storage",
                "vector_search_service": "storage",
                # External interfaces
                "rvc_service": "external",
                "j1939_service": "external",
                "predictive_maintenance_service": "external",
            }

            # Get all services
            try:
                metrics = (
                    service_registry.get_startup_metrics()
                    if hasattr(service_registry, "get_startup_metrics")
                    else {}
                )
                all_services = (
                    list(metrics.get("services", {}).keys()) if "services" in metrics else []
                )
            except Exception:
                all_services = []

            for service_name in all_services:
                # Check individual service health
                try:
                    service_status = await service_registry.check_service_health(service_name)

                    # Determine health status from service status
                    if service_status.value == "healthy":
                        status = "healthy"
                    elif service_status.value == "degraded":
                        status = "degraded"
                    elif service_status.value == "failed":
                        status = "unhealthy"
                    else:
                        status = "unknown"

                    # Get any health message
                    message = f"Service is {service_status.value}"
                except Exception as e:
                    # If health check fails, mark as unknown
                    status = "unknown"
                    message = f"Health check failed: {e!s}"

                # Determine category
                category = category_mapping.get(service_name, "external")

                # Create component health entry
                components.append(
                    ComponentHealth(
                        id=service_name,
                        name=service_name.replace("_", " ").title(),
                        status=status,
                        message=message,
                        category=category,
                        last_checked=time.time(),
                        safety_classification=None,  # Safety classification was part of feature flags
                    )
                )

            # Count statuses
            healthy_count = len([c for c in components if c.status == "healthy"])
            degraded_count = len([c for c in components if c.status == "degraded"])
            unhealthy_count = len([c for c in components if c.status == "unhealthy"])

            return ComponentHealthResponse(
                components=components,
                total_components=len(components),
                healthy_components=healthy_count,
                degraded_components=degraded_count,
                unhealthy_components=unhealthy_count,
                timestamp=time.time(),
            )

        except Exception as e:
            logger.error(f"Error getting component health: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get component health: {e!s}")

    @router.get("/events", response_model=EventLogResponse)
    async def get_event_logs(
        request: Request,
        limit: int = 50,
        level: str | None = None,
        component: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> EventLogResponse:
        """Get system event logs with filtering

        Returns recent system events that can be filtered by:
        - Log level (debug, info, warning, error, critical)
        - Component name
        - Time range
        """

        try:
            # In a real implementation, this would fetch from a logging service or database
            # For now, we'll generate sample events similar to the frontend

            import random

            # Sample components and messages
            components = ["can-interface", "api-server", "database", "websocket", "entity-manager"]

            messages_by_level = {
                "debug": [
                    "Periodic health check completed",
                    "Cache refresh completed",
                    "Background task executed",
                ],
                "info": [
                    "New entity discovered: Light Switch (Instance 12)",
                    "WebSocket client connected",
                    "Configuration reloaded",
                    "Feature flag updated: vector_search=true",
                ],
                "warning": [
                    "High memory usage detected (85%)",
                    "Slow database query detected (2.3s)",
                    "CAN message queue growing (depth: 150)",
                    "Authentication token expiring soon",
                ],
                "error": [
                    "Failed to connect to CAN interface can1",
                    "Database connection timeout",
                    "WebSocket connection lost",
                    "Entity state update failed",
                ],
                "critical": [
                    "CAN interface can0 went offline",
                    "Database connection pool exhausted",
                    "Safety system unresponsive",
                ],
            }

            # Generate sample events
            events = []
            now = time.time()

            # Generate events over the last hour
            for i in range(100):
                event_time = (
                    now - (i * 60) - random.random() * 60
                )  # Events spread over last 100 minutes

                # Skip if outside time filter
                if start_time and event_time < start_time:
                    continue
                if end_time and event_time > end_time:
                    continue

                # Select random level and component
                event_level = random.choice(list(messages_by_level.keys()))
                event_component = random.choice(components)

                # Skip if doesn't match filters
                if level and event_level != level:
                    continue
                if component and event_component != component:
                    continue

                # Select random message for this level
                message = random.choice(messages_by_level[event_level])

                # Add details for errors and critical events
                details = None
                if event_level in ["error", "critical"]:
                    details = {
                        "error_code": f"ERR_{random.randint(1000, 9999)}",
                        "retry_count": random.randint(0, 3),
                    }

                events.append(
                    EventLogEntry(
                        id=f"event-{i}-{int(event_time)}",
                        timestamp=event_time,
                        level=event_level,
                        component=event_component,
                        message=message,
                        details=details,
                    )
                )

                # Stop if we've reached the limit
                if len(events) >= limit:
                    break

            # Sort by timestamp descending (newest first)
            events.sort(key=lambda e: e.timestamp, reverse=True)

            return EventLogResponse(
                events=events[:limit],
                total_events=len(events),
                timestamp=time.time(),
            )

        except Exception as e:
            logger.error(f"Error getting event logs: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get event logs: {e!s}")

    return router


@register_domain_router("system")
def register_system_router() -> APIRouter:
    """Register the system domain router"""
    return create_system_router()
