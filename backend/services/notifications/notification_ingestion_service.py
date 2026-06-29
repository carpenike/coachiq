"""Notification Ingestion Service (Refactored)

Handles real-time reception of analytics events with minimal latency.
This service is optimized for speed and does not touch the database directly.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from backend.core.performance import PerformanceMonitor
from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationStatus,
)
from backend.models.notification_analytics import NotificationDeliveryLog

logger = logging.getLogger(__name__)


class NotificationIngestionService:
    """Service for high-performance notification event ingestion."""

    def __init__(self, performance_monitor: PerformanceMonitor, queue_size_limit: int = 10000):
        """Initialize the ingestion service.

        Args:
            performance_monitor: Performance monitoring instance
            queue_size_limit: Maximum queue size before applying backpressure
        """
        self._monitor = performance_monitor
        self._queue: asyncio.Queue[NotificationDeliveryLog] = asyncio.Queue(
            maxsize=queue_size_limit
        )
        self._metrics_dropped = 0

        # Apply performance monitoring
        self._apply_monitoring()

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.track_delivery = self._monitor.monitor_service_method(
            "NotificationIngestionService", "track_delivery"
        )(self.track_delivery)

        self.track_engagement = self._monitor.monitor_service_method(
            "NotificationIngestionService", "track_engagement"
        )(self.track_engagement)

    async def track_delivery(
        self,
        notification: NotificationPayload,
        channel: NotificationChannel,
        status: NotificationStatus,
        delivery_time_ms: int | None = None,
        error_message: str | None = None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Track a notification delivery attempt with non-blocking ingestion.

        Args:
            notification: The notification that was delivered
            channel: Channel used for delivery
            status: Delivery status
            delivery_time_ms: Time taken for delivery in milliseconds
            error_message: Error message if failed
            error_code: Structured error code if failed
            metadata: Additional metadata

        Returns:
            True if successfully queued, False if queue is full
        """
        log_entry = NotificationDeliveryLog(
            notification_id=notification.id,
            channel=channel.value,
            notification_type=notification.level.value,
            status=status.value,
            recipient=notification.recipient,
            delivered_at=datetime.now(UTC) if status == NotificationStatus.DELIVERED else None,
            delivery_time_ms=delivery_time_ms,
            retry_count=notification.retry_count,
            error_message=error_message,
            error_code=error_code,
            metadata=metadata or {},
        )

        try:
            # Non-blocking put
            self._queue.put_nowait(log_entry)
            return True
        except asyncio.QueueFull:
            self._metrics_dropped += 1
            logger.warning(
                f"Ingestion queue full, dropped metric. Total dropped: {self._metrics_dropped}"
            )
            return False

    async def track_engagement(
        self,
        notification_id: str,
        action: str,  # opened, clicked, dismissed
        timestamp: datetime | None = None,
    ) -> bool:
        """Track user engagement with a notification.

        This creates a minimal log entry for engagement tracking.
        The processing service will handle updating the original delivery log.

        Args:
            notification_id: ID of the notification
            action: Engagement action (opened, clicked, dismissed)
            timestamp: When the action occurred

        Returns:
            True if successfully queued
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Create a minimal log entry for engagement
        engagement_entry = NotificationDeliveryLog(
            notification_id=notification_id,
            channel="engagement",  # Special marker
            notification_type="engagement",
            status=action,
            recipient="",  # Will be filled by processor
            metadata={
                "engagement_action": action,
                "engagement_timestamp": timestamp.isoformat(),
            },
        )

        try:
            self._queue.put_nowait(engagement_entry)
            return True
        except asyncio.QueueFull:
            self._metrics_dropped += 1
            logger.warning(
                f"Ingestion queue full, dropped engagement. Total dropped: {self._metrics_dropped}"
            )
            return False

    def get_queue(self) -> asyncio.Queue[NotificationDeliveryLog]:
        """Get the ingestion queue for processing.

        Returns:
            The asyncio queue containing ingested events
        """
        return self._queue

    def get_queue_stats(self) -> dict[str, Any]:
        """Get current queue statistics.

        Returns:
            Dictionary with queue statistics
        """
        return {
            "queue_size": self._queue.qsize(),
            "queue_limit": self._queue.maxsize,
            "queue_full": self._queue.full(),
            "metrics_dropped": self._metrics_dropped,
        }
