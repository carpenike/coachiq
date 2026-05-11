"""
Performance optimization and priority message handling for RV-C.

This module provides message prioritization, queue management, and performance
optimization for real-time CAN message processing.
"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    """Message priority levels based on safety and operational importance."""

    CRITICAL = 1  # Safety-critical messages (emergency stop, alarms)
    HIGH = 2  # Important control messages (engine, brakes, steering)
    NORMAL = 3  # Standard operation messages (lights, HVAC)
    LOW = 4  # Information/status messages
    BACKGROUND = 5  # Diagnostic and maintenance messages


@dataclass
class PrioritizedMessage:
    """A CAN message with priority information."""

    timestamp: float
    priority: MessagePriority
    dgn: int
    source_address: int
    data: bytes
    can_id: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: "PrioritizedMessage") -> bool:
        """Compare messages for priority queue ordering."""
        # Lower priority value = higher priority (critical=1 comes first)
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        # If same priority, older messages first
        return self.timestamp < other.timestamp


@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring message processing."""

    messages_processed: int = 0
    messages_dropped: int = 0
    average_processing_time: float = 0.0
    queue_size_current: int = 0
    queue_size_max: int = 0
    priority_distribution: dict[MessagePriority, int] = field(default_factory=dict)
    last_reset: float = field(default_factory=time.time)


