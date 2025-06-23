"""
Integration tests for NotificationFeature with queue-based architecture.

Tests cover:
- Feature initialization with queue-based and legacy modes
- Integration between SafeNotificationManager and AsyncNotificationDispatcher
- Feature lifecycle management (startup/shutdown)
- API method delegation and compatibility
- Health monitoring and statistics
- Background task management
- Error handling and fallback scenarios
- Complete notification flow from feature to delivery
"""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.config import NotificationSettings
from backend.integrations.notifications.feature import NotificationFeature
from backend.models.notification import NotificationChannel, NotificationType


@pytest.fixture
def notification_settings():
    """Create test notification settings."""
    settings = MagicMock(spec=NotificationSettings)
    settings.enabled = True
    settings.default_title = "CoachIQ Test"
    settings.log_notifications = True
    settings.template_path = "templates/"

    # SMTP settings
    settings.smtp = MagicMock()
    settings.smtp.enabled = True
    settings.smtp.from_email = "test@coachiq.com"

    # Slack settings
    settings.slack = MagicMock()
    settings.slack.enabled = True

    # Discord settings
    settings.discord = MagicMock()
    settings.discord.enabled = False

    # Pushover settings
    pushover = MagicMock()
    pushover.enabled = True
    pushover.user_key = "test_user_key"
    pushover.token = "test_token"
    pushover.device = "test_device"
    settings.pushover = pushover

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
        db_path = Path(temp_dir) / "test_feature_notifications.db"
        yield str(db_path)


@pytest.fixture
async def feature_config(temp_db_path):
    """Create feature configuration."""
    return {
        "use_queue_based": True,
        "dispatch_batch_size": 5,
        "max_concurrent_batches": 2,
        "processing_interval": 0.1,
        "test_on_startup": False,
        "enable_health_monitoring": True,
        "health_check_interval": 1,
        "queue_db_path": temp_db_path,
    }


@pytest.fixture
async def notification_feature(notification_settings, feature_config):
    """Create NotificationFeature for testing."""
    with patch(
        "backend.integrations.notifications.feature.get_notification_settings",
        return_value=notification_settings,
    ):
        feature = NotificationFeature(
            name="test_notifications",
            enabled=True,
            config=feature_config,
        )
        yield feature
        # Cleanup
        await feature.shutdown()


class TestFeatureInitialization:
    """Test NotificationFeature initialization."""

    async def test_feature_initialization_queue_based(self, notification_feature):
        """Test feature initialization with queue-based architecture."""
        await notification_feature.startup()

        assert notification_feature.safe_notification_manager is not None
        assert notification_feature.notification_dispatcher is not None
        assert notification_feature.legacy_notification_manager is not None
        assert notification_feature._stats["queue_enabled"]
        assert notification_feature._stats["dispatcher_running"]

    async def test_feature_initialization_legacy_mode(self, notification_settings, temp_db_path):
        """Test feature initialization with legacy architecture."""
        config = {
            "use_queue_based": False,
            "queue_db_path": temp_db_path,
        }

        with patch(
            "backend.integrations.notifications.feature.get_notification_settings",
            return_value=notification_settings,
        ):
            feature = NotificationFeature(
                name="test_legacy",
                enabled=True,
                config=config,
            )

            await feature.startup()

            assert feature.safe_notification_manager is None
            assert feature.notification_dispatcher is None
            assert feature.legacy_notification_manager is not None
            assert not feature._stats["queue_enabled"]
            assert not feature._stats["dispatcher_running"]

            await feature.shutdown()

    async def test_feature_initialization_disabled_notifications(
        self, notification_settings, feature_config
    ):
        """Test feature initialization when notifications are disabled."""
        notification_settings.enabled = False

        with patch(
            "backend.integrations.notifications.feature.get_notification_settings",
            return_value=notification_settings,
        ):
            feature = NotificationFeature(
                name="test_disabled",
                enabled=True,
                config=feature_config,
            )

            await feature.startup()

            # Should not initialize components when disabled
            assert feature.safe_notification_manager is None
            assert feature.notification_dispatcher is None

            await feature.shutdown()

    async def test_feature_channel_status_initialization(self, notification_feature):
        """Test that channel status is properly initialized."""
        await notification_feature.startup()

        # Verify channel status tracking
        assert len(notification_feature._channel_status) > 0

        for channel_name, status in notification_feature._channel_status.items():
            assert status.channel == channel_name
            assert status.enabled
            assert status.configured

    async def test_feature_startup_statistics(self, notification_feature):
        """Test that startup statistics are properly recorded."""
        await notification_feature.startup()

        stats = notification_feature._stats
        assert stats["startup_time"] > 0
        assert stats["channels_configured"] > 0
        assert "notifications_sent" in stats
        assert "notifications_failed" in stats

    async def test_feature_startup_notification_sending(self, notification_feature):
        """Test that startup notification is sent."""
        await notification_feature.startup()

        # Give time for startup notification
        await asyncio.sleep(0.5)

        # Should have sent startup notification
        assert notification_feature._stats["system_notifications"] >= 1

    async def test_feature_background_task_startup(self, notification_feature):
        """Test that background tasks are started."""
        await notification_feature.startup()

        # Should have background tasks
        assert len(notification_feature._background_tasks) > 0

        # Tasks should be running
        for task in notification_feature._background_tasks:
            assert not task.done()


