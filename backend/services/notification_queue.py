"""
SQLite-based Notification Queue for Persistent, Reliable Delivery

This module implements a SQLite-backed notification queue with WAL mode for
durability, designed for safety-critical RV-C environments where notifications
must survive system restarts and handle intermittent connectivity.

Key Features:
- SQLite with WAL mode for crash-safe persistence
- Async/await interface for non-blocking operations
- Dead letter queue for permanently failed notifications
- Batch processing for efficiency
- Comprehensive statistics and monitoring
- Write batching to minimize flash storage wear

Example:
    >>> queue = NotificationQueue("data/notifications.db")
    >>> await queue.initialize()
    >>> notification_id = await queue.enqueue(notification_payload)
    >>> batch = await queue.dequeue_batch(size=10)
    >>> await queue.mark_complete(notification_id)
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite

from backend.models.notification import (
    DeadLetterEntry,
    NotificationPayload,
    NotificationStatus,
    QueueStatistics,
)


class NotificationQueue:
    """
    SQLite-backed persistent notification queue with async interface.

    Designed for reliability in RV-C vehicle environments with:
    - WAL mode for crash-safe durability
    - Write batching to reduce storage wear
    - Comprehensive error handling and retry logic
    - Background cleanup and maintenance
    """

    def __init__(self, db_path: str = "data/notifications.db"):
        """
        Initialize notification queue.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.logger = logging.getLogger(f"{__name__}.NotificationQueue")

        # Write batching for flash storage protection
        self._write_batch: list[NotificationPayload] = []
        self._batch_lock = asyncio.Lock()
        self._batch_timer: asyncio.Task | None = None
        self._batch_size = 10
        self._batch_timeout = 0.5  # 500ms

        # Statistics tracking
        self._stats_cache: QueueStatistics | None = None
        self._stats_cache_expires: datetime | None = None

        # Connection pool for concurrent access
        self._db_initialized = False
        self._maintenance_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """Initialize database schema and configuration."""
        try:
            # Ensure directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Initialize database schema
            await self._init_schema()

            # Configure SQLite for durability and performance
            await self._configure_sqlite()

            # Start background maintenance tasks
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())

            self._db_initialized = True
            self.logger.info(f"NotificationQueue initialized: {self.db_path}")

        except Exception as e:
            self.logger.error(f"Failed to initialize notification queue: {e}")
            raise

    async def enqueue(self, notification: NotificationPayload) -> str:
        """
        Add notification to queue with write batching.

        Args:
            notification: Notification payload to enqueue

        Returns:
            str: Notification ID
        """
        if not self._db_initialized:
            await self.initialize()

        async with self._batch_lock:
            self._write_batch.append(notification)

            # Start batch timer if not already running
            if self._batch_timer is None or self._batch_timer.done():
                self._batch_timer = asyncio.create_task(self._batch_timeout_handler())

            # Flush immediately if batch is full
            if len(self._write_batch) >= self._batch_size:
                await self._flush_write_batch()

        return notification.id

    async def dequeue_batch(self, size: int = 10) -> list[NotificationPayload]:
        """
        Get batch of pending notifications for processing.

        Args:
            size: Maximum batch size

        Returns:
            List of notification payloads ready for processing
        """
        if not self._db_initialized:
            await self.initialize()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Get notifications ready for processing
                async with db.execute(
                    """
                    SELECT data, retry_count, scheduled_for
                    FROM notifications
                    WHERE status = 'pending'
                    AND (scheduled_for IS NULL OR scheduled_for <= ?)
                    ORDER BY priority ASC, created_at ASC
                    LIMIT ?
                """,
                    (datetime.utcnow().isoformat(), size),
                ) as cursor:
                    rows = await cursor.fetchall()

                if not rows:
                    return []

                # Parse notification data
                notifications = []
                notification_ids = []

                for row in rows:
                    try:
                        data = json.loads(row[0])
                        notification = NotificationPayload.model_validate(data)
                        notification.retry_count = row[1]
                        notifications.append(notification)
                        notification_ids.append(notification.id)
                    except Exception as e:
                        self.logger.warning(f"Failed to parse notification data: {e}")
                        continue

                # Mark as processing to prevent duplicate processing
                if notification_ids:
                    # Generate safe parameterized query with correct number of placeholders
                    await db.execute(
                        """  # nosec B608
                        UPDATE notifications
                        SET status = 'processing', last_attempt = ?
                        WHERE id IN ({})
                    """.format(",".join("?" * len(notification_ids))),  # nosec B608
                        [datetime.utcnow().isoformat(), *notification_ids],
                    )
                    await db.commit()

                return notifications

        except Exception as e:
            self.logger.error(f"Failed to dequeue notifications: {e}")
            return []

    async def mark_complete(self, notification_id: str) -> bool:
        """
        Mark notification as successfully completed.

        Args:
            notification_id: ID of completed notification

        Returns:
            bool: True if marked successfully
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    UPDATE notifications
                    SET status = 'sent', completed_at = ?
                    WHERE id = ?
                """,
                    (datetime.utcnow().isoformat(), notification_id),
                )
                await db.commit()
                return True

        except Exception as e:
            self.logger.error(f"Failed to mark notification complete: {e}")
            return False

    async def mark_failed(
        self, notification_id: str, error_message: str, should_retry: bool = True
    ) -> bool:
        """
        Mark notification as failed and handle retry logic.

        Args:
            notification_id: ID of failed notification
            error_message: Failure reason
            should_retry: Whether to retry or move to DLQ

        Returns:
            bool: True if handled successfully
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Get current notification data
                async with db.execute(
                    """
                    SELECT data, retry_count, max_retries
                    FROM notifications
                    WHERE id = ?
                """,
                    (notification_id,),
                ) as cursor:
                    row = await cursor.fetchone()

                if not row:
                    return False

                data, retry_count, max_retries = row
                retry_count += 1

                # Check if we should retry or move to DLQ
                if should_retry and retry_count < max_retries:
                    # Schedule retry with exponential backoff
                    retry_delay = min(300, 30 * (2**retry_count))  # Max 5 minutes
                    retry_time = datetime.utcnow() + timedelta(seconds=retry_delay)

                    await db.execute(
                        """
                        UPDATE notifications
                        SET status = 'pending',
                            retry_count = ?,
                            last_error = ?,
                            scheduled_for = ?
                        WHERE id = ?
                    """,
                        (retry_count, error_message, retry_time.isoformat(), notification_id),
                    )

                    self.logger.info(
                        f"Notification {notification_id} scheduled for retry {retry_count}/{max_retries}"
                    )

                else:
                    # Move to dead letter queue
                    await self._move_to_dlq(notification_id, error_message, retry_count)

                await db.commit()
                return True

        except Exception as e:
            self.logger.error(f"Failed to mark notification as failed: {e}")
            return False

    async def get_statistics(self) -> QueueStatistics:
        """
        Get comprehensive queue statistics.

        Returns:
            QueueStatistics: Current queue statistics
        """
        # Use cached stats if recent
        now = datetime.utcnow()
        if self._stats_cache and self._stats_cache_expires and now < self._stats_cache_expires:
            return self._stats_cache

        try:
            async with aiosqlite.connect(self.db_path) as db:
                stats = QueueStatistics(
                    pending_count=0,
                    processing_count=0,
                    completed_count=0,
                    failed_count=0,
                    dlq_count=0,
                    avg_processing_time=None,
                    success_rate=0.0,
                    oldest_pending=None,
                    last_success=None,
                    last_failure=None,
                    dispatcher_running=False,
                    queue_size_bytes=None,
                )

                # Count notifications by status
                async with db.execute("""
                    SELECT status, COUNT(*)
                    FROM notifications
                    GROUP BY status
                """) as cursor:
                    async for row in cursor:
                        status, count = row
                        if status == "pending":
                            stats.pending_count = count
                        elif status == "processing":
                            stats.processing_count = count
                        elif status == "sent":
                            stats.completed_count = count
                        elif status == "failed":
                            stats.failed_count = count

                # Dead letter queue count
                async with db.execute("SELECT COUNT(*) FROM dead_letter_queue") as cursor:
                    row = await cursor.fetchone()
                    stats.dlq_count = row[0] if row else 0

                # Performance metrics (last 24 hours)
                yesterday = (now - timedelta(days=1)).isoformat()

                async with db.execute(
                    """
                    SELECT
                        AVG(CASE WHEN completed_at IS NOT NULL
                            THEN (julianday(completed_at) - julianday(created_at)) * 86400
                            ELSE NULL END) as avg_time,
                        COUNT(CASE WHEN status = 'sent' AND completed_at > ? THEN 1 END) as success_count,
                        COUNT(CASE WHEN completed_at > ? OR created_at > ? THEN 1 END) as total_count
                    FROM notifications
                    WHERE created_at > ?
                """,
                    (yesterday, yesterday, yesterday, yesterday),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        stats.avg_processing_time = float(row[0])
                        success_count = row[1] or 0
                        total_count = row[2] or 0
                        if total_count > 0:
                            stats.success_rate = success_count / total_count

                # Queue health indicators
                async with db.execute("""
                    SELECT MIN(created_at) FROM notifications WHERE status = 'pending'
                """) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        stats.oldest_pending = datetime.fromisoformat(row[0])

                async with db.execute("""
                    SELECT MAX(completed_at) FROM notifications WHERE status = 'sent'
                """) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        stats.last_success = datetime.fromisoformat(row[0])

                # Database size
                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
                stats.queue_size_bytes = db_size

                # Cache results for 30 seconds
                self._stats_cache = stats
                self._stats_cache_expires = now + timedelta(seconds=30)

                return stats

        except Exception as e:
            self.logger.error(f"Failed to get queue statistics: {e}")
            return QueueStatistics(
                pending_count=0,
                processing_count=0,
                completed_count=0,
                failed_count=0,
                dlq_count=0,
                avg_processing_time=None,
                success_rate=0.0,
                oldest_pending=None,
                last_success=None,
                last_failure=None,
                dispatcher_running=False,
                queue_size_bytes=None,
            )

    async def cleanup_old_notifications(self, days: int = 30) -> int:
        """
        Clean up old completed notifications.

        Args:
            days: Age threshold for cleanup

        Returns:
            int: Number of notifications cleaned up
        """
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    DELETE FROM notifications
                    WHERE status IN ('sent', 'failed')
                    AND completed_at < ?
                """,
                    (cutoff_date,),
                )

                deleted_count = cursor.rowcount
                await db.commit()

                if deleted_count > 0:
                    self.logger.info(f"Cleaned up {deleted_count} old notifications")

                return deleted_count

        except Exception as e:
            self.logger.error(f"Failed to cleanup old notifications: {e}")
            return 0

    async def get_dead_letter_queue(self, limit: int = 100) -> list[DeadLetterEntry]:
        """
        Get entries from dead letter queue.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of dead letter entries
        """
        try:
            async with (
                aiosqlite.connect(self.db_path) as db,
                db.execute(
                    """
                    SELECT id, original_data, failed_at, failure_reason,
                           total_attempts, error_history, reviewed, can_retry, retry_after
                    FROM dead_letter_queue
                    ORDER BY failed_at DESC
                    LIMIT ?
                """,
                    (limit,),
                ) as cursor,
            ):
                entries = []
                async for row in cursor:
                    try:
                        original_data = json.loads(row[1])
                        original_notification = NotificationPayload.model_validate(original_data)

                        error_history = json.loads(row[5]) if row[5] else []

                        entry = DeadLetterEntry(
                            id=row[0],
                            original_notification=original_notification,
                            failed_at=datetime.fromisoformat(row[2]),
                            failure_reason=row[3],
                            total_attempts=row[4],
                            error_history=error_history,
                            reviewed=bool(row[6]),
                            can_retry=bool(row[7]),
                            retry_after=datetime.fromisoformat(row[8]) if row[8] else None,
                        )
                        entries.append(entry)

                    except Exception as e:
                        self.logger.warning(f"Failed to parse DLQ entry: {e}")
                        continue

                return entries

        except Exception as e:
            self.logger.error(f"Failed to get dead letter queue: {e}")
            return []

    async def retry_from_dlq(self, dlq_entry_id: str) -> bool:
        """
        Retry a notification from the dead letter queue.

        Args:
            dlq_entry_id: ID of DLQ entry to retry

        Returns:
            bool: True if successfully moved back to main queue
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Get DLQ entry
                async with db.execute(
                    """
                    SELECT original_data FROM dead_letter_queue WHERE id = ?
                """,
                    (dlq_entry_id,),
                ) as cursor:
                    row = await cursor.fetchone()

                if not row:
                    return False

                # Parse and reset notification
                original_data = json.loads(row[0])
                notification = NotificationPayload.model_validate(original_data)
                notification.retry_count = 0
                notification.status = NotificationStatus.PENDING
                notification.last_error = None
                notification.scheduled_for = None

                # Re-enqueue
                await self._insert_notification(notification)

                # Remove from DLQ
                await db.execute("DELETE FROM dead_letter_queue WHERE id = ?", (dlq_entry_id,))
                await db.commit()

                self.logger.info(f"Notification {notification.id} retried from DLQ")
                return True

        except Exception as e:
            self.logger.error(f"Failed to retry from DLQ: {e}")
            return False

    async def close(self) -> None:
        """Clean shutdown of queue."""
        try:
            # Cancel maintenance task
            if self._maintenance_task and not self._maintenance_task.done():
                self._maintenance_task.cancel()
                try:
                    await self._maintenance_task
                except asyncio.CancelledError:
                    pass

            # Flush any pending writes
            async with self._batch_lock:
                if self._write_batch:
                    await self._flush_write_batch()

            # Cancel batch timer
            if self._batch_timer and not self._batch_timer.done():
                self._batch_timer.cancel()

            self.logger.info("NotificationQueue shutdown complete")

        except Exception as e:
            self.logger.error(f"Error during queue shutdown: {e}")

    # Private implementation methods

    async def _init_schema(self) -> None:
        """Initialize database schema."""
        async with aiosqlite.connect(self.db_path) as db:
            # Main notifications table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    data TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 1,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    scheduled_for TEXT,
                    last_attempt TEXT,
                    last_error TEXT,
                    completed_at TEXT
                )
            """)

            # Dead letter queue
            await db.execute("""
                CREATE TABLE IF NOT EXISTS dead_letter_queue (
                    id TEXT PRIMARY KEY,
                    original_data TEXT NOT NULL,
                    failed_at TEXT NOT NULL,
                    failure_reason TEXT NOT NULL,
                    total_attempts INTEGER NOT NULL,
                    error_history TEXT,
                    reviewed INTEGER NOT NULL DEFAULT 0,
                    can_retry INTEGER NOT NULL DEFAULT 1,
                    retry_after TEXT
                )
            """)

            # Indexes for performance
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_status_priority
                ON notifications(status, priority, created_at)
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_scheduled
                ON notifications(scheduled_for) WHERE scheduled_for IS NOT NULL
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_created_status
                ON notifications(created_at, status)
            """)

            await db.commit()

    async def _configure_sqlite(self) -> None:
        """Configure SQLite for durability and performance."""
        async with aiosqlite.connect(self.db_path) as db:
            # WAL mode for better crash safety and concurrent access
            await db.execute("PRAGMA journal_mode=WAL")

            # Full synchronous for safety-critical environment
            await db.execute("PRAGMA synchronous=NORMAL")  # Balance safety/performance

            # Larger cache for better performance
            await db.execute("PRAGMA cache_size=-64000")  # 64MB cache

            # WAL auto-checkpoint for space management
            await db.execute("PRAGMA wal_autocheckpoint=1000")

            # Enable auto-vacuum for storage management
            await db.execute("PRAGMA auto_vacuum=INCREMENTAL")

            await db.commit()

    async def _batch_timeout_handler(self) -> None:
        """Handle write batch timeout."""
        try:
            await asyncio.sleep(self._batch_timeout)
            async with self._batch_lock:
                if self._write_batch:
                    await self._flush_write_batch()
        except asyncio.CancelledError:
            pass

    async def _flush_write_batch(self) -> None:
        """Flush pending write batch to database."""
        if not self._write_batch:
            return

        try:
            async with aiosqlite.connect(self.db_path) as db:
                for notification in self._write_batch:
                    await self._insert_notification_in_transaction(db, notification)
                await db.commit()

            self.logger.debug(f"Flushed batch of {len(self._write_batch)} notifications")
            self._write_batch.clear()

        except Exception as e:
            self.logger.error(f"Failed to flush write batch: {e}")
            # Keep notifications in batch for retry

    async def _insert_notification(self, notification: NotificationPayload) -> None:
        """Insert single notification (used for retries)."""
        async with aiosqlite.connect(self.db_path) as db:
            await self._insert_notification_in_transaction(db, notification)
            await db.commit()

    async def _insert_notification_in_transaction(
        self, db: aiosqlite.Connection, notification: NotificationPayload
    ) -> None:
        """Insert notification within existing transaction."""
        data = notification.model_dump_json()

        await db.execute(
            """
            INSERT OR REPLACE INTO notifications
            (id, created_at, data, status, priority, retry_count, max_retries,
             scheduled_for, last_attempt, last_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                notification.id,
                notification.created_at.isoformat(),
                data,
                notification.status.value,
                notification.priority,
                notification.retry_count,
                notification.max_retries,
                notification.scheduled_for.isoformat() if notification.scheduled_for else None,
                notification.last_attempt.isoformat() if notification.last_attempt else None,
                notification.last_error,
            ),
        )

    async def _move_to_dlq(
        self, notification_id: str, error_message: str, total_attempts: int
    ) -> None:
        """Move notification to dead letter queue."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Get original notification data
                async with db.execute(
                    """
                    SELECT data FROM notifications WHERE id = ?
                """,
                    (notification_id,),
                ) as cursor:
                    row = await cursor.fetchone()

                if not row:
                    return

                # Insert into DLQ
                dlq_id = f"dlq_{notification_id}_{int(time.time())}"
                await db.execute(
                    """
                    INSERT INTO dead_letter_queue
                    (id, original_data, failed_at, failure_reason, total_attempts,
                     error_history, reviewed, can_retry)
                    VALUES (?, ?, ?, ?, ?, ?, 0, 1)
                """,
                    (
                        dlq_id,
                        row[0],  # original data
                        datetime.utcnow().isoformat(),
                        error_message,
                        total_attempts,
                        json.dumps([error_message]),  # Start error history
                    ),
                )

                # Remove from main queue
                await db.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))

                self.logger.warning(f"Notification {notification_id} moved to DLQ: {error_message}")

        except Exception as e:
            self.logger.error(f"Failed to move notification to DLQ: {e}")

    async def _maintenance_loop(self) -> None:
        """Background maintenance tasks."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour

                # Clean up old notifications
                await self.cleanup_old_notifications()

                # Incremental vacuum for space management
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("PRAGMA incremental_vacuum(100)")
                    await db.commit()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Maintenance loop error: {e}")
