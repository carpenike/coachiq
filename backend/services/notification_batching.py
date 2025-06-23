"""
Smart notification batching service for efficient bulk delivery.

This module implements intelligent batching algorithms that group notifications
based on channel, recipient, priority, and time windows to optimize delivery
performance and reduce API calls.

Key Features:
- Smart grouping by channel, recipient, and priority
- Time-window based batching with configurable delays
- Channel-specific batch size limits
- Priority-aware batch processing
- Automatic batch overflow handling
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationType,
)


class BatchingStrategy(str, Enum):
    """Notification batching strategies."""

    TIME_WINDOW = "time_window"  # Batch by time windows
    SIZE_THRESHOLD = "size_threshold"  # Batch by size
    HYBRID = "hybrid"  # Combine time and size
    PRIORITY_GROUPED = "priority_grouped"  # Group by priority levels
    RECIPIENT_GROUPED = "recipient_grouped"  # Group by recipient


class BatchWindow:
    """Represents a time window for collecting notifications."""

    def __init__(self, window_id: str, start_time: datetime, end_time: datetime):
        self.window_id = window_id
        self.start_time = start_time
        self.end_time = end_time
        self.notifications: list[NotificationPayload] = []
        self.is_closed = False

    def add_notification(self, notification: NotificationPayload) -> bool:
        """Add notification to window if still open."""
        if self.is_closed or datetime.utcnow() > self.end_time:
            self.is_closed = True
            return False

        self.notifications.append(notification)
        return True

    def should_flush(self, max_size: int) -> bool:
        """Check if window should be flushed."""
        return (
            len(self.notifications) >= max_size
            or datetime.utcnow() > self.end_time
            or self.is_closed
        )

    def close(self) -> list[NotificationPayload]:
        """Close window and return notifications."""
        self.is_closed = True
        return self.notifications.copy()


class BatchGroup:
    """Groups notifications for batch processing."""

    def __init__(
        self,
        group_id: str,
        channel: NotificationChannel,
        max_size: int = 100,
        max_wait_seconds: int = 5,
    ):
        self.group_id = group_id
        self.channel = channel
        self.max_size = max_size
        self.max_wait_seconds = max_wait_seconds
        self.notifications: list[NotificationPayload] = []
        self.created_at = datetime.utcnow()
        self.priority_sum = 0
        self.recipients: set[str] = set()

    def add_notification(self, notification: NotificationPayload) -> bool:
        """Add notification to group."""
        if len(self.notifications) >= self.max_size:
            return False

        self.notifications.append(notification)
        self.priority_sum += self._get_priority_weight(notification.level)

        if notification.recipient:
            self.recipients.add(notification.recipient)

        return True

    def should_flush(self) -> bool:
        """Check if group should be flushed."""
        age = (datetime.utcnow() - self.created_at).total_seconds()

        return (
            len(self.notifications) >= self.max_size
            or age >= self.max_wait_seconds
            or self._has_critical_notification()
        )

    def get_average_priority(self) -> float:
        """Get average priority of notifications in group."""
        if not self.notifications:
            return 0.0
        return self.priority_sum / len(self.notifications)

    def _get_priority_weight(self, level: NotificationType) -> int:
        """Get numeric weight for priority level."""
        weights = {
            NotificationType.INFO: 1,
            NotificationType.SUCCESS: 1,
            NotificationType.WARNING: 2,
            NotificationType.ERROR: 3,
            NotificationType.CRITICAL: 4,
        }
        return weights.get(level, 1)

    def _has_critical_notification(self) -> bool:
        """Check if group contains critical notifications."""
        return any(n.level == NotificationType.CRITICAL for n in self.notifications)


class NotificationBatcher:
    """
    Intelligent notification batching service.

    Groups notifications for efficient bulk delivery based on
    configurable strategies and channel-specific rules.
    """

    def __init__(self, strategy: BatchingStrategy = BatchingStrategy.HYBRID):
        self.strategy = strategy
        self.logger = logging.getLogger(f"{__name__}.NotificationBatcher")

        # Batching configuration per channel
        self.channel_config = {
            NotificationChannel.SMTP: {
                "max_batch_size": 50,
                "max_wait_seconds": 5,
                "min_batch_size": 5,
            },
            NotificationChannel.WEBHOOK: {
                "max_batch_size": 100,
                "max_wait_seconds": 2,
                "min_batch_size": 10,
            },
            NotificationChannel.SLACK: {
                "max_batch_size": 20,
                "max_wait_seconds": 3,
                "min_batch_size": 3,
            },
            NotificationChannel.PUSHOVER: {
                "max_batch_size": 1,  # Pushover doesn't support batching
                "max_wait_seconds": 0,
                "min_batch_size": 1,
            },
        }

        # Active batches
        self.active_groups: dict[str, BatchGroup] = {}
        self.time_windows: dict[str, BatchWindow] = {}

        # Batch processing queue
        self.batch_queue: asyncio.Queue[BatchGroup] = asyncio.Queue()

        # Statistics
        self.stats = {
            "total_batches": 0,
            "total_notifications": 0,
            "avg_batch_size": 0.0,
            "batching_efficiency": 0.0,
            "channel_stats": defaultdict(
                lambda: {
                    "batches": 0,
                    "notifications": 0,
                    "avg_size": 0.0,
                }
            ),
        }

        # Background tasks
        self._flush_task: asyncio.Task | None = None
        self._window_manager_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """Initialize the batching service."""
        # Start background tasks
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._window_manager_task = asyncio.create_task(self._window_manager_loop())

        self.logger.info(f"NotificationBatcher initialized with {self.strategy} strategy")

    async def add_notification(self, notification: NotificationPayload) -> str:
        """
        Add notification to appropriate batch.

        Returns:
            Batch ID the notification was added to
        """
        try:
            # Route based on strategy
            if self.strategy == BatchingStrategy.TIME_WINDOW:
                return await self._add_to_time_window(notification)
            if self.strategy == BatchingStrategy.SIZE_THRESHOLD:
                return await self._add_to_size_batch(notification)
            if self.strategy == BatchingStrategy.PRIORITY_GROUPED:
                return await self._add_to_priority_group(notification)
            if self.strategy == BatchingStrategy.RECIPIENT_GROUPED:
                return await self._add_to_recipient_group(notification)
            # HYBRID
            return await self._add_to_hybrid_batch(notification)

        except Exception as e:
            self.logger.error(f"Failed to batch notification {notification.id}: {e}")
            # Fallback: create immediate single-notification batch
            return await self._create_immediate_batch(notification)

    async def get_ready_batches(self, limit: int = 10) -> list[BatchGroup]:
        """Get batches ready for processing."""
        ready_batches = []

        # Check all active groups
        for group_id, group in list(self.active_groups.items()):
            if group.should_flush():
                ready_batches.append(group)
                del self.active_groups[group_id]

                # Update statistics
                self._update_stats(group)

                if len(ready_batches) >= limit:
                    break

        return ready_batches

    async def force_flush_channel(self, channel: NotificationChannel) -> list[BatchGroup]:
        """Force flush all batches for a specific channel."""
        flushed_groups = []

        for group_id, group in list(self.active_groups.items()):
            if group.channel == channel:
                flushed_groups.append(group)
                del self.active_groups[group_id]
                self._update_stats(group)

        self.logger.info(f"Force flushed {len(flushed_groups)} batches for {channel.value}")
        return flushed_groups

    async def force_flush_all(self) -> list[BatchGroup]:
        """Force flush all active batches."""
        all_groups = list(self.active_groups.values())
        self.active_groups.clear()

        for group in all_groups:
            self._update_stats(group)

        self.logger.info(f"Force flushed all {len(all_groups)} active batches")
        return all_groups

    def get_statistics(self) -> dict[str, Any]:
        """Get batching statistics."""
        return {
            "strategy": self.strategy.value,
            "active_batches": len(self.active_groups),
            "total_batches": self.stats["total_batches"],
            "total_notifications": self.stats["total_notifications"],
            "avg_batch_size": self.stats["avg_batch_size"],
            "batching_efficiency": self.stats["batching_efficiency"],
            "channel_breakdown": dict(self.stats["channel_stats"]),
            "active_batch_details": self._get_active_batch_details(),
        }

    # Private batching strategy implementations

    async def _add_to_time_window(self, notification: NotificationPayload) -> str:
        """Add notification using time window strategy."""
        window_duration = timedelta(seconds=5)  # 5-second windows
        current_time = datetime.utcnow()

        # Calculate window ID
        window_start = current_time.replace(second=(current_time.second // 5) * 5, microsecond=0)
        window_id = f"window_{window_start.timestamp()}"

        # Get or create window
        if window_id not in self.time_windows:
            window_end = window_start + window_duration
            self.time_windows[window_id] = BatchWindow(window_id, window_start, window_end)

        window = self.time_windows[window_id]

        # Add to window
        if window.add_notification(notification):
            return window_id
        # Window closed, create new one
        new_window_id = f"window_{current_time.timestamp()}"
        new_window = BatchWindow(new_window_id, current_time, current_time + window_duration)
        new_window.add_notification(notification)
        self.time_windows[new_window_id] = new_window
        return new_window_id

    async def _add_to_size_batch(self, notification: NotificationPayload) -> str:
        """Add notification using size threshold strategy."""
        # Group by channel
        for channel in notification.channels:
            group_id = f"size_{channel.value}"

            if group_id not in self.active_groups:
                config = self.channel_config.get(channel, {})
                self.active_groups[group_id] = BatchGroup(
                    group_id,
                    channel,
                    max_size=config.get("max_batch_size", 50),
                    max_wait_seconds=config.get("max_wait_seconds", 5),
                )

            group = self.active_groups[group_id]
            if group.add_notification(notification):
                return group_id
            # Group full, create new one
            new_group_id = f"size_{channel.value}_{datetime.utcnow().timestamp()}"
            new_group = BatchGroup(
                new_group_id,
                channel,
                max_size=config.get("max_batch_size", 50),
                max_wait_seconds=config.get("max_wait_seconds", 5),
            )
            new_group.add_notification(notification)
            self.active_groups[new_group_id] = new_group
            return new_group_id

        return f"size_default_{datetime.utcnow().timestamp()}"

    async def _add_to_priority_group(self, notification: NotificationPayload) -> str:
        """Add notification using priority grouping strategy."""
        # Determine priority bucket
        priority_bucket = "low"
        if notification.level in [NotificationType.ERROR, NotificationType.CRITICAL]:
            priority_bucket = "high"
        elif notification.level == NotificationType.WARNING:
            priority_bucket = "medium"

        # Group by channel and priority
        for channel in notification.channels:
            group_id = f"priority_{channel.value}_{priority_bucket}"

            if group_id not in self.active_groups:
                config = self.channel_config.get(channel, {})
                # High priority gets smaller batches for faster delivery
                max_size = config.get("max_batch_size", 50)
                if priority_bucket == "high":
                    max_size = min(10, max_size)
                elif priority_bucket == "medium":
                    max_size = min(25, max_size)

                self.active_groups[group_id] = BatchGroup(
                    group_id,
                    channel,
                    max_size=max_size,
                    max_wait_seconds=1 if priority_bucket == "high" else 3,
                )

            group = self.active_groups[group_id]
            if group.add_notification(notification):
                return group_id

        return f"priority_default_{datetime.utcnow().timestamp()}"

    async def _add_to_recipient_group(self, notification: NotificationPayload) -> str:
        """Add notification using recipient grouping strategy."""
        if not notification.recipient:
            return await self._add_to_size_batch(notification)

        # Group by recipient and channel
        for channel in notification.channels:
            group_id = f"recipient_{channel.value}_{notification.recipient}"

            if group_id not in self.active_groups:
                config = self.channel_config.get(channel, {})
                self.active_groups[group_id] = BatchGroup(
                    group_id,
                    channel,
                    max_size=min(20, config.get("max_batch_size", 50)),
                    max_wait_seconds=config.get("max_wait_seconds", 5),
                )

            group = self.active_groups[group_id]
            if group.add_notification(notification):
                return group_id

        return f"recipient_default_{datetime.utcnow().timestamp()}"

    async def _add_to_hybrid_batch(self, notification: NotificationPayload) -> str:
        """Add notification using hybrid strategy."""
        # Combine multiple factors for intelligent batching

        # Critical notifications get immediate processing
        if notification.level == NotificationType.CRITICAL:
            return await self._create_immediate_batch(notification)

        # High priority notifications get priority grouping
        if notification.level in [NotificationType.ERROR]:
            return await self._add_to_priority_group(notification)

        # Group by channel and recipient for efficiency
        for channel in notification.channels:
            # Create group key considering multiple factors
            recipient_key = notification.recipient or "broadcast"
            priority_key = "high" if notification.level == NotificationType.WARNING else "normal"

            group_id = f"hybrid_{channel.value}_{recipient_key}_{priority_key}"

            if group_id not in self.active_groups:
                config = self.channel_config.get(channel, {})
                self.active_groups[group_id] = BatchGroup(
                    group_id,
                    channel,
                    max_size=config.get("max_batch_size", 50),
                    max_wait_seconds=config.get("max_wait_seconds", 5),
                )

            group = self.active_groups[group_id]
            if group.add_notification(notification):
                return group_id
            # Group full, check if we should flush or create new
            if group.should_flush():
                await self.batch_queue.put(group)
                del self.active_groups[group_id]

            # Create new group
            new_group_id = f"{group_id}_{datetime.utcnow().timestamp()}"
            new_group = BatchGroup(
                new_group_id,
                channel,
                max_size=config.get("max_batch_size", 50),
                max_wait_seconds=config.get("max_wait_seconds", 5),
            )
            new_group.add_notification(notification)
            self.active_groups[new_group_id] = new_group
            return new_group_id

        return f"hybrid_default_{datetime.utcnow().timestamp()}"

    async def _create_immediate_batch(self, notification: NotificationPayload) -> str:
        """Create immediate single-notification batch."""
        for channel in notification.channels:
            group_id = f"immediate_{channel.value}_{notification.id}"
            group = BatchGroup(group_id, channel, max_size=1, max_wait_seconds=0)
            group.add_notification(notification)
            await self.batch_queue.put(group)
            self._update_stats(group)

        return f"immediate_{notification.id}"

    async def _flush_loop(self) -> None:
        """Background task to flush batches periodically."""
        while True:
            try:
                await asyncio.sleep(1)  # Check every second

                # Get batches ready to flush
                ready_batches = await self.get_ready_batches()

                # Queue them for processing
                for batch in ready_batches:
                    await self.batch_queue.put(batch)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Flush loop error: {e}")

    async def _window_manager_loop(self) -> None:
        """Background task to manage time windows."""
        while True:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds

                # Clean up closed windows
                current_time = datetime.utcnow()
                closed_windows = []

                for window_id, window in self.time_windows.items():
                    if window.should_flush(100) or current_time > window.end_time:
                        notifications = window.close()
                        if notifications:
                            # Convert to batch group
                            for channel in set(n.channels[0] for n in notifications if n.channels):
                                group = BatchGroup(
                                    f"{window_id}_{channel.value}",
                                    channel,
                                )
                                for notif in notifications:
                                    if channel in notif.channels:
                                        group.add_notification(notif)

                                if group.notifications:
                                    await self.batch_queue.put(group)
                                    self._update_stats(group)

                        closed_windows.append(window_id)

                # Remove closed windows
                for window_id in closed_windows:
                    del self.time_windows[window_id]

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Window manager loop error: {e}")

    def _update_stats(self, group: BatchGroup) -> None:
        """Update batching statistics."""
        batch_size = len(group.notifications)

        self.stats["total_batches"] += 1
        self.stats["total_notifications"] += batch_size

        # Update average
        if self.stats["total_batches"] > 0:
            self.stats["avg_batch_size"] = (
                self.stats["total_notifications"] / self.stats["total_batches"]
            )

        # Update channel stats
        channel_stat = self.stats["channel_stats"][group.channel.value]
        channel_stat["batches"] += 1
        channel_stat["notifications"] += batch_size
        channel_stat["avg_size"] = channel_stat["notifications"] / channel_stat["batches"]

        # Calculate batching efficiency (how much we're batching vs individual sends)
        if self.stats["total_notifications"] > 0:
            self.stats["batching_efficiency"] = 1 - (
                self.stats["total_batches"] / self.stats["total_notifications"]
            )

    def _get_active_batch_details(self) -> list[dict[str, Any]]:
        """Get details of active batches."""
        return [
            {
                "group_id": group.group_id,
                "channel": group.channel.value,
                "size": len(group.notifications),
                "age_seconds": (datetime.utcnow() - group.created_at).total_seconds(),
                "avg_priority": group.get_average_priority(),
                "recipients": len(group.recipients),
            }
            for group in self.active_groups.values()
        ]

    async def close(self) -> None:
        """Clean shutdown of batching service."""
        # Cancel background tasks
        if self._flush_task:
            self._flush_task.cancel()
        if self._window_manager_task:
            self._window_manager_task.cancel()

        # Flush all remaining batches
        await self.force_flush_all()

        self.logger.info("NotificationBatcher shutdown complete")
