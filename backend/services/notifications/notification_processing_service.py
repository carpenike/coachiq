"""Notification Processing Service (Refactored)

Manages the data lifecycle for notification analytics including:
- Batch processing from ingestion queue
- Periodic aggregation
- Queue health monitoring
"""

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.core.performance import PerformanceMonitor
from backend.models.notification_analytics import (
    AggregationPeriod,
    MetricType,
    NotificationDeliveryLog,
    NotificationMetricAggregate,
    NotificationQueueHealth,
)
from backend.repositories.notification_analytics_repository import NotificationAnalyticsRepository

logger = logging.getLogger(__name__)


class NotificationProcessingService:
    """Service for processing notification analytics data."""

    def __init__(
        self,
        analytics_repository: NotificationAnalyticsRepository,
        performance_monitor: PerformanceMonitor,
        ingestion_queue: asyncio.Queue[NotificationDeliveryLog],
        batch_size: int = 100,
        flush_interval: float = 30.0,
    ):
        """Initialize the processing service.

        Args:
            analytics_repository: Repository for analytics data
            performance_monitor: Performance monitoring instance
            ingestion_queue: Queue from ingestion service
            batch_size: Size of batches for processing
            flush_interval: Seconds between flush operations
        """
        self._repository = analytics_repository
        self._monitor = performance_monitor
        self._queue = ingestion_queue
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._running = False

        # Apply performance monitoring
        self._apply_monitoring()

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.process_batch = self._monitor.monitor_service_method(
            "NotificationProcessingService", "process_batch"
        )(self.process_batch)

        self.perform_hourly_aggregation = self._monitor.monitor_service_method(
            "NotificationProcessingService", "perform_hourly_aggregation"
        )(self.perform_hourly_aggregation)

        self.calculate_queue_health = self._monitor.monitor_service_method(
            "NotificationProcessingService", "calculate_queue_health"
        )(self.calculate_queue_health)

    async def run_processor(self) -> None:
        """Main processing loop - pulls from queue and persists batches."""
        self._running = True
        logger.info("Notification processor started")

        while self._running:
            try:
                # Collect a batch
                batch = []
                deadline = time.perf_counter() + self._flush_interval

                while len(batch) < self._batch_size and time.perf_counter() < deadline:
                    try:
                        timeout = max(0, deadline - time.perf_counter())
                        item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                        batch.append(item)
                    except TimeoutError:
                        break  # Flush what we have

                if batch:
                    await self.process_batch(batch)

            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Back off on error

    async def process_batch(self, batch: list[NotificationDeliveryLog]) -> None:
        """Process a batch of notification events.

        Args:
            batch: List of delivery logs to process
        """
        # Separate engagement updates from new logs
        engagement_updates = []
        delivery_logs = []

        for entry in batch:
            if entry.channel == "engagement":
                engagement_updates.append(entry)
            else:
                delivery_logs.append(entry)

        # Save delivery logs
        if delivery_logs:
            success = await self._repository.save_delivery_logs(delivery_logs)
            if success:
                logger.debug(f"Processed {len(delivery_logs)} delivery logs")
            else:
                logger.error(f"Failed to save {len(delivery_logs)} delivery logs")

        # Process engagement updates
        for engagement in engagement_updates:
            action = engagement.metadata.get("engagement_action")
            timestamp = datetime.fromisoformat(engagement.metadata["engagement_timestamp"])

            success = await self._repository.update_engagement(
                engagement.notification_id, action, timestamp
            )
            if not success:
                logger.warning(f"Failed to update engagement for {engagement.notification_id}")

    async def run_aggregator(self) -> None:
        """Periodic aggregation loop."""
        self._running = True
        logger.info("Notification aggregator started")

        while self._running:
            try:
                # Wait until 5 minutes past the hour
                now = datetime.now(UTC)
                next_hour = now.replace(minute=5, second=0, microsecond=0)
                if now >= next_hour:
                    next_hour += timedelta(hours=1)

                wait_seconds = (next_hour - now).total_seconds()
                await asyncio.sleep(wait_seconds)

                if not self._running:
                    break

                # Perform aggregations
                await self.perform_hourly_aggregation()
                await self.perform_daily_aggregation()
                await self.perform_weekly_aggregation()

            except Exception as e:
                logger.error(f"Error in aggregation loop: {e}", exc_info=True)
                await asyncio.sleep(300)  # Wait 5 minutes on error

    async def perform_hourly_aggregation(self) -> None:
        """Perform hourly metric aggregation."""
        # Aggregate the previous complete hour
        now = datetime.now(UTC)
        hour_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        hour_end = hour_start + timedelta(hours=1)

        for metric_type in MetricType:
            # Check if already aggregated
            exists = await self._repository.check_aggregate_exists(
                metric_type.value, AggregationPeriod.HOURLY.value, hour_start
            )

            if not exists:
                value = await self._repository.calculate_metric_value(
                    metric_type, hour_start, hour_end
                )

                aggregate = NotificationMetricAggregate(
                    metric_type=metric_type.value,
                    aggregation_period=AggregationPeriod.HOURLY.value,
                    period_start=hour_start,
                    period_end=hour_end,
                    value=value,
                    count=1,  # Would be calculated properly
                )

                await self._repository.save_metric_aggregate(aggregate)
                logger.info(f"Aggregated {metric_type.value} for hour {hour_start}")

    async def perform_daily_aggregation(self) -> None:
        """Perform daily aggregation if at start of day."""
        now = datetime.now(UTC)
        if now.hour == 0:  # Only run at midnight
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            day_end = day_start + timedelta(days=1)

            for metric_type in MetricType:
                exists = await self._repository.check_aggregate_exists(
                    metric_type.value, AggregationPeriod.DAILY.value, day_start
                )

                if not exists:
                    value = await self._repository.calculate_metric_value(
                        metric_type, day_start, day_end
                    )

                    aggregate = NotificationMetricAggregate(
                        metric_type=metric_type.value,
                        aggregation_period=AggregationPeriod.DAILY.value,
                        period_start=day_start,
                        period_end=day_end,
                        value=value,
                        count=1,
                    )

                    await self._repository.save_metric_aggregate(aggregate)
                    logger.info(f"Aggregated {metric_type.value} for day {day_start.date()}")

    async def perform_weekly_aggregation(self) -> None:
        """Perform weekly aggregation if at start of week."""
        now = datetime.now(UTC)
        if now.weekday() == 0 and now.hour == 0:  # Monday at midnight
            week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)
            week_end = week_start + timedelta(days=7)

            for metric_type in MetricType:
                exists = await self._repository.check_aggregate_exists(
                    metric_type.value, AggregationPeriod.WEEKLY.value, week_start
                )

                if not exists:
                    value = await self._repository.calculate_metric_value(
                        metric_type, week_start, week_end
                    )

                    aggregate = NotificationMetricAggregate(
                        metric_type=metric_type.value,
                        aggregation_period=AggregationPeriod.WEEKLY.value,
                        period_start=week_start,
                        period_end=week_end,
                        value=value,
                        count=1,
                    )

                    await self._repository.save_metric_aggregate(aggregate)
                    logger.info(
                        f"Aggregated {metric_type.value} for week starting {week_start.date()}"
                    )

    async def run_health_monitor(self) -> None:
        """Periodic queue health monitoring."""
        self._running = True
        logger.info("Queue health monitor started")

        while self._running:
            try:
                await asyncio.sleep(300)  # Every 5 minutes

                if not self._running:
                    break

                health = await self.calculate_queue_health()
                await self._repository.save_queue_health(health)

            except Exception as e:
                logger.error(f"Error in health monitoring: {e}", exc_info=True)

    async def calculate_queue_health(self) -> NotificationQueueHealth:
        """Calculate current queue health metrics."""
        one_hour_ago = datetime.now(UTC) - timedelta(hours=1)

        # Get statistics from repository
        stats = await self._repository.get_queue_statistics(one_hour_ago)

        # Calculate rates
        processing_rate = stats["processed_count"] / 3600.0  # per second
        success_rate = stats["success_count"] / max(stats["processed_count"], 1)

        # Calculate health score
        health_score = self._calculate_health_score(
            stats["pending_count"],
            processing_rate,
            success_rate,
            stats["avg_wait_time"],
        )

        return NotificationQueueHealth(
            timestamp=datetime.now(UTC),
            queue_depth=stats["pending_count"],
            processing_rate=processing_rate,
            success_rate=success_rate,
            average_wait_time=stats["avg_wait_time"],
            average_processing_time=stats["avg_processing_time"],
            dlq_size=0,  # Would come from actual queue
            active_workers=1,  # Would come from task manager
            memory_usage_mb=None,
            cpu_usage_percent=None,
            health_score=health_score,
        )

    def _calculate_health_score(
        self,
        queue_depth: int,
        processing_rate: float,
        success_rate: float,
        avg_wait_time: float,
    ) -> float:
        """Calculate overall queue health score."""
        score = 1.0

        # Penalize high queue depth
        if queue_depth > 1000:
            score *= 0.8
        elif queue_depth > 5000:
            score *= 0.5

        # Penalize low processing rate
        if processing_rate < 1.0:
            score *= 0.9
        elif processing_rate < 0.1:
            score *= 0.7

        # Penalize low success rate
        score *= success_rate

        # Penalize high wait times
        if avg_wait_time > 300:  # 5 minutes
            score *= 0.9
        elif avg_wait_time > 600:  # 10 minutes
            score *= 0.7

        return max(0.0, min(1.0, score))

    async def stop(self) -> None:
        """Stop the processing service."""
        self._running = False
        logger.info("Stopping notification processing service")
