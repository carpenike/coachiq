"""
Enhanced Async Notification Dispatcher with Analytics Integration

This module extends the AsyncNotificationDispatcher to include comprehensive
analytics tracking for all notification deliveries.
"""

import time
from typing import Any

from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationStatus,
)
from backend.services.async_notification_dispatcher import AsyncNotificationDispatcher
from backend.services.notification_analytics_service import NotificationAnalyticsService


class AnalyticsNotificationDispatcher(AsyncNotificationDispatcher):
    """
    Enhanced notification dispatcher with integrated analytics tracking.

    Extends the base dispatcher to track all delivery attempts, performance
    metrics, and errors for comprehensive analytics.
    """

    def __init__(
        self, *args, analytics_service: NotificationAnalyticsService | None = None, **kwargs
    ):
        """
        Initialize dispatcher with analytics service.

        Args:
            analytics_service: Optional analytics service for metric tracking
            *args, **kwargs: Arguments passed to parent class
        """
        super().__init__(*args, **kwargs)
        self.analytics_service = analytics_service

    async def _process_single_notification(self, notification: NotificationPayload) -> bool:
        """
        Process a single notification with analytics tracking.

        Args:
            notification: Notification to process

        Returns:
            bool: True if successful, False if failed
        """
        start_time = time.time()
        channel = self._determine_primary_channel(notification)
        error_message = None
        error_code = None

        try:
            # Determine delivery method based on channels
            success = False

            if NotificationChannel.SMTP in notification.channels:
                success = await self._send_email(notification)
                channel = NotificationChannel.SMTP
            elif NotificationChannel.WEBHOOK in notification.channels:
                success = await self._send_webhook_notification(notification)
                channel = NotificationChannel.WEBHOOK
            else:
                success = await self._send_apprise_notification(notification)

            processing_time = time.time() - start_time
            delivery_time_ms = int(processing_time * 1000)

            if success:
                await self.queue.mark_complete(notification.id)
                status = NotificationStatus.DELIVERED

                self.logger.debug(
                    f"Notification {notification.id} delivered successfully in {processing_time:.2f}s"
                )
            else:
                await self.queue.mark_failed(notification.id, "Delivery failed", should_retry=True)
                status = NotificationStatus.FAILED
                error_message = "Delivery failed"
                error_code = "DELIVERY_FAILED"

            # Track analytics
            if self.analytics_service:
                await self.analytics_service.track_delivery(
                    notification=notification,
                    channel=channel,
                    status=status,
                    delivery_time_ms=delivery_time_ms,
                    error_message=error_message,
                    error_code=error_code,
                    metadata={
                        "retry_count": notification.retry_count,
                        "priority": notification.priority,
                    },
                )

            return success

        except Exception as e:
            error_msg = f"Processing error: {e!s}"
            error_code = self._classify_error(e)

            self.logger.error(f"Failed to process notification {notification.id}: {error_msg}")

            await self.queue.mark_failed(notification.id, error_msg, should_retry=True)

            # Track error for adaptive behavior
            await self._track_error(notification.id, str(e))

            # Track analytics for failure
            if self.analytics_service:
                processing_time = time.time() - start_time
                await self.analytics_service.track_delivery(
                    notification=notification,
                    channel=channel,
                    status=NotificationStatus.FAILED,
                    delivery_time_ms=int(processing_time * 1000),
                    error_message=error_msg,
                    error_code=error_code,
                    metadata={
                        "exception_type": type(e).__name__,
                        "retry_count": notification.retry_count,
                    },
                )

            return False

    async def _send_email(self, notification: NotificationPayload) -> bool:
        """Send email notification with analytics tracking."""
        start_time = time.time()

        try:
            result = await super()._send_email(notification)

            # Track channel-specific metrics
            if self.analytics_service and result:
                delivery_time = (time.time() - start_time) * 1000
                await self._track_channel_performance(
                    NotificationChannel.SMTP, delivery_time, success=True
                )

            return result

        except Exception as e:
            if self.analytics_service:
                await self._track_channel_performance(
                    NotificationChannel.SMTP, 0, success=False, error=str(e)
                )
            raise

    async def _send_webhook_notification(self, notification: NotificationPayload) -> bool:
        """Send webhook notification with analytics tracking."""
        start_time = time.time()

        try:
            result = await super()._send_webhook_notification(notification)

            if self.analytics_service and result:
                delivery_time = (time.time() - start_time) * 1000
                await self._track_channel_performance(
                    NotificationChannel.WEBHOOK, delivery_time, success=True
                )

            return result

        except Exception as e:
            if self.analytics_service:
                await self._track_channel_performance(
                    NotificationChannel.WEBHOOK, 0, success=False, error=str(e)
                )
            raise

    async def _send_apprise_notification(self, notification: NotificationPayload) -> bool:
        """Send notification via Apprise with analytics tracking."""
        start_time = time.time()
        primary_channel = self._determine_primary_channel(notification)

        try:
            result = await super()._send_apprise_notification(notification)

            if self.analytics_service and result:
                delivery_time = (time.time() - start_time) * 1000
                await self._track_channel_performance(primary_channel, delivery_time, success=True)

            return result

        except Exception as e:
            if self.analytics_service:
                await self._track_channel_performance(
                    primary_channel, 0, success=False, error=str(e)
                )
            raise

    async def _send_pushover_notification(self, notification: NotificationPayload) -> bool:
        """Send Pushover notification with analytics tracking."""
        start_time = time.time()

        try:
            result = await super()._send_pushover_notification(notification)

            if self.analytics_service and result:
                delivery_time = (time.time() - start_time) * 1000
                await self._track_channel_performance(
                    NotificationChannel.PUSHOVER, delivery_time, success=True
                )

            return result

        except Exception as e:
            if self.analytics_service:
                await self._track_channel_performance(
                    NotificationChannel.PUSHOVER, 0, success=False, error=str(e)
                )
            raise

    # Analytics helper methods

    def _determine_primary_channel(self, notification: NotificationPayload) -> NotificationChannel:
        """Determine the primary channel for a notification."""
        if notification.channels:
            return notification.channels[0]
        return NotificationChannel.SYSTEM

    def _classify_error(self, error: Exception) -> str:
        """Classify error type for analytics."""
        error_type = type(error).__name__
        error_msg = str(error).lower()

        # Common error classifications
        if "timeout" in error_msg:
            return "TIMEOUT_ERROR"
        if "connection" in error_msg:
            return "CONNECTION_ERROR"
        if "authentication" in error_msg or "auth" in error_msg:
            return "AUTH_ERROR"
        if "rate" in error_msg and "limit" in error_msg:
            return "RATE_LIMIT_ERROR"
        if "invalid" in error_msg:
            return "INVALID_CONFIG_ERROR"
        if "network" in error_msg:
            return "NETWORK_ERROR"
        return f"UNKNOWN_{error_type.upper()}"

    async def _track_channel_performance(
        self,
        channel: NotificationChannel,
        delivery_time_ms: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Track channel-specific performance metrics."""
        if not self.analytics_service:
            return

        # This would be implemented to track channel-specific metrics
        # For now, it's handled by the main track_delivery method

    async def _update_health_status(self) -> None:
        """Update health status with analytics integration."""
        await super()._update_health_status()

        # Additional analytics-specific health tracking
        if self.analytics_service:
            # The analytics service will handle queue health tracking
            # through its own health monitoring loop
            pass

    def get_metrics(self) -> dict[str, Any]:
        """Get dispatcher metrics with analytics enhancements."""
        metrics = super().get_metrics()

        # Add analytics-specific metrics if available
        if self.analytics_service:
            metrics["analytics_enabled"] = True
            metrics["analytics_buffer_size"] = len(self.analytics_service._metric_buffer)
        else:
            metrics["analytics_enabled"] = False

        return metrics
