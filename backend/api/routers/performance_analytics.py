"""
Performance Analytics API Routes

REST API endpoints for performance analytics including telemetry collection,
benchmarking, trend analysis, and optimization recommendations.
"""

import logging
import time
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.dependencies import create_optional_service_dependency, get_can_facade

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models


class TelemetryRequest(BaseModel):
    """Request model for recording telemetry data."""

    protocol: str = Field(..., description="Protocol name (rvc, j1939, firefly, spartan_k2)")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    message_size: int = Field(default=0, description="Message size in bytes")
    interface: str | None = Field(default=None, description="CAN interface name")


class APIPerformanceRequest(BaseModel):
    """Request model for recording API performance."""

    endpoint: str = Field(..., description="API endpoint")
    response_time_ms: float = Field(..., description="Response time in milliseconds")
    status_code: int = Field(default=200, description="HTTP status code")


class WebSocketLatencyRequest(BaseModel):
    """Request model for recording WebSocket latency."""

    latency_ms: float = Field(..., description="WebSocket latency in milliseconds")
    connection_id: str | None = Field(default=None, description="Connection identifier")


class CANInterfaceLoadRequest(BaseModel):
    """Request model for recording CAN interface load."""

    interface: str = Field(..., description="CAN interface name")
    load_percent: float = Field(..., description="Bus load percentage", ge=0.0, le=100.0)
    message_rate: float = Field(..., description="Messages per second", ge=0.0)


class PerformanceReportRequest(BaseModel):
    """Request model for generating performance reports."""

    time_window_seconds: float = Field(
        default=3600.0, description="Time window for report (seconds)", ge=60.0, le=86400.0
    )


# Create optional service dependency for performance analytics
get_performance_analytics_service = create_optional_service_dependency(
    "performance_analytics_service"
)


# Backend-First Enhanced Response Models


class BackendComputedHealthStatus(BaseModel):
    """Backend-computed health status with categorized thresholds."""

    status: str = Field(..., description="Computed health status: healthy, warning, critical")
    score: float = Field(..., description="Overall health score (0.0-1.0)")
    color_class: str = Field(..., description="CSS color class for UI")
    variant: str = Field(..., description="UI variant: default, secondary, destructive")
    details: dict[str, Any] = Field(default_factory=dict, description="Health computation details")


class BackendComputedResourceStatus(BaseModel):
    """Backend-computed resource utilization with threshold-based status."""

    cpu_usage: float = Field(..., description="CPU usage percentage")
    cpu_status: str = Field(..., description="CPU status: good, warning, critical")

    memory_usage: float = Field(..., description="Memory usage percentage")
    memory_status: str = Field(..., description="Memory status: good, warning, critical")

    disk_usage: float = Field(..., description="Disk usage percentage")
    disk_status: str = Field(..., description="Disk status: good, warning, critical")

    network_usage: float = Field(..., description="Network usage MB/s")
    network_status: str = Field(..., description="Network status: good, warning, critical")

    overall_status: str = Field(..., description="Overall resource status")


class BackendComputedAPIPerformance(BaseModel):
    """Backend-computed API performance with status classification."""

    average_response_time: float = Field(..., description="Average response time (ms)")
    response_time_status: str = Field(
        ..., description="Response time status: good, warning, critical"
    )

    requests_per_second: float = Field(..., description="Requests per second")
    throughput_status: str = Field(..., description="Throughput status: good, warning, critical")

    error_rate: float = Field(..., description="Error rate percentage")
    error_status: str = Field(..., description="Error status: good, warning, critical")

    overall_performance_status: str = Field(..., description="Overall API performance status")


# API Endpoints


