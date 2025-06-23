"""Notification Analytics Service (Refactored)

This is the main coordinator service that orchestrates the three specialized services:
- NotificationIngestionService: Real-time event ingestion
- NotificationProcessingService: Background processing and aggregation
- NotificationReportingService: Report generation and data serving

This refactored version provides backward compatibility while using the new architecture.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

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
    NotificationErrorAnalysis,
    NotificationMetric,
    NotificationQueueHealth,
)
from backend.models.notification_analytics import (
    NotificationReport as NotificationReportModel,
)
from backend.repositories.notification_analytics_repository import NotificationAnalyticsRepository
from backend.services.database_manager import DatabaseManager
from backend.services.notification_ingestion_service import NotificationIngestionService
from backend.services.notification_processing_service import NotificationProcessingService
from backend.services.notification_reporting_service import NotificationReportingService

logger = logging.getLogger(__name__)


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

        self._reporting_service = NotificationReportingService(
            self._repository, performance_monitor, database_manager
        )

        # Background task management
        self._task_manager = BackgroundTaskManager()
        self._running = False

        # Legacy compatibility
        self.db_manager = database_manager
        self.logger = logger

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
        """Track a notification delivery attempt."""
        success = await self._ingestion_service.track_delivery(
            notification=notification,
            channel=channel,
            status=status,
            delivery_time_ms=delivery_time_ms,
            error_message=error_message,
            error_code=error_code,
            metadata=metadata,
        )

        if not success:
            logger.warning("Failed to track delivery - ingestion queue full")

    async def track_engagement(
        self,
        notification_id: str,
        action: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Track user engagement with a notification."""
        success = await self._ingestion_service.track_engagement(
            notification_id=notification_id,
            action=action,
            timestamp=timestamp,
        )

        if not success:
            logger.warning("Failed to track engagement - ingestion queue full")

    # Reporting methods (delegated to reporting service)

    async def get_channel_metrics(
        self,
        channel: NotificationChannel | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[ChannelMetrics]:
        """Get metrics for notification channels."""
        return await self._reporting_service.get_channel_metrics(
            channel=channel,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_aggregated_metrics(
        self,
        metric_type: MetricType,
        aggregation_period: AggregationPeriod,
        start_date: datetime,
        end_date: datetime | None = None,
        channel: NotificationChannel | None = None,
        notification_type: NotificationType | None = None,
    ) -> list[NotificationMetric]:
        """Get aggregated metrics for a specific period."""
        return await self._reporting_service.get_aggregated_metrics(
            metric_type=metric_type,
            aggregation_period=aggregation_period,
            start_date=start_date,
            end_date=end_date,
            channel=channel,
            notification_type=notification_type,
        )

    async def analyze_errors(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        min_occurrences: int = 5,
    ) -> list[NotificationErrorAnalysis]:
        """Analyze notification delivery errors."""
        return await self._reporting_service.analyze_errors(
            start_date=start_date,
            end_date=end_date,
            min_occurrences=min_occurrences,
        )

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
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            format=format,
            parameters=parameters,
            generated_by=generated_by,
        )

    async def get_queue_health(self) -> NotificationQueueHealth:
        """Get current notification queue health metrics."""
        return await self._processing_service.calculate_queue_health()

    # Additional methods for monitoring

    def get_ingestion_stats(self) -> dict[str, Any]:
        """Get current ingestion queue statistics."""
        return self._ingestion_service.get_queue_stats()

    def get_background_task_status(self) -> list[dict[str, Any]]:
        """Get status of all background tasks."""
        return self._task_manager.get_task_status()
