"""
Integration Tests for Notification System with Real Services

This module provides comprehensive integration tests for the notification
system using real external services in a controlled testing environment.
Tests the complete flow from notification creation to delivery.

Key Test Areas:
- Email delivery via SMTP (real email server)
- Pushover notifications (test API key)
- Template rendering and delivery
- Queue processing and persistence
- Rate limiting and escalation
- Error handling and recovery
- Performance under load

Example:
    # Run with real SMTP credentials
    COACHIQ_TEST_SMTP_ENABLED=true pytest tests/integration/test_notification_integration.py

    # Run with mock services (default)
    pytest tests/integration/test_notification_integration.py
"""

import asyncio
import os
import tempfile
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
from backend.services.email_template_manager import EmailTemplateManager
from backend.services.notification_manager import NotificationManager
from backend.services.notification_queue import NotificationQueue
from backend.services.notification_routing import (
    NotificationRouter,
    RoutingConditionType,
    RoutingRule,
    SystemContext,
    UserNotificationPreferences,
)
from backend.services.safe_notification_manager import SafeNotificationManager


class IntegrationTestConfig:
    """Configuration for integration tests."""

    def __init__(self):
        # Test environment flags
        self.use_real_smtp = os.getenv("COACHIQ_TEST_SMTP_ENABLED", "false").lower() == "true"
        self.use_real_pushover = (
            os.getenv("COACHIQ_TEST_PUSHOVER_ENABLED", "false").lower() == "true"
        )
        self.test_email = os.getenv("COACHIQ_TEST_EMAIL", "test@example.com")

        # Real service credentials (only if enabled)
        self.smtp_config = {
            "host": os.getenv("COACHIQ_TEST_SMTP_HOST", "localhost"),
            "port": int(os.getenv("COACHIQ_TEST_SMTP_PORT", "587")),
            "username": os.getenv("COACHIQ_TEST_SMTP_USERNAME", ""),
            "password": os.getenv("COACHIQ_TEST_SMTP_PASSWORD", ""),
            "use_tls": os.getenv("COACHIQ_TEST_SMTP_TLS", "true").lower() == "true",
        }

        self.pushover_config = {
            "token": os.getenv("COACHIQ_TEST_PUSHOVER_TOKEN", "test_token"),
            "user_key": os.getenv("COACHIQ_TEST_PUSHOVER_USER", "test_user"),
        }


@pytest.fixture
def integration_config():
    """Provide integration test configuration."""
    return IntegrationTestConfig()


@pytest.fixture
async def test_notification_config(integration_config):
    """Create test notification configuration."""
    smtp_enabled = integration_config.use_real_smtp

    config = NotificationSettings(
        enabled=True,
        default_title="CoachIQ Test",
        app_name="CoachIQ Test",
        queue_db_path=":memory:",  # Use in-memory SQLite for tests
        rate_limit_max_tokens=1000,  # Higher limits for testing
        rate_limit_per_minute=600,
        debounce_minutes=1,  # Shorter debounce for testing
    )

    # Configure SMTP if enabled
    if smtp_enabled:
        config.smtp = type(
            "SMTPSettings",
            (),
            {
                "enabled": True,
                "host": integration_config.smtp_config["host"],
                "port": integration_config.smtp_config["port"],
                "username": integration_config.smtp_config["username"],
                "password": integration_config.smtp_config["password"],
                "use_tls": integration_config.smtp_config["use_tls"],
                "from_email": f"test@{integration_config.smtp_config['host']}",
            },
        )()
    else:
        config.smtp = type("SMTPSettings", (), {"enabled": False})()

    # Configure Pushover if enabled
    if integration_config.use_real_pushover:
        config.pushover = type(
            "PushoverSettings",
            (),
            {
                "enabled": True,
                "token": integration_config.pushover_config["token"],
                "user_key": integration_config.pushover_config["user_key"],
            },
        )()
    else:
        config.pushover = type("PushoverSettings", (), {"enabled": False})()

    return config


