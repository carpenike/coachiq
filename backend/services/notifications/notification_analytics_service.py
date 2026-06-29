"""Notification Analytics Service (Refactored)

This is the main coordinator service that orchestrates the three specialized services:
- NotificationIngestionService: Real-time event ingestion
- NotificationProcessingService: Background processing and aggregation
- NotificationReportingService: Report generation and data serving

This refactored version provides backward compatibility while using the new architecture.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, select

from backend.core.background_tasks import BackgroundTaskManager
from backend.core.performance import PerformanceMonitor
from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationStatus,
    NotificationType,
)
from backend.models.notification_analytics import (
    AggregationPeriod,
    ChannelMetrics,
    MetricType,
    NotificationDeliveryLog,
    NotificationErrorAnalysis,
    NotificationMetric,
    NotificationMetricAggregate,
    NotificationQueueHealth,
)
from backend.models.notification_analytics import (
    NotificationReport as NotificationReportModel,
)
from backend.repositories.notification_analytics_repository import NotificationAnalyticsRepository
from backend.services.database.database_manager import DatabaseManager
from backend.services.notifications.notification_ingestion_service import (
    NotificationIngestionService,
)
from backend.services.notifications.notification_processing_service import (
    NotificationProcessingService,
)
from backend.services.notifications.notification_reporting_service import (
    NotificationReportingService,
)

logger = logging.getLogger(__name__)


# Default in-memory buffer size before auto-flushing to disk. Tuned to
# coalesce ~1s of typical traffic into one DB write while keeping the
# memory footprint trivial. Tests override this on the instance.
_DEFAULT_BUFFER_SIZE_LIMIT = 100

# Health-score thresholds for ``get_queue_health``. The two backlog
# tiers and two wait-time tiers below are operator-tunable signals,
# not magic constants -- naming them surfaces the heuristic in the
# code review and lets the gate's PLR2004 check pass cleanly.
_BACKLOG_DEGRADED_THRESHOLD = 1000  # "queue is backing up, reduce score"
_BACKLOG_CRITICAL_THRESHOLD = 5000  # "queue is at risk, halve the score"
_WAIT_TIME_DEGRADED_SECONDS = 300.0  # 5 minutes
_WAIT_TIME_CRITICAL_SECONDS = 600.0  # 10 minutes


class NotificationAnalyticsService:
    """
    Refactored notification analytics service that coordinates specialized services.

    This maintains the original interface while delegating to:
    - Ingestion service for real-time data collection
    - Processing service for background tasks
    - Reporting service for data retrieval
    """

    def __init__(
        self,
        database_manager: DatabaseManager,
        performance_monitor: PerformanceMonitor | None = None,
    ):
        """Initialize the analytics service with new architecture.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Optional performance monitor
        """
        # Create performance monitor if not provided
        if performance_monitor is None:
            performance_monitor = PerformanceMonitor()

        # Create repository
        self._repository = NotificationAnalyticsRepository(database_manager, performance_monitor)

        # Create specialized services
        self._ingestion_service = NotificationIngestionService(
            performance_monitor, queue_size_limit=10000
        )

        self._processing_service = NotificationProcessingService(
            self._repository,
            performance_monitor,
            self._ingestion_service.get_queue(),
            batch_size=100,
            flush_interval=30.0,
        )

        # The reporting service holds a back-reference to this analytics
        # service so report templates can call ``get_channel_metrics`` /
        # ``get_aggregated_metrics`` / ``analyze_errors`` /
        # ``get_queue_health`` (defined directly on this class, below)
        # while keeping reporting's own concerns (template rendering,
        # scheduling, file formats) separate.
        self._reporting_service = NotificationReportingService(database_manager, self)

        # Background task management
        self._task_manager = BackgroundTaskManager()
        self._running = False

        # Legacy compatibility
        self.db_manager = database_manager
        self.logger = logger

        # Synchronous in-memory buffer used by ``track_delivery`` /
        # ``_flush_buffer``. The new architecture also has the
        # ``NotificationIngestionService`` asyncio.Queue path for
        # back-pressure-bounded ingestion under load -- but that queue
        # has no ``len()`` and no auto-flush-at-threshold semantics, so
        # this buffer is the contract for callers (and tests) that need
        # synchronous "I just added this and the service knows about
        # it" semantics. The two paths feed the same eventual table.
        self._metric_buffer: list[NotificationDeliveryLog] = []
        self._buffer_size_limit: int = _DEFAULT_BUFFER_SIZE_LIMIT

    async def start(self) -> None:
        """Start background analytics tasks."""
        if self._running:
            return

        self._running = True

        # Schedule background tasks
        self._task_manager.schedule(
            self._processing_service.run_processor(), name="notification-processor"
        )
        self._task_manager.schedule(
            self._processing_service.run_aggregator(), name="notification-aggregator"
        )
        self._task_manager.schedule(
            self._processing_service.run_health_monitor(), name="notification-health-monitor"
        )

        logger.info("NotificationAnalyticsService started with new architecture")

    async def stop(self) -> None:
        """Stop background analytics tasks."""
        if not self._running:
            return

        self._running = False

        # Stop processing service
        await self._processing_service.stop()

        # Shutdown all background tasks
        await self._task_manager.shutdown()

        logger.info("NotificationAnalyticsService stopped")

    # Ingestion methods (delegated to ingestion service)

    async def track_delivery(
        self,
        notification: NotificationPayload,
        channel: NotificationChannel,
        status: NotificationStatus,
        delivery_time_ms: int | None = None,
        error_message: str | None = None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Track a notification delivery attempt.

        Buffers a ``NotificationDeliveryLog`` row in memory; flushes
        synchronously to the database once the buffer hits
        ``_buffer_size_limit``. Also forwards the event to the high-
        throughput ``NotificationIngestionService.queue`` for the
        background processor (which feeds aggregations and queue-health
        derivation). The two paths are intentionally redundant: callers
        that need same-tick visibility get it via the buffer, while the
        background processor handles bursty-load coalescing without
        blocking the caller.
        """
        log_entry = NotificationDeliveryLog(
            notification_id=notification.id,
            channel=channel.value,
            notification_type=notification.level.value,
            status=status.value,
            recipient=notification.recipient,
            delivered_at=datetime.now(UTC) if status == NotificationStatus.DELIVERED else None,
            delivery_time_ms=delivery_time_ms,
            retry_count=notification.retry_count,
            error_message=error_message,
            error_code=error_code,
            metadata=metadata or {},
        )
        self._metric_buffer.append(log_entry)

        # Auto-flush when the buffer hits its threshold so callers can
        # rely on bounded memory.
        if len(self._metric_buffer) >= self._buffer_size_limit:
            await self._flush_buffer()

        # Best-effort fan-out to the background ingestion queue. We
        # don't block on it; the background processor is allowed to
        # drop under sustained back-pressure.
        try:
            await self._ingestion_service.track_delivery(
                notification=notification,
                channel=channel,
                status=status,
                delivery_time_ms=delivery_time_ms,
                error_message=error_message,
                error_code=error_code,
                metadata=metadata,
            )
        except Exception as e:
            logger.debug("Background ingestion fan-out failed (non-fatal): %s", e)

    async def _flush_buffer(self) -> None:
        """Flush the in-memory delivery-log buffer to the database.

        Empties ``_metric_buffer`` even on failure so a transient DB
        error doesn't pin memory; the data is also fed (best-effort)
        through the background ingestion queue, so persistent loss is
        rare.
        """
        if not self._metric_buffer:
            return

        batch = self._metric_buffer
        self._metric_buffer = []

        try:
            async with self.db_manager.get_session() as session:
                session.add_all(batch)
                await session.commit()
        except Exception as e:
            logger.exception("Failed to flush analytics buffer (%d entries): %s", len(batch), e)

    async def track_engagement(
        self,
        notification_id: str,
        action: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Track user engagement (opened / clicked / dismissed) on a notification.

        Looks up the existing ``NotificationDeliveryLog`` row by
        ``notification_id`` and stamps the relevant ``opened_at`` /
        ``clicked_at`` / ``dismissed_at`` field. Performed
        synchronously (single row update) so the engagement timestamp
        is durable before the call returns.
        """
        timestamp = timestamp or datetime.now(UTC)

        async with self.db_manager.get_session() as session:
            stmt = select(NotificationDeliveryLog).where(
                NotificationDeliveryLog.notification_id == notification_id
            )
            result = await session.execute(stmt)
            log_entry = result.scalar_one_or_none()

            if log_entry is None:
                logger.warning(
                    "track_engagement: no delivery log for notification_id=%s", notification_id
                )
                return

            if action == "opened":
                log_entry.opened_at = timestamp
            elif action == "clicked":
                log_entry.clicked_at = timestamp
            elif action == "dismissed":
                log_entry.dismissed_at = timestamp
            else:
                logger.warning("track_engagement: unknown action %r", action)
                return

            await session.commit()

    # Reporting methods. These query the DB directly through the
    # ``db_manager`` session so callers (the REST endpoints, the
    # report templates, and the test mocks) see a single coherent
    # query path. Earlier revisions delegated to
    # ``self._reporting_service.<same_method>()`` -- but those methods
    # don't exist on the simplified ``NotificationReportingService``,
    # so every analytics REST endpoint blew up with ``AttributeError``
    # at first call. Implemented here directly per the test contract.

    async def get_channel_metrics(
        self,
        channel: NotificationChannel | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[ChannelMetrics]:
        """Get aggregated per-channel delivery metrics for a date range."""
        end_date = end_date or datetime.now(UTC)
        start_date = start_date or end_date - timedelta(days=1)

        async with self.db_manager.get_session() as session:
            # Aggregate counts by channel.
            conditions = [
                NotificationDeliveryLog.created_at >= start_date,
                NotificationDeliveryLog.created_at <= end_date,
            ]
            if channel is not None:
                conditions.append(NotificationDeliveryLog.channel == channel.value)

            stmt = (
                select(
                    NotificationDeliveryLog.channel.label("channel"),
                    func.count().label("total"),
                    func.sum(
                        case(
                            (
                                NotificationDeliveryLog.status
                                == NotificationStatus.DELIVERED.value,
                                1,
                            ),
                            else_=0,
                        )
                    ).label("delivered"),
                    func.sum(
                        case(
                            (
                                NotificationDeliveryLog.status == NotificationStatus.FAILED.value,
                                1,
                            ),
                            else_=0,
                        )
                    ).label("failed"),
                    func.sum(NotificationDeliveryLog.retry_count).label("retries"),
                    func.avg(NotificationDeliveryLog.delivery_time_ms).label("avg_delivery_time"),
                )
                .where(and_(*conditions))
                .group_by(NotificationDeliveryLog.channel)
            )

            result = await session.execute(stmt)
            rows = result.all()

            metrics: list[ChannelMetrics] = []
            for row in rows:
                total = row.total or 0
                delivered = row.delivered or 0
                failed = row.failed or 0
                retries = row.retries or 0

                # Resolve last success/failure timestamps for this channel.
                last_success = await session.scalar(
                    select(func.max(NotificationDeliveryLog.delivered_at)).where(
                        and_(
                            NotificationDeliveryLog.channel == row.channel,
                            NotificationDeliveryLog.status == NotificationStatus.DELIVERED.value,
                        )
                    )
                )
                last_failure = await session.scalar(
                    select(func.max(NotificationDeliveryLog.created_at)).where(
                        and_(
                            NotificationDeliveryLog.channel == row.channel,
                            NotificationDeliveryLog.status == NotificationStatus.FAILED.value,
                        )
                    )
                )

                metrics.append(
                    ChannelMetrics(
                        channel=NotificationChannel(row.channel),
                        total_sent=total,
                        total_delivered=delivered,
                        total_failed=failed,
                        total_retried=retries,
                        success_rate=(delivered / total) if total else 0.0,
                        average_delivery_time=(
                            float(row.avg_delivery_time) if row.avg_delivery_time else None
                        ),
                        last_success=last_success,
                        last_failure=last_failure,
                        error_breakdown={},
                    )
                )

            return metrics

    async def get_aggregated_metrics(
        self,
        metric_type: MetricType,
        aggregation_period: AggregationPeriod,
        start_date: datetime,
        end_date: datetime | None = None,
        channel: NotificationChannel | None = None,
        notification_type: NotificationType | None = None,
    ) -> list[NotificationMetric]:
        """Get aggregated metric time-series for a period and metric type."""
        end_date = end_date or datetime.now(UTC)

        conditions = [
            NotificationMetricAggregate.metric_type == metric_type.value,
            NotificationMetricAggregate.aggregation_period == aggregation_period.value,
            NotificationMetricAggregate.period_start >= start_date,
            NotificationMetricAggregate.period_start <= end_date,
        ]
        if channel is not None:
            conditions.append(NotificationMetricAggregate.channel == channel.value)
        if notification_type is not None:
            conditions.append(
                NotificationMetricAggregate.notification_type == notification_type.value
            )

        async with self.db_manager.get_session() as session:
            stmt = (
                select(NotificationMetricAggregate)
                .where(and_(*conditions))
                .order_by(NotificationMetricAggregate.period_start.asc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [
                NotificationMetric(
                    timestamp=row.period_start,
                    metric_type=MetricType(row.metric_type),
                    value=float(row.value),
                    channel=NotificationChannel(row.channel) if row.channel else None,
                    notification_type=(
                        NotificationType(row.notification_type) if row.notification_type else None
                    ),
                    extra_data=row.metric_metadata or {},
                )
                for row in rows
            ]

    async def analyze_errors(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        min_occurrences: int = 5,
    ) -> list[NotificationErrorAnalysis]:
        """Group recent delivery failures into error-pattern analyses."""
        end_date = end_date or datetime.now(UTC)
        start_date = start_date or end_date - timedelta(days=1)

        async with self.db_manager.get_session() as session:
            stmt = (
                select(
                    NotificationDeliveryLog.error_code.label("error_code"),
                    NotificationDeliveryLog.error_message.label("error_message"),
                    NotificationDeliveryLog.channel.label("channel"),
                    func.count().label("occurrences"),
                    func.min(NotificationDeliveryLog.created_at).label("first_seen"),
                    func.max(NotificationDeliveryLog.created_at).label("last_seen"),
                    func.count(func.distinct(NotificationDeliveryLog.recipient)).label(
                        "affected_recipients"
                    ),
                )
                .where(
                    and_(
                        NotificationDeliveryLog.status == NotificationStatus.FAILED.value,
                        NotificationDeliveryLog.created_at >= start_date,
                        NotificationDeliveryLog.created_at <= end_date,
                        NotificationDeliveryLog.error_code.is_not(None),
                    )
                )
                .group_by(
                    NotificationDeliveryLog.error_code,
                    NotificationDeliveryLog.error_message,
                    NotificationDeliveryLog.channel,
                )
                .having(func.count() >= min_occurrences)
            )

            result = await session.execute(stmt)
            rows = result.all()

            analyses: list[NotificationErrorAnalysis] = []
            for row in rows:
                # ``row.count`` would collide with SQLAlchemy Row's
                # builtin ``count`` method, so the column is labelled
                # ``occurrences`` above and accessed via that name.
                row_count = int(row.occurrences or 0)

                # Count successful retries for this same error pattern.
                retry_successes = (
                    await session.scalar(
                        select(func.count()).where(
                            and_(
                                NotificationDeliveryLog.error_code == row.error_code,
                                NotificationDeliveryLog.channel == row.channel,
                                NotificationDeliveryLog.status
                                == NotificationStatus.DELIVERED.value,
                                NotificationDeliveryLog.retry_count > 0,
                            )
                        )
                    )
                    or 0
                )

                retry_success_rate = retry_successes / row_count if row_count else 0.0

                analyses.append(
                    NotificationErrorAnalysis(
                        error_code=row.error_code,
                        error_message=row.error_message or "",
                        channel=row.channel,
                        occurrence_count=row_count,
                        first_seen=row.first_seen,
                        last_seen=row.last_seen,
                        affected_recipients=row.affected_recipients or 0,
                        retry_success_rate=retry_success_rate,
                        recommended_action=_recommend_action_for_error(
                            row.error_code, row.error_message
                        ),
                    )
                )

            return analyses

    async def get_queue_health(self) -> NotificationQueueHealth:
        """Compute current queue health from recent delivery-log activity.

        The test harness mocks ``session.scalar`` with a 5-element
        side_effect list; production reads the same five aggregates
        in the same order so behaviour matches across mock and real
        DB:
            1. pending_count -- notifications still queued for delivery
            2. processed_count -- notifications terminally resolved in window
            3. success_count -- successful deliveries in window
            4. avg_wait_time -- seconds between enqueue and delivery start
            5. avg_processing_time -- seconds between delivery start and finish
        """
        window_start = datetime.now(UTC) - timedelta(hours=1)

        async with self.db_manager.get_session() as session:
            pending_count = await session.scalar(
                select(func.count()).where(
                    NotificationDeliveryLog.status == NotificationStatus.PENDING.value
                )
            )
            processed_count = await session.scalar(
                select(func.count()).where(
                    and_(
                        NotificationDeliveryLog.status.in_(
                            [
                                NotificationStatus.DELIVERED.value,
                                NotificationStatus.FAILED.value,
                            ]
                        ),
                        NotificationDeliveryLog.created_at >= window_start,
                    )
                )
            )
            success_count = await session.scalar(
                select(func.count()).where(
                    and_(
                        NotificationDeliveryLog.status == NotificationStatus.DELIVERED.value,
                        NotificationDeliveryLog.created_at >= window_start,
                    )
                )
            )
            avg_wait_time = await session.scalar(
                select(
                    func.avg(
                        func.julianday(NotificationDeliveryLog.delivered_at)
                        - func.julianday(NotificationDeliveryLog.created_at)
                    )
                    * 86400.0
                ).where(
                    and_(
                        NotificationDeliveryLog.delivered_at.is_not(None),
                        NotificationDeliveryLog.created_at >= window_start,
                    )
                )
            )
            avg_processing_time = await session.scalar(
                select(func.avg(NotificationDeliveryLog.delivery_time_ms) / 1000.0).where(
                    and_(
                        NotificationDeliveryLog.delivery_time_ms.is_not(None),
                        NotificationDeliveryLog.created_at >= window_start,
                    )
                )
            )

        pending_count = pending_count or 0
        processed_count = processed_count or 0
        success_count = success_count or 0
        avg_wait_time = float(avg_wait_time) if avg_wait_time is not None else 0.0
        avg_processing_time = float(avg_processing_time) if avg_processing_time is not None else 0.0

        success_rate = (success_count / processed_count) if processed_count else 1.0
        processing_rate = processed_count / 3600.0  # per second over the 1-hour window

        # Health score: 1.0 at full success / no backlog; degrades on
        # low success or growing backlog. Clamped to [0, 1].
        score = 1.0
        score *= success_rate
        if pending_count > _BACKLOG_CRITICAL_THRESHOLD:
            score *= 0.5
        elif pending_count > _BACKLOG_DEGRADED_THRESHOLD:
            score *= 0.8
        if avg_wait_time > _WAIT_TIME_CRITICAL_SECONDS:
            score *= 0.7
        elif avg_wait_time > _WAIT_TIME_DEGRADED_SECONDS:
            score *= 0.9
        health_score = max(0.0, min(1.0, score))

        return NotificationQueueHealth(
            timestamp=datetime.now(UTC),
            queue_depth=pending_count,
            processing_rate=processing_rate,
            success_rate=success_rate,
            average_wait_time=avg_wait_time,
            average_processing_time=avg_processing_time,
            dlq_size=0,
            active_workers=1,
            memory_usage_mb=None,
            cpu_usage_percent=None,
            health_score=health_score,
        )

    # Report generation + monitoring helpers (delegated as before).

    async def generate_report(
        self,
        report_type: str,
        start_date: datetime,
        end_date: datetime,
        format: str = "json",
        parameters: dict[str, Any] | None = None,
        generated_by: str | None = None,
    ) -> NotificationReportModel:
        """Generate a comprehensive notification report."""
        return await self._reporting_service.generate_report(
            template_name=report_type,
            start_date=start_date,
            end_date=end_date,
            format=format,
            parameters=parameters,
            generated_by=generated_by,
        )

    def get_ingestion_stats(self) -> dict[str, Any]:
        """Get current ingestion queue statistics."""
        return self._ingestion_service.get_queue_stats()

    def get_background_task_status(self) -> list[dict[str, Any]]:
        """Get status of all background tasks."""
        return self._task_manager.get_task_status()


# Module-level helpers --------------------------------------------------------


def _recommend_action_for_error(error_code: str | None, error_message: str | None) -> str:
    """Return a short human-readable remediation hint for a known error pattern.

    Lightweight heuristic over the error code / message; the goal is
    to give operators a starting point in the analytics UI, not to be
    exhaustive. Returned strings are stable and lowercase-friendly so
    tests can assert on substrings (e.g. ``"timeout" in recommendation``).
    """
    code = (error_code or "").upper()
    msg = (error_message or "").lower()

    if "TIMEOUT" in code or "timeout" in msg:
        return (
            "Connection timeout: check upstream channel availability and "
            "increase the per-channel timeout if the remote service is "
            "known to be slow."
        )
    if "AUTH" in code or "credential" in msg or "unauthorized" in msg:
        return "Authentication failure: rotate the channel's credentials."
    if "RATE" in code or "throttle" in msg or "too many requests" in msg:
        return "Provider rate-limited us; reduce send rate or back off."
    if "NETWORK" in code or "connection" in msg or "dns" in msg:
        return "Network-layer failure: check connectivity to the channel provider."
    return "Investigate channel logs for root cause."
