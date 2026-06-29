"""
Diagnostics Domain API Router (v2)

Provides domain-specific diagnostic endpoints with enhanced capabilities:
- Real-time fault monitoring and correlation
- Predictive maintenance integration
- Cross-protocol DTC analysis
- Enhanced reporting and alerting

This router integrates with existing diagnostic services.
"""

import logging
import time
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.api.domains import register_domain_router
from backend.core.dependencies import get_service_registry
from backend.core.service_registry import ServiceRegistry, ServiceStatus
from backend.integrations.diagnostics.handler import DiagnosticHandler
from backend.integrations.diagnostics.models import ProtocolType
from backend.schemas.domain_api import (
    DiagnosticAccuracySummary,
    DiagnosticHealthTrend,
    DiagnosticsHealthResponse,
    DiagnosticsServiceFeatures,
    DiagnosticStatisticsMetrics,
    DiagnosticStatisticsResponse,
    DiagnosticTroubleCodeCollection,
)

logger = logging.getLogger(__name__)

EXCELLENT_HEALTH_THRESHOLD = 90.0
GOOD_HEALTH_THRESHOLD = 75.0
FAIR_HEALTH_THRESHOLD = 60.0
POOR_HEALTH_THRESHOLD = 40.0
DEGRADED_HEALTH_THRESHOLD = 75.0


def _get_optional_registry() -> ServiceRegistry | None:
    """Return the ServiceRegistry when available for request-time diagnostics."""
    try:
        return get_service_registry()
    except RuntimeError:
        return None


def _get_optional_service(service_name: str) -> Any | None:
    """Return an optional ServiceRegistry service without failing the endpoint."""
    service_registry = _get_optional_registry()
    if service_registry is None or not service_registry.has_service(service_name):
        return None
    return service_registry.get_service(service_name)


def get_diagnostics_handler() -> DiagnosticHandler | None:
    """Get the registered diagnostics handler for v2 diagnostics endpoints."""
    return cast("DiagnosticHandler | None", _get_optional_service("diagnostic_handler"))


def get_optional_can_facade() -> Any | None:
    """Get the CAN facade for computed diagnostics health when available."""
    return _get_optional_service("can_facade")


def _overall_health_from_score(health_score: float) -> str:
    """Map a numeric score to the v2 diagnostics health enum."""
    if health_score >= EXCELLENT_HEALTH_THRESHOLD:
        return "excellent"
    if health_score >= GOOD_HEALTH_THRESHOLD:
        return "good"
    if health_score >= FAIR_HEALTH_THRESHOLD:
        return "fair"
    if health_score >= POOR_HEALTH_THRESHOLD:
        return "poor"
    return "critical"


def _dtc_dicts(handler: DiagnosticHandler | None) -> list[dict[str, Any]]:
    """Return active DTCs from the diagnostics handler as dictionaries."""
    if handler is None:
        return []
    return [dtc.to_dict() for dtc in handler.get_active_dtcs()]


def _filter_dtcs(
    dtcs: list[dict[str, Any]],
    system_type: str | None = None,
    severity: str | None = None,
    protocol: str | None = None,
) -> list[dict[str, Any]]:
    """Filter DTC dictionaries by common query parameters."""
    filtered_dtcs = dtcs
    if system_type:
        filtered_dtcs = [dtc for dtc in filtered_dtcs if dtc.get("system_type") == system_type]
    if severity:
        filtered_dtcs = [dtc for dtc in filtered_dtcs if dtc.get("severity") == severity]
    if protocol:
        filtered_dtcs = [dtc for dtc in filtered_dtcs if dtc.get("protocol") == protocol]
    return filtered_dtcs


