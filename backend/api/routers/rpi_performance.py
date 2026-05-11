"""
Lightweight Performance Monitoring API for Raspberry Pi

Simple, efficient endpoints for monitoring RPi performance with minimal overhead.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.core.dependencies import get_rpi_performance_monitor
from backend.core.rpi_performance_monitor import LightweightPerformanceMonitor
from backend.core.structured_logging import get_logger

logger = get_logger(__name__, "RPiPerformanceAPI")

router = APIRouter(
    prefix="/api/rpi-performance",
    tags=["rpi-performance"],
    responses={
        404: {"description": "Performance data not found"},
        500: {"description": "Internal server error"},
    },
)


@router.get("/health-summary")
async def get_performance_health_summary(
    monitor: LightweightPerformanceMonitor = Depends(get_rpi_performance_monitor)
) -> dict[str, Any]:
    """
    Get performance health summary optimized for RPi dashboard.
    
    Returns:
        Comprehensive health overview with category scores and status
    """
    try:
        health_summary = monitor.get_health_summary()
        return {
            "status": "success",
            "data": health_summary,
            "timestamp": monitor._buffers.get("timestamp", 0) if monitor._buffers else 0
        }
    except Exception as e:
        logger.error(f"Failed to get performance health summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve performance health summary")


@router.get("/operation/{operation_key}")
async def get_operation_stats(
    operation_key: str,
    monitor: LightweightPerformanceMonitor = Depends(get_rpi_performance_monitor)
) -> dict[str, Any]:
    """
    Get detailed statistics for a specific operation.
    
    Args:
        operation_key: The operation to get stats for (e.g., 'entity_service.get_all_entities')
    
    Returns:
        Detailed operation statistics including latency percentiles
    """
    try:
        stats = monitor.get_operation_stats(operation_key)
        if "error" in stats:
            raise HTTPException(status_code=404, detail=f"Operation '{operation_key}' not found")

        return {
            "status": "success",
            "operation": operation_key,
            "data": stats
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get operation stats for '{operation_key}': {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve operation statistics")


@router.get("/all-stats")
async def get_all_performance_stats(
    monitor: LightweightPerformanceMonitor = Depends(get_rpi_performance_monitor)
) -> dict[str, Any]:
    """
    Get statistics for all monitored operations.
    
    Returns:
        Complete performance statistics for all operations
    """
    try:
        all_stats = monitor.get_all_stats()
        return {
            "status": "success",
            "data": all_stats,
            "operation_count": len(all_stats)
        }
    except Exception as e:
        logger.error(f"Failed to get all performance stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve performance statistics")


@router.get("/thresholds")
async def get_alert_thresholds(
    monitor: LightweightPerformanceMonitor = Depends(get_rpi_performance_monitor)
) -> dict[str, Any]:
    """
    Get current alert thresholds for all categories.
    
    Returns:
        Current alert thresholds by category
    """
    try:
        return {
            "status": "success",
            "data": monitor._alert_thresholds.copy()
        }
    except Exception as e:
        logger.error(f"Failed to get alert thresholds: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert thresholds")


@router.post("/thresholds/{category}")
async def update_alert_threshold(
    category: str,
    threshold_ms: float = Query(..., description="New threshold in milliseconds"),
    monitor: LightweightPerformanceMonitor = Depends(get_rpi_performance_monitor)
) -> dict[str, Any]:
    """
    Update alert threshold for a category.
    
    Args:
        category: Category to update (api, service, database, cache, can)
        threshold_ms: New threshold in milliseconds
    
    Returns:
        Updated threshold confirmation
    """
    try:
        if threshold_ms <= 0:
            raise HTTPException(status_code=400, detail="Threshold must be positive")

        if category not in monitor._alert_thresholds:
            raise HTTPException(status_code=404, detail=f"Category '{category}' not found")

        old_threshold = monitor._alert_thresholds[category]
        monitor.set_alert_threshold(category, threshold_ms)

        return {
            "status": "success",
            "message": f"Updated {category} threshold from {old_threshold}ms to {threshold_ms}ms",
            "category": category,
            "old_threshold_ms": old_threshold,
            "new_threshold_ms": threshold_ms
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update threshold for '{category}': {e}")
        raise HTTPException(status_code=500, detail="Failed to update alert threshold")


@router.get("/baselines")
async def get_performance_baselines(
    monitor: LightweightPerformanceMonitor = Depends(get_rpi_performance_monitor)
) -> dict[str, Any]:
    """
    Get current performance baselines.
    
    Returns:
        Performance baselines for all operations
    """
    try:
        return {
            "status": "success",
            "data": monitor._baselines.copy(),
            "baseline_window": monitor._baseline_window
        }
    except Exception as e:
        logger.error(f"Failed to get performance baselines: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve performance baselines")


@router.post("/reset")
async def reset_performance_buffers(
    monitor: LightweightPerformanceMonitor = Depends(get_rpi_performance_monitor)
) -> dict[str, Any]:
    """
    Reset all performance monitoring buffers.
    
    Useful for testing or starting fresh monitoring.
    
    Returns:
        Reset confirmation
    """
    try:
        buffer_count = len(monitor._buffers)
        monitor.reset_buffers()

        return {
            "status": "success",
            "message": f"Reset {buffer_count} performance buffers",
            "buffers_cleared": buffer_count
        }
    except Exception as e:
        logger.error(f"Failed to reset performance buffers: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset performance buffers")


@router.get("/memory-usage")
async def get_memory_usage(
    monitor: LightweightPerformanceMonitor = Depends(get_rpi_performance_monitor)
) -> dict[str, Any]:
    """
    Get estimated memory usage of the performance monitoring system.
    
    Returns:
        Memory usage statistics
    """
    try:
        memory_kb = monitor._estimate_memory_usage()
        buffer_count = len(monitor._buffers)
        total_metrics = sum(len(buffer._buffer) for buffer in monitor._buffers.values())

        return {
            "status": "success",
            "data": {
                "estimated_memory_kb": memory_kb,
                "buffer_count": buffer_count,
                "total_metrics": total_metrics,
                "buffer_size_limit": monitor._buffer_size,
                "metrics_per_buffer": total_metrics / buffer_count if buffer_count > 0 else 0
            }
        }
    except Exception as e:
        logger.error(f"Failed to get memory usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memory usage")


@router.get("/live-metrics")
async def get_live_metrics(
    limit: int = Query(10, description="Number of recent metrics per operation"),
    monitor: LightweightPerformanceMonitor = Depends(get_rpi_performance_monitor)
) -> dict[str, Any]:
    """
    Get live performance metrics for real-time monitoring.
    
    Args:
        limit: Maximum number of recent metrics per operation
    
    Returns:
        Recent performance data for real-time dashboard
    """
    try:
        live_data = {}

        for operation_key, buffer in monitor._buffers.items():
            # Get most recent metrics
            recent_metrics = list(buffer._buffer)[-limit:] if buffer._buffer else []

            live_data[operation_key] = {
                "recent_metrics": [
                    {
                        "latency_ms": metric.latency_ms,
                        "timestamp": metric.timestamp,
                        "request_id": metric.request_id
                    }
                    for metric in recent_metrics
                ],
                "current_stats": buffer.get_stats()
            }

        return {
            "status": "success",
            "data": live_data,
            "limit": limit,
            "timestamp": __import__("time").time()
        }
    except Exception as e:
        logger.error(f"Failed to get live metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve live metrics")


# Health check endpoint for the performance monitoring API itself
@router.get("/status")
async def performance_api_status() -> JSONResponse:
    """
    Check if the performance monitoring API is healthy.
    
    Returns:
        API status information
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "rpi-performance-api",
            "timestamp": __import__("time").time()
        }
    )
