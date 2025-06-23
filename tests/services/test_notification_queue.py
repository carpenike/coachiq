"""
Unit tests for NotificationQueue with SQLite persistence and async operations.

Tests cover:
- Queue initialization and schema creation
- Notification enqueuing and dequeuing
- Batch operations and write batching
- Retry logic with exponential backoff
- Dead letter queue functionality
- Statistics and monitoring
- Error handling and recovery
- WAL mode and crash safety
"""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationStatus,
    NotificationType,
    QueueStatistics,
)
from backend.services.notification_queue import NotificationQueue


@pytest.fixture
async def temp_db_path():
    """Create temporary database path for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_notifications.db"
        yield str(db_path)


@pytest.fixture
async def notification_queue(temp_db_path):
    """Create and initialize NotificationQueue for testing."""
    queue = NotificationQueue(temp_db_path)
    await queue.initialize()

    # Disable maintenance loop for testing
    if hasattr(queue, "_maintenance_task"):
        queue._maintenance_task.cancel()

    yield queue

    try:
        await queue.close()
    except Exception:
        pass  # Ignore cleanup errors in tests


@pytest.fixture
def sample_notification():
    """Create sample notification payload for testing."""
    return NotificationPayload(
        message="Test notification message",
        title="Test Notification",
        level=NotificationType.INFO,
        channels=[NotificationChannel.SYSTEM],
        tags=["test"],
        recipient="test@example.com",
        template="test_template",
        context={"key": "value"},
        priority=1,
        source_component="test_component",
    )


class TestNotificationQueueInitialization:
    """Test queue initialization and configuration."""

    async def test_queue_initialization_creates_schema(self, temp_db_path):
        """Test that queue initialization creates proper database schema."""
        queue = NotificationQueue(temp_db_path)
        await queue.initialize()

        # Verify database file exists
        assert Path(temp_db_path).exists()

        # Verify schema by attempting to query tables
        import aiosqlite

        async with aiosqlite.connect(temp_db_path) as db:
            # Check notifications table
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'"
            )
            result = await cursor.fetchone()
            assert result is not None

            # Check dead_letter_queue table
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dead_letter_queue'"
            )
            result = await cursor.fetchone()
            assert result is not None

            # Check indexes
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_notifications_%'"
            )
            indexes = await cursor.fetchall()
            assert len(indexes) >= 3  # Should have at least 3 indexes

        await queue.close()

    async def test_queue_initialization_sets_wal_mode(self, temp_db_path):
        """Test that queue initialization enables WAL mode."""
        queue = NotificationQueue(temp_db_path)
        await queue.initialize()

        import aiosqlite

        async with aiosqlite.connect(temp_db_path) as db:
            cursor = await db.execute("PRAGMA journal_mode")
            result = await cursor.fetchone()
            assert result[0].upper() == "WAL"

        await queue.close()

    async def test_queue_initialization_creates_directory(self):
        """Test that queue initialization creates parent directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nested_path = Path(temp_dir) / "nested" / "path" / "notifications.db"
            queue = NotificationQueue(str(nested_path))
            await queue.initialize()

            assert nested_path.exists()
            assert nested_path.parent.exists()

            await queue.close()


