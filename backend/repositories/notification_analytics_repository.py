"""Notification analytics repository.

This repository manages notification metrics, aggregations, and analytics data
using the repository pattern.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.performance import PerformanceMonitor
from backend.models.notification import NotificationStatus
from backend.models.notification_analytics import (
    AggregationPeriod,
    MetricType,
    NotificationDeliveryLog,
    NotificationErrorAnalysis,
    NotificationMetricAggregate,
    NotificationQueueHealth,
)
from backend.models.notification_analytics import (
    NotificationReport as NotificationReportModel,
)
from backend.repositories.base import MonitoredRepository
from backend.services.database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class NotificationAnalyticsRepository(MonitoredRepository):
    """Repository for notification analytics and metrics."""

    def __init__(self, database_manager: DatabaseManager, performance_monitor: PerformanceMonitor):
        """Initialize notification analytics repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)
        self.db_manager = database_manager
        self._metric_buffer: list[NotificationDeliveryLog] = []
        self._buffer_lock = asyncio.Lock()

    @MonitoredRepository._monitored_operation("save_delivery_logs")
    async def save_delivery_logs(self, logs: list[NotificationDeliveryLog]) -> bool:
        """Save notification delivery logs.

        Args:
            logs: List of delivery logs to save

        Returns:
            True if successful
        """
        try:
            async with self.db_manager.get_session() as session:
                session.add_all(logs)
                await session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save delivery logs: {e}")
            return False

    @MonitoredRepository._monitored_operation("update_engagement")
    async def update_engagement(
        self, notification_id: str, action: str, timestamp: datetime
    ) -> bool:
        """Update engagement data for a notification.

        Args:
            notification_id: ID of the notification
            action: Engagement action (opened, clicked, dismissed)
            timestamp: When the action occurred

        Returns:
            True if successful
        """
        try:
            async with self.db_manager.get_session() as session:
                stmt = select(NotificationDeliveryLog).where(
                    NotificationDeliveryLog.notification_id == notification_id
                )
                result = await session.execute(stmt)
                log_entry = result.scalar_one_or_none()

                if log_entry:
                    if action == "opened":
                        log_entry.opened_at = timestamp
                    elif action == "clicked":
                        log_entry.clicked_at = timestamp
                    elif action == "dismissed":
                        log_entry.dismissed_at = timestamp

                    await session.commit()
                    return True

            return False
        except Exception as e:
            logger.error(f"Failed to update engagement: {e}")
            return False

    @MonitoredRepository._monitored_operation("get_channel_statistics")
    async def get_channel_statistics(
        self,
        channel: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get channel statistics.

        Args:
            channel: Optional specific channel
            start_date: Start of period
            end_date: End of period

        Returns:
            List of channel statistics
        """
        if end_date is None:
            end_date = datetime.now(UTC)
        if start_date is None:
            start_date = end_date - timedelta(days=7)

        async with self.db_manager.get_session() as session:
            # Build base query
            query = select(
                NotificationDeliveryLog.channel,
                func.count().label("total"),
                func.sum(
                    func.cast(
                        NotificationDeliveryLog.status == NotificationStatus.DELIVERED.value,
                        func.Integer,
                    )
                ).label("delivered"),
                func.sum(
                    func.cast(
                        NotificationDeliveryLog.status == NotificationStatus.FAILED.value,
                        func.Integer,
                    )
                ).label("failed"),
                func.sum(NotificationDeliveryLog.retry_count).label("retries"),
                func.avg(NotificationDeliveryLog.delivery_time_ms).label("avg_delivery_time"),
            ).where(
                and_(
                    NotificationDeliveryLog.created_at >= start_date,
                    NotificationDeliveryLog.created_at <= end_date,
                )
            )

            if channel:
                query = query.where(NotificationDeliveryLog.channel == channel)

            query = query.group_by(NotificationDeliveryLog.channel)

            result = await session.execute(query)
            rows = result.all()

            return [
                {
                    "channel": row.channel,
                    "total": row.total or 0,
                    "delivered": row.delivered or 0,
                    "failed": row.failed or 0,
                    "retries": row.retries or 0,
                    "avg_delivery_time": row.avg_delivery_time,
                }
                for row in rows
            ]

    @MonitoredRepository._monitored_operation("get_error_patterns")
    async def get_error_patterns(
        self, start_date: datetime, end_date: datetime, min_occurrences: int = 5
    ) -> list[dict[str, Any]]:
        """Get error patterns analysis.

        Args:
            start_date: Start of analysis period
            end_date: End of analysis period
            min_occurrences: Minimum occurrences to include

        Returns:
            List of error patterns
        """
        async with self.db_manager.get_session() as session:
            query = (
                select(
                    NotificationDeliveryLog.error_code,
                    NotificationDeliveryLog.error_message,
                    NotificationDeliveryLog.channel,
                    func.count().label("count"),
                    func.min(NotificationDeliveryLog.created_at).label("first_seen"),
                    func.max(NotificationDeliveryLog.created_at).label("last_seen"),
                    func.count(func.distinct(NotificationDeliveryLog.recipient)).label(
                        "affected_recipients"
                    ),
                )
                .where(
                    and_(
                        NotificationDeliveryLog.error_code.isnot(None),
                        NotificationDeliveryLog.created_at >= start_date,
                        NotificationDeliveryLog.created_at <= end_date,
                    )
                )
                .group_by(
                    NotificationDeliveryLog.error_code,
                    NotificationDeliveryLog.error_message,
                    NotificationDeliveryLog.channel,
                )
                .having(func.count() >= min_occurrences)
            )

            result = await session.execute(query)
            return [
                {
                    "error_code": row.error_code,
                    "error_message": row.error_message,
                    "channel": row.channel,
                    "count": row.count,
                    "first_seen": row.first_seen,
                    "last_seen": row.last_seen,
                    "affected_recipients": row.affected_recipients,
                }
                for row in result
            ]

    @MonitoredRepository._monitored_operation("save_error_analyses")
    async def save_error_analyses(self, analyses: list[NotificationErrorAnalysis]) -> bool:
        """Save error analysis records.

        Args:
            analyses: Error analyses to save

        Returns:
            True if successful
        """
        try:
            async with self.db_manager.get_session() as session:
                session.add_all(analyses)
                await session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save error analyses: {e}")
            return False

    @MonitoredRepository._monitored_operation("get_metric_aggregates")
    async def get_metric_aggregates(
        self,
        metric_type: str,
        aggregation_period: str,
        start_date: datetime,
        end_date: datetime,
        channel: str | None = None,
        notification_type: str | None = None,
    ) -> list[NotificationMetricAggregate]:
        """Get metric aggregates.

        Args:
            metric_type: Type of metric
            aggregation_period: Aggregation period
            start_date: Start of period
            end_date: End of period
            channel: Optional channel filter
            notification_type: Optional notification type filter

        Returns:
            List of metric aggregates
        """
        async with self.db_manager.get_session() as session:
            query = select(NotificationMetricAggregate).where(
                and_(
                    NotificationMetricAggregate.metric_type == metric_type,
                    NotificationMetricAggregate.aggregation_period == aggregation_period,
                    NotificationMetricAggregate.period_start >= start_date,
                    NotificationMetricAggregate.period_start <= end_date,
                )
            )

            if channel:
                query = query.where(NotificationMetricAggregate.channel == channel)
            if notification_type:
                query = query.where(
                    NotificationMetricAggregate.notification_type == notification_type
                )

            result = await session.execute(query.order_by(NotificationMetricAggregate.period_start))
            return list(result.scalars().all())

    @MonitoredRepository._monitored_operation("save_metric_aggregate")
    async def save_metric_aggregate(self, aggregate: NotificationMetricAggregate) -> bool:
        """Save a metric aggregate.

        Args:
            aggregate: Metric aggregate to save

        Returns:
            True if successful
        """
        try:
            async with self.db_manager.get_session() as session:
                session.add(aggregate)
                await session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save metric aggregate: {e}")
            return False

    @MonitoredRepository._monitored_operation("check_aggregate_exists")
    async def check_aggregate_exists(
        self, metric_type: str, aggregation_period: str, period_start: datetime
    ) -> bool:
        """Check if a metric aggregate already exists.

        Args:
            metric_type: Type of metric
            aggregation_period: Aggregation period
            period_start: Start of period

        Returns:
            True if aggregate exists
        """
        async with self.db_manager.get_session() as session:
            stmt = (
                select(func.count())
                .select_from(NotificationMetricAggregate)
                .where(
                    and_(
                        NotificationMetricAggregate.metric_type == metric_type,
                        NotificationMetricAggregate.aggregation_period == aggregation_period,
                        NotificationMetricAggregate.period_start == period_start,
                    )
                )
            )

            count = await session.scalar(stmt)
            return count is not None and count > 0

    @MonitoredRepository._monitored_operation("calculate_metric_value")
    async def calculate_metric_value(
        self, metric_type: MetricType, start: datetime, end: datetime
    ) -> float:
        """Calculate a metric value for a period.

        Args:
            metric_type: Type of metric
            start: Start of period
            end: End of period

        Returns:
            Calculated metric value
        """
        async with self.db_manager.get_session() as session:
            if metric_type == MetricType.DELIVERY_COUNT:
                stmt = (
                    select(func.count())
                    .select_from(NotificationDeliveryLog)
                    .where(
                        and_(
                            NotificationDeliveryLog.created_at >= start,
                            NotificationDeliveryLog.created_at < end,
                        )
                    )
                )
                return float(await session.scalar(stmt) or 0)

            if metric_type == MetricType.SUCCESS_RATE:
                total_stmt = (
                    select(func.count())
                    .select_from(NotificationDeliveryLog)
                    .where(
                        and_(
                            NotificationDeliveryLog.created_at >= start,
                            NotificationDeliveryLog.created_at < end,
                        )
                    )
                )
                total = await session.scalar(total_stmt) or 0

                success_stmt = (
                    select(func.count())
                    .select_from(NotificationDeliveryLog)
                    .where(
                        and_(
                            NotificationDeliveryLog.created_at >= start,
                            NotificationDeliveryLog.created_at < end,
                            NotificationDeliveryLog.status == NotificationStatus.DELIVERED.value,
                        )
                    )
                )
                success = await session.scalar(success_stmt) or 0

                return success / max(total, 1)

            if metric_type == MetricType.AVERAGE_DELIVERY_TIME:
                avg_stmt = select(func.avg(NotificationDeliveryLog.delivery_time_ms)).where(
                    and_(
                        NotificationDeliveryLog.created_at >= start,
                        NotificationDeliveryLog.created_at < end,
                        NotificationDeliveryLog.delivery_time_ms.isnot(None),
                    )
                )
                return float(await session.scalar(avg_stmt) or 0.0)

            return 0.0

    @MonitoredRepository._monitored_operation("save_report")
    async def save_report(self, report: NotificationReportModel) -> bool:
        """Save a notification report.

        Args:
            report: Report to save

        Returns:
            True if successful
        """
        try:
            async with self.db_manager.get_session() as session:
                session.add(report)
                await session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            return False

    @MonitoredRepository._monitored_operation("save_queue_health")
    async def save_queue_health(self, health: NotificationQueueHealth) -> bool:
        """Save queue health metrics.

        Args:
            health: Queue health to save

        Returns:
            True if successful
        """
        try:
            async with self.db_manager.get_session() as session:
                session.add(health)
                await session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save queue health: {e}")
            return False

    @MonitoredRepository._monitored_operation("get_queue_statistics")
    async def get_queue_statistics(self, since: datetime) -> dict[str, Any]:
        """Get queue statistics since a given time.

        Args:
            since: Time to get statistics from

        Returns:
            Queue statistics
        """
        async with self.db_manager.get_session() as session:
            # Count pending notifications
            pending_stmt = (
                select(func.count())
                .select_from(NotificationDeliveryLog)
                .where(NotificationDeliveryLog.status == NotificationStatus.PENDING.value)
            )
            pending_count = await session.scalar(pending_stmt) or 0

            # Count processed
            processed_stmt = (
                select(func.count())
                .select_from(NotificationDeliveryLog)
                .where(
                    and_(
                        NotificationDeliveryLog.created_at >= since,
                        NotificationDeliveryLog.status.in_(
                            [NotificationStatus.DELIVERED.value, NotificationStatus.FAILED.value]
                        ),
                    )
                )
            )
            processed_count = await session.scalar(processed_stmt) or 0

            # Count successful
            success_stmt = (
                select(func.count())
                .select_from(NotificationDeliveryLog)
                .where(
                    and_(
                        NotificationDeliveryLog.created_at >= since,
                        NotificationDeliveryLog.status == NotificationStatus.DELIVERED.value,
                    )
                )
            )
            success_count = await session.scalar(success_stmt) or 0

            # Average wait time
            avg_wait_stmt = select(
                func.avg(
                    func.extract(
                        "epoch",
                        NotificationDeliveryLog.delivered_at - NotificationDeliveryLog.created_at,
                    )
                )
            ).where(
                and_(
                    NotificationDeliveryLog.created_at >= since,
                    NotificationDeliveryLog.delivered_at.isnot(None),
                )
            )
            avg_wait_time = await session.scalar(avg_wait_stmt) or 0.0

            # Average processing time
            avg_processing_stmt = select(func.avg(NotificationDeliveryLog.delivery_time_ms)).where(
                and_(
                    NotificationDeliveryLog.created_at >= since,
                    NotificationDeliveryLog.delivery_time_ms.isnot(None),
                )
            )
            avg_processing_time = (await session.scalar(avg_processing_stmt) or 0.0) / 1000.0

            return {
                "pending_count": pending_count,
                "processed_count": processed_count,
                "success_count": success_count,
                "avg_wait_time": avg_wait_time,
                "avg_processing_time": avg_processing_time,
            }

    async def add_to_buffer(self, log_entry: NotificationDeliveryLog) -> None:
        """Add a log entry to the buffer.

        Args:
            log_entry: Log entry to buffer
        """
        async with self._buffer_lock:
            self._metric_buffer.append(log_entry)

    async def flush_buffer(self) -> list[NotificationDeliveryLog]:
        """Flush and return the buffer contents.

        Returns:
            List of buffered log entries
        """
        async with self._buffer_lock:
            buffer_copy = self._metric_buffer.copy()
            self._metric_buffer.clear()
            return buffer_copy

    def get_buffer_size(self) -> int:
        """Get current buffer size.

        Returns:
            Number of entries in buffer
        """
        return len(self._metric_buffer)