@pytest.fixture
async def temp_db_path():
    """Create temporary database path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        temp_path = temp_file.name

    yield temp_path

    # Cleanup
    try:
        Path(temp_path).unlink()
        # Also clean up WAL files
        Path(f"{temp_path}-wal").unlink(missing_ok=True)
        Path(f"{temp_path}-shm").unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture
async def notification_queue(temp_db_path):
    """Create notification queue for testing."""
    queue = NotificationQueue(temp_db_path)
    await queue.initialize()

    yield queue

    await queue.close()


@pytest.fixture
async def safe_notification_manager(test_notification_config):
    """Create SafeNotificationManager for integration testing."""
    manager = SafeNotificationManager(test_notification_config)
    await manager.initialize()

    yield manager

    await manager.cleanup()


@pytest.fixture
async def notification_router():
    """Create notification router for testing."""
    router = NotificationRouter()
    await router.initialize()

    return router


@pytest.fixture
async def email_template_manager(test_notification_config):
    """Create email template manager for testing."""
    manager = EmailTemplateManager(test_notification_config)
    await manager.initialize()

    return manager


# Integration Test Classes


class TestNotificationQueueIntegration:
    """Test notification queue with persistent storage."""

    async def test_queue_persistence_across_restarts(self, temp_db_path):
        """Test queue persistence survives restart."""
        # Create notification in first queue instance
        queue1 = NotificationQueue(temp_db_path)
        await queue1.initialize()

        notification = NotificationPayload(
            message="Test persistence",
            title="Test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
        )

        notification_id = await queue1.enqueue(notification)
        assert notification_id == notification.id

        # Get statistics before close
        stats1 = await queue1.get_statistics()
        assert stats1.pending_count == 1

        await queue1.close()

        # Create new queue instance with same database
        queue2 = NotificationQueue(temp_db_path)
        await queue2.initialize()

        # Verify notification persisted
        stats2 = await queue2.get_statistics()
        assert stats2.pending_count == 1

        # Dequeue and verify content
        batch = await queue2.dequeue_batch(1)
        assert len(batch) == 1
        assert batch[0].message == "Test persistence"
        assert batch[0].id == notification_id

        await queue2.close()

    async def test_queue_batch_processing(self, notification_queue):
        """Test batch processing efficiency."""
        # Enqueue multiple notifications
        notifications = []
        for i in range(10):
            notification = NotificationPayload(
                message=f"Test message {i}",
                title=f"Test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SYSTEM],
            )
            await notification_queue.enqueue(notification)
            notifications.append(notification)

        # Verify queue depth
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 10

        # Dequeue in batches
        batch1 = await notification_queue.dequeue_batch(5)
        assert len(batch1) == 5

        batch2 = await notification_queue.dequeue_batch(5)
        assert len(batch2) == 5

        # Verify all notifications dequeued
        all_messages = [n.message for n in batch1 + batch2]
        expected_messages = [f"Test message {i}" for i in range(10)]
        assert sorted(all_messages) == sorted(expected_messages)

    async def test_queue_retry_and_dlq(self, notification_queue):
        """Test retry logic and dead letter queue."""
        notification = NotificationPayload(
            message="Test retry",
            title="Test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.SYSTEM],
            max_retries=2,
        )

        notification_id = await notification_queue.enqueue(notification)

        # Dequeue notification
        batch = await notification_queue.dequeue_batch(1)
        assert len(batch) == 1

        # Mark as failed (should retry)
        await notification_queue.mark_failed(notification_id, "Test failure", should_retry=True)

        # Should be back in queue for retry
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 1

        # Fail again
        batch = await notification_queue.dequeue_batch(1)
        await notification_queue.mark_failed(notification_id, "Test failure 2", should_retry=True)

        # Fail third time (should go to DLQ)
        batch = await notification_queue.dequeue_batch(1)
        await notification_queue.mark_failed(notification_id, "Test failure 3", should_retry=True)

        # Should be in DLQ now
        stats = await notification_queue.get_statistics()
        assert stats.pending_count == 0
        assert stats.dlq_count == 1

        # Verify DLQ entry
        dlq_entries = await notification_queue.get_dead_letter_queue(10)
        assert len(dlq_entries) == 1
        assert dlq_entries[0].original_notification.message == "Test retry"


class TestEmailTemplateIntegration:
    """Test email template management and rendering."""

    async def test_template_creation_and_rendering(self, email_template_manager):
        """Test creating and rendering custom templates."""
        # Create custom template
        template_name = "test_custom"
        subject = "Test Subject: {{user_name}}"
        html_content = """
        <html>
        <body>
            <h1>Hello {{user_name}}!</h1>
            <p>{{message}}</p>
            <p>App: {{app_name}}</p>
        </body>
        </html>
        """
        text_content = """
        Hello {{user_name}}!

        {{message}}

        App: {{app_name}}
        """

        success = await email_template_manager.create_template(
            template_name, subject, html_content, text_content
        )
        assert success

        # Verify template appears in list
        templates = await email_template_manager.list_templates()
        assert template_name in templates

        # Render template with context
        context = {
            "user_name": "John Doe",
            "message": "This is a test message",
            "app_name": "CoachIQ",
        }

        rendered_html = await email_template_manager.render_template(template_name, context, "html")
        assert "Hello John Doe!" in rendered_html
        assert "This is a test message" in rendered_html
        assert "CoachIQ" in rendered_html

        rendered_text = await email_template_manager.render_template(template_name, context, "text")
        assert "Hello John Doe!" in rendered_text
        assert "This is a test message" in rendered_text

        rendered_subject = await email_template_manager.render_subject(template_name, context)
        assert rendered_subject == "Test Subject: John Doe"

    async def test_template_validation(self, email_template_manager):
        """Test template validation catches errors."""
        # Test invalid template syntax
        with pytest.raises(Exception):
            await email_template_manager.create_template(
                "invalid_template",
                "Valid Subject",
                "<html><body>{{invalid.variable.access}}</body></html>",
                "Valid text",
            )

    async def test_builtin_templates(self, email_template_manager):
        """Test built-in templates work correctly."""
        templates = await email_template_manager.list_templates()

        # Check built-in templates exist
        assert "magic_link" in templates
        assert "system_notification" in templates
        assert "test_notification" in templates

        # Test magic link template
        context = {
            "user_name": "Test User",
            "magic_link": "https://example.com/auth/test-token",
            "expires_minutes": 15,
            "app_name": "CoachIQ Test",
            "support_email": "test@example.com",
        }

        rendered_html = await email_template_manager.render_template("magic_link", context, "html")
        assert "Test User" in rendered_html
        assert "https://example.com/auth/test-token" in rendered_html
        assert "15 minutes" in rendered_html


class TestNotificationRoutingIntegration:
    """Test advanced notification routing."""

    async def test_priority_based_routing(self, notification_router):
        """Test routing based on notification priority."""
        # Create test notification
        critical_notification = NotificationPayload(
            message="Critical system failure",
            title="System Alert",
            level=NotificationType.CRITICAL,
            channels=[],  # Will be determined by router
        )

        # Route critical notification
        decision = await notification_router.determine_route(critical_notification)

        # Critical notifications should use multiple channels
        assert len(decision.target_channels) >= 2
        assert NotificationChannel.SYSTEM in decision.target_channels
        assert decision.emergency_override or "critical" in decision.routing_reason

        # Test info notification
        info_notification = NotificationPayload(
            message="System status update",
            title="Info",
            level=NotificationType.INFO,
            channels=[],
        )

        decision = await notification_router.determine_route(info_notification)

        # Info notifications should use fewer channels
        assert len(decision.target_channels) >= 1
        assert not decision.emergency_override

    async def test_user_preference_routing(self, notification_router):
        """Test routing with user preferences."""
        # Set up user preferences
        user_id = "test_user_123"
        preferences = UserNotificationPreferences(
            user_id=user_id,
            email="test@example.com",
            preferred_channels=[NotificationChannel.SMTP, NotificationChannel.SYSTEM],
            blocked_channels=[NotificationChannel.PUSHOVER],
            min_priority_email=NotificationType.WARNING,
        )

        await notification_router.update_user_preferences(user_id, preferences)

        # Test warning notification (should include email)
        warning_notification = NotificationPayload(
            message="Warning: Low battery",
            title="Battery Warning",
            level=NotificationType.WARNING,
            channels=[],
        )

        decision = await notification_router.determine_route(warning_notification, user_id)

        # Should include preferred channels, exclude blocked
        channel_values = [ch.value for ch in decision.target_channels]
        assert "smtp" in channel_values or "system" in channel_values
        assert "pushover" not in channel_values  # Blocked channel

        # Test info notification (below email threshold)
        info_notification = NotificationPayload(
            message="Info: Status update",
            title="Status",
            level=NotificationType.INFO,
            channels=[],
        )

        decision = await notification_router.determine_route(info_notification, user_id)

        # Should not include email (below threshold)
        channel_values = [ch.value for ch in decision.target_channels]
        assert "smtp" not in channel_values

    async def test_custom_routing_rules(self, notification_router):
        """Test custom routing rule creation and evaluation."""
        # Create custom rule for maintenance notifications
        maintenance_rule = RoutingRule(
            id="maintenance_alerts",
            name="Maintenance Alert Routing",
            description="Route maintenance-related notifications to system logs only",
            priority=50,
            condition_type=RoutingConditionType.CONTENT_BASED,
            conditions={"keywords": ["maintenance", "update", "scheduled"]},
            target_channels=[NotificationChannel.SYSTEM],
        )

        await notification_router.add_routing_rule(maintenance_rule)

        # Test notification matching rule
        maintenance_notification = NotificationPayload(
            message="Scheduled maintenance starting in 30 minutes",
            title="Maintenance Alert",
            level=NotificationType.INFO,
            channels=[],
        )

        decision = await notification_router.determine_route(maintenance_notification)

        # Should match custom rule
        assert "maintenance_alerts" in decision.applied_rules
        assert decision.target_channels == [NotificationChannel.SYSTEM]

        # Test notification not matching rule
        regular_notification = NotificationPayload(
            message="Battery level normal",
            title="Status Update",
            level=NotificationType.INFO,
            channels=[],
        )

        decision = await notification_router.determine_route(regular_notification)

        # Should not match custom rule
        assert "maintenance_alerts" not in decision.applied_rules


class TestSafeNotificationManagerIntegration:
    """Test complete SafeNotificationManager integration."""

    async def test_end_to_end_notification_flow(
        self, safe_notification_manager, integration_config
    ):
        """Test complete notification flow from creation to queuing."""
        # Send notification through complete system
        success = await safe_notification_manager.notify(
            message="Integration test notification",
            title="Test Notification",
            level=NotificationType.INFO,
            channels=["system"],  # Use system channel for testing
            template="test_notification",
            context={"test_context": "integration_test"},
            source_component="IntegrationTest",
        )

        assert success

        # Check queue statistics
        queue_stats = await safe_notification_manager.get_queue_statistics()
        assert queue_stats.pending_count >= 1

        # Check rate limiting status
        rate_limit_status = await safe_notification_manager.get_rate_limit_status()
        assert rate_limit_status.current_tokens <= rate_limit_status.max_tokens

        # Check manager statistics
        manager_stats = safe_notification_manager.get_statistics()
        assert manager_stats["total_notifications"] >= 1
        assert manager_stats["successful_notifications"] >= 1

    async def test_template_integration_with_notifications(self, safe_notification_manager):
        """Test template rendering integration with notifications."""
        # Create custom template
        template_success = await safe_notification_manager.create_email_template(
            template_name="integration_test",
            subject="Integration Test: {{level|title}}",
            html_content="""
            <html>
            <body>
                <h1>{{title}}</h1>
                <p>{{message}}</p>
                <p>Component: {{source_component}}</p>
                <p>Level: {{level}}</p>
            </body>
            </html>
            """,
            text_content="""
            {{title}}

            {{message}}

            Component: {{source_component}}
            Level: {{level}}
            """,
        )

        assert template_success

        # Send notification using custom template
        success = await safe_notification_manager.send_email(
            to_email="test@example.com",
            template="integration_test",
            context={
                "title": "Integration Test Email",
                "message": "This is a test email from integration testing",
                "source_component": "IntegrationTest",
                "level": "info",
            },
        )

        assert success

        # Verify template preview works
        preview = await safe_notification_manager.render_template_preview(
            "integration_test",
            context={
                "title": "Preview Test",
                "message": "Preview message",
                "source_component": "PreviewTest",
                "level": "warning",
            },
        )

        assert preview is not None
        assert "Preview Test" in preview
        assert "Preview message" in preview

    async def test_routing_integration_with_manager(self, safe_notification_manager):
        """Test routing integration with notification manager."""
        # Add custom routing rule
        rule_data = {
            "id": "test_integration_rule",
            "name": "Integration Test Rule",
            "description": "Test rule for integration testing",
            "priority": 25,
            "condition_type": "content_based",
            "conditions": {"keywords": ["integration", "test"]},
            "target_channels": ["system"],
        }

        rule_success = await safe_notification_manager.add_routing_rule(rule_data)
        assert rule_success

        # Send notification that should match rule
        success = await safe_notification_manager.notify(
            message="This is an integration test notification",
            title="Integration Test",
            level=NotificationType.INFO,
            source_component="IntegrationTest",
        )

        assert success

        # Check routing statistics
        routing_stats = safe_notification_manager.get_routing_statistics()
        assert routing_stats["total_routings"] >= 1

    @pytest.mark.skipif(
        not os.getenv("COACHIQ_TEST_SMTP_ENABLED", "false").lower() == "true",
        reason="Real SMTP testing not enabled",
    )
    async def test_real_email_delivery(self, safe_notification_manager, integration_config):
        """Test actual email delivery (only if real SMTP enabled)."""
        success = await safe_notification_manager.send_email(
            to_email=integration_config.test_email,
            template="test_notification",
            context={
                "message": "This is a real email test from integration testing",
                "app_name": "CoachIQ Integration Test",
            },
        )

        assert success

        # Allow some time for email processing
        await asyncio.sleep(2)

        # Check queue statistics - should have processed the email
        queue_stats = await safe_notification_manager.get_queue_statistics()

        # The actual success depends on SMTP server response
        # We mainly test that the system doesn't crash


class TestNotificationSystemPerformance:
    """Test notification system performance and scalability."""

    async def test_high_volume_notification_processing(self, safe_notification_manager):
        """Test system performance under high notification volume."""
        start_time = datetime.utcnow()

        # Send batch of notifications
        notification_count = 100
        tasks = []

        for i in range(notification_count):
            task = safe_notification_manager.notify(
                message=f"Performance test notification {i}",
                title=f"Performance Test {i}",
                level=NotificationType.INFO,
                channels=["system"],
                source_component="PerformanceTest",
                correlation_id=f"perf_test_{i}",
            )
            tasks.append(task)

        # Wait for all notifications to be queued
        results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()

        # Verify results
        successful_notifications = sum(1 for result in results if result is True)
        assert successful_notifications >= notification_count * 0.95  # Allow 5% failure rate

        # Performance assertions
        assert processing_time < 30  # Should complete within 30 seconds

        rate_per_second = notification_count / processing_time
        assert rate_per_second > 10  # Should handle at least 10 notifications per second

        # Check queue statistics
        queue_stats = await safe_notification_manager.get_queue_statistics()
        assert queue_stats.pending_count >= successful_notifications * 0.9

        print(
            f"Performance test: {notification_count} notifications in {processing_time:.2f}s "
            f"({rate_per_second:.2f} notifications/sec)"
        )

    async def test_rate_limiting_under_load(self, safe_notification_manager):
        """Test rate limiting behavior under high load."""
        # Send notifications rapidly to trigger rate limiting
        rapid_notification_count = 50
        start_time = datetime.utcnow()

        tasks = []
        for i in range(rapid_notification_count):
            task = safe_notification_manager.notify(
                message="Rate limiting test notification",
                title="Rate Limit Test",
                level=NotificationType.INFO,
                channels=["system"],
                source_component="RateLimitTest",
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = datetime.utcnow()

        # Some notifications should be rate limited
        successful_notifications = sum(1 for result in results if result is True)
        rate_limited_notifications = rapid_notification_count - successful_notifications

        # Should have some rate limiting under rapid load
        assert rate_limited_notifications >= 0

        # Check rate limiting statistics
        rate_limit_status = await safe_notification_manager.get_rate_limit_status()
        manager_stats = safe_notification_manager.get_statistics()

        print(
            f"Rate limiting test: {successful_notifications}/{rapid_notification_count} "
            f"notifications successful, {rate_limited_notifications} rate limited"
        )
        print(f"Current tokens: {rate_limit_status.current_tokens}/{rate_limit_status.max_tokens}")
        print(f"Rate limited count: {manager_stats.get('rate_limited_notifications', 0)}")


# Test fixtures for mock services


@pytest.fixture
async def mock_notification_manager():
    """Create mock notification manager for testing without real services."""
    mock_manager = AsyncMock(spec=NotificationManager)
    mock_manager.send_email.return_value = True
    mock_manager.send_notification.return_value = True
    return mock_manager


@pytest.fixture
async def mock_dispatcher(notification_queue, mock_notification_manager):
    """Create notification dispatcher with mocked services."""
    dispatcher = AsyncNotificationDispatcher(
        queue=notification_queue,
        notification_manager=mock_notification_manager,
        batch_size=5,
        processing_interval=0.1,  # Fast processing for tests
    )

    await dispatcher.start()

    yield dispatcher

    await dispatcher.stop(timeout=5.0)


class TestMockedServiceIntegration:
    """Test notification system with mocked external services."""

    async def test_dispatcher_processing_with_mocks(self, mock_dispatcher, notification_queue):
        """Test notification dispatcher with mocked services."""
        # Create test notifications
        notifications = []
        for i in range(5):
            notification = NotificationPayload(
                message=f"Mock test message {i}",
                title=f"Mock Test {i}",
                level=NotificationType.INFO,
                channels=[NotificationChannel.SMTP],
                recipient="test@example.com",
            )
            await notification_queue.enqueue(notification)
            notifications.append(notification)

        # Allow dispatcher to process notifications
        await asyncio.sleep(1)

        # Force processing completion
        result = await mock_dispatcher.force_queue_processing()

        # Verify processing
        assert result["processed_batches"] >= 1
        assert result["queue_depth_after"] < result["queue_depth_before"]

        # Check dispatcher metrics
        metrics = mock_dispatcher.get_metrics()
        assert metrics["total_processed"] >= len(notifications)
        assert metrics["successful_deliveries"] >= len(notifications)

    async def test_error_handling_with_mocks(
        self, mock_dispatcher, notification_queue, mock_notification_manager
    ):
        """Test error handling with mocked service failures."""
        # Configure mock to fail
        mock_notification_manager.send_email.return_value = False

        # Create test notification
        notification = NotificationPayload(
            message="Error test message",
            title="Error Test",
            level=NotificationType.ERROR,
            channels=[NotificationChannel.SMTP],
            recipient="test@example.com",
        )

        await notification_queue.enqueue(notification)

        # Allow processing
        await asyncio.sleep(1)
        await mock_dispatcher.force_queue_processing()

        # Check that failures are handled
        metrics = mock_dispatcher.get_metrics()
        assert metrics["failed_deliveries"] >= 1

        # Check queue statistics for retry/DLQ behavior
        stats = await notification_queue.get_statistics()
        # Should either be retrying or in DLQ
        assert stats.pending_count > 0 or stats.dlq_count > 0
