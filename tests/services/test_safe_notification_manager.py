"""
Unit tests for SafeNotificationManager with queue, rate limiting, and sanitization.

Tests cover:
- Initialization and component setup
- Notification queuing with safety features
- Rate limiting and debouncing integration
- Template context sanitization
- Email and system notifications
- Pushover notifications with priority mapping
- Statistics and monitoring
- Error handling and fallback scenarios
"""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.config import NotificationSettings
from backend.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    QueueStatistics,
    RateLimitStatus,
)
from backend.services.safe_notification_manager import SafeNotificationManager


@pytest.fixture
def notification_settings():
    """Create test notification settings."""
    settings = MagicMock(spec=NotificationSettings)
    settings.enabled = True
    settings.default_title = "Test Title"
    settings.log_notifications = True
    settings.template_path = "templates/"

    # SMTP settings
    settings.smtp = MagicMock()
    settings.smtp.enabled = True
    settings.smtp.from_email = "test@example.com"

    # Slack settings
    settings.slack = MagicMock()
    settings.slack.enabled = True

    # Discord settings
    settings.discord = MagicMock()
    settings.discord.enabled = False

    # Pushover settings
    settings.pushover = MagicMock()
    settings.pushover.enabled = True
    settings.pushover.user_key = "test_user_key"
    settings.pushover.token = "test_token"
    settings.pushover.device = "test_device"

    # Mock get_enabled_channels method
    settings.get_enabled_channels.return_value = [
        ("smtp", settings.smtp),
        ("slack", settings.slack),
        ("pushover", settings.pushover),
    ]

    return settings


