"""
Real Service Integration Tests for Notification System

This module provides tests that interact with real external services
when appropriate environment variables are set. These tests are typically
run in CI/CD environments or dedicated testing environments.

Environment Variables:
- COACHIQ_TEST_SMTP_ENABLED=true: Enable real SMTP testing
- COACHIQ_TEST_SMTP_HOST: SMTP server hostname
- COACHIQ_TEST_SMTP_PORT: SMTP server port
- COACHIQ_TEST_SMTP_USERNAME: SMTP username
- COACHIQ_TEST_SMTP_PASSWORD: SMTP password
- COACHIQ_TEST_SMTP_TLS: Use TLS (true/false)
- COACHIQ_TEST_EMAIL: Target email for testing
- COACHIQ_TEST_PUSHOVER_ENABLED=true: Enable Pushover testing
- COACHIQ_TEST_PUSHOVER_TOKEN: Pushover app token
- COACHIQ_TEST_PUSHOVER_USER: Pushover user key

Example Usage:
    # Run only mock tests (default)
    pytest tests/integration/test_notification_real_services.py

    # Run with real SMTP (requires environment variables)
    COACHIQ_TEST_SMTP_ENABLED=true COACHIQ_TEST_EMAIL=your@email.com pytest tests/integration/test_notification_real_services.py::TestRealEmailDelivery

    # Run with real Pushover (requires environment variables)
    COACHIQ_TEST_PUSHOVER_ENABLED=true pytest tests/integration/test_notification_real_services.py::TestRealPushoverDelivery
"""

import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

try:
    import apprise

    APPRISE_AVAILABLE = True
except ImportError:
    APPRISE_AVAILABLE = False

from backend.core.config import NotificationSettings
from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationType,
)
from backend.services.safe_notification_manager import SafeNotificationManager


def requires_real_smtp(func):
    """Decorator to skip tests if real SMTP is not enabled."""
    return pytest.mark.skipif(
        not os.getenv("COACHIQ_TEST_SMTP_ENABLED", "false").lower() == "true",
        reason="Real SMTP testing not enabled. Set COACHIQ_TEST_SMTP_ENABLED=true",
    )(func)


def requires_real_pushover(func):
    """Decorator to skip tests if real Pushover is not enabled."""
    return pytest.mark.skipif(
        not (
            os.getenv("COACHIQ_TEST_PUSHOVER_ENABLED", "false").lower() == "true"
            and APPRISE_AVAILABLE
        ),
        reason="Real Pushover testing not enabled or apprise not available",
    )(func)