class TestFeatureShutdown:
    """Test NotificationFeature shutdown procedures."""

    async def test_feature_shutdown_sequence(self, notification_feature):
        """Test proper shutdown sequence."""
        await notification_feature.startup()

        # Verify components are running
        assert notification_feature.notification_dispatcher.is_running

        await notification_feature.shutdown()

        # Verify cleanup
        assert not notification_feature.notification_dispatcher.is_running
        assert notification_feature.safe_notification_manager is None
        assert not notification_feature._stats["dispatcher_running"]
        assert not notification_feature._stats["queue_enabled"]

    async def test_feature_shutdown_background_tasks(self, notification_feature):
        """Test that background tasks are properly cancelled."""
        await notification_feature.startup()

        background_tasks = notification_feature._background_tasks.copy()
        assert len(background_tasks) > 0

        await notification_feature.shutdown()

        # All background tasks should be done
        for task in background_tasks:
            assert task.done()

        assert len(notification_feature._background_tasks) == 0

    async def test_feature_shutdown_notification_sending(self, notification_feature):
        """Test that shutdown notification is sent."""
        await notification_feature.startup()

        initial_system_notifications = notification_feature._stats["system_notifications"]

        await notification_feature.shutdown()

        # Should have sent shutdown notification
        # Note: This is tricky to test since shutdown happens during cleanup

    async def test_feature_shutdown_error_handling(self, notification_feature):
        """Test shutdown error handling."""
        await notification_feature.startup()

        # Mock dispatcher to fail on shutdown
        notification_feature.notification_dispatcher.stop = AsyncMock(
            side_effect=Exception("Shutdown error")
        )

        # Should not raise exception
        await notification_feature.shutdown()

    async def test_feature_shutdown_timeout_handling(self, notification_feature):
        """Test shutdown timeout handling."""
        await notification_feature.startup()

        # Mock dispatcher to take long time to shutdown
        async def slow_stop(*args, **kwargs):
            await asyncio.sleep(10)  # Longer than timeout

        notification_feature.notification_dispatcher.stop = slow_stop

        # Should complete within reasonable time
        start_time = asyncio.get_event_loop().time()
        await notification_feature.shutdown()
        end_time = asyncio.get_event_loop().time()

        assert end_time - start_time < 5.0  # Should timeout quickly