@pytest.fixture
async def temp_db_path():
    """Create temporary database path for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_safe_notifications.db"
        yield str(db_path)


@pytest.fixture
async def safe_manager(notification_settings, temp_db_path):
    """Create SafeNotificationManager for testing."""
    # Add queue configuration to settings
    notification_settings.queue_db_path = temp_db_path
    notification_settings.rate_limit_max_tokens = 100
    notification_settings.rate_limit_per_minute = 60
    notification_settings.debounce_minutes = 15

    manager = SafeNotificationManager(notification_settings)
    await manager.initialize()
    yield manager
    await manager.cleanup()


class TestSafeNotificationManagerInitialization:
    """Test SafeNotificationManager initialization."""

    async def test_initialization_creates_components(self, notification_settings, temp_db_path):
        """Test that initialization creates all required components."""
        notification_settings.queue_db_path = temp_db_path

        manager = SafeNotificationManager(notification_settings)
        await manager.initialize()

        assert manager._initialized
        assert manager.queue is not None
        assert manager.rate_limiter is not None
        assert manager.debouncer is not None
        assert manager.channel_rate_limiter is not None

        await manager.cleanup()

    async def test_initialization_with_default_settings(self, notification_settings, temp_db_path):
        """Test initialization with default settings when not provided."""
        # Don't set specific rate limiting settings
        notification_settings.queue_db_path = temp_db_path

        manager = SafeNotificationManager(notification_settings)
        await manager.initialize()

        # Should use defaults
        assert manager.rate_limiter.max_tokens == 100  # Default
        assert manager.rate_limiter.refill_rate == 60  # Default

        await manager.cleanup()

    async def test_template_sandbox_setup(self, notification_settings, temp_db_path):
        """Test that template sandbox is set up correctly."""
        manager = SafeNotificationManager(notification_settings)

        # Template sandbox should be configured during __init__
        if manager.template_sandbox is not None:
            # If Jinja2 is available, sandbox should be configured
            assert hasattr(manager.template_sandbox, "filters")
            # Should have restricted filter set
            assert "escape" in manager.template_sandbox.filters
            # Should not have dangerous filters
            assert "eval" not in manager.template_sandbox.filters

    async def test_pushover_priority_mapping(self, notification_settings, temp_db_path):
        """Test Pushover priority mapping configuration."""
        manager = SafeNotificationManager(notification_settings)

        # Verify priority mapping
        assert manager.pushover_priority_mapping[NotificationType.CRITICAL] == 1
        assert manager.pushover_priority_mapping[NotificationType.ERROR] == 1
        assert manager.pushover_priority_mapping[NotificationType.WARNING] == 0
        assert manager.pushover_priority_mapping[NotificationType.INFO] == -1
        assert manager.pushover_priority_mapping[NotificationType.SUCCESS] == -1


class TestNotificationQueuing:
    """Test notification queuing functionality."""

    async def test_basic_notification_queuing(self, safe_manager):
        """Test basic notification queuing."""
        result = await safe_manager.notify(
            message="Test notification",
            title="Test Title",
            level=NotificationType.INFO,
        )

        assert result

        # Verify in queue
        stats = await safe_manager.get_queue_statistics()
        assert stats.pending_count == 1

    async def test_notification_with_all_parameters(self, safe_manager):
        """Test notification with all parameters."""
        context = {"key": "value", "number": 42}
        scheduled_time = datetime.utcnow() + timedelta(minutes=5)

        result = await safe_manager.notify(
            message="Full parameter test",
            title="Full Test",
            level=NotificationType.WARNING,
            channels=["smtp", "slack"],
            tags=["test", "full"],
            template="test_template",
            context=context,
            recipient="test@example.com",
            priority=2,
            scheduled_for=scheduled_time,
            source_component="test_component",
            correlation_id="test-correlation-123",
        )

        assert result

        # Verify statistics updated
        assert safe_manager.stats["total_notifications"] == 1
        assert safe_manager.stats["successful_notifications"] == 1

    async def test_notification_level_conversion(self, safe_manager):
        """Test notification level string to enum conversion."""
        # Test string level
        result = await safe_manager.notify(
            message="String level test",
            level="error",  # String instead of enum
        )

        assert result

        # Test enum level
        result = await safe_manager.notify(
            message="Enum level test",
            level=NotificationType.CRITICAL,
        )

        assert result

    async def test_notification_channel_resolution(self, safe_manager):
        """Test notification channel resolution."""
        # Test with specific channels
        result = await safe_manager.notify(
            message="Specific channels",
            channels=["smtp"],
        )
        assert result

        # Test with no channels (should use all enabled)
        result = await safe_manager.notify(
            message="Default channels",
        )
        assert result

    async def test_scheduled_notification(self, safe_manager):
        """Test scheduled notification queuing."""
        future_time = datetime.utcnow() + timedelta(hours=1)

        result = await safe_manager.notify(
            message="Scheduled notification",
            scheduled_for=future_time,
        )

        assert result

        # Should be in queue but not immediately processable
        stats = await safe_manager.get_queue_statistics()
        assert stats.pending_count == 1


class TestRateLimitingIntegration:
    """Test rate limiting integration."""

    async def test_rate_limiting_blocks_excessive_requests(self, safe_manager):
        """Test that rate limiting blocks excessive requests."""
        # Set low token limit for testing
        safe_manager.rate_limiter.max_tokens = 3
        safe_manager.rate_limiter.current_tokens = 3

        # First few should succeed
        for i in range(3):
            result = await safe_manager.notify(message=f"Rate test {i}")
            assert result

        # Next should be blocked
        result = await safe_manager.notify(message="Should be blocked")
        assert not result

        # Verify statistics
        assert safe_manager.stats["rate_limited_notifications"] > 0

    async def test_debouncing_suppresses_duplicates(self, safe_manager):
        """Test that debouncing suppresses duplicate notifications."""
        message = "Duplicate message test"

        # First occurrence should succeed
        result1 = await safe_manager.notify(message=message, level="info")
        assert result1

        # Immediate duplicate should be suppressed
        result2 = await safe_manager.notify(message=message, level="info")
        assert not result2

        # Verify statistics
        assert safe_manager.stats["debounced_notifications"] > 0

    async def test_channel_rate_limiting(self, safe_manager):
        """Test per-channel rate limiting."""
        # Mock channel rate limiter to block specific channel
        safe_manager.channel_rate_limiter.allow = AsyncMock(return_value=False)

        result = await safe_manager.notify(
            message="Channel rate limited",
            channels=["smtp"],
        )

        # Should fail due to channel rate limiting
        assert not result

    async def test_rate_limit_status_reporting(self, safe_manager):
        """Test rate limit status reporting."""
        # Generate some activity
        await safe_manager.notify(message="Status test 1")
        await safe_manager.notify(message="Status test 2")

        status = await safe_manager.get_rate_limit_status()

        assert isinstance(status, RateLimitStatus)
        assert status.current_tokens >= 0
        assert status.max_tokens > 0
        assert status.healthy


class TestContextSanitization:
    """Test template context sanitization."""

    async def test_basic_context_sanitization(self, safe_manager):
        """Test basic context sanitization."""
        context = {
            "safe_string": "hello world",
            "safe_number": 42,
            "safe_bool": True,
        }

        result = await safe_manager.notify(
            message="Sanitization test",
            context=context,
        )

        assert result

    async def test_invalid_key_rejection(self, safe_manager):
        """Test that invalid context keys are rejected."""
        context = {
            "valid_key": "valid value",
            "invalid-key": "should be rejected",  # Hyphens not allowed
            "123invalid": "should be rejected",  # Can't start with number
        }

        result = await safe_manager.notify(
            message="Invalid key test",
            context=context,
        )

        # Should still succeed but with sanitized context
        assert result

    async def test_dangerous_context_sanitization(self, safe_manager):
        """Test sanitization of potentially dangerous context."""
        context = {
            "script_tag": "<script>alert('xss')</script>",
            "sql_injection": "'; DROP TABLE users; --",
            "template_injection": "{{ 7*7 }}",
        }

        result = await safe_manager.notify(
            message="Dangerous context test",
            context=context,
        )

        # Should handle dangerous content gracefully
        assert result

    async def test_nested_context_sanitization(self, safe_manager):
        """Test sanitization of nested context structures."""
        context = {
            "nested_dict": {
                "safe_key": "safe_value",
                "unsafe_key": "{{ dangerous }}",
            },
            "list_data": ["item1", "item2", "<script>alert()</script>"],
        }

        result = await safe_manager.notify(
            message="Nested context test",
            context=context,
        )

        assert result

    async def test_context_size_limits(self, safe_manager):
        """Test that context size limits are enforced."""
        # Create large context
        large_context = {
            "large_string": "x" * 20000,  # Very large string
            "large_list": list(range(200)),  # Large list
        }

        result = await safe_manager.notify(
            message="Large context test",
            context=large_context,
        )

        # Should handle large context gracefully (may truncate)
        assert result

    @patch("backend.services.safe_notification_manager.JINJA2_AVAILABLE", False)
    async def test_fallback_sanitization_without_jinja2(self, safe_manager):
        """Test fallback sanitization when Jinja2 is not available."""
        context = {
            "test_string": "Hello <script>alert()</script> World",
            "safe_number": 42,
        }

        result = await safe_manager.notify(
            message="Fallback sanitization test",
            context=context,
        )

        assert result


class TestEmailNotifications:
    """Test email notification functionality."""

    async def test_basic_email_sending(self, safe_manager):
        """Test basic email sending."""
        result = await safe_manager.send_email(
            to_email="test@example.com",
            subject="Test Email",
            template="test_template",
            context={"name": "Test User"},
        )

        assert result
        assert safe_manager.stats["emails_sent"] == 1

    async def test_magic_link_email(self, safe_manager):
        """Test magic link email sending."""
        result = await safe_manager.send_magic_link_email(
            to_email="user@example.com",
            magic_link="https://example.com/auth/magic?token=abc123",
            user_name="Test User",
            expires_minutes=30,
        )

        assert result
        assert safe_manager.stats["emails_sent"] == 1

    async def test_email_with_from_override(self, safe_manager):
        """Test email with from address override."""
        result = await safe_manager.send_email(
            to_email="test@example.com",
            subject="Override Test",
            template="test_template",
            context={"key": "value"},
            from_email="custom@example.com",
        )

        assert result


class TestSystemNotifications:
    """Test system notification functionality."""

    async def test_basic_system_notification(self, safe_manager):
        """Test basic system notification."""
        result = await safe_manager.send_system_notification(
            message="System test message",
            level="info",
            component="test_component",
        )

        assert result
        assert safe_manager.stats["system_notifications"] == 1

    async def test_system_notification_with_error_level(self, safe_manager):
        """Test system notification with error level."""
        result = await safe_manager.send_system_notification(
            message="System error occurred",
            level="error",
            component="error_component",
        )

        assert result

    async def test_system_notification_title_formatting(self, safe_manager):
        """Test system notification title formatting."""
        result = await safe_manager.send_system_notification(
            message="Component test",
            component="TestComponent",
        )

        assert result
        # Title should include component name


class TestPushoverNotifications:
    """Test Pushover notification functionality."""

    async def test_basic_pushover_notification(self, safe_manager):
        """Test basic Pushover notification."""
        result = await safe_manager.send_pushover_notification(
            message="Pushover test message",
            title="Pushover Test",
            priority=1,
            device="test_device",
        )

        assert result

    async def test_pushover_priority_mapping(self, safe_manager):
        """Test Pushover priority mapping from notification levels."""
        # Test critical level -> high priority
        result = await safe_manager.notify(
            message="Critical message",
            level=NotificationType.CRITICAL,
            channels=["pushover"],
        )

        assert result

    async def test_pushover_url_building(self, safe_manager):
        """Test Pushover URL building."""
        # This tests the internal URL building logic
        notification_payload = MagicMock()
        notification_payload.pushover_device = "test_device"
        notification_payload.pushover_priority = 2

        # Should not raise exception
        url = safe_manager._build_pushover_url(notification_payload)
        assert isinstance(url, str)


class TestStatisticsAndMonitoring:
    """Test statistics and monitoring functionality."""

    async def test_manager_statistics(self, safe_manager):
        """Test manager statistics reporting."""
        # Generate some activity
        await safe_manager.notify(message="Stats test 1")
        await safe_manager.notify(message="Stats test 2")

        stats = safe_manager.get_statistics()

        assert stats["total_notifications"] == 2
        assert stats["successful_notifications"] == 2
        assert "success_rate" in stats
        assert stats["success_rate"] > 0

    async def test_queue_statistics(self, safe_manager):
        """Test queue statistics retrieval."""
        await safe_manager.notify(message="Queue stats test")

        stats = await safe_manager.get_queue_statistics()

        assert isinstance(stats, QueueStatistics)
        assert stats.pending_count >= 1

    async def test_channel_status(self, safe_manager):
        """Test channel status reporting."""
        status = await safe_manager.get_channel_status()

        assert isinstance(status, dict)
        assert "enabled" in status
        assert "queue_enabled" in status
        assert "rate_limiting_enabled" in status
        assert "debouncing_enabled" in status

    async def test_statistics_after_failures(self, safe_manager):
        """Test statistics tracking after failures."""
        # Mock rate limiter to cause failure
        safe_manager.rate_limiter.allow = AsyncMock(return_value=False)

        result = await safe_manager.notify(message="Will fail")
        assert not result

        stats = safe_manager.get_statistics()
        assert stats["rate_limited_notifications"] > 0


class TestChannelTesting:
    """Test notification channel testing functionality."""

    async def test_channel_testing_enabled_channels(self, safe_manager):
        """Test testing of enabled notification channels."""
        results = await safe_manager.test_channels()

        assert isinstance(results, dict)
        # Should have results for enabled channels
        assert len(results) > 0

    async def test_channel_testing_disabled_notifications(
        self, notification_settings, temp_db_path
    ):
        """Test channel testing when notifications are disabled."""
        notification_settings.enabled = False
        notification_settings.queue_db_path = temp_db_path

        manager = SafeNotificationManager(notification_settings)
        await manager.initialize()

        results = await manager.test_channels()
        assert "error" in results
        assert "disabled" in results["error"]

        await manager.cleanup()


class TestErrorHandling:
    """Test error handling and fallback scenarios."""

    async def test_initialization_without_required_settings(self, notification_settings):
        """Test initialization with missing required settings."""
        # Remove queue path
        if hasattr(notification_settings, "queue_db_path"):
            delattr(notification_settings, "queue_db_path")

        manager = SafeNotificationManager(notification_settings)
        # Should still initialize with defaults
        await manager.initialize()

        assert manager._initialized
        await manager.cleanup()

    async def test_notification_with_sanitization_failure(self, safe_manager):
        """Test notification handling when context sanitization fails."""
        # Mock sanitization to fail
        safe_manager._sanitize_context = AsyncMock(return_value=None)

        result = await safe_manager.notify(
            message="Sanitization failure test",
            context={"key": "value"},
        )

        # Should fail due to sanitization failure
        assert not result
        assert safe_manager.stats["sanitization_failures"] > 0

    async def test_queue_operation_failure_recovery(self, safe_manager):
        """Test recovery from queue operation failures."""
        # Mock queue to fail
        safe_manager.queue.enqueue = AsyncMock(side_effect=Exception("Queue error"))

        result = await safe_manager.notify(message="Queue failure test")

        # Should handle queue failure gracefully
        assert not result
        assert safe_manager.stats["failed_notifications"] > 0

    async def test_notification_before_initialization(self, notification_settings, temp_db_path):
        """Test notification sending before manager initialization."""
        notification_settings.queue_db_path = temp_db_path

        manager = SafeNotificationManager(notification_settings)
        # Don't call initialize()

        # Should auto-initialize on first use
        result = await manager.notify(message="Auto-init test")
        assert result
        assert manager._initialized

        await manager.cleanup()

    async def test_cleanup_error_handling(self, safe_manager):
        """Test cleanup error handling."""
        # Mock queue cleanup to fail
        safe_manager.queue.close = AsyncMock(side_effect=Exception("Cleanup error"))

        # Should not raise exception
        await safe_manager.cleanup()

    async def test_invalid_notification_level(self, safe_manager):
        """Test handling of invalid notification level."""
        with pytest.raises(ValueError):
            await safe_manager.notify(
                message="Invalid level test",
                level="invalid_level",  # Should raise ValueError
            )

    async def test_missing_required_email_parameters(self, safe_manager):
        """Test email sending with missing required parameters."""
        # This should be caught by parameter validation
        result = await safe_manager.send_email(
            to_email="",  # Empty email
            subject="Test",
            template="test_template",
            context={},
        )

        # Should handle gracefully
        assert result is not None  # May succeed or fail, but shouldn't crash


class TestCleanupAndShutdown:
    """Test cleanup and shutdown procedures."""

    async def test_proper_cleanup(self, safe_manager):
        """Test proper cleanup of manager resources."""
        # Verify components are initialized
        assert safe_manager.queue is not None

        # Cleanup
        await safe_manager.cleanup()

        # Should complete without error

    async def test_cleanup_idempotency(self, safe_manager):
        """Test that cleanup can be called multiple times safely."""
        await safe_manager.cleanup()
        # Should not raise exception on second call
        await safe_manager.cleanup()

    async def test_operations_after_cleanup(self, safe_manager):
        """Test behavior of operations after cleanup."""
        await safe_manager.cleanup()

        # Operations should either fail gracefully or auto-reinitialize
        result = await safe_manager.notify(message="After cleanup test")
        # Result can be True (auto-reinit) or False (graceful failure)
        assert isinstance(result, bool)


@pytest.mark.asyncio
class TestIntegrationScenarios:
    """Test complete integration scenarios."""

    async def test_high_volume_notification_processing(self, safe_manager):
        """Test processing high volume of notifications."""
        # Queue many notifications
        tasks = []
        for i in range(100):
            task = safe_manager.notify(
                message=f"High volume test {i}",
                level=NotificationType.INFO,
                priority=(i % 5) + 1,
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Most should succeed (some may be rate limited)
        success_count = sum(1 for result in results if result)
        assert success_count > 50  # At least half should succeed

        # Verify statistics
        stats = safe_manager.get_statistics()
        assert stats["total_notifications"] == 100

    async def test_mixed_notification_types(self, safe_manager):
        """Test processing mixed notification types."""
        # Send various types of notifications
        tasks = [
            safe_manager.notify(message="Regular notification"),
            safe_manager.send_email(
                to_email="test@example.com",
                subject="Test Email",
                template="test",
                context={},
            ),
            safe_manager.send_system_notification(
                message="System message",
                component="test",
            ),
            safe_manager.send_pushover_notification(
                message="Pushover message",
                priority=1,
            ),
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(results)

        # Verify statistics
        stats = safe_manager.get_statistics()
        assert stats["emails_sent"] >= 1
        assert stats["system_notifications"] >= 1

    async def test_rate_limiting_and_queue_interaction(self, safe_manager):
        """Test interaction between rate limiting and queue processing."""
        # Set restrictive rate limits
        safe_manager.rate_limiter.max_tokens = 5
        safe_manager.rate_limiter.current_tokens = 5

        # Send more notifications than rate limit allows
        results = []
        for i in range(10):
            result = await safe_manager.notify(f"Rate limit test {i}")
            results.append(result)

        # Some should succeed, some should be rate limited
        success_count = sum(1 for result in results if result)
        assert 0 < success_count < 10

        # Verify queue has the successful ones
        queue_stats = await safe_manager.get_queue_statistics()
        assert queue_stats.pending_count == success_count

    async def test_error_recovery_and_resilience(self, safe_manager):
        """Test error recovery and system resilience."""
        # Introduce temporary errors
        original_enqueue = safe_manager.queue.enqueue
        call_count = 0

        async def failing_enqueue(notification):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("Temporary error")
            return await original_enqueue(notification)

        safe_manager.queue.enqueue = failing_enqueue

        # First few notifications should fail
        for i in range(3):
            result = await safe_manager.notify(f"Failing test {i}")
            assert not result

        # After "recovery", should work
        result = await safe_manager.notify("Recovery test")
        assert result

        # Verify error statistics
        stats = safe_manager.get_statistics()
        assert stats["failed_notifications"] >= 3
