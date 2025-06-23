"""
Notification Feature Integration

Feature integration for the unified notification system following the
established feature management patterns. This feature manages the SafeNotificationManager
lifecycle with queue-based architecture and provides integration hooks for other features.
"""

import asyncio
import logging
import time
from typing import Any

from backend.core.config import get_notification_settings
from backend.models.notification import NotificationChannelStatus, NotificationType
from backend.services.async_notification_dispatcher import AsyncNotificationDispatcher
from backend.services.feature_base import Feature
from backend.services.feature_models import SafetyClassification
from backend.services.notification_manager import NotificationManager
from backend.services.safe_notification_manager import SafeNotificationManager

logger = logging.getLogger(__name__)


class NotificationFeature(Feature):
    """
    Notification feature providing unified multi-channel notification delivery.

    This feature manages the SafeNotificationManager lifecycle with queue-based architecture
    and provides a centralized interface for sending notifications across all supported
    channels including SMTP, Slack, Discord, Pushover, and others through Apprise integration.

    Features modern queue-based delivery with:
    - Persistent SQLite queue with WAL mode
    - Rate limiting and debouncing for safety-critical environments
    - Background async dispatcher with retry logic
    - Template sanitization and input validation
    """

    def __init__(
        self,
        name: str = "notifications",
        enabled: bool = False,
        core: bool = False,
        config: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        friendly_name: str | None = None,
        safety_classification: SafetyClassification | None = None,
        log_state_transitions: bool = True,
    ):
        """Initialize the notification feature."""
        super().__init__(
            name=name,
            enabled=enabled,
            core=core,
            config=config,
            dependencies=dependencies,
            friendly_name=friendly_name or "Modern Notification System",
            safety_classification=safety_classification,
            log_state_transitions=log_state_transitions,
        )

        # Get notification settings
        self.notification_settings = get_notification_settings()

        # Initialize components - Phase 1 uses both for compatibility
        self.safe_notification_manager: SafeNotificationManager | None = None
        self.notification_dispatcher: AsyncNotificationDispatcher | None = None
        self.legacy_notification_manager: NotificationManager | None = None

        # Feature statistics
        self._stats = {
            "startup_time": 0.0,
            "notifications_sent": 0,
            "notifications_failed": 0,
            "notifications_queued": 0,
            "notifications_processed": 0,
            "emails_sent": 0,
            "system_notifications": 0,
            "channels_configured": 0,
            "templates_loaded": 0,
            "queue_enabled": False,
            "dispatcher_running": False,
        }

        # Channel status tracking
        self._channel_status: dict[str, NotificationChannelStatus] = {}

        # Background tasks
        self._background_tasks: list[asyncio.Task] = []

    async def startup(self) -> None:
        """Initialize notification system components."""
        if not self.notification_settings.enabled:
            logger.info("Notification feature disabled")
            return

        try:
            start_time = time.perf_counter()

            # Determine if queue-based architecture should be used (Phase 1 rollout)
            use_queue_based = self.config.get("use_queue_based", True)

            if use_queue_based:
                logger.info("Initializing modern queue-based notification system")

                # Initialize SafeNotificationManager with queue
                self.safe_notification_manager = SafeNotificationManager(self.notification_settings)
                await self.safe_notification_manager.initialize()
                self._stats["queue_enabled"] = True

                # Initialize legacy manager for dispatcher delivery
                self.legacy_notification_manager = NotificationManager(self.notification_settings)

                # Initialize AsyncNotificationDispatcher
                self.notification_dispatcher = AsyncNotificationDispatcher(
                    queue=self.safe_notification_manager.queue,
                    notification_manager=self.legacy_notification_manager,
                    config=self.notification_settings,
                    batch_size=self.config.get("dispatch_batch_size", 10),
                    max_concurrent_batches=self.config.get("max_concurrent_batches", 3),
                    processing_interval=self.config.get("processing_interval", 1.0),
                )

                # Start background dispatcher
                await self.notification_dispatcher.start()
                self._stats["dispatcher_running"] = True

                logger.info("Queue-based notification system initialized successfully")

            else:
                # Fallback to legacy system
                logger.info("Using legacy notification manager (queue disabled)")
                self.legacy_notification_manager = NotificationManager(self.notification_settings)

            # Get initial channel status
            enabled_channels = self.notification_settings.get_enabled_channels()
            self._stats["channels_configured"] = len(enabled_channels)

            # Initialize channel status tracking
            for channel_name, _ in enabled_channels:
                self._channel_status[channel_name] = NotificationChannelStatus(
                    channel=channel_name,
                    enabled=True,
                    configured=True,
                    healthy=True,
                    last_success=None,
                    last_failure=None,
                    consecutive_failures=0,
                    total_sent=0,
                    total_failures=0,
                    success_rate=0.0,
                    average_delivery_time=None,
                )

            # Test notification channels (optional)
            if self.config.get("test_on_startup", False):
                await self._test_notification_channels()

            # Send startup notification
            await self._send_startup_notification()

            # Start background monitoring tasks
            await self._start_background_tasks()

            startup_time = time.perf_counter() - start_time
            self._stats["startup_time"] = startup_time

            architecture = "queue-based" if use_queue_based else "legacy"
            logger.info(
                f"Notification feature started successfully with {architecture} architecture ({startup_time:.2f}s)"
            )

        except Exception as e:
            logger.error(f"Failed to start notification feature: {e}")
            # Don't fail startup for notification issues

    async def shutdown(self) -> None:
        """Shutdown notification system components."""
        try:
            # Send shutdown notification
            manager = self.safe_notification_manager or self.legacy_notification_manager
            if manager:
                await manager.send_system_notification(
                    message="CoachIQ notification system shutting down",
                    level="info",
                    component="Notification System",
                )

            # Stop async dispatcher first
            if self.notification_dispatcher:
                logger.info("Stopping async notification dispatcher...")
                await self.notification_dispatcher.stop(timeout=30.0)
                self.notification_dispatcher = None
                self._stats["dispatcher_running"] = False

            # Cancel background tasks
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()

            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)

            self._background_tasks.clear()

            # Clean up SafeNotificationManager
            if self.safe_notification_manager:
                await self.safe_notification_manager.cleanup()
                self.safe_notification_manager = None
                self._stats["queue_enabled"] = False

            # Clean up legacy notification manager
            self.legacy_notification_manager = None

            logger.info("Notification feature shutdown complete")

        except Exception as e:
            logger.error(f"Error during notification feature shutdown: {e}")

    @property
    def health(self) -> str:
        """Get the health status of the feature as a string."""
        if not self.notification_settings.enabled:
            return "disabled"

        # Check if any manager is available
        if not (self.safe_notification_manager or self.legacy_notification_manager):
            return "failed"

        # Check dispatcher health if queue-based
        if self.safe_notification_manager and self.notification_dispatcher:
            if not self.notification_dispatcher.is_running:
                return "degraded"  # Queue available but dispatcher not running

        # Check channel health
        healthy_channels = sum(1 for status in self._channel_status.values() if status.healthy)
        total_channels = len(self._channel_status)

        if total_channels == 0:
            return "degraded"  # No channels configured

        health_ratio = healthy_channels / total_channels

        if health_ratio >= 1.0:
            return "healthy"
        if health_ratio >= 0.5:
            return "degraded"
        return "failed"

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive status of the notification feature."""
        status = {
            "enabled": self.notification_settings.enabled,
            "healthy": self.health == "healthy",
            "architecture": "queue-based" if self.safe_notification_manager else "legacy",
            "safe_manager_initialized": self.safe_notification_manager is not None,
            "legacy_manager_initialized": self.legacy_notification_manager is not None,
            "dispatcher_running": self.notification_dispatcher is not None
            and self.notification_dispatcher.is_running,
            "statistics": self._stats.copy(),
            "channels": {},
            "configuration": {
                "smtp_enabled": self.notification_settings.smtp.enabled,
                "slack_enabled": self.notification_settings.slack.enabled,
                "discord_enabled": self.notification_settings.discord.enabled,
                "pushover_enabled": getattr(self.notification_settings, "pushover", {}).get(
                    "enabled", False
                ),
                "log_notifications": self.notification_settings.log_notifications,
                "template_path": self.notification_settings.template_path,
                "queue_enabled": self._stats.get("queue_enabled", False),
            },
        }

        # Add channel status
        for channel_name, channel_status in self._channel_status.items():
            status["channels"][channel_name] = {
                "enabled": channel_status.enabled,
                "healthy": channel_status.healthy,
                "configured": channel_status.configured,
                "total_sent": channel_status.total_sent,
                "total_failures": channel_status.total_failures,
                "success_rate": channel_status.success_rate,
                "last_success": channel_status.last_success.isoformat()
                if channel_status.last_success
                else None,
                "last_failure": channel_status.last_failure.isoformat()
                if channel_status.last_failure
                else None,
            }

        # Add queue statistics if available
        if self.safe_notification_manager:
            try:
                # Get queue stats (this will be async in practice)
                status["queue_statistics"] = {
                    "available": True,
                    "note": "Queue statistics available via async API",
                }
                status["rate_limiting"] = {
                    "available": True,
                    "note": "Rate limiting statistics available via async API",
                }
            except Exception as e:
                status["queue_statistics"] = {"error": str(e)}

        # Add dispatcher metrics if available
        if self.notification_dispatcher:
            try:
                dispatcher_metrics = self.notification_dispatcher.get_metrics()
                status["dispatcher_metrics"] = dispatcher_metrics
            except Exception as e:
                status["dispatcher_metrics"] = {"error": str(e)}

        # Add notification manager status if available (legacy compatibility)
        manager = self.safe_notification_manager or self.legacy_notification_manager
        if manager and hasattr(manager, "get_channel_status"):
            status["notification_manager"] = manager.get_channel_status()

        return status

    # Public API methods for other features to use

    async def send_notification(
        self,
        message: str,
        title: str | None = None,
        level: str = "info",
        tags: list[str] | None = None,
        template: str | None = None,
        context: dict[str, Any] | None = None,
        channels: list[str] | None = None,
        **kwargs,
    ) -> bool:
        """
        Send notification through the notification system.

        Args:
            message: Notification message
            title: Optional notification title
            level: Notification level (info, warning, error, critical)
            tags: Optional channel tags to target (legacy)
            template: Optional template name
            context: Optional template context
            channels: Optional specific channels to target
            **kwargs: Additional notification parameters

        Returns:
            bool: True if notification was sent/queued successfully
        """
        # Use SafeNotificationManager if available (queue-based)
        if self.safe_notification_manager:
            try:
                # Convert level to NotificationType
                level_enum = NotificationType(level.lower()) if isinstance(level, str) else level

                result = await self.safe_notification_manager.notify(
                    message=message,
                    title=title,
                    level=level_enum,
                    channels=channels,
                    tags=tags,
                    template=template,
                    context=context,
                    **kwargs,
                )

                # Update statistics
                if result:
                    self._stats["notifications_queued"] += 1
                    self._stats["notifications_sent"] += 1
                else:
                    self._stats["notifications_failed"] += 1

                return result

            except Exception as e:
                logger.error(f"Error sending notification via SafeNotificationManager: {e}")
                self._stats["notifications_failed"] += 1
                return False

        # Fallback to legacy manager
        elif self.legacy_notification_manager:
            try:
                result = await self.legacy_notification_manager.send_notification(
                    message=message,
                    title=title,
                    notify_type=level,
                    tags=tags,
                    template=template,
                    context=context,
                )

                # Update statistics
                if result:
                    self._stats["notifications_sent"] += 1
                else:
                    self._stats["notifications_failed"] += 1

                return result

            except Exception as e:
                logger.error(f"Error sending notification via legacy manager: {e}")
                self._stats["notifications_failed"] += 1
                return False

        else:
            logger.warning("No notification manager initialized, cannot send notification")
            return False

    async def send_email(
        self,
        to_email: str,
        subject: str,
        template: str,
        context: dict[str, Any],
        from_email: str | None = None,
        **kwargs,
    ) -> bool:
        """
        Send email notification.

        Args:
            to_email: Recipient email address
            subject: Email subject
            template: Template name
            context: Template context
            from_email: Optional override for from email
            **kwargs: Additional email parameters

        Returns:
            bool: True if email was sent/queued successfully
        """
        # Use SafeNotificationManager if available (queue-based)
        if self.safe_notification_manager:
            try:
                result = await self.safe_notification_manager.send_email(
                    to_email=to_email,
                    subject=subject,
                    template=template,
                    context=context,
                    from_email=from_email,
                    **kwargs,
                )

                # Update statistics
                if result:
                    self._stats["emails_sent"] += 1
                    self._stats["notifications_queued"] += 1
                    self._stats["notifications_sent"] += 1
                else:
                    self._stats["notifications_failed"] += 1

                return result

            except Exception as e:
                logger.error(f"Error sending email via SafeNotificationManager to {to_email}: {e}")
                self._stats["notifications_failed"] += 1
                return False

        # Fallback to legacy manager
        elif self.legacy_notification_manager:
            try:
                result = await self.legacy_notification_manager.send_email(
                    to_email=to_email,
                    subject=subject,
                    template=template,
                    context=context,
                    from_email=from_email,
                )

                # Update statistics
                if result:
                    self._stats["emails_sent"] += 1
                    self._stats["notifications_sent"] += 1
                else:
                    self._stats["notifications_failed"] += 1

                return result

            except Exception as e:
                logger.error(f"Error sending email via legacy manager to {to_email}: {e}")
                self._stats["notifications_failed"] += 1
                return False

        else:
            logger.warning("No notification manager initialized, cannot send email")
            return False

    async def send_magic_link_email(
        self,
        to_email: str,
        magic_link: str,
        user_name: str | None = None,
        expires_minutes: int = 15,
        **kwargs,
    ) -> bool:
        """
        Send magic link authentication email.

        Args:
            to_email: Recipient email address
            magic_link: Magic link URL
            user_name: Optional user display name
            expires_minutes: Link expiration time
            **kwargs: Additional parameters

        Returns:
            bool: True if email was sent/queued successfully
        """
        # Use SafeNotificationManager if available (queue-based)
        if self.safe_notification_manager:
            try:
                result = await self.safe_notification_manager.send_magic_link_email(
                    to_email=to_email,
                    magic_link=magic_link,
                    user_name=user_name,
                    expires_minutes=expires_minutes,
                    **kwargs,
                )

                # Update statistics
                if result:
                    self._stats["emails_sent"] += 1
                    self._stats["notifications_queued"] += 1
                    self._stats["notifications_sent"] += 1
                else:
                    self._stats["notifications_failed"] += 1

                return result

            except Exception as e:
                logger.error(
                    f"Error sending magic link email via SafeNotificationManager to {to_email}: {e}"
                )
                self._stats["notifications_failed"] += 1
                return False

        # Fallback to legacy manager
        elif self.legacy_notification_manager:
            try:
                result = await self.legacy_notification_manager.send_magic_link_email(
                    to_email=to_email,
                    magic_link=magic_link,
                    user_name=user_name,
                    expires_minutes=expires_minutes,
                )

                # Update statistics
                if result:
                    self._stats["emails_sent"] += 1
                    self._stats["notifications_sent"] += 1
                else:
                    self._stats["notifications_failed"] += 1

                return result

            except Exception as e:
                logger.error(
                    f"Error sending magic link email via legacy manager to {to_email}: {e}"
                )
                self._stats["notifications_failed"] += 1
                return False

        else:
            logger.warning("No notification manager initialized, cannot send magic link email")
            return False

    async def send_system_notification(
        self, message: str, level: str = "info", component: str | None = None, **kwargs
    ) -> bool:
        """
        Send system notification.

        Args:
            message: System notification message
            level: Notification level
            component: Optional component name
            **kwargs: Additional parameters

        Returns:
            bool: True if notification was sent/queued successfully
        """
        # Use SafeNotificationManager if available (queue-based)
        if self.safe_notification_manager:
            try:
                result = await self.safe_notification_manager.send_system_notification(
                    message=message, level=level, component=component, **kwargs
                )

                # Update statistics
                if result:
                    self._stats["system_notifications"] += 1
                    self._stats["notifications_queued"] += 1
                    self._stats["notifications_sent"] += 1
                else:
                    self._stats["notifications_failed"] += 1

                return result

            except Exception as e:
                logger.error(f"Error sending system notification via SafeNotificationManager: {e}")
                self._stats["notifications_failed"] += 1
                return False

        # Fallback to legacy manager
        elif self.legacy_notification_manager:
            try:
                result = await self.legacy_notification_manager.send_system_notification(
                    message=message, level=level, component=component
                )

                # Update statistics
                if result:
                    self._stats["system_notifications"] += 1
                    self._stats["notifications_sent"] += 1
                else:
                    self._stats["notifications_failed"] += 1

                return result

            except Exception as e:
                logger.error(f"Error sending system notification via legacy manager: {e}")
                self._stats["notifications_failed"] += 1
                return False

        else:
            logger.warning("No notification manager initialized, cannot send system notification")
            return False

    async def test_channels(self) -> dict[str, Any]:
        """Test all configured notification channels."""
        # Use SafeNotificationManager if available
        if self.safe_notification_manager:
            try:
                return await self.safe_notification_manager.test_channels()
            except Exception as e:
                logger.error(
                    f"Error testing notification channels via SafeNotificationManager: {e}"
                )
                return {"error": str(e)}

        # Fallback to legacy manager
        elif self.legacy_notification_manager:
            try:
                return await self.legacy_notification_manager.test_channels()
            except Exception as e:
                logger.error(f"Error testing notification channels via legacy manager: {e}")
                return {"error": str(e)}

        else:
            return {"error": "No notification manager initialized"}

    # New queue-based API methods

    async def send_pushover_notification(
        self,
        message: str,
        title: str | None = None,
        priority: int | None = None,
        device: str | None = None,
        **kwargs,
    ) -> bool:
        """
        Send Pushover notification with specific parameters.

        Args:
            message: Message text
            title: Optional title
            priority: Pushover priority (-2 to 2)
            device: Specific device to target
            **kwargs: Additional parameters

        Returns:
            bool: True if notification was sent/queued successfully
        """
        if self.safe_notification_manager:
            try:
                return await self.safe_notification_manager.send_pushover_notification(
                    message=message,
                    title=title,
                    priority=priority,
                    device=device,
                    **kwargs,
                )
            except Exception as e:
                logger.error(f"Error sending Pushover notification: {e}")
                return False
        else:
            # Fallback to regular notification with pushover channel
            return await self.send_notification(
                message=message,
                title=title,
                channels=["pushover"],
                pushover_priority=priority,
                pushover_device=device,
                **kwargs,
            )

    async def get_queue_statistics(self) -> dict[str, Any]:
        """Get comprehensive queue statistics."""
        if self.safe_notification_manager:
            try:
                stats = await self.safe_notification_manager.get_queue_statistics()
                return stats.model_dump()
            except Exception as e:
                logger.error(f"Error getting queue statistics: {e}")
                return {"error": str(e)}
        else:
            return {"error": "Queue-based manager not available"}

    async def get_rate_limit_status(self) -> dict[str, Any]:
        """Get rate limiting status."""
        if self.safe_notification_manager:
            try:
                status = await self.safe_notification_manager.get_rate_limit_status()
                return status.model_dump()
            except Exception as e:
                logger.error(f"Error getting rate limit status: {e}")
                return {"error": str(e)}
        else:
            return {"error": "Queue-based manager not available"}

    async def force_queue_processing(self) -> dict[str, Any]:
        """Force immediate processing of pending queue items (for testing/debugging)."""
        if self.notification_dispatcher:
            try:
                return await self.notification_dispatcher.force_queue_processing()
            except Exception as e:
                logger.error(f"Error forcing queue processing: {e}")
                return {"error": str(e)}
        else:
            return {"error": "Notification dispatcher not available"}

    # Internal helper methods

    async def _send_startup_notification(self) -> None:
        """Send startup notification."""
        manager = self.safe_notification_manager or self.legacy_notification_manager
        if not manager:
            return

        try:
            enabled_channels = self.notification_settings.get_enabled_channels()
            channel_names = [name for name, _ in enabled_channels]

            architecture = "queue-based" if self.safe_notification_manager else "legacy"
            message = (
                f"CoachIQ notification system started successfully with {architecture} architecture "
                f"and {len(channel_names)} channels: {', '.join(channel_names)}"
            )

            await manager.send_system_notification(
                message=message, level="info", component="Notification System"
            )

        except Exception as e:
            logger.warning(f"Failed to send startup notification: {e}")

    async def _test_notification_channels(self) -> None:
        """Test notification channels on startup."""
        manager = self.safe_notification_manager or self.legacy_notification_manager
        if not manager:
            return

        try:
            logger.info("Testing notification channels...")
            results = await manager.test_channels()

            for channel, success in results.items():
                if channel in self._channel_status:
                    self._channel_status[channel].healthy = success
                    if not success:
                        logger.warning(f"Notification channel {channel} test failed")
                    else:
                        logger.debug(f"Notification channel {channel} test passed")

        except Exception as e:
            logger.warning(f"Error testing notification channels: {e}")

    async def _start_background_tasks(self) -> None:
        """Start background monitoring tasks."""
        try:
            # Start channel health monitoring task
            if self.config.get("enable_health_monitoring", True):
                health_task = asyncio.create_task(self._health_monitoring_loop())
                self._background_tasks.append(health_task)

        except Exception as e:
            logger.warning(f"Error starting background tasks: {e}")

    async def _health_monitoring_loop(self) -> None:
        """Background task for monitoring notification channel health."""
        while True:
            try:
                # Test channels periodically
                manager = self.safe_notification_manager or self.legacy_notification_manager
                if manager:
                    results = await manager.test_channels()

                    for channel, success in results.items():
                        if channel in self._channel_status:
                            status = self._channel_status[channel]
                            status.healthy = success

                            if not success:
                                status.consecutive_failures += 1
                                logger.warning(
                                    f"Notification channel {channel} health check failed "
                                    f"({status.consecutive_failures} consecutive failures)"
                                )
                            else:
                                status.consecutive_failures = 0

                # Update queue and dispatcher statistics
                if self.safe_notification_manager and self.notification_dispatcher:
                    try:
                        queue_stats = await self.safe_notification_manager.get_queue_statistics()
                        dispatcher_metrics = self.notification_dispatcher.get_metrics()

                        # Update feature stats with latest queue info
                        self._stats["notifications_processed"] = dispatcher_metrics.get(
                            "total_processed", 0
                        )
                        self._stats["dispatcher_running"] = self.notification_dispatcher.is_running

                    except Exception as e:
                        logger.debug(f"Error updating queue statistics: {e}")

                # Sleep for health check interval (default 5 minutes)
                await asyncio.sleep(self.config.get("health_check_interval", 300))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in notification health monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
