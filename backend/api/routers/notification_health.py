"""
Health check endpoint for the lightweight notification system.

Provides performance metrics and health status suitable for monitoring.
"""

from fastapi import APIRouter
from typing import Dict, Any

from backend.core.dependencies_v2 import get_settings
from backend.services.notification_lightweight import LightweightNotificationManager


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/health")
async def get_notification_health() -> Dict[str, Any]:
    """
    Get health status and performance metrics for the notification system.

    Returns:
        Health information including:
        - System status
        - Circuit breaker states
        - Connection pool statistics
        - Cache performance
        - Batching efficiency
        - Memory usage
        - Performance metrics
    """
    # Get notification manager instance
    # In production, this would be injected via dependency
    settings = get_settings()
    manager = LightweightNotificationManager(settings.notifications)

    # Get health information
    health = await manager.get_health()

    return health


@router.post("/test")
async def test_notification(
    message: str = "Test notification",
    level: str = "info",
    channels: list[str] = ["webhook"]
) -> Dict[str, Any]:
    """
    Send a test notification to verify the system is working.

    Args:
        message: Test message content
        level: Notification level (info, warning, error, critical)
        channels: List of channels to test

    Returns:
        Test results including success status and timing
    """
    import time

    settings = get_settings()
    manager = LightweightNotificationManager(settings.notifications)
    await manager.initialize()

    start_time = time.time()

    try:
        success = await manager.send_notification(
            message=message,
            title="Test Notification",
            level=level,
            channels=channels,
            batch=False,  # Don't batch test notifications
        )

        duration_ms = (time.time() - start_time) * 1000

        return {
            "success": success,
            "duration_ms": duration_ms,
            "message": message,
            "level": level,
            "channels": channels,
        }

    finally:
        await manager.close()