@pytest.fixture
def real_smtp_config():
    """Real SMTP configuration from environment variables."""
    return {
        "host": os.getenv("COACHIQ_TEST_SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("COACHIQ_TEST_SMTP_PORT", "587")),
        "username": os.getenv("COACHIQ_TEST_SMTP_USERNAME", ""),
        "password": os.getenv("COACHIQ_TEST_SMTP_PASSWORD", ""),
        "use_tls": os.getenv("COACHIQ_TEST_SMTP_TLS", "true").lower() == "true",
        "from_email": os.getenv("COACHIQ_TEST_FROM_EMAIL", "test@coachiq.com"),
        "test_email": os.getenv("COACHIQ_TEST_EMAIL", "test@example.com"),
    }


@pytest.fixture
def real_pushover_config():
    """Real Pushover configuration from environment variables."""
    return {
        "token": os.getenv("COACHIQ_TEST_PUSHOVER_TOKEN", ""),
        "user_key": os.getenv("COACHIQ_TEST_PUSHOVER_USER", ""),
    }


@pytest.fixture
async def real_notification_config(real_smtp_config, real_pushover_config):
    """Create notification configuration for real service testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        temp_db_path = temp_file.name

    config = NotificationSettings(
        enabled=True,
        default_title="CoachIQ Integration Test",
        app_name="CoachIQ Integration Test",
        queue_db_path=temp_db_path,
        rate_limit_max_tokens=1000,
        rate_limit_per_minute=600,
        debounce_minutes=1,
    )

    # Configure real SMTP
    if os.getenv("COACHIQ_TEST_SMTP_ENABLED", "false").lower() == "true":
        config.smtp = type(
            "SMTPSettings",
            (),
            {
                "enabled": True,
                "host": real_smtp_config["host"],
                "port": real_smtp_config["port"],
                "username": real_smtp_config["username"],
                "password": real_smtp_config["password"],
                "use_tls": real_smtp_config["use_tls"],
                "from_email": real_smtp_config["from_email"],
            },
        )()
    else:
        config.smtp = type("SMTPSettings", (), {"enabled": False})()

    # Configure real Pushover
    if os.getenv("COACHIQ_TEST_PUSHOVER_ENABLED", "false").lower() == "true":
        config.pushover = type(
            "PushoverSettings",
            (),
            {
                "enabled": True,
                "token": real_pushover_config["token"],
                "user_key": real_pushover_config["user_key"],
            },
        )()
    else:
        config.pushover = type("PushoverSettings", (), {"enabled": False})()

    yield config

    # Cleanup
    try:
        Path(temp_db_path).unlink()
        Path(f"{temp_db_path}-wal").unlink(missing_ok=True)
        Path(f"{temp_db_path}-shm").unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture
async def real_notification_manager(real_notification_config):
    """Create SafeNotificationManager with real service configuration."""
    manager = SafeNotificationManager(real_notification_config)
    await manager.initialize()

    yield manager

    await manager.cleanup()


class TestRealEmailDelivery:
    """Test real email delivery through SMTP."""

    @requires_real_smtp
    async def test_send_magic_link_email(self, real_notification_manager, real_smtp_config):
        """Test sending magic link email through real SMTP."""
        success = await real_notification_manager.send_magic_link_email(
            to_email=real_smtp_config["test_email"],
            magic_link="https://coachiq.example.com/auth/magic/test-token-12345",
            user_name="Integration Test User",
            expires_minutes=15,
        )

        assert success, "Magic link email should be queued successfully"

        # Allow time for processing
        await asyncio.sleep(2)

        # Check queue statistics
        stats = await real_notification_manager.get_queue_statistics()
        print(
            f"Queue stats after magic link email: pending={stats.pending_count}, "
            f"completed={stats.completed_count}, failed={stats.failed_count}"
        )

    @requires_real_smtp
    async def test_send_system_notification_email(
        self, real_notification_manager, real_smtp_config
    ):
        """Test sending system notification email through real SMTP."""
        success = await real_notification_manager.send_email(
            to_email=real_smtp_config["test_email"],
            template="system_notification",
            context={
                "title": "Integration Test System Alert",
                "message": "This is a test system notification sent during integration testing.",
                "level": "warning",
                "source_component": "IntegrationTest",
                "correlation_id": f"test_{datetime.utcnow().isoformat()}",
                "app_name": "CoachIQ Integration Test",
                "support_email": real_smtp_config["from_email"],
            },
        )

        assert success, "System notification email should be queued successfully"

        # Allow time for processing
        await asyncio.sleep(2)

        # Check queue statistics
        stats = await real_notification_manager.get_queue_statistics()
        print(
            f"Queue stats after system notification: pending={stats.pending_count}, "
            f"completed={stats.completed_count}, failed={stats.failed_count}"
        )

    @requires_real_smtp
    async def test_send_test_notification_email(self, real_notification_manager, real_smtp_config):
        """Test sending test notification email through real SMTP."""
        success = await real_notification_manager.send_email(
            to_email=real_smtp_config["test_email"],
            template="test_notification",
            context={
                "message": "CoachIQ notification system integration test completed successfully!",
                "app_name": "CoachIQ Integration Test",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        assert success, "Test notification email should be queued successfully"

        # Allow time for processing
        await asyncio.sleep(2)

        # Check queue statistics
        stats = await real_notification_manager.get_queue_statistics()
        print(
            f"Queue stats after test notification: pending={stats.pending_count}, "
            f"completed={stats.completed_count}, failed={stats.failed_count}"
        )

    @requires_real_smtp
    async def test_email_template_rendering_with_real_smtp(
        self, real_notification_manager, real_smtp_config
    ):
        """Test email template rendering and delivery through real SMTP."""
        # Create custom template for testing
        template_name = "integration_test_custom"
        success = await real_notification_manager.create_email_template(
            template_name=template_name,
            subject="CoachIQ Integration Test - {{test_type|title}}",
            html_content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>CoachIQ Integration Test</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; }
                    .header { background-color: #007bff; color: white; padding: 20px; text-align: center; }
                    .content { padding: 20px; background-color: #f8f9fa; }
                    .footer { padding: 20px; font-size: 0.9em; color: #666; }
                    .success { color: #28a745; font-weight: bold; }
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>{{app_name}} Integration Test</h1>
                </div>
                <div class="content">
                    <h2>Test Type: {{test_type}}</h2>
                    <p class="success">✅ Email template rendering is working correctly!</p>
                    <p>{{message}}</p>
                    <p><strong>Test Details:</strong></p>
                    <ul>
                        <li>Timestamp: {{timestamp}}</li>
                        <li>Component: {{source_component}}</li>
                        <li>Template: {{template_name}}</li>
                    </ul>
                </div>
                <div class="footer">
                    <p>This email was generated during integration testing of the CoachIQ notification system.</p>
                </div>
            </body>
            </html>
            """,
            text_content="""
            {{app_name}} Integration Test

            Test Type: {{test_type}}

            ✅ Email template rendering is working correctly!

            {{message}}

            Test Details:
            - Timestamp: {{timestamp}}
            - Component: {{source_component}}
            - Template: {{template_name}}

            This email was generated during integration testing of the CoachIQ notification system.
            """,
        )

        assert success, "Custom template creation should succeed"

        # Send email using custom template
        success = await real_notification_manager.send_email(
            to_email=real_smtp_config["test_email"],
            template=template_name,
            context={
                "test_type": "custom template rendering",
                "message": "The notification system successfully rendered this email using a custom Jinja2 template with full HTML and text content.",
                "timestamp": datetime.utcnow().isoformat(),
                "source_component": "RealServiceIntegrationTest",
                "template_name": template_name,
                "app_name": "CoachIQ Integration Test",
            },
        )

        assert success, "Custom template email should be queued successfully"

        # Allow time for processing
        await asyncio.sleep(3)

        # Check final statistics
        stats = await real_notification_manager.get_queue_statistics()
        manager_stats = real_notification_manager.get_statistics()

        print(
            f"Final queue stats: pending={stats.pending_count}, "
            f"completed={stats.completed_count}, failed={stats.failed_count}"
        )
        print(
            f"Manager stats: total={manager_stats['total_notifications']}, "
            f"successful={manager_stats['successful_notifications']}, "
            f"failed={manager_stats['failed_notifications']}"
        )