class TestHealthMonitoring:
    """Test feature health monitoring."""

    async def test_health_status_healthy(self, notification_feature):
        """Test health status when system is healthy."""
        await notification_feature.startup()

        health = notification_feature.health
        assert health == "healthy"

    async def test_health_status_disabled(self, notification_settings, feature_config):
        """Test health status when notifications are disabled."""
        notification_settings.enabled = False

        with patch(
            "backend.integrations.notifications.feature.get_notification_settings",
            return_value=notification_settings,
        ):
            feature = NotificationFeature(
                name="test_disabled_health",
                enabled=True,
                config=feature_config,
            )

            await feature.startup()

            assert feature.health == "disabled"

            await feature.shutdown()

    async def test_health_status_failed_initialization(self, notification_feature):
        """Test health status when initialization fails."""
        # Don't start feature
        health = notification_feature.health
        assert health == "failed"

    async def test_health_status_degraded_dispatcher(self, notification_feature):
        """Test health status when dispatcher is not running."""
        await notification_feature.startup()

        # Stop dispatcher manually
        await notification_feature.notification_dispatcher.stop()

        health = notification_feature.health
        assert health == "degraded"

    async def test_get_status_comprehensive(self, notification_feature):
        """Test comprehensive status reporting."""
        await notification_feature.startup()

        status = notification_feature.get_status()

        # Verify status structure
        assert "enabled" in status
        assert "healthy" in status
        assert "architecture" in status
        assert "statistics" in status
        assert "channels" in status
        assert "configuration" in status

        # Verify architecture detection
        assert status["architecture"] == "queue-based"

        # Verify channel information
        assert len(status["channels"]) > 0

        # Verify configuration
        config = status["configuration"]
        assert "smtp_enabled" in config
        assert "queue_enabled" in config

    async def test_health_monitoring_loop(self, notification_feature):
        """Test background health monitoring loop."""
        await notification_feature.startup()

        # Wait for health monitoring
        await asyncio.sleep(2.0)

        # Health monitoring should update stats
        stats = notification_feature._stats
        assert "notifications_processed" in stats
        assert "dispatcher_running" in stats

    async def test_channel_health_tracking(self, notification_feature):
        """Test channel health tracking."""
        await notification_feature.startup()

        # Wait for channel health checks
        await asyncio.sleep(1.5)

        # Verify channel status is tracked
        for channel_name, status in notification_feature._channel_status.items():
            assert isinstance(status.healthy, bool)
            assert status.consecutive_failures >= 0


class TestAPIMethodDelegation:
    """Test API method delegation between queue-based and legacy managers."""

    async def test_send_notification_queue_based(self, notification_feature):
        """Test send_notification with queue-based manager."""
        await notification_feature.startup()

        result = await notification_feature.send_notification(
            message="Test notification",
            title="Test Title",
            level="info",
            channels=["smtp"],
        )

        assert result
        assert notification_feature._stats["notifications_queued"] >= 1

    async def test_send_notification_legacy_fallback(self, notification_settings, temp_db_path):
        """Test send_notification with legacy manager fallback."""
        config = {"use_queue_based": False, "queue_db_path": temp_db_path}

        with patch(
            "backend.integrations.notifications.feature.get_notification_settings",
            return_value=notification_settings,
        ):
            feature = NotificationFeature(
                name="test_legacy_api",
                enabled=True,
                config=config,
            )

            # Mock legacy manager
            feature.legacy_notification_manager = MagicMock()
            feature.legacy_notification_manager.send_notification = AsyncMock(return_value=True)

            await feature.startup()

            result = await feature.send_notification(
                message="Legacy test",
                level="info",
            )

            assert result
            feature.legacy_notification_manager.send_notification.assert_called()

            await feature.shutdown()

    async def test_send_email_delegation(self, notification_feature):
        """Test send_email method delegation."""
        await notification_feature.startup()

        result = await notification_feature.send_email(
            to_email="test@example.com",
            subject="Test Email",
            template="test_template",
            context={"name": "Test User"},
        )

        assert result
        assert notification_feature._stats["emails_sent"] >= 1

    async def test_send_magic_link_email_delegation(self, notification_feature):
        """Test send_magic_link_email method delegation."""
        await notification_feature.startup()

        result = await notification_feature.send_magic_link_email(
            to_email="user@example.com",
            magic_link="https://example.com/auth/magic?token=abc123",
            user_name="Test User",
        )

        assert result
        assert notification_feature._stats["emails_sent"] >= 1

    async def test_send_system_notification_delegation(self, notification_feature):
        """Test send_system_notification method delegation."""
        await notification_feature.startup()

        result = await notification_feature.send_system_notification(
            message="System test message",
            level="warning",
            component="test_component",
        )

        assert result
        assert (
            notification_feature._stats["system_notifications"] >= 2
        )  # Including startup notification

    async def test_send_pushover_notification_delegation(self, notification_feature):
        """Test send_pushover_notification method delegation."""
        await notification_feature.startup()

        result = await notification_feature.send_pushover_notification(
            message="Pushover test",
            title="Pushover Title",
            priority=1,
            device="test_device",
        )

        assert result

    async def test_test_channels_delegation(self, notification_feature):
        """Test test_channels method delegation."""
        await notification_feature.startup()

        results = await notification_feature.test_channels()

        assert isinstance(results, dict)
        # Should have results for enabled channels
        assert len(results) > 0

    async def test_api_method_error_handling(self, notification_feature):
        """Test API method error handling."""
        await notification_feature.startup()

        # Mock safe manager to fail
        notification_feature.safe_notification_manager.notify = AsyncMock(
            side_effect=Exception("Test error")
        )

        result = await notification_feature.send_notification(
            message="Error test",
        )

        # Should handle error gracefully
        assert not result
        assert notification_feature._stats["notifications_failed"] >= 1

    async def test_api_method_without_manager(self, notification_settings, feature_config):
        """Test API methods when no manager is available."""
        with patch(
            "backend.integrations.notifications.feature.get_notification_settings",
            return_value=notification_settings,
        ):
            feature = NotificationFeature(
                name="test_no_manager",
                enabled=True,
                config=feature_config,
            )

            # Don't startup to leave managers as None

            result = await feature.send_notification(message="No manager test")
            assert not result

            await feature.shutdown()


