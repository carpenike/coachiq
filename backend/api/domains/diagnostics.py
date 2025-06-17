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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.api.domains import register_domain_router
from backend.core.dependencies_v2 import get_feature_manager

logger = logging.getLogger(__name__)

# Domain-specific schemas for v2 API
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
    overall_health: str = Field(..., description="Overall system health: excellent/good/fair/poor/critical")
    health_score: float = Field(..., description="Health score 0-100")
    active_systems: list[str] = Field(..., description="List of active systems")
    degraded_systems: list[str] = Field(..., description="Systems with issues")
    last_assessment: float = Field(..., description="Last health assessment timestamp")

def create_diagnostics_router() -> APIRouter:
    """Create the diagnostics domain router with all endpoints"""
    router = APIRouter(tags=["diagnostics-v2"])

    def _check_domain_api_enabled(request: Request) -> None:
        """Check if diagnostics API v2 is enabled"""
        feature_manager = get_feature_manager(request)
        if not feature_manager.is_enabled("domain_api_v2"):
            raise HTTPException(
                status_code=404,
                detail="Domain API v2 is disabled. Enable with COACHIQ_FEATURES__DOMAIN_API_V2=true"
            )
        if not feature_manager.is_enabled("diagnostics_api_v2"):
            raise HTTPException(
                status_code=404,
                detail="Diagnostics API v2 is disabled. Enable with COACHIQ_FEATURES__DIAGNOSTICS_API_V2=true"
            )

    async def get_diagnostics_feature(request: Request):
        """Get advanced diagnostics feature for domain API v2"""
        _check_domain_api_enabled(request)

        feature_manager = get_feature_manager(request)
        feature = feature_manager.get_feature("advanced_diagnostics")

        if not feature or not feature.is_healthy():
            raise HTTPException(
                status_code=503,
                detail="Advanced diagnostics feature not available"
            )

        return feature

    @router.get("/health")
    async def health_check(request: Request) -> dict[str, Any]:
        """Health check endpoint for diagnostics domain API"""
        _check_domain_api_enabled(request)

        return {
            "status": "healthy",
            "domain": "diagnostics",
            "version": "v2",
            "features": {
                "real_time_monitoring": True,
                "predictive_alerts": True,
                "cross_protocol_analysis": True,
            },
            "timestamp": "2025-01-11T00:00:00Z"
        }

    @router.get("/schemas")
    async def get_schemas(request: Request) -> dict[str, Any]:
        """Export schemas for diagnostics domain"""
        _check_domain_api_enabled(request)

        return {
            "message": "Diagnostics schemas will be implemented in Phase 2",
            "available_endpoints": ["/health", "/schemas", "/metrics", "/faults", "/system-status"]
        }

    @router.get("/metrics", response_model=SystemMetrics)
    async def get_system_metrics(
        request: Request,
        feature=Depends(get_diagnostics_feature)
    ) -> SystemMetrics:
        """Get real-time system performance metrics"""
        try:
            # Get metrics from diagnostics feature
            status = feature.get_status()

            # Extract performance metrics with safe defaults
            stats = status.get("statistics", {})

            return SystemMetrics(
                cpu_usage=0.0,  # Would be implemented via psutil in production
                memory_usage=0.0,  # Would be implemented via psutil in production
                can_bus_load=stats.get("can_bus_load", 0.0),
                message_rate=stats.get("message_rate", 0.0),
                error_rate=stats.get("error_rate", 0.0),
                uptime_seconds=time.time() - stats.get("startup_time", time.time()),
                timestamp=time.time()
            )
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get metrics: {e!s}")

    @router.get("/faults", response_model=FaultSummary)
    async def get_fault_summary(
        request: Request,
        system_type: str | None = Query(None, description="Filter by system type"),
        severity: str | None = Query(None, description="Filter by severity"),
        feature=Depends(get_diagnostics_feature)
    ) -> FaultSummary:
        """Get fault summary with domain-specific aggregations"""
        try:
            # Use existing DTC functionality
            dtc_dicts = []
            if hasattr(feature, "handler") and feature.handler:
                dtcs = feature.handler.get_active_dtcs()
                dtc_dicts = [dtc.to_dict() for dtc in dtcs]

            # Apply filters
            filtered_dtcs = dtc_dicts
            if system_type:
                filtered_dtcs = [dtc for dtc in filtered_dtcs if dtc.get("system_type") == system_type]
            if severity:
                filtered_dtcs = [dtc for dtc in filtered_dtcs if dtc.get("severity") == severity]

            # Compute aggregations
            active_faults = len([dtc for dtc in filtered_dtcs if not dtc.get("resolved", False)])
            critical_faults = len([dtc for dtc in filtered_dtcs if dtc.get("severity") == "critical"])

            by_system = {}
            by_protocol = {}
            for dtc in filtered_dtcs:
                system = dtc.get("system_type", "unknown")
                protocol = dtc.get("protocol", "unknown")
                by_system[system] = by_system.get(system, 0) + 1
                by_protocol[protocol] = by_protocol.get(protocol, 0) + 1

            return FaultSummary(
                active_faults=active_faults,
                total_faults=len(filtered_dtcs),
                critical_faults=critical_faults,
                by_system=by_system,
                by_protocol=by_protocol,
                last_updated=time.time()
            )
        except Exception as e:
            logger.error(f"Error getting fault summary: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get faults: {e!s}")

    @router.get("/system-status", response_model=SystemStatus)
    async def get_system_status(
        request: Request,
        feature=Depends(get_diagnostics_feature)
    ) -> SystemStatus:
        """Get overall system health status"""
        try:
            health_data = feature.get_system_health()

            # Compute overall health assessment
            health_score = 100.0  # Default healthy
            degraded_systems = []
            active_systems = list(health_data.keys()) if health_data else ["rvc", "entity_manager"]

            # Calculate health score based on system statuses
            if health_data:
                system_scores = []
                for system, data in health_data.items():
                    score = data.get("health_score", 100.0)
                    system_scores.append(score)
                    if score < 80.0:
                        degraded_systems.append(system)

                health_score = sum(system_scores) / len(system_scores) if system_scores else 100.0

            # Determine overall health status
            if health_score >= 90:
                overall_health = "excellent"
            elif health_score >= 75:
                overall_health = "good"
            elif health_score >= 60:
                overall_health = "fair"
            elif health_score >= 40:
                overall_health = "poor"
            else:
                overall_health = "critical"

            return SystemStatus(
                overall_health=overall_health,
                health_score=health_score,
                active_systems=active_systems,
                degraded_systems=degraded_systems,
                last_assessment=time.time()
            )
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get system status: {e!s}")

    @router.get("/dtcs")
    async def get_dtcs(
        request: Request,
        system_type: str | None = Query(None, description="Filter by system type"),
        severity: str | None = Query(None, description="Filter by severity"),
        protocol: str | None = Query(None, description="Filter by protocol"),
        feature=Depends(get_diagnostics_feature)
    ) -> dict[str, Any]:
        """Get diagnostic trouble codes"""
        try:
            # Get DTCs from diagnostics feature
            dtc_dicts = []
            if hasattr(feature, "handler") and feature.handler:
                dtcs = feature.handler.get_active_dtcs()
                dtc_dicts = [dtc.to_dict() for dtc in dtcs]

            # Apply filters
            filtered_dtcs = dtc_dicts
            if system_type:
                filtered_dtcs = [dtc for dtc in filtered_dtcs if dtc.get("system_type") == system_type]
            if severity:
                filtered_dtcs = [dtc for dtc in filtered_dtcs if dtc.get("severity") == severity]
            if protocol:
                filtered_dtcs = [dtc for dtc in filtered_dtcs if dtc.get("protocol") == protocol]

            # Return DTCCollection format expected by frontend
            active_count = len([dtc for dtc in filtered_dtcs if not dtc.get("resolved", False)])

            by_severity = {}
            by_protocol = {}
            for dtc in filtered_dtcs:
                sev = dtc.get("severity", "unknown")
                proto = dtc.get("protocol", "unknown")
                by_severity[sev] = by_severity.get(sev, 0) + 1
                by_protocol[proto] = by_protocol.get(proto, 0) + 1

            return {
                "dtcs": filtered_dtcs,
                "total_count": len(filtered_dtcs),
                "active_count": active_count,
                "by_severity": by_severity,
                "by_protocol": by_protocol
            }
        except Exception as e:
            logger.error(f"Error getting DTCs: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get DTCs: {e!s}")

    @router.post("/dtcs/resolve")
    async def resolve_dtc(
        request: Request,
        body: dict[str, Any],
        feature=Depends(get_diagnostics_feature)
    ) -> dict[str, bool]:
        """Resolve a diagnostic trouble code"""
        try:
            protocol = body.get("protocol")
            code = body.get("code")
            source_address = body.get("source_address", 0)

            # Resolve via diagnostics feature
            resolved = False
            if hasattr(feature, "handler") and feature.handler:
                resolved = feature.handler.resolve_dtc(protocol, code, source_address)

            return {"resolved": resolved}
        except Exception as e:
            logger.error(f"Error resolving DTC: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to resolve DTC: {e!s}")

    @router.get("/statistics")
    async def get_statistics(
        request: Request,
        feature=Depends(get_diagnostics_feature)
    ) -> dict[str, Any]:
        """Get diagnostic statistics"""
        try:
            status = feature.get_status()
            stats = status.get("statistics", {})

            # Return in v2 format expected by frontend
            return {
                "metrics": {
                    "total_dtcs": stats.get("total_dtcs", 0),
                    "active_dtcs": stats.get("active_dtcs", 0),
                    "resolved_dtcs": stats.get("resolved_dtcs", 0),
                    "processing_rate": stats.get("processing_rate", 0.0),
                    "system_health_trend": stats.get("system_health_trend", "stable")
                },
                "correlation": {
                    "accuracy": stats.get("correlation_accuracy", 0.0)
                },
                "prediction": {
                    "accuracy": stats.get("prediction_accuracy", 0.0)
                }
            }
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get statistics: {e!s}")

    @router.get("/correlations")
    async def get_correlations(
        request: Request,
        time_window_seconds: float | None = Query(60.0, description="Time window for correlation analysis"),
        feature=Depends(get_diagnostics_feature)
    ) -> list[dict[str, Any]]:
        """Get fault correlations"""
        try:
            # Get correlations from diagnostics feature
            correlations = []
            if hasattr(feature, "handler") and feature.handler:
                raw_correlations = feature.handler.get_fault_correlations(time_window_seconds)
                correlations = [corr.to_dict() for corr in raw_correlations]

            return correlations
        except Exception as e:
            logger.error(f"Error getting correlations: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get correlations: {e!s}")

    @router.get("/predictions")
    async def get_predictions(
        request: Request,
        time_horizon_days: int = Query(90, description="Time horizon for predictions in days"),
        feature=Depends(get_diagnostics_feature)
    ) -> list[dict[str, Any]]:
        """Get maintenance predictions"""
        try:
            # Get predictions from diagnostics feature
            predictions = []
            if hasattr(feature, "handler") and feature.handler:
                raw_predictions = feature.handler.get_maintenance_predictions(time_horizon_days)
                predictions = [pred.to_dict() for pred in raw_predictions]

            return predictions
        except Exception as e:
            logger.error(f"Error getting predictions: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get predictions: {e!s}")

    return router

@register_domain_router("diagnostics")
def register_diagnostics_router(app_state) -> APIRouter:
    """Register the diagnostics domain router"""
    return create_diagnostics_router()
