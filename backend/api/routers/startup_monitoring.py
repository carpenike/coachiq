"""
Startup Monitoring API Router

Phase 2M: Startup Performance Monitoring
Provides API endpoints for accessing startup performance metrics,
health validation results, and performance baseline comparisons.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request
from pydantic import BaseModel, Field

from backend.core.dependencies_v2 import get_feature_manager, get_service_registry
from backend.middleware.startup_monitoring import get_startup_monitor
from backend.core.service_registry_v2 import EnhancedServiceRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/startup", tags=["startup_monitoring"])


# Response Models

class StartupHealthStatus(BaseModel):
    """Startup health validation status."""

    healthy: bool = Field(..., description="Overall startup health status")
    total_startup_time_ms: float = Field(..., description="Total startup time in milliseconds")
    services_started: int = Field(..., description="Number of services successfully started")
    services_failed: int = Field(..., description="Number of services that failed to start")
    warnings: list[str] = Field(default_factory=list, description="Startup warnings")
    errors: list[str] = Field(default_factory=list, description="Startup errors")
    performance_grade: str = Field(..., description="Performance grade (A, B, C, D, F)")
    meets_baseline: bool = Field(..., description="Whether startup meets performance baseline")


class ServiceTimingInfo(BaseModel):
    """Service startup timing information."""

    name: str = Field(..., description="Service name")
    startup_time_ms: float = Field(..., description="Service startup time in milliseconds")
    success: bool = Field(..., description="Whether service started successfully")
    dependencies: list[str] = Field(default_factory=list, description="Service dependencies")
    tags: list[str] = Field(default_factory=list, description="Service tags")


class StartupPerformanceReport(BaseModel):
    """Comprehensive startup performance report."""

    total_startup_time_ms: float = Field(..., description="Total startup time")
    service_registry_time_ms: float = Field(..., description="ServiceRegistry initialization time")
    service_count: int = Field(..., description="Number of services")
    average_service_time_ms: float = Field(..., description="Average service startup time")
    slowest_services: list[ServiceTimingInfo] = Field(..., description="5 slowest services")
    baseline_comparison: Dict[str, Any] = Field(..., description="Baseline performance comparison")
    health_checks: Dict[str, bool] = Field(..., description="Component health check results")
    warnings: list[str] = Field(..., description="Performance warnings")
    errors: list[str] = Field(..., description="Performance errors")
    performance_analysis: Dict[str, Any] = Field(..., description="Performance analysis")


def _check_monitoring_enabled(request: Request) -> None:
    """Check if startup monitoring features are enabled."""
    feature_manager = get_feature_manager(request)
    if not feature_manager.is_enabled("startup_monitoring"):
        raise HTTPException(
            status_code=404,
            detail="Startup monitoring features are disabled"
        )


def _get_startup_report_from_request(request: Request):
    """Safely get startup report from request state."""
    try:
        return getattr(request.state, 'startup_report', None)
    except AttributeError:
        return None


def _calculate_performance_grade(startup_time_ms: float, baseline_ms: float = 500.0) -> str:
    """Calculate performance grade based on startup time."""
    if startup_time_ms <= baseline_ms:
        return "A"
    elif startup_time_ms <= baseline_ms * 1.2:
        return "B"
    elif startup_time_ms <= baseline_ms * 1.5:
        return "C"
    elif startup_time_ms <= baseline_ms * 2.0:
        return "D"
    else:
        return "F"


@router.get(
    "/health",
    response_model=StartupHealthStatus,
    summary="Get startup health status",
    description="Get overall startup health validation status and basic metrics.",
)
async def get_startup_health(
    request: Request,
    service_registry: EnhancedServiceRegistry = Depends(get_service_registry),
) -> StartupHealthStatus:
    """
    Get startup health validation status.

    Returns overall health status based on:
    - Service startup success rates
    - Total startup time vs baseline
    - Critical component availability
    - Performance warnings/errors
    """
    _check_monitoring_enabled(request)

    try:
        # Get startup monitor data
        monitor = get_startup_monitor()

        # Get service registry metrics
        registry_metrics = service_registry.get_startup_metrics()

        # Get startup report if available
        startup_report = _get_startup_report_from_request(request) if hasattr(request, 'state') else None

        # Calculate health metrics
        services_started = len([s for s in service_registry.list_services()])
        services_failed = len(registry_metrics.get("startup_errors", {}))
        total_time = registry_metrics.get("total_startup_time_ms", 0)

        # Determine overall health
        healthy = (
            services_failed == 0 and
            total_time < 1000 and  # Less than 1 second
            (startup_report is None or len(startup_report.errors) == 0)
        )

        # Get warnings and errors
        warnings = []
        errors = []

        if startup_report:
            warnings.extend(startup_report.warnings)
            errors.extend(startup_report.errors)

        if total_time > 500:  # Baseline exceeded
            warnings.append(f"Startup time {total_time:.1f}ms exceeds 500ms baseline")

        if services_failed > 0:
            errors.append(f"{services_failed} services failed to start")

        # Calculate performance grade
        performance_grade = _calculate_performance_grade(total_time)
        meets_baseline = total_time <= 500

        return StartupHealthStatus(
            healthy=healthy,
            total_startup_time_ms=total_time,
            services_started=services_started,
            services_failed=services_failed,
            warnings=warnings,
            errors=errors,
            performance_grade=performance_grade,
            meets_baseline=meets_baseline,
        )

    except Exception as e:
        logger.error(f"Error getting startup health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/metrics",
    response_model=StartupPerformanceReport,
    summary="Get startup performance metrics",
    description="Get comprehensive startup performance metrics and analysis.",
)
async def get_startup_metrics(
    request: Request,
    service_registry: EnhancedServiceRegistry = Depends(get_service_registry),
) -> StartupPerformanceReport:
    """
    Get comprehensive startup performance metrics.

    Provides detailed analysis including:
    - Service-by-service timing breakdown
    - Performance baseline comparisons
    - Component health check results
    - Performance analysis and recommendations
    """
    _check_monitoring_enabled(request)

    try:
        # Get startup monitor and registry data
        monitor = get_startup_monitor()
        registry_metrics = service_registry.get_startup_metrics()
        startup_report = _get_startup_report_from_request(request)

        # Get service timings with metadata
        service_timings = service_registry.get_service_timings()
        slowest_services = []

        for service_name, timing in sorted(
            service_timings.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]:
            # Get service definition for metadata
            service_def = service_registry._service_definitions.get(service_name)
            dependencies = []
            tags = []

            if service_def:
                dependencies = [dep.name for dep in service_def.dependencies]
                tags = list(service_def.tags) if service_def.tags else []

            slowest_services.append(ServiceTimingInfo(
                name=service_name,
                startup_time_ms=timing,
                success=service_name in service_registry.list_services(),
                dependencies=dependencies,
                tags=tags,
            ))

        # Performance baseline comparison
        baseline_comparison = {
            "target_total_ms": 500.0,
            "actual_total_ms": registry_metrics.get("total_startup_time_ms", 0),
            "target_service_registry_ms": 120.0,
            "actual_service_registry_ms": getattr(service_registry, '_startup_time', 0) * 1000,
            "meets_target": registry_metrics.get("total_startup_time_ms", 0) <= 500.0,
        }

        # Health checks from startup report
        health_checks = {}
        if startup_report:
            health_checks = startup_report.health_check_results

        # Add service registry health
        health_checks["service_registry"] = len(registry_metrics.get("startup_errors", {})) == 0

        # Performance analysis
        total_time = registry_metrics.get("total_startup_time_ms", 0)
        service_count = registry_metrics.get("service_count", 0)

        performance_analysis = {
            "performance_grade": _calculate_performance_grade(total_time),
            "efficiency_score": min(100, max(0, 100 - (total_time - 500) / 10)),
            "bottlenecks": [
                service["name"] for service in slowest_services
                if service.startup_time_ms > 200
            ],
            "optimization_suggestions": [],
        }

        # Add optimization suggestions
        if total_time > 500:
            performance_analysis["optimization_suggestions"].append(
                "Consider optimizing service initialization order"
            )

        if len([s for s in slowest_services if s.startup_time_ms > 200]) > 0:
            performance_analysis["optimization_suggestions"].append(
                "Review slow service initialization functions"
            )

        # Get warnings and errors
        warnings = startup_report.warnings if startup_report else []
        errors = startup_report.errors if startup_report else []

        return StartupPerformanceReport(
            total_startup_time_ms=total_time,
            service_registry_time_ms=baseline_comparison["actual_service_registry_ms"],
            service_count=service_count,
            average_service_time_ms=registry_metrics.get("average_service_time_ms", 0),
            slowest_services=slowest_services,
            baseline_comparison=baseline_comparison,
            health_checks=health_checks,
            warnings=warnings,
            errors=errors,
            performance_analysis=performance_analysis,
        )

    except Exception as e:
        logger.error(f"Error getting startup metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/services",
    response_model=list[ServiceTimingInfo],
    summary="Get service startup timings",
    description="Get detailed timing information for all services.",
)
async def get_service_timings(
    request: Request,
    service_registry: EnhancedServiceRegistry = Depends(get_service_registry),
) -> list[ServiceTimingInfo]:
    """
    Get detailed service startup timing information.

    Returns timing data for each service including:
    - Startup time in milliseconds
    - Success/failure status
    - Dependencies
    - Service tags
    """
    _check_monitoring_enabled(request)

    try:
        service_timings = service_registry.get_service_timings()
        services_list = service_registry.list_services()

        timing_info = []

        for service_name, timing in service_timings.items():
            # Get service definition for metadata
            service_def = service_registry._service_definitions.get(service_name)
            dependencies = []
            tags = []

            if service_def:
                dependencies = [dep.name for dep in service_def.dependencies]
                tags = list(service_def.tags) if service_def.tags else []

            timing_info.append(ServiceTimingInfo(
                name=service_name,
                startup_time_ms=timing,
                success=service_name in services_list,
                dependencies=dependencies,
                tags=tags,
            ))

        # Sort by startup time (slowest first)
        timing_info.sort(key=lambda x: x.startup_time_ms, reverse=True)

        return timing_info

    except Exception as e:
        logger.error(f"Error getting service timings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/report",
    response_model=Dict[str, Any],
    summary="Get startup monitoring report",
    description="Get the complete startup monitoring report if available.",
)
async def get_startup_report(request: Request) -> Dict[str, Any]:
    """
    Get the complete startup monitoring report.

    Returns the detailed startup report generated by the monitoring middleware,
    including all phases, timings, and analysis.
    """
    _check_monitoring_enabled(request)

    try:
        startup_report = _get_startup_report_from_request(request)

        if not startup_report:
            raise HTTPException(
                status_code=404,
                detail="Startup report not available - application may still be starting"
            )

        return startup_report.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting startup report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/baseline-comparison",
    response_model=Dict[str, Any],
    summary="Get performance baseline comparison",
    description="Get comprehensive performance baseline comparison analysis.",
)
async def get_baseline_comparison(request: Request) -> Dict[str, Any]:
    """
    Get performance baseline comparison analysis.

    Provides detailed comparison against performance baselines including:
    - Component-level performance grades
    - Improvement recommendations
    - Regression alerts
    - Optimization scoring
    """
    _check_monitoring_enabled(request)

    try:
        # Get startup monitor and report
        monitor = get_startup_monitor()
        startup_report = _get_startup_report_from_request(request)

        if not startup_report:
            raise HTTPException(
                status_code=404,
                detail="Startup report not available for baseline comparison"
            )

        # Generate baseline comparison report
        baseline_report = monitor.generate_performance_baseline_report(startup_report)

        logger.info(
            f"Generated baseline comparison: grade={baseline_report['performance_grade']}, "
            f"score={baseline_report['optimization_score']:.1f}"
        )

        return baseline_report

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating baseline comparison: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