class PriorityMessageHandler:
    """
    Handles message prioritization and performance optimization for RV-C.

    Provides:
    - Message priority classification
    - Priority-based queuing
    - Performance monitoring
    - Load balancing
    """

    def __init__(self, settings: Any = None, max_queue_size: int = 10000):
        """
        Initialize the priority message handler.

        Args:
            settings: Application settings instance
            max_queue_size: Maximum number of messages to queue
        """
        self.settings = settings or get_settings()
        self.max_queue_size = max_queue_size

        # Priority queues for different message types
        self._priority_queues: dict[MessagePriority, deque] = {
            priority: deque(maxlen=max_queue_size // len(MessagePriority))
            for priority in MessagePriority
        }

        # Performance metrics
        self.metrics = PerformanceMetrics()
        self._processing_times: deque = deque(maxlen=1000)  # Rolling window for average

        # Priority classification rules
        self._priority_rules = self._setup_priority_rules()

        # Rate limiting per priority
        self._priority_limits = {
            MessagePriority.CRITICAL: 1000.0,  # No practical limit for critical
            MessagePriority.HIGH: 200.0,  # 200 msg/sec for high priority
            MessagePriority.NORMAL: 100.0,  # 100 msg/sec for normal
            MessagePriority.LOW: 50.0,  # 50 msg/sec for low priority
            MessagePriority.BACKGROUND: 10.0,  # 10 msg/sec for background
        }

        # Processing state
        self._processing_active = False
        # Last-emit timestamp PER PRIORITY (not a single global value); the
        # rate limiter must track each class independently or a high-rate
        # critical message would block subsequent normal/low traffic for
        # one normal-priority interval.
        self._last_emit_at: dict[MessagePriority, float] = {
            priority: 0.0 for priority in MessagePriority
        }

        logger.info("Priority message handler initialized")

    def _setup_priority_rules(self) -> dict[int, MessagePriority]:
        """Setup DGN to priority classification rules."""
        rules = {}

        # Critical safety messages (highest priority)
        critical_dgns = [
            0x1FECA,  # DM_RV (Active diagnostic message)
            0x1FDB8,  # Emergency stop
            0x1FF00,  # Engine emergency stop
        ]
        for dgn in critical_dgns:
            rules[dgn] = MessagePriority.CRITICAL

        # High priority - engine, transmission, chassis control
        high_priority_dgns = [
            0x1FF01,  # Engine temperature
            0x1FF02,  # Engine RPM
            0x1FF03,  # Engine hours
            0x1FE6C,  # Transmission temperature
            0x1FE6D,  # Transmission gear
            0x1FD48,  # Vehicle speed
            0x1FE56,  # Brake control
            0x1FE40,  # Steering control
        ]
        for dgn in high_priority_dgns:
            rules[dgn] = MessagePriority.HIGH

        # Normal priority - HVAC, lighting, basic systems
        normal_priority_dgns = [
            0x1FFB1,  # DC dimmer command
            0x1FFB2,  # DC dimmer status
            0x1FFB3,  # Generic indication command
            0x1FFB4,  # Generic indication status
            0x1FF9C,  # Thermostat command
            0x1FF9D,  # Thermostat status
            0x1FFF7,  # AC load command
            0x1FFF8,  # AC load status
        ]
        for dgn in normal_priority_dgns:
            rules[dgn] = MessagePriority.NORMAL

        # Low priority - sensors, monitoring
        low_priority_dgns = [
            0x1FF9E,  # Temperature
            0x1FF9F,  # Humidity
            0x1FFF9,  # DC voltage/current
            0x1FFFA,  # Fluid level
            0x1FFFB,  # Tank level
        ]
        for dgn in low_priority_dgns:
            rules[dgn] = MessagePriority.LOW

        # Background priority - diagnostics, configuration
        background_dgns = [
            0x1FEF2,  # Product identification
            0x1FEF1,  # Component identification
            0x1FEF0,  # Request
            0x1FEE0,  # Configuration
        ]
        for dgn in background_dgns:
            rules[dgn] = MessagePriority.BACKGROUND

        return rules

    def categorize_message_priority(self, dgn: int) -> MessagePriority:
        """
        Classify message priority based on DGN.

        Args:
            dgn: DGN (Data Group Number)

        Returns:
            MessagePriority classification
        """
        # Extract PGN from DGN for classification
        pgn = dgn & 0x3FFFF

        # Check exact PGN match first
        if pgn in self._priority_rules:
            return self._priority_rules[pgn]

        # Fallback to range-based classification
        if 0x1FEC0 <= pgn <= 0x1FECF:  # Diagnostic messages
            return MessagePriority.CRITICAL
        if 0x1FE00 <= pgn <= 0x1FE5F:  # Engine/transmission
            return MessagePriority.HIGH
        if 0x1FF00 <= pgn <= 0x1FF9F:  # Control commands
            return MessagePriority.NORMAL
        if 0x1FFA0 <= pgn <= 0x1FFEF:  # Status messages
            return MessagePriority.LOW
        if 0x1FEF0 <= pgn <= 0x1FEFF:  # Configuration/identification
            return MessagePriority.BACKGROUND
        # Default to normal priority for unknown messages
        return MessagePriority.NORMAL

    def should_process_immediately(self, dgn: int) -> bool:
        """
        Determine if message needs immediate processing.

        Args:
            dgn: DGN (Data Group Number)

        Returns:
            True if message should be processed immediately
        """
        priority = self.categorize_message_priority(dgn)

        # Critical and high priority messages should be processed immediately
        return priority in (MessagePriority.CRITICAL, MessagePriority.HIGH)

    def queue_by_priority(
        self,
        dgn: int,
        source_address: int,
        data: bytes,
        can_id: int,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Queue message by priority for ordered processing.

        Args:
            dgn: DGN (Data Group Number)
            source_address: Source address
            data: Message data
            can_id: CAN ID
            metadata: Optional metadata

        Returns:
            True if message was queued, False if dropped
        """
        current_time = time.time()
        priority = self.categorize_message_priority(dgn)

        # Check rate limiting for this priority level
        if not self._check_rate_limit(priority):
            self.metrics.messages_dropped += 1
            logger.debug(
                f"Message dropped due to rate limiting: DGN {dgn:X}, priority {priority.name}"
            )
            return False

        # Create prioritized message
        message = PrioritizedMessage(
            timestamp=current_time,
            priority=priority,
            dgn=dgn,
            source_address=source_address,
            data=data,
            can_id=can_id,
            metadata=metadata or {},
        )

        # Add to appropriate priority queue
        queue = self._priority_queues[priority]

        # Check if queue is full
        if queue.maxlen is not None and len(queue) >= queue.maxlen:
            # For critical messages, drop oldest low-priority message if possible
            if priority == MessagePriority.CRITICAL:
                if self._drop_lowest_priority_message():
                    logger.info("Dropped low priority message to make room for critical message")
                else:
                    self.metrics.messages_dropped += 1
                    logger.warning("Critical message queue full - dropping message")
                    return False
            else:
                self.metrics.messages_dropped += 1
                logger.debug(f"Queue full for priority {priority.name} - dropping message")
                return False

        # Add message to queue
        queue.append(message)

        # Update metrics
        self.metrics.messages_processed += 1
        self.metrics.priority_distribution[priority] = (
            self.metrics.priority_distribution.get(priority, 0) + 1
        )
        self.metrics.queue_size_current = self.get_total_queue_size()
        self.metrics.queue_size_max = max(
            self.metrics.queue_size_max, self.metrics.queue_size_current
        )

        return True

    def _check_rate_limit(self, priority: MessagePriority) -> bool:
        """Check if priority level is under rate limit.

        Tracks the last-emit timestamp per priority class, so a high-rate
        critical message stream cannot starve unrelated normal/low traffic.
        """
        current_time = time.time()
        limit = self._priority_limits.get(priority, 50.0)  # messages per second
        min_interval = 1.0 / limit

        last_emit = self._last_emit_at.get(priority, 0.0)
        if current_time - last_emit < min_interval:
            return False

        self._last_emit_at[priority] = current_time
        return True

    def _drop_lowest_priority_message(self) -> bool:
        """Drop the oldest message from the lowest priority non-empty queue."""
        # Check queues from lowest to highest priority
        for priority in reversed(list(MessagePriority)):
            queue = self._priority_queues[priority]
            if queue:
                queue.popleft()  # Drop oldest message
                logger.debug(f"Dropped {priority.name} priority message to make room")
                return True
        return False

    def get_next_message(self) -> PrioritizedMessage | None:
        """
        Get the next highest priority message for processing.

        Returns:
            Next message to process or None if no messages queued
        """
        # Check queues from highest to lowest priority
        for priority in MessagePriority:
            queue = self._priority_queues[priority]
            if queue:
                message = queue.popleft()
                self.metrics.queue_size_current = self.get_total_queue_size()
                return message

        return None

    def get_messages_batch(self, max_batch_size: int = 100) -> list[PrioritizedMessage]:
        """
        Get a batch of messages for efficient processing.

        Args:
            max_batch_size: Maximum number of messages to return

        Returns:
            List of messages ordered by priority
        """
        batch = []

        # Collect messages from all priority queues
        for priority in MessagePriority:
            queue = self._priority_queues[priority]

            # Take messages from this priority level
            while queue and len(batch) < max_batch_size:
                batch.append(queue.popleft())

        self.metrics.queue_size_current = self.get_total_queue_size()
        return batch

    def get_total_queue_size(self) -> int:
        """Get total number of queued messages across all priorities."""
        return sum(len(queue) for queue in self._priority_queues.values())

    def get_queue_sizes_by_priority(self) -> dict[MessagePriority, int]:
        """Get queue sizes for each priority level."""
        return {priority: len(queue) for priority, queue in self._priority_queues.items()}

    def record_processing_time(self, processing_time: float) -> None:
        """
        Record message processing time for performance metrics.

        Args:
            processing_time: Time in seconds to process a message
        """
        self._processing_times.append(processing_time)

        # Update rolling average
        if self._processing_times:
            self.metrics.average_processing_time = sum(self._processing_times) / len(
                self._processing_times
            )

    def get_performance_metrics(self) -> dict[str, Any]:
        """
        Get current performance metrics.

        Returns:
            Dictionary with performance statistics
        """
        current_time = time.time()
        uptime = current_time - self.metrics.last_reset

        return {
            "uptime_seconds": uptime,
            "messages_processed": self.metrics.messages_processed,
            "messages_dropped": self.metrics.messages_dropped,
            "drop_rate": self.metrics.messages_dropped / max(self.metrics.messages_processed, 1),
            "average_processing_time_ms": self.metrics.average_processing_time * 1000,
            "current_queue_size": self.metrics.queue_size_current,
            "max_queue_size": self.metrics.queue_size_max,
            "queue_utilization": self.metrics.queue_size_current / max(self.max_queue_size, 1),
            "priority_distribution": {
                priority.name: count
                for priority, count in self.metrics.priority_distribution.items()
            },
            "queue_sizes_by_priority": {
                priority.name: size for priority, size in self.get_queue_sizes_by_priority().items()
            },
            "messages_per_second": self.metrics.messages_processed / max(uptime, 1),
        }

    def reset_metrics(self) -> None:
        """Reset performance metrics."""
        self.metrics = PerformanceMetrics()
        self._processing_times.clear()
        logger.info("Performance metrics reset")

    def clear_queues(self) -> int:
        """
        Clear all message queues.

        Returns:
            Number of messages cleared
        """
        total_cleared = 0

        for queue in self._priority_queues.values():
            total_cleared += len(queue)
            queue.clear()

        self.metrics.queue_size_current = 0
        logger.info(f"Cleared {total_cleared} messages from all queues")

        return total_cleared

    def clear_queue_by_priority(self, priority: MessagePriority) -> int:
        """
        Clear messages from a specific priority queue.

        Args:
            priority: Priority level to clear

        Returns:
            Number of messages cleared
        """
        queue = self._priority_queues[priority]
        cleared_count = len(queue)
        queue.clear()

        self.metrics.queue_size_current = self.get_total_queue_size()
        logger.info(f"Cleared {cleared_count} messages from {priority.name} queue")

        return cleared_count

    def update_priority_rules(self, dgn_priority_map: dict[int, MessagePriority]) -> None:
        """
        Update priority classification rules.

        Args:
            dgn_priority_map: Mapping of DGN to MessagePriority
        """
        self._priority_rules.update(dgn_priority_map)
        logger.info(f"Updated priority rules for {len(dgn_priority_map)} DGNs")

    def get_priority_rules(self) -> dict[int, MessagePriority]:
        """Get current priority classification rules."""
        return self._priority_rules.copy()

    async def process_queue_continuously(
        self,
        processor_func: Callable,
        batch_size: int = 50,
        sleep_interval: float = 0.001,  # 1ms sleep between batches
    ) -> None:
        """
        Continuously process messages from queues.

        Args:
            processor_func: Function to process messages (async)
            batch_size: Number of messages to process per batch
            sleep_interval: Sleep time between processing batches
        """
        self._processing_active = True
        logger.info("Started continuous queue processing")

        try:
            while self._processing_active:
                # Get batch of messages
                batch = self.get_messages_batch(batch_size)

                if batch:
                    # Process batch
                    start_time = time.time()

                    try:
                        await processor_func(batch)

                        # Record processing time
                        processing_time = time.time() - start_time
                        self.record_processing_time(processing_time / len(batch))  # Per message

                    except Exception as e:
                        logger.error(f"Error processing message batch: {e}")
                        # Continue processing despite errors

                else:
                    # No messages to process, sleep a bit longer
                    await asyncio.sleep(sleep_interval * 10)
                    continue

                # Brief sleep to prevent busy waiting
                await asyncio.sleep(sleep_interval)

        except asyncio.CancelledError:
            logger.info("Queue processing cancelled")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in queue processing: {e}")
            raise
        finally:
            self._processing_active = False
            logger.info("Stopped continuous queue processing")

    def stop_processing(self) -> None:
        """Stop continuous queue processing."""
        self._processing_active = False