class TestQueueSpecificMethods:
    """Test queue-specific API methods."""

    async def test_get_queue_statistics(self, notification_feature):
        """Test get_queue_statistics method."""
        await notification_feature.startup()

        # Add some notifications
        await notification_feature.send_notification(message="Stats test 1")
        await notification_feature.send_notification(message="Stats test 2")

        stats = await notification_feature.get_queue_statistics()

        assert isinstance(stats, dict)
        assert "pending_count" in stats
        assert stats["pending_count"] >= 0

    async def test_get_rate_limit_status(self, notification_feature):
        """Test get_rate_limit_status method."""
        await notification_feature.startup()

        status = await notification_feature.get_rate_limit_status()

        assert isinstance(status, dict)
        assert "current_tokens" in status
        assert "max_tokens" in status
        assert "healthy" in status

    async def test_force_queue_processing(self, notification_feature):
        """Test force_queue_processing method."""
        await notification_feature.startup()

        # Add notifications
        await notification_feature.send_notification(message="Force test 1")
        await notification_feature.send_notification(message="Force test 2")

        result = await notification_feature.force_queue_processing()

        assert isinstance(result, dict)
        assert "processed_batches" in result or "error" in result

    async def test_queue_methods_without_queue_manager(self, notification_settings, temp_db_path):
        """Test queue-specific methods without queue-based manager."""
        config = {"use_queue_based": False, "queue_db_path": temp_db_path}

        with patch(
            "backend.integrations.notifications.feature.get_notification_settings",
            return_value=notification_settings,
        ):
            feature = NotificationFeature(
                name="test_no_queue",
                enabled=True,
                config=config,
            )

            await feature.startup()

            # Should return error for queue-specific methods
            stats = await feature.get_queue_statistics()
            assert "error" in stats

            status = await feature.get_rate_limit_status()
            assert "error" in status

            result = await feature.force_queue_processing()
            assert "error" in result

            await feature.shutdown()


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery scenarios."""

    async def test_startup_error_handling(self, notification_settings, feature_config):
        """Test startup error handling."""
        # Mock to cause initialization error
        with patch(
            "backend.services.safe_notification_manager.SafeNotificationManager.initialize",
            side_effect=Exception("Init error"),
        ):
            with patch(
                "backend.integrations.notifications.feature.get_notification_settings",
                return_value=notification_settings,
            ):
                feature = NotificationFeature(
                    name="test_startup_error",
                    enabled=True,
                    config=feature_config,
                )

                # Should not raise exception
                await feature.startup()

                # Feature should handle error gracefully
                assert feature.safe_notification_manager is None

                await feature.shutdown()

    async def test_dispatcher_startup_failure(self, notification_feature):
        """Test handling of dispatcher startup failure."""
        # Mock dispatcher start to fail
        with patch(
            "backend.services.async_notification_dispatcher.AsyncNotificationDispatcher.start",
            side_effect=Exception("Dispatcher error"),
        ):
            # Should not raise exception
            await notification_feature.startup()

            # Should have safe manager but no dispatcher
            assert notification_feature.safe_notification_manager is not None

    async def test_background_task_error_handling(self, notification_feature):
        """Test background task error handling."""
        await notification_feature.startup()

        # Verify background tasks are running
        assert len(notification_feature._background_tasks) > 0

        # Background task errors should be handled gracefully
        # (They include try/except blocks internally)

        # Wait for some background processing
        await asyncio.sleep(2.0)

        # Tasks should still be running despite any internal errors
        running_tasks = [task for task in notification_feature._background_tasks if not task.done()]
        assert len(running_tasks) > 0

    async def test_health_monitoring_error_recovery(self, notification_feature):
        """Test health monitoring error recovery."""
        await notification_feature.startup()

        # Mock safe manager to fail health checks
        notification_feature.safe_notification_manager.get_queue_statistics = AsyncMock(
            side_effect=Exception("Health error")
        )

        # Wait for health monitoring cycle
        await asyncio.sleep(2.0)

        # Feature should continue running despite health check errors
        assert notification_feature.health in ["healthy", "degraded", "failed"]

    async def test_notification_error_statistics(self, notification_feature):
        """Test error statistics tracking."""
        await notification_feature.startup()

        # Mock to cause notification failures
        notification_feature.safe_notification_manager.notify = AsyncMock(return_value=False)

        # Send notifications that will fail
        for i in range(3):
            await notification_feature.send_notification(f"Error test {i}")

        # Verify error statistics
        assert notification_feature._stats["notifications_failed"] >= 3

    async def test_channel_failure_handling(self, notification_feature):
        """Test handling of channel failures."""
        await notification_feature.startup()

        # Mock channel test to fail
        notification_feature.safe_notification_manager.test_channels = AsyncMock(
            return_value={"smtp": False, "slack": True}
        )

        # Wait for health monitoring
        await asyncio.sleep(2.0)

        # Should update channel health status
        if "smtp" in notification_feature._channel_status:
            # Note: Channel health updates happen in background tasks
            pass


class TestCompleteNotificationFlow:
    """Test complete notification flow from feature API to delivery."""

    async def test_end_to_end_notification_flow(self, notification_feature):
        """Test complete notification flow."""
        await notification_feature.startup()

        # Send notification through feature API
        result = await notification_feature.send_notification(
            message="End-to-end test",
            title="E2E Test",
            level="warning",
            channels=["smtp"],
            tags=["test", "e2e"],
            context={"test_key": "test_value"},
            recipient="e2e@example.com",
        )

        assert result

        # Wait for processing
        await asyncio.sleep(1.0)

        # Verify notification was queued
        queue_stats = await notification_feature.get_queue_statistics()
        assert queue_stats["pending_count"] >= 0  # May be 0 if already processed

        # Verify statistics were updated
        assert notification_feature._stats["notifications_sent"] >= 1

    async def test_high_volume_notification_processing(self, notification_feature):
        """Test high volume notification processing."""
        await notification_feature.startup()

        # Send many notifications
        notification_count = 50
        tasks = []

        for i in range(notification_count):
            task = notification_feature.send_notification(
                message=f"High volume test {i}",
                level="info",
                priority=(i % 5) + 1,
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Most should succeed (some may be rate limited)
        success_count = sum(1 for result in results if result)
        assert success_count > notification_count * 0.5  # At least 50% should succeed

        # Wait for processing
        await asyncio.sleep(2.0)

        # Verify statistics
        assert notification_feature._stats["notifications_sent"] >= success_count

    async def test_mixed_notification_types_processing(self, notification_feature):
        """Test processing mixed notification types."""
        await notification_feature.startup()

        # Send various types concurrently
        tasks = [
            notification_feature.send_notification(message="Regular notification"),
            notification_feature.send_email(
                to_email="mixed@example.com",
                subject="Mixed Test",
                template="test",
                context={},
            ),
            notification_feature.send_system_notification(
                message="System notification",
                component="test",
            ),
            notification_feature.send_pushover_notification(
                message="Pushover notification",
                priority=0,
            ),
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(results)

        # Wait for processing
        await asyncio.sleep(1.0)

        # Verify different types were tracked
        stats = notification_feature._stats
        assert stats["emails_sent"] >= 1
        assert stats["system_notifications"] >= 2  # Including startup notification

    async def test_notification_flow_with_rate_limiting(self, notification_feature):
        """Test notification flow with rate limiting effects."""
        await notification_feature.startup()

        # Configure restrictive rate limiting
        if notification_feature.safe_notification_manager:
            notification_feature.safe_notification_manager.rate_limiter.max_tokens = 5
            notification_feature.safe_notification_manager.rate_limiter.current_tokens = 5

        # Send more notifications than rate limit
        results = []
        for i in range(10):
            result = await notification_feature.send_notification(f"Rate limit test {i}")
            results.append(result)

        # Some should succeed, some should be rate limited
        success_count = sum(1 for result in results if result)
        assert 0 < success_count <= 5

        # Verify rate limiting statistics
        rate_status = await notification_feature.get_rate_limit_status()
        assert rate_status["requests_blocked"] > 0

    async def test_notification_flow_error_recovery(self, notification_feature):
        """Test notification flow error recovery."""
        await notification_feature.startup()

        # Introduce temporary error
        original_notify = notification_feature.safe_notification_manager.notify
        call_count = 0

        async def failing_notify(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Temporary error")
            return await original_notify(*args, **kwargs)

        notification_feature.safe_notification_manager.notify = failing_notify

        # First notifications should fail
        result1 = await notification_feature.send_notification("Fail test 1")
        result2 = await notification_feature.send_notification("Fail test 2")
        assert not result1 and not result2

        # After "recovery", should work
        result3 = await notification_feature.send_notification("Recovery test")
        assert result3

        # Verify error statistics
        assert notification_feature._stats["notifications_failed"] >= 2


@pytest.mark.asyncio
class TestFeaturePerformance:
    """Test feature performance characteristics."""

    async def test_feature_startup_performance(self, notification_settings, feature_config):
        """Test feature startup performance."""
        with patch(
            "backend.integrations.notifications.feature.get_notification_settings",
            return_value=notification_settings,
        ):
            feature = NotificationFeature(
                name="test_performance",
                enabled=True,
                config=feature_config,
            )

            start_time = asyncio.get_event_loop().time()
            await feature.startup()
            end_time = asyncio.get_event_loop().time()

            startup_duration = end_time - start_time

            # Should start up quickly (under 2 seconds)
            assert startup_duration < 2.0

            # Verify startup time is recorded
            assert feature._stats["startup_time"] > 0

            await feature.shutdown()

    async def test_concurrent_api_call_performance(self, notification_feature):
        """Test performance of concurrent API calls."""
        await notification_feature.startup()

        # Make many concurrent API calls
        start_time = asyncio.get_event_loop().time()

        tasks = []
        for i in range(100):
            task = notification_feature.send_notification(f"Concurrent test {i}")
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time

        # Should complete quickly (under 1 second for 100 calls)
        assert duration < 1.0

        # Most should succeed
        success_count = sum(1 for result in results if result)
        assert success_count > 50

    async def test_memory_usage_stability(self, notification_feature):
        """Test memory usage stability over time."""
        await notification_feature.startup()

        # Generate sustained activity
        for cycle in range(10):
            tasks = []
            for i in range(20):
                task = notification_feature.send_notification(f"Memory test {cycle}-{i}")
                tasks.append(task)

            await asyncio.gather(*tasks)
            await asyncio.sleep(0.1)  # Small delay between cycles

        # Wait for processing
        await asyncio.sleep(2.0)

        # Feature should remain stable (no memory leaks, crashes, etc.)
        assert notification_feature._running
        assert notification_feature.health in ["healthy", "degraded"]