class TestRealPushoverDelivery:
    """Test real Pushover notification delivery."""

    @requires_real_pushover
    async def test_send_pushover_notification(
        self, real_notification_manager, real_pushover_config
    ):
        """Test sending Pushover notification through real API."""
        success = await real_notification_manager.send_pushover_notification(
            message="CoachIQ integration test notification via Pushover",
            title="CoachIQ Integration Test",
            priority=0,  # Normal priority
        )

        assert success, "Pushover notification should be queued successfully"

        # Allow time for processing
        await asyncio.sleep(2)

        # Check queue statistics
        stats = await real_notification_manager.get_queue_statistics()
        print(
            f"Queue stats after Pushover notification: pending={stats.pending_count}, "
            f"completed={stats.completed_count}, failed={stats.failed_count}"
        )

    @requires_real_pushover
    async def test_send_high_priority_pushover_notification(
        self, real_notification_manager, real_pushover_config
    ):
        """Test sending high priority Pushover notification."""
        success = await real_notification_manager.notify(
            message="HIGH PRIORITY: CoachIQ integration test - critical system alert simulation",
            title="Critical Alert Test",
            level=NotificationType.CRITICAL,
            channels=["pushover"],
            source_component="CriticalAlertTest",
        )

        assert success, "Critical Pushover notification should be queued successfully"

        # Allow time for processing
        await asyncio.sleep(2)

        # Check queue statistics
        stats = await real_notification_manager.get_queue_statistics()
        print(
            f"Queue stats after critical Pushover notification: pending={stats.pending_count}, "
            f"completed={stats.completed_count}, failed={stats.failed_count}"
        )


class TestRealServiceCombination:
    """Test combinations of real services."""

    @pytest.mark.skipif(
        not (
            os.getenv("COACHIQ_TEST_SMTP_ENABLED", "false").lower() == "true"
            and os.getenv("COACHIQ_TEST_PUSHOVER_ENABLED", "false").lower() == "true"
        ),
        reason="Both SMTP and Pushover testing not enabled",
    )
    async def test_multi_channel_notification(
        self, real_notification_manager, real_smtp_config, real_pushover_config
    ):
        """Test notification delivery across multiple real channels."""
        success = await real_notification_manager.notify(
            message="Multi-channel integration test: This notification should be delivered via both email and Pushover",
            title="Multi-Channel Integration Test",
            level=NotificationType.WARNING,
            channels=["smtp", "pushover"],
            template="system_notification",
            context={
                "app_name": "CoachIQ Integration Test",
                "support_email": real_smtp_config["from_email"],
                "source_component": "MultiChannelTest",
                "correlation_id": f"multi_channel_test_{datetime.utcnow().isoformat()}",
            },
            recipient=real_smtp_config["test_email"],
        )

        assert success, "Multi-channel notification should be queued successfully"

        # Allow extra time for multi-channel processing
        await asyncio.sleep(5)

        # Check final statistics
        stats = await real_notification_manager.get_queue_statistics()
        manager_stats = real_notification_manager.get_statistics()
        routing_stats = real_notification_manager.get_routing_statistics()

        print("Multi-channel test results:")
        print(
            f"  Queue: pending={stats.pending_count}, completed={stats.completed_count}, failed={stats.failed_count}"
        )
        print(
            f"  Manager: total={manager_stats['total_notifications']}, successful={manager_stats['successful_notifications']}"
        )
        print(
            f"  Routing: total={routing_stats.get('total_routings', 0)}, matches={routing_stats.get('rule_matches', 0)}"
        )