def _count_by(dtcs: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    """Count DTC dictionaries by a string field."""
    counts: dict[str, int] = {}
    for dtc in dtcs:
        key = str(dtc.get(field_name, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return counts


async def _service_score(service_registry: ServiceRegistry, service_name: str) -> float | None:
    """Return a health score for a registered service, or None when absent."""
    if not service_registry.has_service(service_name):
        return None
    status = await service_registry.check_service_health(service_name)
    if status == ServiceStatus.HEALTHY:
        return 100.0
    if status == ServiceStatus.DEGRADED:
        return 65.0
    if status == ServiceStatus.FAILED:
        return 0.0
    return 40.0


def _can_health_score(can_facade: Any | None) -> tuple[float | None, bool]:
    """Return CAN health score and degraded flag from CANFacade health."""
    if can_facade is None or not hasattr(can_facade, "get_health_status"):
        return None, True
    status = can_facade.get_health_status()
    if status.get("emergency_stop_active"):
        return 20.0, True
    if not status.get("healthy", False):
        return 40.0, True
    if str(status.get("safety_status", "")).lower() == "degraded":
        return 75.0, True
    return 100.0, False


async def _compute_system_status(
    diagnostics_handler: DiagnosticHandler | None, can_facade: Any | None
) -> "SystemStatus":
    """Compute v2 diagnostics system status from registered services and DTCs."""
    service_registry = _get_optional_registry()
    active_systems: list[str] = []
    degraded_systems: list[str] = []
    scores: list[float] = []

    can_score, can_degraded = _can_health_score(can_facade)
    if can_score is not None:
        active_systems.append("can_bus")
        scores.append(can_score)
        if can_degraded:
            degraded_systems.append("can_bus")

    if diagnostics_handler is not None:
        active_systems.append("diagnostics")
        active_dtcs = len(diagnostics_handler.get_active_dtcs())
        diagnostics_score = max(0.0, 100.0 - (active_dtcs * 10.0))
        scores.append(diagnostics_score)
        if active_dtcs:
            degraded_systems.append("diagnostics")

    if service_registry is not None:
        for service_name, system_name in [
            ("entity_service", "entities"),
            ("websocket_manager", "websocket"),
            ("persistence_service", "persistence"),
        ]:
            score = await _service_score(service_registry, service_name)
            if score is None:
                continue
            active_systems.append(system_name)
            scores.append(score)
            if score < DEGRADED_HEALTH_THRESHOLD:
                degraded_systems.append(system_name)

    if not scores:
        degraded_systems.append("service_registry")
        scores.append(0.0)

    health_score = sum(scores) / len(scores)
    return SystemStatus(
        overall_health=_overall_health_from_score(health_score),
        health_score=health_score,
        active_systems=active_systems,
        degraded_systems=degraded_systems,
        last_assessment=time.time(),
    )


# Domain-specific schemas for v1 API
class SystemMetrics(BaseModel):
    """System performance metrics for diagnostics"""

    cpu_usage: float = Field(..., description="CPU usage percentage 0-100")
    memory_usage: float = Field(..., description="Memory usage percentage 0-100")
    can_bus_load: float = Field(..., description="CAN bus load percentage 0-100")
    message_rate: float = Field(..., description="Messages per second")
    error_rate: float = Field(..., description="Error rate percentage 0-100")
    uptime_seconds: float = Field(..., description="System uptime in seconds")
    timestamp: float = Field(..., description="Metrics timestamp")


class FaultSummary(BaseModel):
    """Fault and DTC summary for diagnostics"""

    active_faults: int = Field(..., description="Number of active faults")
    total_faults: int = Field(..., description="Total fault count")
    critical_faults: int = Field(..., description="Critical severity faults")
    by_system: dict[str, int] = Field(..., description="Faults by system type")
    by_protocol: dict[str, int] = Field(..., description="Faults by protocol")
    last_updated: float = Field(..., description="Last update timestamp")


class SystemStatus(BaseModel):
    """Overall system health status"""

    overall_health: str = Field(
        ..., description="Overall system health: excellent/good/fair/poor/critical"
    )
    health_score: float = Field(..., description="Health score 0-100")
    active_systems: list[str] = Field(..., description="List of active systems")
    degraded_systems: list[str] = Field(..., description="Systems with issues")
    last_assessment: float = Field(..., description="Last health assessment timestamp")


DiagnosticsHandlerDependency = Annotated[DiagnosticHandler | None, Depends(get_diagnostics_handler)]
CANFacadeDependency = Annotated[Any | None, Depends(get_optional_can_facade)]
SystemTypeFilter = Annotated[str | None, Query(description="Filter by system type")]
SeverityFilter = Annotated[str | None, Query(description="Filter by severity")]
ProtocolFilter = Annotated[str | None, Query(description="Filter by protocol")]
CorrelationWindow = Annotated[
    float | None, Query(description="Time window for correlation analysis")
]
PredictionHorizon = Annotated[int, Query(description="Time horizon for predictions in days")]


def create_diagnostics_router() -> APIRouter:  # noqa: C901, PLR0915
    """Create the diagnostics domain router with all endpoints"""
    router = APIRouter(tags=["diagnostics"])

    @router.get("/health", response_model=DiagnosticsHealthResponse)
    async def health_check() -> DiagnosticsHealthResponse:
        """Health check endpoint for diagnostics domain API"""

        return DiagnosticsHealthResponse(
            status="healthy",
            domain="diagnostics",
            version="v2",
            diagnostics_services=DiagnosticsServiceFeatures(
                real_time_monitoring=True,
                predictive_alerts=True,
                cross_protocol_analysis=True,
            ),
            timestamp="2025-01-11T00:00:00Z",
        )

    @router.get("/schemas")
    async def get_schemas() -> dict[str, Any]:
        """Export schemas for diagnostics domain"""

        return {
            "message": "Diagnostics schemas will be implemented in Phase 2",
            "available_endpoints": ["/health", "/schemas", "/metrics", "/faults", "/system-status"],
        }

    @router.get("/metrics", response_model=SystemMetrics)
    async def get_system_metrics(can_facade: CANFacadeDependency = None) -> SystemMetrics:
        """Get real-time system performance metrics"""
        try:
            can_status = can_facade.get_health_status() if can_facade is not None else {}

            return SystemMetrics(
                cpu_usage=0.0,  # Would be implemented via psutil in production
                memory_usage=0.0,  # Would be implemented via psutil in production
                can_bus_load=0.0,
                message_rate=0.0,
                error_rate=0.0 if can_status.get("healthy", False) else 100.0,
                uptime_seconds=time.time(),
                timestamp=time.time(),
            )
        except Exception as e:
            logger.error("Error getting system metrics: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to get metrics: {e!s}") from e

    @router.get("/faults", response_model=FaultSummary)
    async def get_fault_summary(
        system_type: SystemTypeFilter = None,
        severity: SeverityFilter = None,
        diagnostics_handler: DiagnosticsHandlerDependency = None,
    ) -> FaultSummary:
        """Get fault summary with domain-specific aggregations"""
        try:
            filtered_dtcs = _filter_dtcs(_dtc_dicts(diagnostics_handler), system_type, severity)
            active_faults = len([dtc for dtc in filtered_dtcs if not dtc.get("resolved", False)])
            critical_faults = len(
                [dtc for dtc in filtered_dtcs if dtc.get("severity") == "critical"]
            )

            return FaultSummary(
                active_faults=active_faults,
                total_faults=len(filtered_dtcs),
                critical_faults=critical_faults,
                by_system=_count_by(filtered_dtcs, "system_type"),
                by_protocol=_count_by(filtered_dtcs, "protocol"),
                last_updated=time.time(),
            )
        except Exception as e:
            logger.error("Error getting fault summary: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to get faults: {e!s}") from e

    @router.get("/system-status", response_model=SystemStatus)
    async def get_system_status(
        diagnostics_handler: DiagnosticsHandlerDependency = None,
        can_facade: CANFacadeDependency = None,
    ) -> SystemStatus:
        """Get overall system health status"""
        try:
            return await _compute_system_status(diagnostics_handler, can_facade)
        except Exception as e:
            logger.error("Error getting system status: %s", e)
            raise HTTPException(
                status_code=500, detail=f"Failed to get system status: {e!s}"
            ) from e

    @router.get("/dtcs", response_model=DiagnosticTroubleCodeCollection)
    async def get_dtcs(
        system_type: SystemTypeFilter = None,
        severity: SeverityFilter = None,
        protocol: ProtocolFilter = None,
        diagnostics_handler: DiagnosticsHandlerDependency = None,
    ) -> DiagnosticTroubleCodeCollection:
        """Get diagnostic trouble codes"""
        try:
            filtered_dtcs = _filter_dtcs(
                _dtc_dicts(diagnostics_handler), system_type, severity, protocol
            )
            active_count = len([dtc for dtc in filtered_dtcs if not dtc.get("resolved", False)])

            return DiagnosticTroubleCodeCollection(
                dtcs=filtered_dtcs,
                total_count=len(filtered_dtcs),
                active_count=active_count,
                by_severity=_count_by(filtered_dtcs, "severity"),
                by_protocol=_count_by(filtered_dtcs, "protocol"),
            )
        except Exception as e:
            logger.error("Error getting DTCs: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to get DTCs: {e!s}") from e

    @router.post("/dtcs/resolve")
    async def resolve_dtc(
        body: dict[str, Any],
        diagnostics_handler: DiagnosticsHandlerDependency = None,
    ) -> dict[str, bool]:
        """Resolve a diagnostic trouble code"""
        try:
            if diagnostics_handler is None:
                return {"resolved": False}

            protocol = body.get("protocol")
            code = body.get("code")
            source_address = body.get("source_address", 0)
            if protocol is None or code is None:
                return {"resolved": False}

            resolved = diagnostics_handler.resolve_dtc(
                int(code), ProtocolType(str(protocol)), int(source_address)
            )

            return {"resolved": resolved}
        except Exception as e:
            logger.error("Error resolving DTC: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to resolve DTC: {e!s}") from e

    @router.get("/statistics", response_model=DiagnosticStatisticsResponse)
    async def get_statistics(
        diagnostics_handler: DiagnosticsHandlerDependency = None,
    ) -> DiagnosticStatisticsResponse:
        """Get diagnostic statistics"""

        def normalize_health_trend(value: object) -> DiagnosticHealthTrend:
            """Normalize dynamic service health trends to the documented frontend enum."""
            if isinstance(value, str) and value in {"improving", "stable", "degrading"}:
                return cast("DiagnosticHealthTrend", value)
            return "stable"

        try:
            stats = diagnostics_handler.get_diagnostic_statistics() if diagnostics_handler else {}
            processing_stats = stats.get("processing_stats", {})
            active_dtcs = int(stats.get("active_dtcs", 0))
            resolved_dtcs = int(stats.get("historical_dtcs", 0))

            return DiagnosticStatisticsResponse(
                metrics=DiagnosticStatisticsMetrics(
                    total_dtcs=active_dtcs + resolved_dtcs,
                    active_dtcs=active_dtcs,
                    resolved_dtcs=resolved_dtcs,
                    processing_rate=float(processing_stats.get("dtcs_processed", 0)),
                    system_health_trend=normalize_health_trend(
                        stats.get("system_health_trend", "stable")
                    ),
                ),
                correlation=DiagnosticAccuracySummary(accuracy=0.0),
                prediction=DiagnosticAccuracySummary(accuracy=0.0),
            )
        except Exception as e:
            logger.error("Error getting statistics: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to get statistics: {e!s}") from e

    @router.get("/correlations")
    async def get_correlations(
        time_window_seconds: CorrelationWindow = 60.0,
        diagnostics_handler: DiagnosticsHandlerDependency = None,
    ) -> list[dict[str, Any]]:
        """Get fault correlations"""
        try:
            if diagnostics_handler is None:
                return []
            raw_correlations = diagnostics_handler.get_fault_correlations(time_window_seconds)
            return [corr.to_dict() for corr in raw_correlations]
        except Exception as e:
            logger.error("Error getting correlations: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to get correlations: {e!s}") from e

    @router.get("/predictions")
    async def get_predictions(
        time_horizon_days: PredictionHorizon = 90,
    ) -> list[dict[str, Any]]:
        """Get maintenance predictions"""
        try:
            _ = time_horizon_days
            return []
        except Exception as e:
            logger.error("Error getting predictions: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to get predictions: {e!s}") from e

    return router


@register_domain_router("diagnostics")
def register_diagnostics_router() -> APIRouter:
    """Register the diagnostics domain router"""
    return create_diagnostics_router()