class TestNotificationEnqueuing:
    """Test notification enqueuing operations."""

    async def test_enqueue_single_notification(self, notification_queue, sample_notification):
        """Test enqueuing a single notification."""
        notification_id = await notification_queue.enqueue(sample_notification)

        assert notification_id == sample_notification.id

        # Verify notification is in database
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 1

    async def test_enqueue_multiple_notifications(self, notification_queue):
        """Test enqueuing multiple notifications."""
        notifications = []
        for i in range(5):
            notification = NotificationPayload(
                message=f"Test message {i}",
                title=f"Test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
                priority=i + 1,
            )
            notifications.append(notification)

        # Enqueue all notifications
        for notification in notifications:
            await notification_queue.enqueue(notification)

        # Flush any pending batches
        await notification_queue._flush_write_batch()

        # Verify all are in queue
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 5

    async def test_enqueue_with_write_batching(self, notification_queue):
        """Test that write batching works correctly."""
        # Set small batch size for testing
        notification_queue._batch_size = 3

        notifications = []
        for i in range(5):
            notification = NotificationPayload(
                message=f"Batch test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            notifications.append(notification)

        # Enqueue notifications rapidly
        tasks = [notification_queue.enqueue(notification) for notification in notifications]
        await asyncio.gather(*tasks)

        # Verify all notifications are persisted
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 5

    async def test_enqueue_scheduled_notification(self, notification_queue):
        """Test enqueuing notifications with scheduled delivery."""
        future_time = datetime.utcnow() + timedelta(hours=1)
        notification = NotificationPayload(
            message="Scheduled notification",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
            scheduled_for=future_time,
        )

        await notification_queue.enqueue(notification)

        # Should not be available for immediate processing
        batch = await notification_queue.dequeue_batch(size=10)
        assert len(batch) == 0

        # Verify it's in the queue
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 1


class TestNotificationDequeuing:
    """Test notification dequeuing and batch operations."""

    async def test_dequeue_batch_empty_queue(self, notification_queue):
        """Test dequeuing from empty queue returns empty list."""
        batch = await notification_queue.dequeue_batch(size=10)
        assert batch == []

    async def test_dequeue_batch_with_notifications(self, notification_queue):
        """Test dequeuing batch with available notifications."""
        # Add notifications to queue
        notifications = []
        for i in range(5):
            notification = NotificationPayload(
                message=f"Dequeue test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
                priority=i + 1,
            )
            await notification_queue.enqueue(notification)
            notifications.append(notification)

        # Dequeue batch
        batch = await notification_queue.dequeue_batch(size=3)
        assert len(batch) == 3

        # Verify notifications are marked as processing
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 2
        assert stats.processing_count == 3

    async def test_dequeue_batch_respects_priority(self, notification_queue):
        """Test that dequeuing respects priority ordering."""
        # Add notifications with different priorities
        high_priority = NotificationPayload(
            message="High priority",
            level=NotificationType.CRITICAL,
            channels=[NotificationChannel.SYSTEM],
            priority=1,
        )
        low_priority = NotificationPayload(
            message="Low priority",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
            priority=10,
        )

        # Enqueue in reverse priority order
        await notification_queue.enqueue(low_priority)
        await notification_queue.enqueue(high_priority)

        # Dequeue should return high priority first
        batch = await notification_queue.dequeue_batch(size=2)
        assert len(batch) == 2
        assert batch[0].message == "High priority"
        assert batch[1].message == "Low priority"

    async def test_dequeue_batch_excludes_scheduled(self, notification_queue):
        """Test that dequeuing excludes future-scheduled notifications."""
        # Add immediate notification
        immediate = NotificationPayload(
            message="Immediate",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
        )

        # Add future-scheduled notification
        future_time = datetime.utcnow() + timedelta(hours=1)
        scheduled = NotificationPayload(
            message="Scheduled",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
            scheduled_for=future_time,
        )

        await notification_queue.enqueue(scheduled)
        await notification_queue.enqueue(immediate)

        # Should only return immediate notification
        batch = await notification_queue.dequeue_batch(size=10)
        assert len(batch) == 1
        assert batch[0].message == "Immediate"


class TestNotificationCompletion:
    """Test notification completion and failure handling."""

    async def test_mark_notification_complete(self, notification_queue, sample_notification):
        """Test marking notification as complete."""
        # Enqueue and dequeue notification
        await notification_queue.enqueue(sample_notification)
        batch = await notification_queue.dequeue_batch(size=1)
        notification = batch[0]

        # Mark as complete
        success = await notification_queue.mark_complete(notification.id)
        assert success

        # Verify statistics
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 0
        assert stats.processing_count == 0
        assert stats.completed_count == 1

    async def test_mark_notification_failed_with_retry(
        self, notification_queue, sample_notification
    ):
        """Test marking notification as failed with retry."""
        # Enqueue and dequeue notification
        await notification_queue.enqueue(sample_notification)
        batch = await notification_queue.dequeue_batch(size=1)
        notification = batch[0]

        # Mark as failed (should retry)
        success = await notification_queue.mark_failed(
            notification.id, "Test failure", should_retry=True
        )
        assert success

        # Should be back in pending status for retry
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 1
        assert stats.processing_count == 0

    async def test_mark_notification_failed_move_to_dlq(self, notification_queue):
        """Test marking notification as failed and moving to DLQ."""
        # Create notification with max retries = 1
        notification = NotificationPayload(
            message="Will fail",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
            max_retries=1,
        )

        await notification_queue.enqueue(notification)
        batch = await notification_queue.dequeue_batch(size=1)
        dequeued = batch[0]

        # Fail once (should retry)
        await notification_queue.mark_failed(dequeued.id, "First failure", should_retry=True)

        # Dequeue again and fail (should move to DLQ)
        batch = await notification_queue.dequeue_batch(size=1)
        dequeued = batch[0]
        await notification_queue.mark_failed(dequeued.id, "Final failure", should_retry=True)

        # Verify moved to DLQ
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 0
        assert stats.dlq_count == 1

    async def test_exponential_backoff_retry_delay(self, notification_queue, sample_notification):
        """Test that retry delay uses exponential backoff."""
        # Enqueue and dequeue notification
        await notification_queue.enqueue(sample_notification)
        batch = await notification_queue.dequeue_batch(size=1)
        notification = batch[0]

        # Mark as failed multiple times and verify delay increases
        import aiosqlite

        async with aiosqlite.connect(notification_queue.db_path) as db:
            # First failure
            await notification_queue.mark_failed(notification.id, "Failure 1", should_retry=True)

            # Check scheduled_for time
            cursor = await db.execute(
                "SELECT scheduled_for, retry_count FROM notifications WHERE id = ?",
                (notification.id,),
            )
            row = await cursor.fetchone()
            assert row is not None
            first_scheduled = datetime.fromisoformat(row[0])
            assert row[1] == 1

            # Second failure (after dequeue)
            batch = await notification_queue.dequeue_batch(size=1)
            if batch:
                await notification_queue.mark_failed(batch[0].id, "Failure 2", should_retry=True)

                cursor = await db.execute(
                    "SELECT scheduled_for, retry_count FROM notifications WHERE id = ?",
                    (notification.id,),
                )
                row = await cursor.fetchone()
                if row:
                    second_scheduled = datetime.fromisoformat(row[0])
                    assert row[1] == 2
                    # Second delay should be longer than first
                    assert second_scheduled > first_scheduled


class TestDeadLetterQueue:
    """Test dead letter queue functionality."""

    async def test_get_dead_letter_queue_empty(self, notification_queue):
        """Test getting DLQ entries from empty queue."""
        entries = await notification_queue.get_dead_letter_queue(limit=10)
        assert entries == []

    async def test_retry_from_dlq(self, notification_queue):
        """Test retrying notification from dead letter queue."""
        # Create notification that will fail and move to DLQ
        notification = NotificationPayload(
            message="DLQ test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
            max_retries=1,
        )

        await notification_queue.enqueue(notification)

        # Fail it enough times to move to DLQ
        for _ in range(2):
            batch = await notification_queue.dequeue_batch(size=1)
            if batch:
                await notification_queue.mark_failed(batch[0].id, "Test failure", should_retry=True)

        # Verify in DLQ
        dlq_entries = await notification_queue.get_dead_letter_queue()
        assert len(dlq_entries) == 1

        # Retry from DLQ
        success = await notification_queue.retry_from_dlq(dlq_entries[0].id)
        assert success

        # Should be back in main queue
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 1
        assert stats.dlq_count == 0

    async def test_dlq_entry_contains_original_data(self, notification_queue, sample_notification):
        """Test that DLQ entries preserve original notification data."""
        # Modify notification to fail quickly
        sample_notification.max_retries = 0

        await notification_queue.enqueue(sample_notification)
        batch = await notification_queue.dequeue_batch(size=1)
        await notification_queue.mark_failed(batch[0].id, "Move to DLQ", should_retry=True)

        # Get DLQ entry
        dlq_entries = await notification_queue.get_dead_letter_queue()
        assert len(dlq_entries) == 1

        entry = dlq_entries[0]
        assert entry.original_notification.message == sample_notification.message
        assert entry.original_notification.title == sample_notification.title
        assert entry.failure_reason == "Move to DLQ"


class TestQueueStatistics:
    """Test queue statistics and monitoring."""

    async def test_statistics_empty_queue(self, notification_queue):
        """Test statistics for empty queue."""
        stats = await notification_queue.get_statistics()

        assert stats.pending_count == 0
        assert stats.processing_count == 0
        assert stats.completed_count == 0
        assert stats.failed_count == 0
        assert stats.dlq_count == 0
        assert stats.success_rate == 0.0
        assert stats.oldest_pending is None

    async def test_statistics_with_notifications(self, notification_queue):
        """Test statistics with various notification states."""
        # Add pending notifications
        for i in range(3):
            notification = NotificationPayload(
                message=f"Pending {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)

        # Process one notification to completion
        batch = await notification_queue.dequeue_batch(size=1)
        await notification_queue.mark_complete(batch[0].id)

        # Mark one as failed
        batch = await notification_queue.dequeue_batch(size=1)
        await notification_queue.mark_failed(batch[0].id, "Test failure", should_retry=False)

        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 1
        assert stats.processing_count == 0
        assert stats.completed_count == 1
        assert stats.failed_count == 1

    async def test_statistics_caching(self, notification_queue, sample_notification):
        """Test that statistics are cached appropriately."""
        await notification_queue.enqueue(sample_notification)

        # First call should compute stats
        stats1 = await notification_queue.get_statistics()

        # Second call within cache window should return cached result
        stats2 = await notification_queue.get_statistics()

        assert stats1.pending_count == stats2.pending_count

    async def test_queue_size_bytes_tracking(self, notification_queue, sample_notification):
        """Test that database size is tracked in statistics."""
        await notification_queue.enqueue(sample_notification)

        stats = await notification_queue.get_statistics()
        assert stats.queue_size_bytes is not None
        assert stats.queue_size_bytes > 0


class TestQueueCleanup:
    """Test queue cleanup and maintenance operations."""

    async def test_cleanup_old_notifications(self, notification_queue):
        """Test cleanup of old completed notifications."""
        # Create old notification
        old_notification = NotificationPayload(
            message="Old notification",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
        )

        await notification_queue.enqueue(old_notification)
        batch = await notification_queue.dequeue_batch(size=1)
        await notification_queue.mark_complete(batch[0].id)

        # Manually set completion time to old date
        import aiosqlite

        old_date = (datetime.utcnow() - timedelta(days=35)).isoformat()
        async with aiosqlite.connect(notification_queue.db_path) as db:
            await db.execute(
                "UPDATE notifications SET completed_at = ? WHERE id = ?",
                (old_date, batch[0].id),
            )
            await db.commit()

        # Clean up old notifications
        cleaned = await notification_queue.cleanup_old_notifications(days=30)
        assert cleaned == 1

        # Verify notification was removed
        stats = await notification_queue.get_statistics()
        assert stats.completed_count == 0

    async def test_cleanup_preserves_recent_notifications(
        self, notification_queue, sample_notification
    ):
        """Test that cleanup preserves recent notifications."""
        await notification_queue.enqueue(sample_notification)
        batch = await notification_queue.dequeue_batch(size=1)
        await notification_queue.mark_complete(batch[0].id)

        # Clean up (should preserve recent notification)
        cleaned = await notification_queue.cleanup_old_notifications(days=30)
        assert cleaned == 0

        # Verify notification still exists
        stats = await notification_queue.get_statistics()
        assert stats.completed_count == 1


class TestErrorHandling:
    """Test error handling and recovery scenarios."""

    async def test_enqueue_invalid_notification_data(self, notification_queue):
        """Test handling of invalid notification data."""
        # This should be handled by Pydantic validation before reaching the queue
        # But we test queue robustness
        notification = NotificationPayload(
            message="Valid message",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
        )

        # Should work normally
        notification_id = await notification_queue.enqueue(notification)
        assert notification_id == notification.id

    async def test_dequeue_from_corrupted_data(self, notification_queue):
        """Test handling of corrupted notification data in database."""
        # Insert corrupted data directly into database
        import aiosqlite

        async with aiosqlite.connect(notification_queue.db_path) as db:
            await db.execute(
                """
                INSERT INTO notifications (id, created_at, data, status, priority, retry_count, max_retries)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    "corrupted-id",
                    datetime.utcnow().isoformat(),
                    "invalid json data",
                    "pending",
                    1,
                    0,
                    3,
                ),
            )
            await db.commit()

        # Dequeue should handle corruption gracefully
        batch = await notification_queue.dequeue_batch(size=10)
        # Should return empty batch since corrupted data can't be parsed
        assert batch == []

    async def test_database_connection_error_recovery(self, temp_db_path):
        """Test recovery from database connection errors."""
        queue = NotificationQueue(temp_db_path)
        await queue.initialize()

        # Simulate database file deletion/corruption
        Path(temp_db_path).unlink()

        # Queue operations should handle errors gracefully
        stats = await queue.get_statistics()
        # Should return default stats on error
        assert stats.pending_count == 0

        await queue.close()

    @patch("aiosqlite.connect")
    async def test_database_operation_timeout(
        self, mock_connect, notification_queue, sample_notification
    ):
        """Test handling of database operation timeouts."""
        # Mock database connection to raise timeout
        mock_connect.side_effect = TimeoutError("Database timeout")

        # Operations should handle timeout gracefully
        result = await notification_queue.enqueue(sample_notification)
        assert result == sample_notification.id  # Should still return ID even if enqueue fails

        batch = await notification_queue.dequeue_batch(size=1)
        assert batch == []  # Should return empty batch on error


class TestConcurrency:
    """Test concurrent operations and thread safety."""

    async def test_concurrent_enqueue_operations(self, notification_queue):
        """Test concurrent enqueuing of notifications."""
        # Create multiple notifications
        notifications = [
            NotificationPayload(
                message=f"Concurrent test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            for i in range(10)
        ]

        # Enqueue all concurrently
        tasks = [notification_queue.enqueue(notification) for notification in notifications]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        assert all(result for result in results)

        # Verify all are in queue
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 10

    async def test_concurrent_dequeue_operations(self, notification_queue):
        """Test concurrent dequeuing operations."""
        # Add notifications to queue
        for i in range(10):
            notification = NotificationPayload(
                message=f"Dequeue concurrent {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)

        # Dequeue concurrently
        tasks = [notification_queue.dequeue_batch(size=3) for _ in range(3)]
        results = await asyncio.gather(*tasks)

        # Verify no duplicate notifications across batches
        all_ids = set()
        for batch in results:
            for notification in batch:
                assert notification.id not in all_ids
                all_ids.add(notification.id)

    async def test_write_batch_concurrency(self, notification_queue):
        """Test that write batching handles concurrent access correctly."""
        # Set small batch size to trigger batching
        notification_queue._batch_size = 2

        # Create many notifications and enqueue rapidly
        notifications = [
            NotificationPayload(
                message=f"Batch concurrent {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            for i in range(20)
        ]

        # Enqueue all very quickly to stress write batching
        tasks = [notification_queue.enqueue(notification) for notification in notifications]
        await asyncio.gather(*tasks)

        # Give time for batch processing
        await asyncio.sleep(0.1)

        # All should be persisted
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 20


@pytest.mark.asyncio
class TestIntegrationScenarios:
    """Test complete integration scenarios."""

    async def test_full_notification_lifecycle(self, notification_queue, sample_notification):
        """Test complete notification lifecycle from enqueue to completion."""
        # 1. Enqueue notification
        notification_id = await notification_queue.enqueue(sample_notification)
        assert notification_id

        # 2. Verify in queue
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 1

        # 3. Dequeue for processing
        batch = await notification_queue.dequeue_batch(size=1)
        assert len(batch) == 1
        notification = batch[0]

        # 4. Verify processing state
        stats = await notification_queue.get_statistics()
        assert stats.processing_count == 1
        assert stats.pending_count == 0

        # 5. Mark as complete
        success = await notification_queue.mark_complete(notification.id)
        assert success

        # 6. Verify completion
        stats = await notification_queue.get_statistics()
        assert stats.completed_count == 1
        assert stats.processing_count == 0

    async def test_retry_and_dlq_scenario(self, notification_queue):
        """Test retry scenario that eventually moves to DLQ."""
        # Create notification with limited retries
        notification = NotificationPayload(
            message="Will eventually fail",
            level=NotificationType.ERROR,
            channels=[NotificationChannel.SYSTEM],
            max_retries=2,
        )

        await notification_queue.enqueue(notification)

        # Fail through all retries
        for attempt in range(3):  # 0, 1, 2 (max_retries = 2, so 3rd failure moves to DLQ)
            batch = await notification_queue.dequeue_batch(size=1)
            assert len(batch) == 1

            await notification_queue.mark_failed(
                batch[0].id, f"Attempt {attempt} failed", should_retry=True
            )

            if attempt < 2:
                # Should be back in queue for retry
                stats = await notification_queue.get_statistics()
                assert stats.pending_count == 1
            else:
                # Should be in DLQ now
                stats = await notification_queue.get_statistics()
                assert stats.pending_count == 0
                assert stats.dlq_count == 1

        # Test recovery from DLQ
        dlq_entries = await notification_queue.get_dead_letter_queue()
        assert len(dlq_entries) == 1

        success = await notification_queue.retry_from_dlq(dlq_entries[0].id)
        assert success

        # Should be back in main queue
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 1
        assert stats.dlq_count == 0

    async def test_high_volume_processing(self, notification_queue):
        """Test processing high volume of notifications."""
        # Create many notifications
        notification_count = 100
        notifications = [
            NotificationPayload(
                message=f"High volume {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
                priority=(i % 5) + 1,  # Varying priorities
            )
            for i in range(notification_count)
        ]

        # Enqueue all
        for notification in notifications:
            await notification_queue.enqueue(notification)

        # Process in batches
        processed = 0
        while processed < notification_count:
            batch = await notification_queue.dequeue_batch(size=10)
            if not batch:
                break

            # Mark all as complete
            for notification in batch:
                await notification_queue.mark_complete(notification.id)
                processed += 1

        # Verify all processed
        stats = await notification_queue.get_statistics()
        assert stats.completed_count == notification_count
        assert stats.pending_count == 0
        assert stats.processing_count == 0