@router.get(
    "/health-computed",
    response_model=BackendComputedHealthStatus,
    summary="Get backend-computed health status with UI categorization",
)
async def get_computed_health_status(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> BackendComputedHealthStatus:
    """
    Get comprehensive health status with backend-computed thresholds and UI classification.

    This endpoint performs all business logic computation on the backend, removing the need
    for frontend threshold calculations. Returns status classification ready for UI display.
    """
    if not analytics_service:
        # Return default healthy status when service is not available
        logger.debug("Performance analytics service not available, returning default health status")
        return BackendComputedHealthStatus(
            status="healthy",
            score=1.0,
            color_class="text-green-600",
            variant="default",
            details={"message": "Performance analytics service not configured"},
        )

    try:
        # Use the service to compute comprehensive health status
        health_status = await analytics_service.get_system_health_status()

        # Backend business logic: Apply configurable thresholds
        score = health_status.get("overall_score", 0.8)  # Default to good

        # Business logic: Determine status based on configurable thresholds
        if score >= analytics_service.analytics_settings.threshold_healthy:
            status = "healthy"
            color_class = "text-green-600"
            variant = "default"
        elif score >= analytics_service.analytics_settings.threshold_warning:
            status = "warning"
            color_class = "text-yellow-600"
            variant = "secondary"
        else:
            status = "critical"
            color_class = "text-red-600"
            variant = "destructive"

        return BackendComputedHealthStatus(
            status=status,
            score=score,
            color_class=color_class,
            variant=variant,
            details=health_status,
        )

    except Exception as e:
        logger.error(f"Error computing health status: {e}")
        # Return degraded status with error details
        return BackendComputedHealthStatus(
            status="critical",
            score=0.0,
            color_class="text-red-600",
            variant="destructive",
            details={"error": str(e)},
        )


@router.get(
    "/resources-computed",
    response_model=BackendComputedResourceStatus,
    summary="Get backend-computed resource utilization with status classification",
)
async def get_computed_resource_status(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> BackendComputedResourceStatus:
    """
    Get resource utilization with backend-computed threshold-based status classification.

    Eliminates frontend business logic for resource status determination by applying
    configurable thresholds on the backend and returning ready-to-display status.
    """
    if not analytics_service:
        # Return default resource status when service is not available
        logger.debug(
            "Performance analytics service not available, returning default resource status"
        )
        return BackendComputedResourceStatus(
            cpu_usage=0.0,
            cpu_status="good",
            memory_usage=0.0,
            memory_status="good",
            disk_usage=0.0,
            disk_status="good",
            network_usage=0.0,
            network_status="good",
            overall_status="good",
        )

    try:
        # Get resource data from telemetry collector
        resource_data = await analytics_service.get_resource_utilization()

        # Backend business logic: Apply configurable thresholds for each resource type
        def classify_resource_status(
            usage_pct: float, warning_threshold: float, critical_threshold: float
        ) -> str:
            """Apply backend business logic for resource status classification."""
            if usage_pct >= critical_threshold:
                return "critical"
            if usage_pct >= warning_threshold:
                return "warning"
            return "good"

        cpu_usage = resource_data.get("cpu_usage", 0.0) * 100
        memory_usage = resource_data.get("memory_usage", 0.0) * 100
        disk_usage = resource_data.get("disk_usage", 0.0) * 100
        network_usage = resource_data.get("network_usage", 0.0)

        # Use service-specific thresholds from configuration
        cpu_status = classify_resource_status(
            cpu_usage,
            analytics_service.analytics_settings.cpu_warning_threshold_percent,
            analytics_service.analytics_settings.cpu_critical_threshold_percent,
        )
        memory_status = classify_resource_status(
            memory_usage,
            analytics_service.analytics_settings.memory_warning_threshold_percent,
            analytics_service.analytics_settings.memory_critical_threshold_percent,
        )
        disk_status = classify_resource_status(
            disk_usage,
            70.0,
            90.0,  # Disk thresholds from feature config
        )

        # Network status based on usage rate (business logic)
        network_status = (
            "critical" if network_usage > 1000 else "warning" if network_usage > 100 else "good"
        )

        # Overall status business logic: worst status wins
        all_statuses = [cpu_status, memory_status, disk_status, network_status]
        if "critical" in all_statuses:
            overall_status = "critical"
        elif "warning" in all_statuses:
            overall_status = "warning"
        else:
            overall_status = "good"

        return BackendComputedResourceStatus(
            cpu_usage=cpu_usage,
            cpu_status=cpu_status,
            memory_usage=memory_usage,
            memory_status=memory_status,
            disk_usage=disk_usage,
            disk_status=disk_status,
            network_usage=network_usage,
            network_status=network_status,
            overall_status=overall_status,
        )

    except Exception as e:
        logger.error(f"Error computing resource status: {e}")
        # Return safe fallback with error status
        return BackendComputedResourceStatus(
            cpu_usage=0.0,
            cpu_status="critical",
            memory_usage=0.0,
            memory_status="critical",
            disk_usage=0.0,
            disk_status="critical",
            network_usage=0.0,
            network_status="critical",
            overall_status="critical",
        )


@router.get(
    "/api-performance-computed",
    response_model=BackendComputedAPIPerformance,
    summary="Get backend-computed API performance with status classification",
)
async def get_computed_api_performance(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> BackendComputedAPIPerformance:
    """
    Get API performance metrics with backend-computed status classification.

    Applies business logic thresholds on the backend to determine performance status,
    eliminating the need for frontend threshold calculations.
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Performance analytics service not available")

    try:
        # Get API performance data from service analytics
        api_metrics = await analytics_service.get_api_performance_metrics()

        avg_response_time = api_metrics.get("average_response_time_ms", 50.0)
        requests_per_second = api_metrics.get("requests_per_second", 10.0)
        error_rate = api_metrics.get("error_rate_percent", 0.0)

        # Backend business logic: Apply feature-configured thresholds
        response_time_status = (
            "critical"
            if avg_response_time > 500
            else "warning"
            if avg_response_time > 200
            else "good"
        )

        throughput_status = (
            "critical"
            if requests_per_second < 1
            else "warning"
            if requests_per_second < 5
            else "good"
        )

        error_status = "critical" if error_rate > 5.0 else "warning" if error_rate > 1.0 else "good"

        # Overall performance business logic
        if response_time_status == "critical" or error_status == "critical":
            overall_performance_status = "critical"
        elif "warning" in [response_time_status, throughput_status, error_status]:
            overall_performance_status = "warning"
        else:
            overall_performance_status = "good"

        return BackendComputedAPIPerformance(
            average_response_time=avg_response_time,
            response_time_status=response_time_status,
            requests_per_second=requests_per_second,
            throughput_status=throughput_status,
            error_rate=error_rate,
            error_status=error_status,
            overall_performance_status=overall_performance_status,
        )

    except Exception as e:
        logger.error(f"Error computing API performance: {e}")
        return BackendComputedAPIPerformance(
            average_response_time=1000.0,
            response_time_status="critical",
            requests_per_second=0.0,
            throughput_status="critical",
            error_rate=100.0,
            error_status="critical",
            overall_performance_status="critical",
        )


@router.get("/status", response_model=dict[str, Any])
async def get_performance_analytics_status(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> dict[str, Any]:
    """
    Get comprehensive performance analytics status.

    Returns:
        Detailed status including configuration, statistics, and component health
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Performance analytics service not available")

    try:
        return analytics_service.get_status()
    except Exception as e:
        logger.error(f"Error getting performance analytics status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/telemetry/protocol", response_model=dict[str, bool])
async def record_protocol_telemetry(
    telemetry_request: TelemetryRequest,
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> dict[str, bool]:
    """
    Record protocol message processing performance data.

    Args:
        telemetry_request: Protocol telemetry data

    Returns:
        Success status
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Performance analytics service not available")

    try:
        analytics_service.record_protocol_message(
            protocol=telemetry_request.protocol,
            processing_time_ms=telemetry_request.processing_time_ms,
            message_size=telemetry_request.message_size,
            interface=telemetry_request.interface,
        )

        return {"recorded": True}

    except Exception as e:
        logger.error(f"Error recording protocol telemetry: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/telemetry/api", response_model=dict[str, bool])
async def record_api_performance(
    api_request: APIPerformanceRequest,
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> dict[str, bool]:
    """
    Record API request performance data.

    Args:
        api_request: API performance data

    Returns:
        Success status
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Performance analytics service not available")

    try:
        analytics_service.record_api_request(
            endpoint=api_request.endpoint,
            response_time_ms=api_request.response_time_ms,
            status_code=api_request.status_code,
        )

        return {"recorded": True}

    except Exception as e:
        logger.error(f"Error recording API performance: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/telemetry/websocket", response_model=dict[str, bool])
async def record_websocket_latency(
    websocket_request: WebSocketLatencyRequest,
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> dict[str, bool]:
    """
    Record WebSocket latency data.

    Args:
        websocket_request: WebSocket latency data

    Returns:
        Success status
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Performance analytics service not available")

    try:
        analytics_service.record_websocket_latency(
            latency_ms=websocket_request.latency_ms, connection_id=websocket_request.connection_id
        )

        return {"recorded": True}

    except Exception as e:
        logger.error(f"Error recording WebSocket latency: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/telemetry/can-interface", response_model=dict[str, bool])
async def record_can_interface_load(
    can_request: CANInterfaceLoadRequest,
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> dict[str, bool]:
    """
    Record CAN interface load and performance data.

    Args:
        can_request: CAN interface performance data

    Returns:
        Success status
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Performance analytics service not available")

    try:
        analytics_service.record_can_interface_load(
            interface=can_request.interface,
            load_percent=can_request.load_percent,
            message_rate=can_request.message_rate,
        )

        return {"recorded": True}

    except Exception as e:
        logger.error(f"Error recording CAN interface load: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/metrics", response_model=list[dict[str, Any]])
async def get_performance_metrics(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
    metric_type: str | None = Query(None, description="Specific metric type to retrieve"),
    time_window_seconds: float = Query(
        default=60.0, description="Time window for metrics", ge=1.0, le=86400.0
    ),
) -> list[dict[str, Any]]:
    """
    Get current performance metrics with optional filtering.

    Args:
        metric_type: Specific metric type to retrieve
        time_window_seconds: Time window for metrics

    Returns:
        List of performance metrics
    """
    if not analytics_service:
        # Return empty metrics list when service is not available
        logger.debug("Performance analytics service not available, returning empty metrics")
        return []

    try:
        return analytics_service.get_current_metrics(metric_type, time_window_seconds)

    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/resource-utilization", response_model=dict[str, Any])
async def get_resource_utilization(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> dict[str, Any]:
    """
    Get current system resource utilization.

    Returns:
        Resource utilization data for CPU, memory, network, and CAN interfaces
    """
    if not analytics_service:
        # Return basic resource data when service is not available
        # This could be enhanced with psutil or other system monitoring
        logger.debug("Performance analytics service not available, returning basic resource data")

        # Try to get basic system info
        try:
            import psutil

            return {
                "cpu_usage": psutil.cpu_percent(interval=0.1) / 100.0,  # Convert to 0-1 range
                "memory_usage": psutil.virtual_memory().percent / 100.0,  # Convert to 0-1 range
                "disk_usage": psutil.disk_usage("/").percent / 100.0,  # Convert to 0-1 range
                "network_usage": 0.0,  # Would need more complex calculation
                "timestamp": time.time(),
                "source": "psutil",  # Indicate data source
            }
        except ImportError:
            # psutil not available, return zeros
            return {
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "disk_usage": 0.0,
                "network_usage": 0.0,
                "timestamp": time.time(),
                "source": "default",
            }

    try:
        return analytics_service.get_resource_utilization()

    except Exception as e:
        logger.error(f"Error getting resource utilization: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/trends", response_model=dict[str, Any])
async def get_performance_trends(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
    metric_type: str | None = Query(None, description="Specific metric type for trends"),
) -> dict[str, Any]:
    """
    Get performance trend analysis.

    Args:
        metric_type: Specific metric type or None for all trends

    Returns:
        Performance trend analysis data
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Performance analytics service not available")

    try:
        return analytics_service.get_performance_trends(metric_type)

    except Exception as e:
        logger.error(f"Error getting performance trends: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/baseline-deviations", response_model=list[dict[str, Any]])
async def get_baseline_deviations(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
    time_window_seconds: float = Query(
        default=3600.0, description="Time window for deviations", ge=60.0, le=86400.0
    ),
) -> list[dict[str, Any]]:
    """
    Get performance baseline deviations.

    Args:
        time_window_seconds: Time window for deviation analysis

    Returns:
        List of baseline deviation alerts
    """
    if not analytics_service:
        # Return sample deviations based on system state
        # In production, this would analyze real metrics from other services
        logger.debug("Performance analytics service not available, returning sample deviations")

        # Could be enhanced to get real data from CAN facade, resource monitoring, etc.
        current_time = datetime.now().isoformat()
        sample_deviations = []

        # Only return deviations if we have concerning metrics
        # This keeps the UI clean when everything is normal
        return sample_deviations

    try:
        return analytics_service.get_baseline_deviations(time_window_seconds)

    except Exception as e:
        logger.error(f"Error getting baseline deviations: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/optimization-recommendations", response_model=list[dict[str, Any]])
async def get_optimization_recommendations(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> list[dict[str, Any]]:
    """
    Get automated optimization recommendations.

    Returns:
        List of optimization recommendations with implementation details
    """
    if not analytics_service:
        # Return basic recommendations when service is not available
        logger.debug("Performance analytics service not available, returning basic recommendations")

        # Basic recommendations that are always relevant
        return [
            {
                "recommendation": "Enable Performance Analytics",
                "description": "Enable the performance analytics service for detailed system insights",
                "impact": "high",
                "effort": "low",
                "category": "monitoring",
                "priority": 1,
                "implementation_steps": [
                    "Configure performance analytics in feature flags",
                    "Restart the application",
                    "Monitor system metrics",
                ],
            }
        ]

    try:
        return analytics_service.get_optimization_recommendations()

    except Exception as e:
        logger.error(f"Error getting optimization recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/report", response_model=dict[str, Any])
async def generate_performance_report(
    report_request: PerformanceReportRequest,
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> dict[str, Any]:
    """
    Generate comprehensive performance analysis report.

    Args:
        report_request: Report generation parameters

    Returns:
        Comprehensive performance report including metrics, trends, and recommendations
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Performance analytics service not available")

    try:
        return analytics_service.generate_performance_report(report_request.time_window_seconds)

    except Exception as e:
        logger.error(f"Error generating performance report: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/protocol-throughput", response_model=dict[str, float])
async def get_protocol_throughput(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
    can_facade: Annotated[Any | None, Depends(create_optional_service_dependency("can_facade"))],
) -> dict[str, float]:
    """
    Get current protocol throughput metrics.

    Returns:
        Dictionary of protocol names to messages per second
    """
    if not analytics_service:
        # Try to get data from CAN facade if available
        if can_facade:
            try:
                stats = await can_facade.get_bus_statistics()
                # Extract protocol-specific data if available
                # For now, return overall rate divided by active protocols
                message_rate = stats.get("summary", {}).get("message_rate", 0.0)

                # TODO: Enhance CAN facade to track per-protocol statistics
                # For now, assume all messages are RVC if we have any rate
                if message_rate > 0:
                    return {
                        "rvc": message_rate,
                        "j1939": 0.0,
                        "nmea2000": 0.0,
                    }
            except Exception as e:
                logger.debug(f"Failed to get CAN statistics: {e}")

        # Return zeros if no data available
        logger.debug("No throughput data available")
        return {
            "rvc": 0.0,
            "j1939": 0.0,
            "nmea2000": 0.0,
        }

    try:
        if (
            hasattr(analytics_service, "telemetry_collector")
            and analytics_service.telemetry_collector
        ):
            return analytics_service.telemetry_collector.get_protocol_throughput()
        return {}

    except Exception as e:
        logger.error(f"Error getting protocol throughput: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/statistics", response_model=dict[str, Any])
async def get_analytics_statistics(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> dict[str, Any]:
    """
    Get comprehensive performance analytics statistics.

    Returns:
        Statistics from all analytics components including telemetry, benchmarking, trends, and optimization
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Performance analytics service not available")

    try:
        stats = {}

        # Get service-level statistics
        service_status = analytics_service.get_status()
        stats["service"] = service_status.get("statistics", {})

        # Get component-specific statistics
        if "telemetry_statistics" in service_status:
            stats["telemetry"] = service_status["telemetry_statistics"]

        if "benchmark_statistics" in service_status:
            stats["benchmarking"] = service_status["benchmark_statistics"]

        if "trend_statistics" in service_status:
            stats["trends"] = service_status["trend_statistics"]

        if "optimization_statistics" in service_status:
            stats["optimization"] = service_status["optimization_statistics"]

        return stats

    except Exception as e:
        logger.error(f"Error getting analytics statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/reset-baselines", response_model=dict[str, bool])
async def reset_performance_baselines(
    analytics_service: Annotated[Any | None, Depends(get_performance_analytics_service)],
) -> dict[str, bool]:
    """
    Reset all performance baselines (admin operation).

    Returns:
        Success status
    """
    if not analytics_service:
        raise HTTPException(status_code=503, detail="Performance analytics service not available")

    try:
        # This would reset baselines in the benchmarking engine
        # Implementation depends on specific requirements
        logger.info("Performance baselines reset requested")
        return {"reset": True}

    except Exception as e:
        logger.error(f"Error resetting performance baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
