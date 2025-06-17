"""
Enhanced Health Check API Router

Provides comprehensive health monitoring endpoints that expose ServiceRegistry
health information and aggregate service status across the application.

Part of Phase 2D: Health Check System Enhancement
"""

import time
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional
from enum import Enum

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from backend.core.dependencies_v2 import (
    get_app_state,
    get_feature_manager,
)
from backend.core.service_registry import ServiceStatus
from backend.core.config import get_settings


class HealthStatus(str, Enum):
    """Overall health status following IETF health+json standard."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class ServiceHealthDetail(BaseModel):
    """Detailed health information for a single service."""
    name: str
    status: ServiceStatus
    health_status: HealthStatus
    message: Optional[str] = None
    last_check: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class ComponentHealth(BaseModel):
    """Health status of a system component."""
    component_name: str
    component_type: str
    status: HealthStatus
    observed_value: Optional[Any] = None
    observed_unit: Optional[str] = None
    message: Optional[str] = None
    action: Optional[str] = None
    output: Optional[str] = None
    checks: Optional[Dict[str, Dict[str, Any]]] = None


class HealthCheckResponse(BaseModel):
    """IETF-compliant health check response."""
    status: HealthStatus
    version: str = "1"
    service_id: str
    description: str
    timestamp: datetime
    notes: Optional[List[str]] = None
    output: Optional[str] = None
    checks: Optional[Dict[str, ComponentHealth]] = None
    links: Optional[Dict[str, str]] = None
    service_registry: Optional[Dict[str, Any]] = None
    startup_metrics: Optional[Dict[str, Any]] = None


router = APIRouter(
    prefix="/api/health",
    tags=["health", "monitoring"],
    responses={
        503: {"description": "Service unavailable"},
        500: {"description": "Internal server error"},
    },
)


def service_status_to_health(status: ServiceStatus) -> HealthStatus:
    """Convert ServiceStatus to IETF HealthStatus."""
    if status == ServiceStatus.HEALTHY:
        return HealthStatus.PASS
    elif status in (ServiceStatus.DEGRADED, ServiceStatus.STARTING):
        return HealthStatus.WARN
    else:
        return HealthStatus.FAIL


@router.get(
    "",
    summary="Comprehensive health check",
    description="Returns detailed health status including ServiceRegistry information",
    response_class=Response,
)
async def health_check(
    request: Request,
    include_registry: bool = Query(True, description="Include ServiceRegistry details"),
    include_metrics: bool = Query(True, description="Include startup metrics"),
    include_components: bool = Query(True, description="Include component health details"),
) -> Response:
    """
    Comprehensive health check endpoint that aggregates health status from:
    - ServiceRegistry (all registered services)
    - Feature Manager (feature health)
    - Core infrastructure components
    - Safety-critical systems

    This endpoint provides a complete view of system health for monitoring
    and alerting systems.
    """
    start_time = time.time()

    try:
        # Get dependencies
        app_state = get_app_state(request)
        service_registry = app_state.service_registry
        feature_manager = get_feature_manager(request)
        settings = get_settings()

        # Initialize response components
        overall_status = HealthStatus.PASS
        notes = []
        checks = {}

        # 1. Check ServiceRegistry health
        if include_registry:
            registry_health = await check_service_registry_health(service_registry)
            if registry_health["status"] != HealthStatus.PASS:
                overall_status = max_health_status(overall_status, registry_health["status"])
                notes.append(f"ServiceRegistry: {registry_health['message']}")

            if include_components:
                checks["service_registry"] = ComponentHealth(
                    component_name="service_registry",
                    component_type="core",
                    status=registry_health["status"],
                    message=registry_health["message"],
                    observed_value=registry_health["healthy_count"],
                    observed_unit="services",
                    checks=registry_health.get("service_details"),
                )

        # 2. Check Feature Manager health
        if feature_manager:
            feature_health = await check_feature_manager_health(feature_manager)
            if feature_health["status"] != HealthStatus.PASS:
                overall_status = max_health_status(overall_status, feature_health["status"])
                notes.append(f"FeatureManager: {feature_health['message']}")

            if include_components:
                checks["feature_manager"] = ComponentHealth(
                    component_name="feature_manager",
                    component_type="core",
                    status=feature_health["status"],
                    message=feature_health["message"],
                    observed_value=feature_health["healthy_count"],
                    observed_unit="features",
                )

        # 3. Check critical services
        critical_services = ["persistence_service", "database_manager", "entity_service"]
        for service_name in critical_services:
            if service_registry.has_service(service_name):
                service = service_registry.get_service(service_name)
                if hasattr(service, "check_health"):
                    try:
                        await service.check_health()
                        service_status = HealthStatus.PASS
                        message = "Service operational"
                    except Exception as e:
                        service_status = HealthStatus.FAIL
                        message = f"Health check failed: {str(e)}"
                        overall_status = HealthStatus.FAIL
                        notes.append(f"{service_name}: {message}")

                    if include_components:
                        checks[service_name] = ComponentHealth(
                            component_name=service_name,
                            component_type="critical_service",
                            status=service_status,
                            message=message,
                        )

        # 4. Check safety-critical components if enabled
        if hasattr(app_state, "safety_service") and app_state.safety_service:
            safety_health = await check_safety_service_health(app_state.safety_service)
            if safety_health["status"] == HealthStatus.FAIL:
                overall_status = HealthStatus.FAIL
                notes.append("Safety service critical failure")

            if include_components:
                checks["safety_service"] = ComponentHealth(
                    component_name="safety_service",
                    component_type="safety_critical",
                    status=safety_health["status"],
                    message=safety_health["message"],
                    action=safety_health.get("action"),
                )

        # Build response
        response = HealthCheckResponse(
            status=overall_status,
            service_id=f"coachiq-{settings.environment}",
            description=get_health_description(overall_status),
            timestamp=datetime.now(UTC),
            notes=notes if notes else None,
            checks=checks if include_components else None,
        )

        # Add ServiceRegistry details if requested
        if include_registry:
            registry_status = await service_registry.get_health_status()
            response.service_registry = {
                "total_services": len(service_registry.list_services()),
                "service_counts": {
                    status.value: count
                    for status, count in service_registry.get_service_count_by_status().items()
                },
                "services": [
                    {
                        "name": name,
                        "status": status.value,
                        "health": service_status_to_health(status).value,
                    }
                    for name, status in registry_status.items()
                ],
            }

        # Add startup metrics if requested
        if include_metrics:
            metrics = service_registry.get_startup_metrics()
            if metrics:
                metrics["health_check_duration_ms"] = round(
                    (time.time() - start_time) * 1000, 2
                )
                response.startup_metrics = metrics

        # Add useful links
        response.links = {
            "self": str(request.url),
            "health_docs": "/docs#/health",
            "metrics": "/metrics",
            "system_status": "/api/v2/system/status",
        }

        # Determine status code based on health
        status_code = 200 if overall_status == HealthStatus.PASS else 503

        return Response(
            content=response.model_dump_json(exclude_none=True),
            status_code=status_code,
            media_type="application/health+json",
        )

    except Exception as e:
        # Even on error, return a valid health response
        error_response = HealthCheckResponse(
            status=HealthStatus.FAIL,
            service_id="coachiq",
            description=f"Health check error: {str(e)}",
            timestamp=datetime.now(UTC),
            notes=[f"Exception: {type(e).__name__}"],
        )

        # Return error as response
        return Response(
            content=error_response.model_dump_json(exclude_none=True),
            status_code=503,
            media_type="application/health+json",
        )


@router.get(
    "/services",
    response_model=List[ServiceHealthDetail],
    summary="Individual service health status",
    description="Returns health status for all registered services",
)
async def service_health_status(
    request: Request,
    service_name: Optional[str] = Query(None, description="Filter by service name"),
    status: Optional[ServiceStatus] = Query(None, description="Filter by status"),
) -> List[ServiceHealthDetail]:
    """
    Get detailed health status for individual services.

    This endpoint provides granular health information for each service
    registered with the ServiceRegistry, including their current status
    and any health check results.
    """
    app_state = get_app_state(request)
    service_registry = app_state.service_registry

    # Get all service statuses
    health_status = await service_registry.get_health_status()

    services = []
    for name, svc_status in health_status.items():
        # Apply filters
        if service_name and name != service_name:
            continue
        if status and svc_status != status:
            continue

        # Get service instance for additional health details
        health_detail = ServiceHealthDetail(
            name=name,
            status=svc_status,
            health_status=service_status_to_health(svc_status),
            last_check=datetime.now(UTC),
        )

        # Try to get additional health metadata
        if service_registry.has_service(name):
            try:
                service = service_registry.get_service(name)

                # Check for health_details property
                if hasattr(service, "health_details"):
                    health_detail.metadata = service.health_details

                # Check for custom health message
                if hasattr(service, "health_message"):
                    health_detail.message = service.health_message

            except Exception as e:
                health_detail.message = f"Error retrieving service details: {str(e)}"

        services.append(health_detail)

    return services


@router.get(
    "/ready",
    summary="Readiness check with ServiceRegistry",
    description="Lightweight readiness check based on ServiceRegistry status",
)
async def readiness_check(
    request: Request,
    min_healthy_services: int = Query(
        3, description="Minimum number of healthy services required"
    ),
) -> Dict[str, Any]:
    """
    Lightweight readiness check that uses ServiceRegistry to determine
    if the application is ready to serve traffic.

    This is more efficient than the comprehensive health check and is
    suitable for high-frequency monitoring.
    """
    try:
        app_state = get_app_state(request)
        service_registry = app_state.service_registry

        # Get service counts
        status_counts = service_registry.get_service_count_by_status()
        healthy_count = status_counts.get(ServiceStatus.HEALTHY, 0)
        total_count = sum(status_counts.values())

        # Check if we have minimum healthy services
        is_ready = healthy_count >= min_healthy_services

        return {
            "ready": is_ready,
            "healthy_services": healthy_count,
            "total_services": total_count,
            "required_services": min_healthy_services,
            "service_breakdown": {
                status.value: count
                for status, count in status_counts.items()
                if count > 0
            },
        }

    except Exception as e:
        return {
            "ready": False,
            "error": str(e),
            "healthy_services": 0,
            "required_services": min_healthy_services,
        }


@router.get(
    "/startup",
    summary="Startup metrics and timing",
    description="Returns detailed startup performance metrics from ServiceRegistry",
)
async def startup_metrics(request: Request) -> Dict[str, Any]:
    """
    Get detailed startup metrics and timing information.

    This endpoint exposes the ServiceRegistry's startup performance data,
    useful for optimizing startup time and debugging initialization issues.
    """
    app_state = get_app_state(request)
    service_registry = app_state.service_registry
    metrics = service_registry.get_startup_metrics()

    # Add current uptime
    if app_start_time := getattr(request.app.state, "start_time", None):
        metrics["uptime_seconds"] = time.time() - app_start_time

    # Add initialization order if available
    if hasattr(service_registry, "_startup_stages"):
        metrics["startup_stages"] = [
            {
                "stage": stage,
                "services": list(services),
            }
            for stage, services in service_registry._startup_stages.items()
        ]

    return metrics


# Helper functions

async def check_service_registry_health(
    service_registry,
) -> Dict[str, Any]:
    """Check ServiceRegistry health and return standardized result."""
    try:
        status_counts = service_registry.get_service_count_by_status()
        healthy_count = status_counts.get(ServiceStatus.HEALTHY, 0)
        total_count = sum(status_counts.values())

        if healthy_count == total_count and total_count > 0:
            status = HealthStatus.PASS
            message = f"All {total_count} services healthy"
        elif healthy_count > 0:
            status = HealthStatus.WARN
            unhealthy = total_count - healthy_count
            message = f"{healthy_count}/{total_count} services healthy, {unhealthy} unhealthy"
        else:
            status = HealthStatus.FAIL
            message = f"No healthy services (0/{total_count})"

        # Get individual service details
        health_status = await service_registry.get_health_status()
        service_details = {}

        for name, svc_status in health_status.items():
            service_details[name] = {
                "status": service_status_to_health(svc_status).value,
                "service_status": svc_status.value,
            }

        return {
            "status": status,
            "message": message,
            "healthy_count": healthy_count,
            "total_count": total_count,
            "service_details": service_details,
        }

    except Exception as e:
        return {
            "status": HealthStatus.FAIL,
            "message": f"ServiceRegistry check failed: {str(e)}",
            "healthy_count": 0,
        }


async def check_feature_manager_health(feature_manager) -> Dict[str, Any]:
    """Check FeatureManager health and return standardized result."""
    try:
        features = feature_manager.get_all_features()
        healthy_count = sum(
            1 for f in features.values()
            if hasattr(f, "is_healthy") and f.is_healthy()
        )
        total_count = len(features)

        if healthy_count == total_count:
            status = HealthStatus.PASS
            message = f"All {total_count} features healthy"
        elif healthy_count > 0:
            status = HealthStatus.WARN
            message = f"{healthy_count}/{total_count} features healthy"
        else:
            status = HealthStatus.FAIL
            message = "No healthy features"

        return {
            "status": status,
            "message": message,
            "healthy_count": healthy_count,
            "total_count": total_count,
        }

    except Exception as e:
        return {
            "status": HealthStatus.FAIL,
            "message": f"FeatureManager check failed: {str(e)}",
            "healthy_count": 0,
        }


async def check_safety_service_health(safety_service) -> Dict[str, Any]:
    """Check SafetyService health with special handling for safety-critical status."""
    try:
        # SafetyService doesn't have check_health method yet
        # Check if it's initialized and has validator
        if hasattr(safety_service, "validator") and safety_service.validator:
            status = HealthStatus.PASS
            message = "Safety service operational"
            action = None
        else:
            status = HealthStatus.FAIL
            message = "Safety service not properly initialized"
            action = "Check safety service initialization"

        return {
            "status": status,
            "message": message,
            "action": action,
        }

    except Exception as e:
        return {
            "status": HealthStatus.FAIL,
            "message": f"Safety service check failed: {str(e)}",
            "action": "Investigate safety service immediately",
        }


def max_health_status(status1: HealthStatus, status2: HealthStatus) -> HealthStatus:
    """Return the worse health status (FAIL > WARN > PASS)."""
    priority = {HealthStatus.PASS: 0, HealthStatus.WARN: 1, HealthStatus.FAIL: 2}
    return status1 if priority[status1] >= priority[status2] else status2


def get_health_description(status: HealthStatus) -> str:
    """Get human-readable description for health status."""
    descriptions = {
        HealthStatus.PASS: "All systems operational",
        HealthStatus.WARN: "Some services degraded but system functional",
        HealthStatus.FAIL: "Critical services failed - system not fully operational",
    }
    return descriptions.get(status, "Unknown status")
