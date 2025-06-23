"""
Tests for notification analytics and reporting system.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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
    NotificationMetric,
    NotificationQueueHealth,
)
from backend.services.database_manager import DatabaseManager
from backend.services.notification_analytics_service import NotificationAnalyticsService
from backend.services.notification_reporting_service import (
    DailyDigestTemplate,
    NotificationReportingService,
    WeeklyAnalyticsTemplate,
)


@pytest.fixture
async def db_manager():
    """Mock database manager."""
    manager = MagicMock(spec=DatabaseManager)

    # Mock get_session to return AsyncMock context manager
    session_mock = AsyncMock(spec=AsyncSession)
    manager.get_session.return_value.__aenter__.return_value = session_mock
    manager.get_session.return_value.__aexit__.return_value = None

    return manager


@pytest.fixture
async def analytics_service(db_manager):
    """Create analytics service instance."""
    service = NotificationAnalyticsService(db_manager)
    await service.start()
    yield service
    await service.stop()


@pytest.fixture
async def reporting_service(db_manager, analytics_service):
    """Create reporting service instance."""
    service = NotificationReportingService(db_manager, analytics_service)
    await service.start()
    yield service
    await service.stop()


class TestNotificationAnalyticsService:
    """Test notification analytics service."""

    async def test_track_delivery_success(self, analytics_service):
        """Test tracking successful delivery."""
        notification = NotificationPayload(
            id=str(uuid4()),
            message="Test notification",
            title="Test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SMTP],
            recipient="test@example.com",
        )

        await analytics_service.track_delivery(
            notification=notification,
            channel=NotificationChannel.SMTP,
            status=NotificationStatus.DELIVERED,
            delivery_time_ms=150,
        )

        # Verify metric was buffered
        assert len(analytics_service._metric_buffer) == 1
        log = analytics_service._metric_buffer[0]
        assert log.notification_id == notification.id
        assert log.channel == NotificationChannel.SMTP.value
        assert log.status == NotificationStatus.DELIVERED.value
        assert log.delivery_time_ms == 150

    async def test_track_delivery_failure(self, analytics_service):
        """Test tracking failed delivery."""
        notification = NotificationPayload(
            id=str(uuid4()),
            message="Test notification",
            level=NotificationType.ERROR,
            channels=[NotificationChannel.SLACK],
        )

        await analytics_service.track_delivery(
            notification=notification,
            channel=NotificationChannel.SLACK,
            status=NotificationStatus.FAILED,
            error_message="Connection timeout",
            error_code="TIMEOUT_ERROR",
            metadata={"attempt": 1},
        )

        # Verify metric was buffered
        assert len(analytics_service._metric_buffer) == 1
        log = analytics_service._metric_buffer[0]
        assert log.status == NotificationStatus.FAILED.value
        assert log.error_message == "Connection timeout"
        assert log.error_code == "TIMEOUT_ERROR"
        assert log.metadata["attempt"] == 1

    async def test_track_engagement(self, analytics_service, db_manager):
        """Test tracking user engagement."""
        notification_id = str(uuid4())

        # Mock database query
        mock_log = NotificationDeliveryLog(
            notification_id=notification_id,
            channel=NotificationChannel.SMTP.value,
            notification_type=NotificationType.INFO.value,
            status=NotificationStatus.DELIVERED.value,
        )

        session_mock = db_manager.get_session.return_value.__aenter__.return_value
        session_mock.execute.return_value.scalar_one_or_none.return_value = mock_log

        # Track engagement
        await analytics_service.track_engagement(
            notification_id=notification_id,
            action="opened",
        )

        # Verify engagement was tracked
        assert mock_log.opened_at is not None
        session_mock.commit.assert_called_once()

    async def test_buffer_auto_flush(self, analytics_service):
        """Test automatic buffer flushing."""
        # Fill buffer to limit
        for i in range(analytics_service._buffer_size_limit):
            notification = NotificationPayload(
                id=str(uuid4()),
                message=f"Test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )

            await analytics_service.track_delivery(
                notification=notification,
                channel=NotificationChannel.SYSTEM,
                status=NotificationStatus.DELIVERED,
            )

        # Buffer should be flushed
        assert len(analytics_service._metric_buffer) == 0

    async def test_get_channel_metrics(self, analytics_service, db_manager):
        """Test retrieving channel metrics."""
        # Mock database results
        session_mock = db_manager.get_session.return_value.__aenter__.return_value

        # Mock aggregated results
        mock_row = MagicMock()
        mock_row.channel = NotificationChannel.SMTP.value
        mock_row.total = 100
        mock_row.delivered = 95
        mock_row.failed = 5
        mock_row.retries = 3
        mock_row.avg_delivery_time = 250.5

        session_mock.execute.return_value.all.return_value = [mock_row]
        session_mock.scalar.return_value = None  # No last success/failure

        # Get metrics
        metrics = await analytics_service.get_channel_metrics()

        # Verify results
        assert len(metrics) == 1
        metric = metrics[0]
        assert metric.channel == NotificationChannel.SMTP
        assert metric.total_sent == 100
        assert metric.total_delivered == 95
        assert metric.success_rate == 0.95

    async def test_analyze_errors(self, analytics_service, db_manager):
        """Test error analysis."""
        # Mock database results
        session_mock = db_manager.get_session.return_value.__aenter__.return_value

        # Mock error patterns
        mock_pattern = MagicMock()
        mock_pattern.error_code = "TIMEOUT_ERROR"
        mock_pattern.error_message = "Connection timeout"
        mock_pattern.channel = NotificationChannel.SLACK.value
        mock_pattern.count = 25
        mock_pattern.first_seen = datetime.now(UTC) - timedelta(hours=2)
        mock_pattern.last_seen = datetime.now(UTC) - timedelta(minutes=10)
        mock_pattern.affected_recipients = 15

        session_mock.execute.return_value.all.return_value = [mock_pattern]
        session_mock.scalar.return_value = 5  # Retry successes

        # Analyze errors
        analyses = await analytics_service.analyze_errors(min_occurrences=5)

        # Verify results
        assert len(analyses) == 1
        analysis = analyses[0]
        assert analysis.error_code == "TIMEOUT_ERROR"
        assert analysis.occurrence_count == 25
        assert analysis.retry_success_rate == 0.2
        assert "timeout" in analysis.recommended_action.lower()

    async def test_get_aggregated_metrics(self, analytics_service, db_manager):
        """Test retrieving aggregated metrics."""
        # Mock database results
        session_mock = db_manager.get_session.return_value.__aenter__.return_value

        # Create mock aggregates
        now = datetime.now(UTC)
        mock_aggregates = []
        for i in range(24):
            mock_agg = MagicMock()
            mock_agg.metric_type = MetricType.DELIVERY_COUNT.value
            mock_agg.aggregation_period = AggregationPeriod.HOURLY.value
            mock_agg.period_start = now - timedelta(hours=24 - i)
            mock_agg.value = 100 + i * 10
            mock_agg.channel = None
            mock_agg.notification_type = None
            mock_agg.metadata = {}
            mock_aggregates.append(mock_agg)

        session_mock.execute.return_value.scalars.return_value.all.return_value = mock_aggregates

        # Get metrics
        metrics = await analytics_service.get_aggregated_metrics(
            metric_type=MetricType.DELIVERY_COUNT,
            aggregation_period=AggregationPeriod.HOURLY,
            start_date=now - timedelta(days=1),
            end_date=now,
        )

        # Verify results
        assert len(metrics) == 24
        assert all(m.metric_type == MetricType.DELIVERY_COUNT for m in metrics)
        assert metrics[0].value == 100
        assert metrics[-1].value == 330

    async def test_get_queue_health(self, analytics_service, db_manager):
        """Test queue health calculation."""
        # Mock database results
        session_mock = db_manager.get_session.return_value.__aenter__.return_value

        # Mock counts and metrics
        session_mock.scalar.side_effect = [
            50,  # pending_count
            200,  # processed_count
            180,  # success_count
            5.5,  # avg_wait_time
            0.15,  # avg_processing_time (150ms)
        ]

        # Get health
        health = await analytics_service.get_queue_health()

        # Verify results
        assert isinstance(health, NotificationQueueHealth)
        assert health.queue_depth == 50
        assert health.success_rate == 0.9
        assert health.average_wait_time == 5.5
        assert health.average_processing_time == 0.15
        assert 0 <= health.health_score <= 1


class TestNotificationReportingService:
    """Test notification reporting service."""

    async def test_generate_daily_digest_report(self, reporting_service, analytics_service):
        """Test generating daily digest report."""
        # Mock analytics data
        mock_channel_metrics = [
            ChannelMetrics(
                channel=NotificationChannel.SMTP,
                total_sent=1000,
                total_delivered=950,
                total_failed=50,
                total_retried=30,
                success_rate=0.95,
                average_delivery_time=250.0,
                last_success=datetime.now(UTC),
                last_failure=None,
                error_breakdown={},
            )
        ]

        analytics_service.get_channel_metrics = AsyncMock(return_value=mock_channel_metrics)
        analytics_service.get_aggregated_metrics = AsyncMock(return_value=[])
        analytics_service.analyze_errors = AsyncMock(return_value=[])
        analytics_service.get_queue_health = AsyncMock(
            return_value=NotificationQueueHealth(
                timestamp=datetime.now(UTC),
                queue_depth=10,
                processing_rate=5.0,
                success_rate=0.95,
                average_wait_time=2.0,
                average_processing_time=0.2,
                dlq_size=0,
                active_workers=1,
                memory_usage_mb=None,
                cpu_usage_percent=None,
                health_score=0.95,
            )
        )

        # Generate report
        now = datetime.now(UTC)
        report = await reporting_service.generate_report(
            template_name="daily_digest",
            start_date=now - timedelta(days=1),
            end_date=now,
            format="json",
        )

        # Verify report
        assert report.report_type == "daily_digest"
        assert report.format == "json"
        assert report.file_path is not None
        assert report.file_size_bytes > 0

        # Check file content
        file_path = Path(report.file_path)
        assert file_path.exists()

        data = json.loads(file_path.read_text())
        assert data["report_type"] == "daily_digest"
        assert data["summary"]["total_sent"] == 1000
        assert data["summary"]["overall_success_rate"] == 0.95

    async def test_generate_weekly_analytics_report(self, reporting_service, analytics_service):
        """Test generating weekly analytics report."""
        # Mock analytics data for current and previous week
        current_metrics = [
            ChannelMetrics(
                channel=NotificationChannel.SMTP,
                total_sent=7000,
                total_delivered=6650,
                total_failed=350,
                total_retried=200,
                success_rate=0.95,
                average_delivery_time=250.0,
                last_success=datetime.now(UTC),
                last_failure=None,
                error_breakdown={},
            )
        ]

        previous_metrics = [
            ChannelMetrics(
                channel=NotificationChannel.SMTP,
                total_sent=6000,
                total_delivered=5700,
                total_failed=300,
                total_retried=150,
                success_rate=0.95,
                average_delivery_time=240.0,
                last_success=None,
                last_failure=None,
                error_breakdown={},
            )
        ]

        # Mock methods to return different data based on date range
        call_count = 0

        async def mock_get_channel_metrics(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return current_metrics if call_count == 1 else previous_metrics

        analytics_service.get_channel_metrics = mock_get_channel_metrics
        analytics_service.get_aggregated_metrics = AsyncMock(return_value=[])

        # Generate report
        now = datetime.now(UTC)
        report = await reporting_service.generate_report(
            template_name="weekly_analytics",
            start_date=now - timedelta(days=7),
            end_date=now,
            format="json",
        )

        # Verify report
        assert report.report_type == "weekly_analytics"

        # Check trends
        data = json.loads(Path(report.file_path).read_text())
        assert data["summary"]["volume_trend_percent"] > 0  # Volume increased
        assert len(data["insights"]) > 0

    async def test_schedule_report(self, reporting_service):
        """Test scheduling a report."""
        schedule_id = "daily_report_1"

        await reporting_service.schedule_report(
            schedule_id=schedule_id,
            template_name="daily_digest",
            schedule={
                "interval": "daily",
                "hour": 8,
            },
            format="pdf",
            recipients=["admin@example.com"],
        )

        # Verify schedule was created
        assert schedule_id in reporting_service._scheduled_reports
        schedule = reporting_service._scheduled_reports[schedule_id]
        assert schedule["template"] == "daily_digest"
        assert schedule["format"] == "pdf"
        assert schedule["recipients"] == ["admin@example.com"]
        assert schedule["next_run"] is not None

    async def test_unschedule_report(self, reporting_service):
        """Test unscheduling a report."""
        schedule_id = "test_schedule"

        # Schedule first
        await reporting_service.schedule_report(
            schedule_id=schedule_id,
            template_name="daily_digest",
            schedule={"interval": "daily"},
        )

        # Then unschedule
        await reporting_service.unschedule_report(schedule_id)

        # Verify removed
        assert schedule_id not in reporting_service._scheduled_reports

    async def test_list_reports(self, reporting_service, db_manager):
        """Test listing reports."""
        # Mock database results
        session_mock = db_manager.get_session.return_value.__aenter__.return_value

        # Create mock reports
        mock_reports = []
        for i in range(3):
            mock_report = MagicMock()
            mock_report.report_id = f"report_{i}"
            mock_report.report_type = "daily_digest"
            mock_report.report_name = f"Daily Report {i}"
            mock_report.created_at = datetime.now(UTC) - timedelta(days=i)
            mock_report.format = "json"
            mock_report.file_size_bytes = 1000 + i * 100
            mock_reports.append(mock_report)

        session_mock.execute.return_value.scalars.return_value.all.return_value = mock_reports

        # List reports
        reports = await reporting_service.list_reports(
            report_type="daily_digest",
            limit=10,
        )

        # Verify results
        assert len(reports) == 3
        assert all(r.report_type == "daily_digest" for r in reports)

    async def test_report_file_formats(self, reporting_service, analytics_service):
        """Test generating reports in different formats."""
        # Mock minimal analytics data
        analytics_service.get_channel_metrics = AsyncMock(return_value=[])
        analytics_service.get_aggregated_metrics = AsyncMock(return_value=[])
        analytics_service.analyze_errors = AsyncMock(return_value=[])
        analytics_service.get_queue_health = AsyncMock(
            return_value=NotificationQueueHealth(
                timestamp=datetime.now(UTC),
                queue_depth=0,
                processing_rate=0,
                success_rate=1.0,
                average_wait_time=0,
                average_processing_time=0,
                dlq_size=0,
                active_workers=1,
                memory_usage_mb=None,
                cpu_usage_percent=None,
                health_score=1.0,
            )
        )

        now = datetime.now(UTC)

        # Test CSV format
        csv_report = await reporting_service.generate_report(
            template_name="daily_digest",
            start_date=now - timedelta(days=1),
            end_date=now,
            format="csv",
        )

        assert csv_report.format == "csv"
        assert Path(csv_report.file_path).suffix == ".csv"

        # Test HTML format
        html_report = await reporting_service.generate_report(
            template_name="daily_digest",
            start_date=now - timedelta(days=1),
            end_date=now,
            format="html",
        )

        assert html_report.format == "html"
        assert Path(html_report.file_path).suffix == ".html"

        # Verify HTML content
        html_content = Path(html_report.file_path).read_text()
        assert "<html>" in html_content
        assert "daily_digest" in html_content


class TestAnalyticsIntegration:
    """Test integration between analytics components."""

    async def test_dispatcher_analytics_integration(self, analytics_service, db_manager):
        """Test dispatcher integration with analytics."""
        from backend.core.config import NotificationSettings
        from backend.services.async_notification_dispatcher_analytics import (
            AnalyticsNotificationDispatcher,
        )
        from backend.services.notification_manager import NotificationManager
        from backend.services.notification_queue import NotificationQueue

        # Create mock components
        queue = MagicMock(spec=NotificationQueue)
        queue.dequeue_batch = AsyncMock(return_value=[])
        queue.mark_complete = AsyncMock()
        queue.mark_failed = AsyncMock()

        notification_manager = MagicMock(spec=NotificationManager)
        notification_manager.send_notification = AsyncMock(return_value=True)

        config = MagicMock(spec=NotificationSettings)

        # Create dispatcher with analytics
        dispatcher = AnalyticsNotificationDispatcher(
            queue=queue,
            notification_manager=notification_manager,
            config=config,
            analytics_service=analytics_service,
        )

        # Process a notification
        notification = NotificationPayload(
            id=str(uuid4()),
            message="Test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
        )

        success = await dispatcher._process_single_notification(notification)

        # Verify analytics were tracked
        assert success
        assert len(analytics_service._metric_buffer) == 1
        log = analytics_service._metric_buffer[0]
        assert log.notification_id == notification.id
        assert log.status == NotificationStatus.DELIVERED.value

    async def test_end_to_end_analytics_flow(self, analytics_service, reporting_service):
        """Test complete analytics flow from tracking to reporting."""
        # Track some deliveries
        for i in range(10):
            notification = NotificationPayload(
                id=str(uuid4()),
                message=f"Test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SMTP],
                recipient=f"user{i}@example.com",
            )

            await analytics_service.track_delivery(
                notification=notification,
                channel=NotificationChannel.SMTP,
                status=NotificationStatus.DELIVERED if i < 8 else NotificationStatus.FAILED,
                delivery_time_ms=100 + i * 10,
                error_message="Test error" if i >= 8 else None,
            )

        # Flush buffer
        await analytics_service._flush_buffer()

        # Mock analytics retrieval
        analytics_service.get_channel_metrics = AsyncMock(
            return_value=[
                ChannelMetrics(
                    channel=NotificationChannel.SMTP,
                    total_sent=10,
                    total_delivered=8,
                    total_failed=2,
                    total_retried=0,
                    success_rate=0.8,
                    average_delivery_time=145.0,
                    last_success=datetime.now(UTC),
                    last_failure=datetime.now(UTC),
                    error_breakdown={"Test error": 2},
                )
            ]
        )

        # Generate report
        now = datetime.now(UTC)
        report = await reporting_service.generate_report(
            template_name="daily_digest",
            start_date=now - timedelta(days=1),
            end_date=now,
            format="json",
        )

        # Verify report contains tracked data
        data = json.loads(Path(report.file_path).read_text())
        assert data["summary"]["total_sent"] == 10
        assert data["summary"]["total_delivered"] == 8
        assert data["summary"]["overall_success_rate"] == 0.8
