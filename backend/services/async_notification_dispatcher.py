"""
Async Notification Dispatcher for Background Queue Processing

This module implements the background service that processes notifications
from the persistent queue and delivers them via Apprise. Designed for
reliability in RV-C environments with comprehensive error handling,
retry logic, and performance optimization.

Key Features:
- Async/await background processing with configurable concurrency
- Exponential backoff retry logic with jitter
- Dead letter queue handling for permanent failures
- Batch processing for efficiency
- Real-time metrics and health monitoring
- Graceful shutdown and error recovery

Example:
    >>> dispatcher = AsyncNotificationDispatcher(queue, apprise_manager)
    >>> await dispatcher.start()
    >>> # Dispatcher runs in background processing notifications
    >>> await dispatcher.stop()
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

try:
    import apprise

    APPRISE_AVAILABLE = True
except ImportError:
    APPRISE_AVAILABLE = False

import contextlib

from backend.core.config import NotificationSettings
from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
)
from backend.services.notification_manager import NotificationManager
from backend.services.notification_queue import NotificationQueue


class AsyncNotificationDispatcher:
    """
    Background service for processing notification queue.

    Handles the actual delivery of notifications from the persistent queue
    to external services via Apprise, with comprehensive error handling
    and retry logic suitable for safety-critical environments.
    """

    def __init__(
        self,
        queue: NotificationQueue,
        notification_manager: NotificationManager,
        config: NotificationSettings | None = None,
        batch_size: int = 10,
        max_concurrent_batches: int = 3,
        processing_interval: float = 1.0,
        health_check_interval: float = 30.0,
    ):
        """
        Initialize notification dispatcher.

        Args:
            queue: NotificationQueue instance
            notification_manager: Original NotificationManager for actual delivery
            config: Optional notification configuration
            batch_size: Number of notifications to process per batch
            max_concurrent_batches: Maximum concurrent processing batches
            processing_interval: Seconds between queue polling
            health_check_interval: Seconds between health checks
        """
        self.queue = queue
        self.notification_manager = notification_manager
        self.config = config
        self.batch_size = batch_size
        self.max_concurrent_batches = max_concurrent_batches
        self.processing_interval = processing_interval
        self.health_check_interval = health_check_interval

        self.logger = logging.getLogger(f"{__name__}.AsyncNotificationDispatcher")

        # Runtime state
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None
        self._active_batches: set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()

        # Performance metrics
        self.metrics = {
            "total_processed": 0,
            "successful_deliveries": 0,
            "failed_deliveries": 0,
            "retries_attempted": 0,
            "dlq_moves": 0,
            "processing_time_total": 0.0,
            "batches_processed": 0,
            "last_activity": None,
            "startup_time": None,
            "errors": [],
        }

        # Health monitoring
        self.health_status = {
            "status": "stopped",
            "last_heartbeat": None,
            "queue_depth": 0,
            "processing_rate": 0.0,
            "error_rate": 0.0,
            "uptime_seconds": 0,
        }

        # Error tracking for adaptive behavior
        self._recent_errors: list[dict[str, Any]] = []
        self._error_window = timedelta(minutes=15)
        self._backoff_multiplier = 1.0
        self._max_backoff_multiplier = 4.0

    async def start(self) -> None:
        """Start the background dispatcher."""
        if self._running:
            self.logger.warning("Dispatcher already running")
            return

        try:
            self._running = True
            self.metrics["startup_time"] = datetime.utcnow()
            self.health_status["status"] = "starting"

            # Start worker and health monitoring tasks
            self._worker_task = asyncio.create_task(self._worker_loop())
            self._health_task = asyncio.create_task(self._health_monitor_loop())

            self.health_status["status"] = "running"
            self.logger.info("AsyncNotificationDispatcher started")

        except Exception as e:
            self._running = False
            self.health_status["status"] = "failed"
            self.logger.error(f"Failed to start dispatcher: {e}")
            raise

    async def stop(self, timeout: float = 30.0) -> None:
        """
        Stop the dispatcher gracefully.

        Args:
            timeout: Maximum time to wait for graceful shutdown
        """
        if not self._running:
            return

        self.logger.info("Stopping AsyncNotificationDispatcher...")
        self.health_status["status"] = "stopping"

        # Signal shutdown
        self._running = False
        self._shutdown_event.set()

        try:
            # Wait for worker task to complete
            if self._worker_task and not self._worker_task.done():
                await asyncio.wait_for(self._worker_task, timeout=timeout)

            # Wait for all active batches to complete
            if self._active_batches:
                self.logger.info(
                    f"Waiting for {len(self._active_batches)} active batches to complete"
                )
                await asyncio.wait_for(
                    asyncio.gather(*self._active_batches, return_exceptions=True), timeout=timeout
                )

            # Stop health monitor
            if self._health_task and not self._health_task.done():
                self._health_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._health_task

            self.health_status["status"] = "stopped"
            self.logger.info("AsyncNotificationDispatcher stopped successfully")

        except TimeoutError:
            self.logger.warning(f"Dispatcher shutdown timed out after {timeout}s, forcing stop")

            # Cancel all remaining tasks
            for task in [self._worker_task, self._health_task, *list(self._active_batches)]:
                if task and not task.done():
                    task.cancel()

        except Exception as e:
            self.logger.error(f"Error during dispatcher shutdown: {e}")

        finally:
            self.health_status["status"] = "stopped"

    async def _worker_loop(self) -> None:
        """Main worker loop that processes notification batches."""
        self.logger.info("Notification dispatcher worker started")

        while self._running:
            try:
                # Check if we have capacity for more batches
                if len(self._active_batches) >= self.max_concurrent_batches:
                    await asyncio.sleep(self.processing_interval)
                    continue

                # Get batch of notifications to process
                batch = await self.queue.dequeue_batch(self.batch_size)

                if not batch:
                    # No work available, wait before checking again
                    await asyncio.sleep(self.processing_interval)
                    continue

                # Process batch in background task
                batch_task = asyncio.create_task(self._process_batch(batch))
                self._active_batches.add(batch_task)

                # Clean up completed batch tasks
                self._active_batches = {task for task in self._active_batches if not task.done()}

                # Update activity timestamp
                self.metrics["last_activity"] = datetime.utcnow()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Worker loop error: {e}")
                await self._handle_worker_error(e)

                # Apply adaptive backoff on errors
                backoff_time = self.processing_interval * self._backoff_multiplier
                await asyncio.sleep(min(backoff_time, 30.0))  # Max 30 second backoff

        self.logger.info("Notification dispatcher worker stopped")

    async def _process_batch(self, notifications: list[NotificationPayload]) -> None:
        """
        Process a batch of notifications concurrently.

        Args:
            notifications: List of notifications to process
        """
        batch_start_time = time.time()
        batch_id = f"batch_{int(batch_start_time)}"

        try:
            self.logger.debug(
                f"Processing batch {batch_id} with {len(notifications)} notifications"
            )

            # Create tasks for concurrent processing
            tasks = [
                asyncio.create_task(self._process_single_notification(notification))
                for notification in notifications
            ]

            # Wait for all notifications in batch to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Analyze results
            successful = sum(1 for result in results if result is True)
            failed = len(results) - successful

            # Update metrics
            processing_time = time.time() - batch_start_time
            self.metrics["batches_processed"] += 1
            self.metrics["total_processed"] += len(notifications)
            self.metrics["successful_deliveries"] += successful
            self.metrics["failed_deliveries"] += failed
            self.metrics["processing_time_total"] += processing_time

            # Log batch completion
            self.logger.info(
                f"Batch {batch_id} completed: {successful} successful, {failed} failed, "
                f"{processing_time:.2f}s processing time"
            )

            # Adjust backoff based on success rate
            success_rate = successful / len(notifications) if notifications else 0
            await self._adjust_backoff_multiplier(success_rate)

        except Exception as e:
            self.logger.error(f"Batch processing failed: {e}")

            # Mark all notifications in batch as failed
            for notification in notifications:
                await self.queue.mark_failed(
                    notification.id, f"Batch processing error: {e!s}", should_retry=True
                )

    async def _process_single_notification(self, notification: NotificationPayload) -> bool:
        """
        Process a single notification.

        Args:
            notification: Notification to process

        Returns:
            bool: True if successful, False if failed
        """
        try:
            start_time = time.time()

            # Determine delivery method based on channels
            success = False

            if NotificationChannel.SMTP in notification.channels:
                success = await self._send_email(notification)
            elif NotificationChannel.WEBHOOK in notification.channels:
                success = await self._send_webhook_notification(notification)
            else:
                success = await self._send_apprise_notification(notification)

            processing_time = time.time() - start_time

            if success:
                await self.queue.mark_complete(notification.id)
                self.logger.debug(
                    f"Notification {notification.id} delivered successfully in {processing_time:.2f}s"
                )
                return True
            await self.queue.mark_failed(notification.id, "Delivery failed", should_retry=True)
            return False

        except Exception as e:
            error_msg = f"Processing error: {e!s}"
            self.logger.error(f"Failed to process notification {notification.id}: {error_msg}")

            await self.queue.mark_failed(notification.id, error_msg, should_retry=True)

            # Track error for adaptive behavior
            await self._track_error(notification.id, str(e))

            return False

    async def _send_email(self, notification: NotificationPayload) -> bool:
        """Send email notification via original NotificationManager."""
        try:
            if not notification.recipient:
                self.logger.warning(f"Email notification {notification.id} missing recipient")
                return False

            context = notification.context.copy()
            context.update(
                {
                    "title": notification.title,
                    "message": notification.message,
                    "level": notification.level.value,
                }
            )

            return await self.notification_manager.send_email(
                to_email=notification.recipient,
                subject=notification.title or "CoachIQ Notification",
                template=notification.template or "system_notification",
                context=context,
            )

        except Exception as e:
            self.logger.error(f"Email sending failed for {notification.id}: {e}")
            return False

    async def _send_apprise_notification(self, notification: NotificationPayload) -> bool:
        """Send notification via Apprise channels."""
        try:
            # Map channels to tags for Apprise
            channel_tags = [channel.value for channel in notification.channels]

            # Add Pushover-specific handling
            if NotificationChannel.PUSHOVER in notification.channels:
                # Pushover notifications might need special formatting
                return await self._send_pushover_notification(notification)

            # Use original notification manager for delivery
            return await self.notification_manager.send_notification(
                message=notification.message,
                title=notification.title,
                notify_type=notification.level.value,
                tags=channel_tags,
                template=notification.template,
                context=notification.context,
            )

        except Exception as e:
            self.logger.error(f"Apprise notification failed for {notification.id}: {e}")
            return False

    async def _send_pushover_notification(self, notification: NotificationPayload) -> bool:
        """Send Pushover notification with specific formatting."""
        try:
            # Create Pushover-specific Apprise URL if needed
            if self.config and hasattr(self.config, "pushover") and self.config.pushover.enabled:
                pushover_url = self._build_pushover_url(notification)

                # Create temporary Apprise instance for Pushover
                if APPRISE_AVAILABLE:
                    pushover_apprise = apprise.Apprise()
                    pushover_apprise.add(pushover_url)

                    # Map notification level to Pushover priority
                    notify_type = self._map_to_apprise_type(notification.level.value)

                    return await pushover_apprise.async_notify(
                        body=notification.message, title=notification.title, notify_type=notify_type
                    )

            # Fallback to regular Apprise handling
            return await self._send_apprise_notification(notification)

        except Exception as e:
            self.logger.error(f"Pushover notification failed for {notification.id}: {e}")
            return False

    def _build_pushover_url(self, notification: NotificationPayload) -> str:
        """Build Pushover URL with notification-specific parameters."""
        if not self.config or not hasattr(self.config, "pushover"):
            return ""

        pushover_config = self.config.pushover

        # Base Pushover URL
        url = f"pover://{pushover_config.user_key}@{pushover_config.token}"

        # Add device if specified
        device = notification.pushover_device or pushover_config.device
        if device:
            url += f"/{device}"

        # Add priority parameter
        priority = notification.pushover_priority
        if priority is not None:
            url += f"?priority={priority}"

        return url

    async def _send_webhook_notification(self, notification: NotificationPayload) -> bool:
        """Send notification via webhook channel."""
        try:
            # Import webhook channel here to avoid circular imports
            from backend.integrations.notifications.channels.webhook import (
                send_webhook_notification,
            )

            # Send via webhook channel
            success = await send_webhook_notification(notification)

            if success:
                self.logger.debug(f"Webhook notification {notification.id} sent successfully")
            else:
                self.logger.warning(f"Webhook notification {notification.id} failed to send")

            return success

        except Exception as e:
            self.logger.error(f"Webhook notification failed for {notification.id}: {e}")
            return False

    def _map_to_apprise_type(self, level: str):
        """Map notification level to Apprise notification type."""
        if not APPRISE_AVAILABLE:
            return "info"

        type_mapping = {
            "info": apprise.NotifyType.INFO,
            "success": apprise.NotifyType.SUCCESS,
            "warning": apprise.NotifyType.WARNING,
            "error": apprise.NotifyType.FAILURE,
            "critical": apprise.NotifyType.FAILURE,
        }
        return type_mapping.get(level.lower(), apprise.NotifyType.INFO)

    async def _health_monitor_loop(self) -> None:
        """Background health monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._update_health_status()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Health monitoring error: {e}")

    async def _update_health_status(self) -> None:
        """Update health status metrics."""
        try:
            # Get queue statistics
            queue_stats = await self.queue.get_statistics()

            # Calculate processing rate
            if self.metrics["startup_time"]:
                uptime = (datetime.utcnow() - self.metrics["startup_time"]).total_seconds()
                processing_rate = self.metrics["total_processed"] / max(uptime, 1)
            else:
                uptime = 0
                processing_rate = 0

            # Calculate error rate
            total_processed = self.metrics["total_processed"]
            error_rate = self.metrics["failed_deliveries"] / max(total_processed, 1)

            # Update health status
            self.health_status.update(
                {
                    "last_heartbeat": datetime.utcnow(),
                    "queue_depth": queue_stats.pending_count,
                    "processing_rate": processing_rate,
                    "error_rate": error_rate,
                    "uptime_seconds": uptime,
                    "active_batches": len(self._active_batches),
                    "backoff_multiplier": self._backoff_multiplier,
                }
            )

        except Exception as e:
            self.logger.error(f"Failed to update health status: {e}")

    async def _handle_worker_error(self, error: Exception) -> None:
        """Handle worker loop errors with adaptive behavior."""
        error_info = {
            "timestamp": datetime.utcnow(),
            "error": str(error),
            "type": type(error).__name__,
        }

        self.metrics["errors"].append(error_info)

        # Keep only recent errors
        cutoff_time = datetime.utcnow() - self._error_window
        self.metrics["errors"] = [
            err for err in self.metrics["errors"] if err["timestamp"] > cutoff_time
        ]

        # Increase backoff if too many recent errors
        if len(self.metrics["errors"]) > 5:
            self._backoff_multiplier = min(
                self._backoff_multiplier * 1.5, self._max_backoff_multiplier
            )
            self.logger.warning(f"Increased backoff multiplier to {self._backoff_multiplier}")

    async def _track_error(self, notification_id: str, error: str) -> None:
        """Track error for specific notification."""
        self._recent_errors.append(
            {
                "timestamp": datetime.utcnow(),
                "notification_id": notification_id,
                "error": error,
            }
        )

        # Clean up old errors
        cutoff_time = datetime.utcnow() - self._error_window
        self._recent_errors = [err for err in self._recent_errors if err["timestamp"] > cutoff_time]

    async def _adjust_backoff_multiplier(self, success_rate: float) -> None:
        """Adjust backoff multiplier based on recent success rate."""
        if success_rate >= 0.9:
            # High success rate - reduce backoff
            self._backoff_multiplier = max(1.0, self._backoff_multiplier * 0.95)
        elif success_rate < 0.5:
            # Low success rate - increase backoff
            self._backoff_multiplier = min(
                self._max_backoff_multiplier, self._backoff_multiplier * 1.1
            )

    def get_metrics(self) -> dict[str, Any]:
        """Get dispatcher performance metrics."""
        metrics = dict(self.metrics)

        # Add calculated metrics
        if metrics["total_processed"] > 0:
            metrics["success_rate"] = metrics["successful_deliveries"] / metrics["total_processed"]
            metrics["failure_rate"] = metrics["failed_deliveries"] / metrics["total_processed"]
        else:
            metrics["success_rate"] = 0.0
            metrics["failure_rate"] = 0.0

        if metrics["batches_processed"] > 0:
            metrics["avg_batch_processing_time"] = (
                metrics["processing_time_total"] / metrics["batches_processed"]
            )
        else:
            metrics["avg_batch_processing_time"] = 0.0

        # Add current status
        metrics.update(self.health_status)

        return metrics

    def get_health_status(self) -> dict[str, Any]:
        """Get current health status."""
        return dict(self.health_status)

    async def force_queue_processing(self) -> dict[str, Any]:
        """Force immediate processing of pending queue items (for testing/debugging)."""
        if not self._running:
            return {"error": "Dispatcher not running"}

        try:
            # Get current queue depth
            stats_before = await self.queue.get_statistics()

            # Process available batches immediately
            processed_batches = 0
            while True:
                batch = await self.queue.dequeue_batch(self.batch_size)
                if not batch:
                    break

                await self._process_batch(batch)
                processed_batches += 1

                # Safety limit
                if processed_batches >= 10:
                    break

            # Get updated stats
            stats_after = await self.queue.get_statistics()

            return {
                "processed_batches": processed_batches,
                "queue_depth_before": stats_before.pending_count,
                "queue_depth_after": stats_after.pending_count,
                "notifications_processed": stats_before.pending_count - stats_after.pending_count,
            }

        except Exception as e:
            self.logger.error(f"Force processing failed: {e}")
            return {"error": str(e)}

    @property
    def is_running(self) -> bool:
        """Check if dispatcher is currently running."""
        return self._running and self.health_status["status"] == "running"

    @property
    def uptime(self) -> timedelta | None:
        """Get dispatcher uptime."""
        if self.metrics["startup_time"]:
            return datetime.utcnow() - self.metrics["startup_time"]
        return None