class TestRealServiceErrorHandling:
    """Test error handling with real services."""

    @requires_real_smtp
    async def test_invalid_email_address_handling(self, real_notification_manager):
        """Test handling of invalid email addresses."""
        # Send to obviously invalid email
        success = await real_notification_manager.send_email(
            to_email="invalid-email-address-that-should-fail@non-existent-domain-12345.invalid",
            template="test_notification",
            context={
                "message": "This email should fail to deliver due to invalid address",
                "app_name": "CoachIQ Error Test",
            },
        )

        # Should still queue successfully (failure happens during delivery)
        assert success, "Email should be queued even with invalid address"

        # Allow time for delivery attempt and failure
        await asyncio.sleep(5)

        # Check that failures are tracked
        stats = await real_notification_manager.get_queue_statistics()
        manager_stats = real_notification_manager.get_statistics()

        print("Invalid email test results:")
        print(
            f"  Queue: pending={stats.pending_count}, failed={stats.failed_count}, dlq={stats.dlq_count}"
        )
        print(f"  Manager: failed={manager_stats.get('failed_notifications', 0)}")

    @requires_real_smtp
    async def test_rate_limiting_with_real_smtp(self, real_notification_manager, real_smtp_config):
        """Test rate limiting behavior with real SMTP server."""
        # Send rapid burst of emails to test rate limiting
        tasks = []
        for i in range(10):
            task = real_notification_manager.send_email(
                to_email=real_smtp_config["test_email"],
                template="test_notification",
                context={
                    "message": f"Rate limiting test email #{i}",
                    "app_name": "CoachIQ Rate Limit Test",
                },
            )
            tasks.append(task)

        # Execute all tasks simultaneously
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful vs rate-limited
        successful = sum(1 for result in results if result is True)

        # Allow time for processing
        await asyncio.sleep(3)

        # Check rate limiting statistics
        rate_limit_status = await real_notification_manager.get_rate_limit_status()
        manager_stats = real_notification_manager.get_statistics()

        print("Rate limiting test with real SMTP:")
        print(f"  Successful queues: {successful}/10")
        print(f"  Rate limited: {manager_stats.get('rate_limited_notifications', 0)}")
        print(
            f"  Current tokens: {rate_limit_status.current_tokens}/{rate_limit_status.max_tokens}"
        )


# Utility functions for test environment setup


def print_test_environment_info():
    """Print information about test environment configuration."""
    print("\nIntegration Test Environment:")
    print(f"  SMTP Enabled: {os.getenv('COACHIQ_TEST_SMTP_ENABLED', 'false')}")
    print(f"  SMTP Host: {os.getenv('COACHIQ_TEST_SMTP_HOST', 'not set')}")
    print(f"  Test Email: {os.getenv('COACHIQ_TEST_EMAIL', 'not set')}")
    print(f"  Pushover Enabled: {os.getenv('COACHIQ_TEST_PUSHOVER_ENABLED', 'false')}")
    print(f"  Apprise Available: {APPRISE_AVAILABLE}")
    print()


def validate_test_environment():
    """Validate test environment has required configuration."""
    issues = []

    if os.getenv("COACHIQ_TEST_SMTP_ENABLED", "false").lower() == "true":
        required_smtp_vars = [
            "COACHIQ_TEST_SMTP_HOST",
            "COACHIQ_TEST_SMTP_USERNAME",
            "COACHIQ_TEST_SMTP_PASSWORD",
            "COACHIQ_TEST_EMAIL",
        ]

        for var in required_smtp_vars:
            if not os.getenv(var):
                issues.append(f"Missing required environment variable: {var}")

    if os.getenv("COACHIQ_TEST_PUSHOVER_ENABLED", "false").lower() == "true":
        if not APPRISE_AVAILABLE:
            issues.append("Pushover testing enabled but apprise library not available")

        required_pushover_vars = ["COACHIQ_TEST_PUSHOVER_TOKEN", "COACHIQ_TEST_PUSHOVER_USER"]

        for var in required_pushover_vars:
            if not os.getenv(var):
                issues.append(f"Missing required environment variable: {var}")

    if issues:
        print("Test environment validation issues:")
        for issue in issues:
            print(f"  - {issue}")
        print()

    return len(issues) == 0


# Run environment validation when module is imported
if __name__ == "__main__":
    print_test_environment_info()
    if validate_test_environment():
        print("✅ Test environment validation passed")
    else:
        print("❌ Test environment validation failed")
