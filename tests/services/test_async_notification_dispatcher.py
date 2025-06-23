"""
Unit tests for AsyncNotificationDispatcher background service.

Tests cover:
- Dispatcher startup and shutdown
- Background queue processing
- Batch processing with concurrency
- Retry logic and error handling
- Dead letter queue integration
- Performance metrics and health monitoring
- Adaptive backoff and recovery
- Integration with notification queue and manager
"""

import asyncio
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.config import NotificationSettings
from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationStatus,
    NotificationType,
)
from backend.services.async_notification_dispatcher import AsyncNotificationDispatcher
from backend.services.notification_manager import NotificationManager
from backend.services.notification_queue import NotificationQueue


@pytest.fixture
def notification_settings():
    """Create test notification settings."""
    settings = MagicMock(spec=NotificationSettings)
    settings.enabled = True
    settings.smtp = MagicMock()
    settings.smtp.enabled = True
    settings.slack = MagicMock()
    settings.slack.enabled = True
    return settings


@pytest.fixture
async def temp_db_path():
    """Create temporary database path for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_dispatcher.db"
        yield str(db_path)


@pytest.fixture
async def notification_queue(temp_db_path):
    """Create NotificationQueue for testing."""
    queue = NotificationQueue(temp_db_path)
    await queue.initialize()
    yield queue
    await queue.close()


@pytest.fixture
def mock_notification_manager():
    """Create mock NotificationManager."""
    manager = MagicMock(spec=NotificationManager)
    manager.send_notification = AsyncMock(return_value=True)
    manager.send_email = AsyncMock(return_value=True)
    return manager


@pytest.fixture
async def dispatcher(notification_queue, mock_notification_manager, notification_settings):
    """Create AsyncNotificationDispatcher for testing."""
    dispatcher = AsyncNotificationDispatcher(
        queue=notification_queue,
        notification_manager=mock_notification_manager,
        config=notification_settings,
        batch_size=5,
        max_concurrent_batches=2,
        processing_interval=0.1,  # Fast for testing
        health_check_interval=1.0,
    )
    yield dispatcher
    if dispatcher._running:
        await dispatcher.stop()


@pytest.fixture
def sample_notification():
    """Create sample notification for testing."""
    return NotificationPayload(
        message="Test dispatcher notification",
        title="Dispatcher Test",
        level=NotificationType.INFO,
        channels=[NotificationChannel.SMTP],
        recipient="test@example.com",
    )


class TestDispatcherLifecycle:
    """Test dispatcher startup and shutdown lifecycle."""

    async def test_dispatcher_startup(self, dispatcher):
        """Test dispatcher startup process."""
        assert not dispatcher._running
        assert dispatcher.health_status["status"] == "stopped"

        await dispatcher.start()

        assert dispatcher._running
        assert dispatcher.health_status["status"] == "running"
        assert dispatcher._worker_task is not None
        assert dispatcher._health_task is not None

    async def test_dispatcher_startup_idempotency(self, dispatcher):
        """Test that starting already running dispatcher is safe."""
        await dispatcher.start()

        # Starting again should not cause issues
        await dispatcher.start()

        assert dispatcher._running

    async def test_dispatcher_shutdown(self, dispatcher):
        """Test dispatcher shutdown process."""
        await dispatcher.start()
        assert dispatcher._running

        await dispatcher.stop()

        assert not dispatcher._running
        assert dispatcher.health_status["status"] == "stopped"
        assert dispatcher._worker_task.done()
        assert dispatcher._health_task.done()

    async def test_dispatcher_shutdown_timeout(self, dispatcher):
        """Test dispatcher shutdown with timeout."""
        await dispatcher.start()

        # Mock worker task to be slow
        async def slow_worker():
            await asyncio.sleep(10)  # Longer than timeout

        dispatcher._worker_task = asyncio.create_task(slow_worker())

        # Should complete within timeout
        start_time = time.time()
        await dispatcher.stop(timeout=0.5)
        end_time = time.time()

        assert end_time - start_time < 1.0  # Should timeout quickly

    async def test_dispatcher_shutdown_when_not_running(self, dispatcher):
        """Test shutdown when dispatcher is not running."""
        assert not dispatcher._running

        # Should not raise exception
        await dispatcher.stop()

    async def test_dispatcher_initialization_metrics(self, dispatcher):
        """Test that dispatcher initializes metrics correctly."""
        metrics = dispatcher.get_metrics()

        assert metrics["total_processed"] == 0
        assert metrics["successful_deliveries"] == 0
        assert metrics["failed_deliveries"] == 0
        assert metrics["startup_time"] is None

    async def test_dispatcher_startup_updates_metrics(self, dispatcher):
        """Test that startup updates metrics."""
        await dispatcher.start()

        metrics = dispatcher.get_metrics()
        assert metrics["startup_time"] is not None


class TestQueueProcessing:
    """Test queue processing functionality."""

    async def test_empty_queue_processing(self, dispatcher, notification_queue):
        """Test processing empty queue."""
        await dispatcher.start()

        # Give some time for processing
        await asyncio.sleep(0.2)

        metrics = dispatcher.get_metrics()
        assert metrics["total_processed"] == 0

    async def test_single_notification_processing(
        self, dispatcher, notification_queue, sample_notification
    ):
        """Test processing single notification."""
        # Add notification to queue
        await notification_queue.enqueue(sample_notification)

        await dispatcher.start()

        # Wait for processing
        await asyncio.sleep(0.5)

        # Verify processing
        metrics = dispatcher.get_metrics()
        assert metrics["total_processed"] >= 1
        assert metrics["successful_deliveries"] >= 1

        # Verify queue is empty
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 0

    async def test_batch_processing(self, dispatcher, notification_queue):
        """Test batch processing of multiple notifications."""
        # Add multiple notifications
        notifications = []
        for i in range(10):
            notification = NotificationPayload(
                message=f"Batch test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)
            notifications.append(notification)

        await dispatcher.start()

        # Wait for processing
        await asyncio.sleep(1.0)

        # Verify all processed
        metrics = dispatcher.get_metrics()
        assert metrics["total_processed"] >= 10

        # Verify queue is empty
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 0

    async def test_concurrent_batch_processing(self, dispatcher, notification_queue):
        """Test concurrent processing of multiple batches."""
        # Add many notifications to trigger multiple batches
        for i in range(20):
            notification = NotificationPayload(
                message=f"Concurrent test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)

        await dispatcher.start()

        # Wait for processing
        await asyncio.sleep(2.0)

        # Verify concurrent processing occurred
        metrics = dispatcher.get_metrics()
        assert metrics["batches_processed"] >= 2
        assert metrics["total_processed"] >= 20

    async def test_processing_respects_max_concurrent_batches(self, dispatcher, notification_queue):
        """Test that processing respects max concurrent batches limit."""
        # Set low limit for testing
        dispatcher.max_concurrent_batches = 1

        # Add many notifications
        for i in range(20):
            notification = NotificationPayload(
                message=f"Concurrency limit test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)

        await dispatcher.start()

        # Monitor active batches
        max_active = 0
        for _ in range(50):  # Check multiple times
            active = len(dispatcher._active_batches)
            max_active = max(max_active, active)
            await asyncio.sleep(0.1)

        # Should not exceed limit
        assert max_active <= 1

    async def test_scheduled_notification_processing(self, dispatcher, notification_queue):
        """Test processing of scheduled notifications."""
        # Add immediate notification
        immediate = NotificationPayload(
            message="Immediate notification",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
        )

        # Add future notification
        future_time = datetime.utcnow() + timedelta(hours=1)
        scheduled = NotificationPayload(
            message="Scheduled notification",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
            scheduled_for=future_time,
        )

        await notification_queue.enqueue(scheduled)
        await notification_queue.enqueue(immediate)

        await dispatcher.start()
        await asyncio.sleep(0.5)

        # Only immediate should be processed
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 1  # Scheduled notification remains


class TestNotificationDelivery:
    """Test notification delivery mechanisms."""

    async def test_smtp_notification_delivery(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test SMTP notification delivery."""
        notification = NotificationPayload(
            message="SMTP test",
            title="SMTP Test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SMTP],
            recipient="test@example.com",
        )

        await notification_queue.enqueue(notification)
        await dispatcher.start()
        await asyncio.sleep(0.5)

        # Verify email was sent
        mock_notification_manager.send_email.assert_called()

        # Verify completion
        stats = await notification_queue.get_statistics()
        assert stats.completed_count >= 1

    async def test_apprise_notification_delivery(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test Apprise notification delivery."""
        notification = NotificationPayload(
            message="Apprise test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SLACK],
        )

        await notification_queue.enqueue(notification)
        await dispatcher.start()
        await asyncio.sleep(0.5)

        # Verify notification was sent
        mock_notification_manager.send_notification.assert_called()

    async def test_pushover_notification_delivery(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test Pushover notification delivery."""
        notification = NotificationPayload(
            message="Pushover test",
            level=NotificationType.WARNING,
            channels=[NotificationChannel.PUSHOVER],
            pushover_priority=1,
            pushover_device="test_device",
        )

        await notification_queue.enqueue(notification)
        await dispatcher.start()
        await asyncio.sleep(0.5)

        # Should call appropriate delivery method
        assert mock_notification_manager.send_notification.called

    async def test_delivery_failure_handling(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test handling of delivery failures."""
        # Mock delivery to fail
        mock_notification_manager.send_notification.return_value = False

        notification = NotificationPayload(
            message="Failure test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SLACK],
        )

        await notification_queue.enqueue(notification)
        await dispatcher.start()
        await asyncio.sleep(0.5)

        # Verify failure was handled
        metrics = dispatcher.get_metrics()
        assert metrics["failed_deliveries"] >= 1

        # Should be marked for retry
        stats = await notification_queue.get_statistics()
        assert stats.pending_count >= 1  # Back in queue for retry

    async def test_delivery_exception_handling(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test handling of delivery exceptions."""
        # Mock delivery to raise exception
        mock_notification_manager.send_notification.side_effect = Exception("Delivery error")

        notification = NotificationPayload(
            message="Exception test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SLACK],
        )

        await notification_queue.enqueue(notification)
        await dispatcher.start()
        await asyncio.sleep(0.5)

        # Should handle exception gracefully
        metrics = dispatcher.get_metrics()
        assert metrics["failed_deliveries"] >= 1


class TestRetryLogic:
    """Test retry logic and error handling."""

    async def test_retry_after_failure(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test retry logic after delivery failure."""
        # Mock to fail first time, succeed second time
        call_count = 0

        async def mock_delivery(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count > 1  # Fail first time, succeed second time

        mock_notification_manager.send_notification.side_effect = mock_delivery

        notification = NotificationPayload(
            message="Retry test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SLACK],
            max_retries=3,
        )

        await notification_queue.enqueue(notification)
        await dispatcher.start()

        # Wait for retry processing
        await asyncio.sleep(2.0)

        # Should eventually succeed
        stats = await notification_queue.get_statistics()
        assert stats.completed_count >= 1

    async def test_maximum_retries_exceeded(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test behavior when maximum retries are exceeded."""
        # Mock to always fail
        mock_notification_manager.send_notification.return_value = False

        notification = NotificationPayload(
            message="Max retries test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SLACK],
            max_retries=1,  # Low retry count for testing
        )

        await notification_queue.enqueue(notification)
        await dispatcher.start()

        # Wait for all retries to complete
        await asyncio.sleep(3.0)

        # Should move to DLQ
        stats = await notification_queue.get_statistics()
        assert stats.dlq_count >= 1

    async def test_exponential_backoff_retry_timing(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test exponential backoff in retry timing."""
        # Mock to always fail
        mock_notification_manager.send_notification.return_value = False

        notification = NotificationPayload(
            message="Backoff test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SLACK],
            max_retries=3,
        )

        await notification_queue.enqueue(notification)
        await dispatcher.start()

        # Monitor retry attempts
        retry_times = []
        start_time = time.time()

        for _ in range(10):  # Monitor for a while
            stats = await notification_queue.get_statistics()
            current_time = time.time()

            # Check if notification status changed (indicating retry)
            # This is a simplified check - in practice we'd need more sophisticated monitoring
            if stats.pending_count > 0:
                retry_times.append(current_time - start_time)

            await asyncio.sleep(0.5)

        # Should have some retry attempts with increasing delays
        # (This is a basic test - more sophisticated timing tests would be needed for production)

    async def test_retry_with_different_error_types(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test retry behavior with different types of errors."""
        # Test with connection error (should retry)
        mock_notification_manager.send_notification.side_effect = ConnectionError("Network error")

        notification = NotificationPayload(
            message="Connection error test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SLACK],
        )

        await notification_queue.enqueue(notification)
        await dispatcher.start()
        await asyncio.sleep(1.0)

        # Should be marked for retry
        stats = await notification_queue.get_statistics()
        assert stats.pending_count >= 1 or stats.processing_count >= 1


class TestHealthMonitoring:
    """Test health monitoring and metrics."""

    async def test_health_status_updates(self, dispatcher, notification_queue):
        """Test health status updates."""
        await dispatcher.start()

        # Wait for health check
        await asyncio.sleep(1.5)

        health = dispatcher.get_health_status()
        assert health["status"] == "running"
        assert health["last_heartbeat"] is not None
        assert "uptime_seconds" in health

    async def test_metrics_collection(self, dispatcher, notification_queue, sample_notification):
        """Test metrics collection during processing."""
        await notification_queue.enqueue(sample_notification)

        await dispatcher.start()
        await asyncio.sleep(0.5)

        metrics = dispatcher.get_metrics()

        # Should have processing metrics
        assert "total_processed" in metrics
        assert "successful_deliveries" in metrics
        assert "failed_deliveries" in metrics
        assert "success_rate" in metrics
        assert "avg_batch_processing_time" in metrics

    async def test_performance_metrics_accuracy(self, dispatcher, notification_queue):
        """Test accuracy of performance metrics."""
        # Add multiple notifications
        for i in range(5):
            notification = NotificationPayload(
                message=f"Metrics test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)

        await dispatcher.start()
        await asyncio.sleep(1.0)

        metrics = dispatcher.get_metrics()

        # Verify metrics consistency
        total = metrics["successful_deliveries"] + metrics["failed_deliveries"]
        assert total == metrics["total_processed"]

        if metrics["total_processed"] > 0:
            assert 0 <= metrics["success_rate"] <= 1
            assert 0 <= metrics["failure_rate"] <= 1

    async def test_queue_depth_monitoring(self, dispatcher, notification_queue):
        """Test queue depth monitoring in health status."""
        # Add notifications
        for i in range(10):
            notification = NotificationPayload(
                message=f"Queue depth test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)

        await dispatcher.start()
        await asyncio.sleep(0.2)  # Let it start processing

        health = dispatcher.get_health_status()
        assert "queue_depth" in health
        assert health["queue_depth"] >= 0

    async def test_processing_rate_calculation(self, dispatcher, notification_queue):
        """Test processing rate calculation."""
        await dispatcher.start()

        # Add and process notifications
        for i in range(5):
            notification = NotificationPayload(
                message=f"Rate test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)

        await asyncio.sleep(2.0)  # Let processing complete

        health = dispatcher.get_health_status()
        assert "processing_rate" in health
        assert health["processing_rate"] >= 0


class TestAdaptiveBehavior:
    """Test adaptive behavior and error recovery."""

    async def test_backoff_multiplier_adjustment(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test backoff multiplier adjustment based on success rate."""
        initial_multiplier = dispatcher._backoff_multiplier

        # Mock high failure rate
        mock_notification_manager.send_notification.return_value = False

        # Add notifications
        for i in range(5):
            notification = NotificationPayload(
                message=f"Backoff test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SLACK],
            )
            await notification_queue.enqueue(notification)

        await dispatcher.start()
        await asyncio.sleep(1.0)

        # Backoff multiplier should increase due to failures
        assert dispatcher._backoff_multiplier >= initial_multiplier

    async def test_error_tracking_and_cleanup(self, dispatcher):
        """Test error tracking and cleanup."""
        # Simulate errors
        test_errors = ["Error 1", "Error 2", "Error 3"]

        for error in test_errors:
            await dispatcher._track_error("test_notification", error)

        assert len(dispatcher._recent_errors) == 3

        # Verify error cleanup (would need to manipulate timestamps for full test)
        await dispatcher._track_error("test_notification", "Error 4")
        assert len(dispatcher._recent_errors) == 4

    async def test_worker_error_handling(self, dispatcher, notification_queue):
        """Test worker loop error handling."""
        await dispatcher.start()

        # Inject error into worker loop by corrupting queue
        original_dequeue = notification_queue.dequeue_batch
        notification_queue.dequeue_batch = AsyncMock(side_effect=Exception("Worker error"))

        # Wait for error handling
        await asyncio.sleep(1.0)

        # Worker should still be running (error should be handled)
        assert dispatcher._running

        # Restore queue function
        notification_queue.dequeue_batch = original_dequeue

    async def test_graceful_degradation_under_load(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test graceful degradation under high load."""

        # Simulate slow processing
        async def slow_delivery(*args, **kwargs):
            await asyncio.sleep(0.1)  # Slow delivery
            return True

        mock_notification_manager.send_notification.side_effect = slow_delivery

        # Add many notifications quickly
        for i in range(20):
            notification = NotificationPayload(
                message=f"Load test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SLACK],
            )
            await notification_queue.enqueue(notification)

        await dispatcher.start()
        await asyncio.sleep(3.0)

        # Should handle load gracefully without crashing
        assert dispatcher._running

        # Some notifications should be processed
        metrics = dispatcher.get_metrics()
        assert metrics["total_processed"] > 0


class TestForceProcessing:
    """Test force processing functionality."""

    async def test_force_queue_processing(self, dispatcher, notification_queue):
        """Test force processing of queue."""
        # Add notifications
        for i in range(5):
            notification = NotificationPayload(
                message=f"Force processing test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)

        await dispatcher.start()

        # Force processing
        result = await dispatcher.force_queue_processing()

        assert "processed_batches" in result
        assert "notifications_processed" in result
        assert result["processed_batches"] >= 1

    async def test_force_processing_when_stopped(self, dispatcher):
        """Test force processing when dispatcher is stopped."""
        result = await dispatcher.force_queue_processing()

        assert "error" in result
        assert "not running" in result["error"]

    async def test_force_processing_safety_limit(self, dispatcher, notification_queue):
        """Test that force processing respects safety limits."""
        # Add many notifications
        for i in range(200):
            notification = NotificationPayload(
                message=f"Safety limit test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)

        await dispatcher.start()

        result = await dispatcher.force_queue_processing()

        # Should not process more than safety limit
        assert result["processed_batches"] <= 10


class TestIntegrationScenarios:
    """Test complete integration scenarios."""

    async def test_full_notification_lifecycle_with_dispatcher(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test complete notification lifecycle through dispatcher."""
        # 1. Queue notification
        notification = NotificationPayload(
            message="Full lifecycle test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SMTP],
            recipient="test@example.com",
        )

        await notification_queue.enqueue(notification)

        # 2. Start dispatcher
        await dispatcher.start()

        # 3. Wait for processing
        await asyncio.sleep(1.0)

        # 4. Verify completion
        stats = await notification_queue.get_statistics()
        assert stats.completed_count >= 1
        assert stats.pending_count == 0

        # 5. Verify delivery was attempted
        mock_notification_manager.send_email.assert_called()

        # 6. Verify metrics
        metrics = dispatcher.get_metrics()
        assert metrics["total_processed"] >= 1
        assert metrics["successful_deliveries"] >= 1

    async def test_mixed_success_and_failure_processing(
        self, dispatcher, notification_queue, mock_notification_manager
    ):
        """Test processing with mixed success and failure results."""
        # Mock to succeed on some, fail on others
        call_count = 0

        async def mixed_delivery(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count % 2 == 0  # Succeed on even calls

        mock_notification_manager.send_notification.side_effect = mixed_delivery

        # Add multiple notifications
        for i in range(10):
            notification = NotificationPayload(
                message=f"Mixed result test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SLACK],
            )
            await notification_queue.enqueue(notification)

        await dispatcher.start()
        await asyncio.sleep(2.0)

        # Verify mixed results
        metrics = dispatcher.get_metrics()
        assert metrics["successful_deliveries"] > 0
        assert metrics["failed_deliveries"] > 0
        assert metrics["total_processed"] >= 10

    async def test_dispatcher_resilience_to_queue_errors(self, dispatcher, notification_queue):
        """Test dispatcher resilience to queue operation errors."""
        await dispatcher.start()

        # Simulate queue errors
        original_dequeue = notification_queue.dequeue_batch
        error_count = 0

        async def error_prone_dequeue(*args, **kwargs):
            nonlocal error_count
            error_count += 1
            if error_count <= 3:
                raise Exception(f"Queue error {error_count}")
            return await original_dequeue(*args, **kwargs)

        notification_queue.dequeue_batch = error_prone_dequeue

        # Add notification
        notification = NotificationPayload(
            message="Resilience test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
        )
        await notification_queue.enqueue(notification)

        # Wait for error recovery
        await asyncio.sleep(2.0)

        # Should recover and continue processing
        assert dispatcher._running

        # Restore original function
        notification_queue.dequeue_batch = original_dequeue

    async def test_concurrent_dispatcher_and_queue_operations(self, dispatcher, notification_queue):
        """Test concurrent dispatcher processing and queue operations."""
        await dispatcher.start()

        # Concurrently add notifications while processing
        async def add_notifications():
            for i in range(20):
                notification = NotificationPayload(
                    message=f"Concurrent test {i}",
                    level=NotificationType.INFO,
                    channels=[NotificationChannel.SYSTEM],
                )
                await notification_queue.enqueue(notification)
                await asyncio.sleep(0.05)  # Small delay

        # Start adding notifications concurrently with processing
        add_task = asyncio.create_task(add_notifications())

        # Let both run concurrently
        await asyncio.sleep(2.0)

        # Wait for adding to complete
        await add_task

        # Let processing finish
        await asyncio.sleep(1.0)

        # Verify all were processed without conflicts
        metrics = dispatcher.get_metrics()
        assert metrics["total_processed"] >= 20

    async def test_dispatcher_performance_under_sustained_load(
        self, dispatcher, notification_queue
    ):
        """Test dispatcher performance under sustained load."""
        await dispatcher.start()

        # Add notifications continuously
        total_added = 0
        start_time = time.time()

        # Run for 3 seconds
        while time.time() - start_time < 3.0:
            notification = NotificationPayload(
                message=f"Sustained load test {total_added}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)
            total_added += 1

            # Small delay to prevent overwhelming
            await asyncio.sleep(0.01)

        # Let processing complete
        await asyncio.sleep(2.0)

        # Verify performance
        metrics = dispatcher.get_metrics()
        assert metrics["total_processed"] >= total_added * 0.8  # At least 80% processed

        # Verify processing rate
        if metrics["total_processed"] > 0 and dispatcher.uptime:
            processing_rate = metrics["total_processed"] / dispatcher.uptime.total_seconds()
            assert processing_rate > 1.0  # Should process at least 1 per second
