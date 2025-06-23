"""
Tests for Webhook Notification Channel

This module tests the webhook notification channel including configuration,
delivery, authentication, retries, and error handling.
"""

import asyncio
import json
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientError, ClientTimeout
from aiohttp.web import Application, Response, json_response

from backend.integrations.notifications.channels.webhook import (
    WebhookAuthConfig,
    WebhookDeliveryResult,
    WebhookNotificationChannel,
    WebhookTarget,
    send_webhook_notification,
    test_webhook_channels,
)
from backend.models.notification import NotificationChannel, NotificationPayload, NotificationType


class TestWebhookAuthConfig:
    """Test webhook authentication configuration."""

    def test_none_auth_valid(self):
        """Test that 'none' authentication type is valid."""
        config = WebhookAuthConfig(type="none")
        assert config.type == "none"
        assert config.bearer_token is None

    def test_bearer_auth_valid(self):
        """Test bearer token authentication configuration."""
        config = WebhookAuthConfig(type="bearer", bearer_token="test-token")
        assert config.type == "bearer"
        assert config.bearer_token == "test-token"

    def test_apikey_auth_valid(self):
        """Test API key authentication configuration."""
        config = WebhookAuthConfig(type="apikey", api_key="test-key", api_key_header="X-Custom-Key")
        assert config.type == "apikey"
        assert config.api_key == "test-key"
        assert config.api_key_header == "X-Custom-Key"

    def test_basic_auth_valid(self):
        """Test basic authentication configuration."""
        config = WebhookAuthConfig(type="basic", username="user", password="pass")
        assert config.type == "basic"
        assert config.username == "user"
        assert config.password == "pass"

    def test_invalid_auth_type(self):
        """Test that invalid authentication types raise ValueError."""
        with pytest.raises(ValueError, match="Authentication type must be one of"):
            WebhookAuthConfig(type="invalid")

    def test_custom_headers(self):
        """Test custom headers configuration."""
        headers = {"X-Custom": "value", "X-Another": "test"}
        config = WebhookAuthConfig(type="none", custom_headers=headers)
        assert config.custom_headers == headers


class TestWebhookTarget:
    """Test webhook target configuration."""

    def test_valid_target_creation(self):
        """Test creating a valid webhook target."""
        target = WebhookTarget(name="test-webhook", url="https://example.com/webhook", enabled=True)
        assert target.name == "test-webhook"
        assert str(target.url) == "https://example.com/webhook"
        assert target.enabled is True
        assert target.method == "POST"  # Default

    def test_custom_method_validation(self):
        """Test HTTP method validation."""
        target = WebhookTarget(name="test", url="https://example.com/webhook", method="PUT")
        assert target.method == "PUT"

    def test_invalid_method(self):
        """Test that invalid HTTP methods raise ValueError."""
        with pytest.raises(ValueError, match="HTTP method must be one of"):
            WebhookTarget(name="test", url="https://example.com/webhook", method="INVALID")

    def test_default_values(self):
        """Test default configuration values."""
        target = WebhookTarget(name="test", url="https://example.com/webhook")
        assert target.timeout == 30
        assert target.max_retries == 3
        assert target.retry_delay == 1
        assert target.retry_exponential is True
        assert target.verify_ssl is True
        assert target.content_type == "application/json"

    def test_auth_configuration(self):
        """Test authentication configuration integration."""
        auth = WebhookAuthConfig(type="bearer", bearer_token="test-token")
        target = WebhookTarget(name="test", url="https://example.com/webhook", auth=auth)
        assert target.auth.type == "bearer"
        assert target.auth.bearer_token == "test-token"

    def test_notification_filtering(self):
        """Test notification type and tag filtering."""
        target = WebhookTarget(
            name="test",
            url="https://example.com/webhook",
            notification_types=["warning", "error"],
            tags_filter=["security", "system"],
        )
        assert target.notification_types == ["warning", "error"]
        assert target.tags_filter == ["security", "system"]


class TestWebhookNotificationChannel:
    """Test webhook notification channel functionality."""

    @pytest.fixture
    def channel(self):
        """Create webhook channel for testing."""
        return WebhookNotificationChannel()

    @pytest.fixture
    def test_target(self):
        """Create test webhook target."""
        return WebhookTarget(
            name="test-webhook",
            url="https://example.com/webhook",
            enabled=True,
            timeout=10,
            max_retries=2,
        )

    @pytest.fixture
    def test_notification(self):
        """Create test notification payload."""
        return NotificationPayload(
            message="Test notification message",
            title="Test Notification",
            level=NotificationType.INFO,
            channels=[NotificationChannel.WEBHOOK],
            tags=["test", "webhook"],
            source_component="WebhookChannelTest",
        )

    def test_channel_initialization(self, channel):
        """Test channel initialization."""
        assert channel.channel == NotificationChannel.WEBHOOK
        assert channel.enabled is True  # Default from config
        assert channel.targets == {}
        assert channel.stats["total_requests"] == 0

    def test_add_target(self, channel, test_target):
        """Test adding webhook target."""
        channel.add_target(test_target)
        assert "test-webhook" in channel.targets
        assert channel.targets["test-webhook"] == test_target

    def test_remove_target(self, channel, test_target):
        """Test removing webhook target."""
        channel.add_target(test_target)
        assert channel.remove_target("test-webhook") is True
        assert "test-webhook" not in channel.targets
        assert channel.remove_target("nonexistent") is False

    def test_get_target(self, channel, test_target):
        """Test getting webhook target by name."""
        channel.add_target(test_target)
        retrieved = channel.get_target("test-webhook")
        assert retrieved == test_target
        assert channel.get_target("nonexistent") is None

    def test_list_targets(self, channel, test_target):
        """Test listing all target names."""
        assert channel.list_targets() == []
        channel.add_target(test_target)
        assert channel.list_targets() == ["test-webhook"]

    def test_rate_limiting_check(self, channel):
        """Test rate limiting functionality."""
        # Initially should allow requests
        assert channel._check_rate_limit() is True

        # Fill up rate limit
        for _ in range(channel.rate_limit_requests):
            channel._check_rate_limit()

        # Should now be rate limited
        assert channel._check_rate_limit() is False

    def test_should_deliver_to_target(self, channel, test_notification):
        """Test notification filtering logic."""
        # Target with no filtering
        target1 = WebhookTarget(name="all", url="https://example.com/webhook", enabled=True)
        assert channel._should_deliver_to_target(test_notification, target1) is True

        # Disabled target
        target2 = WebhookTarget(name="disabled", url="https://example.com/webhook", enabled=False)
        assert channel._should_deliver_to_target(test_notification, target2) is False

        # Type filtering (should match)
        target3 = WebhookTarget(
            name="type-match",
            url="https://example.com/webhook",
            notification_types=["info", "warning"],
        )
        assert channel._should_deliver_to_target(test_notification, target3) is True

        # Type filtering (should not match)
        target4 = WebhookTarget(
            name="type-no-match", url="https://example.com/webhook", notification_types=["error"]
        )
        assert channel._should_deliver_to_target(test_notification, target4) is False

        # Tag filtering (should match)
        target5 = WebhookTarget(
            name="tag-match", url="https://example.com/webhook", tags_filter=["test"]
        )
        assert channel._should_deliver_to_target(test_notification, target5) is True

        # Tag filtering (should not match)
        target6 = WebhookTarget(
            name="tag-no-match", url="https://example.com/webhook", tags_filter=["production"]
        )
        assert channel._should_deliver_to_target(test_notification, target6) is False

    def test_build_payload(self, channel, test_notification, test_target):
        """Test payload building."""
        payload = channel._build_payload(test_notification, test_target)

        assert payload["id"] == test_notification.id
        assert payload["event_type"] == "notification"
        assert payload["notification"]["title"] == test_notification.title
        assert payload["notification"]["message"] == test_notification.message
        assert payload["notification"]["level"] == test_notification.level.value
        assert payload["notification"]["tags"] == test_notification.tags
        assert payload["webhook"]["target"] == test_target.name
        assert payload["metadata"]["app_name"] == "CoachIQ"

    def test_build_headers_no_auth(self, channel, test_target):
        """Test header building without authentication."""
        payload = {"test": "data"}
        headers = channel._build_headers(test_target, payload)

        assert headers["Content-Type"] == "application/json"
        assert headers["X-Webhook-Event"] == "notification"
        assert headers["X-Webhook-Target"] == test_target.name
        assert "X-Webhook-Timestamp" in headers
        assert "Authorization" not in headers

    def test_build_headers_bearer_auth(self, channel):
        """Test header building with bearer authentication."""
        auth = WebhookAuthConfig(type="bearer", bearer_token="test-token")
        target = WebhookTarget(name="test", url="https://example.com/webhook", auth=auth)
        payload = {"test": "data"}

        headers = channel._build_headers(target, payload)
        assert headers["Authorization"] == "Bearer test-token"

    def test_build_headers_apikey_auth(self, channel):
        """Test header building with API key authentication."""
        auth = WebhookAuthConfig(type="apikey", api_key="test-key", api_key_header="X-API-Key")
        target = WebhookTarget(name="test", url="https://example.com/webhook", auth=auth)
        payload = {"test": "data"}

        headers = channel._build_headers(target, payload)
        assert headers["X-API-Key"] == "test-key"

    def test_build_headers_basic_auth(self, channel):
        """Test header building with basic authentication."""
        auth = WebhookAuthConfig(type="basic", username="user", password="pass")
        target = WebhookTarget(name="test", url="https://example.com/webhook", auth=auth)
        payload = {"test": "data"}

        headers = channel._build_headers(target, payload)
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

    def test_build_headers_with_signature(self, channel):
        """Test header building with signature."""
        target = WebhookTarget(
            name="test",
            url="https://example.com/webhook",
            secret_key="secret",
            signature_header="X-Hub-Signature",
        )
        payload = {"test": "data"}

        headers = channel._build_headers(target, payload)
        assert "X-Hub-Signature" in headers
        assert headers["X-Hub-Signature"].startswith("sha256=")

    def test_build_headers_custom_headers(self, channel):
        """Test header building with custom headers."""
        auth = WebhookAuthConfig(
            type="none", custom_headers={"X-Custom": "value", "X-Source": "coachiq"}
        )
        target = WebhookTarget(name="test", url="https://example.com/webhook", auth=auth)
        payload = {"test": "data"}

        headers = channel._build_headers(target, payload)
        assert headers["X-Custom"] == "value"
        assert headers["X-Source"] == "coachiq"

    @pytest.mark.asyncio
    async def test_send_notification_disabled_channel(self, channel, test_notification):
        """Test sending notification when channel is disabled."""
        channel.enabled = False
        result = await channel.send_notification(test_notification)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_no_targets(self, channel, test_notification):
        """Test sending notification when no targets are configured."""
        result = await channel.send_notification(test_notification)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_rate_limited(self, channel, test_notification, test_target):
        """Test sending notification when rate limited."""
        channel.add_target(test_target)

        # Exhaust rate limit
        for _ in range(channel.rate_limit_requests + 1):
            channel._check_rate_limit()

        result = await channel.send_notification(test_notification)
        assert result is False
        assert channel.stats["rate_limited"] > 0

    @pytest.mark.asyncio
    async def test_context_manager(self, channel):
        """Test webhook channel as async context manager."""
        async with channel as ctx:
            assert ctx == channel
            assert channel._session is not None

    def test_get_status(self, channel, test_target):
        """Test getting channel status."""
        channel.add_target(test_target)
        status = channel.get_status()

        assert status["enabled"] is True
        assert status["targets_configured"] == 1
        assert status["targets_enabled"] == 1
        assert "rate_limit" in status
        assert "statistics" in status
        assert status["session_active"] is False  # Not in context manager


class TestWebhookDelivery:
    """Test webhook delivery functionality with mocked HTTP responses."""

    @pytest.fixture
    def channel(self):
        """Create webhook channel for testing."""
        return WebhookNotificationChannel()

    @pytest.fixture
    def test_target(self):
        """Create test webhook target."""
        return WebhookTarget(
            name="test-webhook",
            url="https://httpbin.org/post",  # Test endpoint
            enabled=True,
            timeout=5,
            max_retries=1,
        )

    @pytest.fixture
    def test_notification(self):
        """Create test notification payload."""
        return NotificationPayload(
            message="Test webhook delivery",
            title="Test Notification",
            level=NotificationType.WARNING,
            channels=[NotificationChannel.WEBHOOK],
            tags=["test", "delivery"],
            source_component="WebhookDeliveryTest",
        )

    @pytest.mark.asyncio
    async def test_successful_delivery(self, channel, test_target, test_notification):
        """Test successful webhook delivery."""
        channel.add_target(test_target)

        with patch("aiohttp.ClientSession.request") as mock_request:
            # Mock successful response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value="OK")
            mock_request.return_value.__aenter__.return_value = mock_response

            async with channel:
                result = await channel.send_notification(test_notification)

            assert result is True
            assert channel.stats["successful_requests"] == 1
            assert channel.stats["total_requests"] == 1

    @pytest.mark.asyncio
    async def test_failed_delivery_4xx(self, channel, test_target, test_notification):
        """Test failed webhook delivery with 4xx response."""
        channel.add_target(test_target)

        with patch("aiohttp.ClientSession.request") as mock_request:
            # Mock 400 Bad Request response
            mock_response = AsyncMock()
            mock_response.status = 400
            mock_response.text = AsyncMock(return_value="Bad Request")
            mock_request.return_value.__aenter__.return_value = mock_response

            async with channel:
                result = await channel.send_notification(test_notification)

            assert result is False
            assert channel.stats["failed_requests"] == 1

    @pytest.mark.asyncio
    async def test_failed_delivery_5xx(self, channel, test_target, test_notification):
        """Test failed webhook delivery with 5xx response."""
        channel.add_target(test_target)

        with patch("aiohttp.ClientSession.request") as mock_request:
            # Mock 500 Internal Server Error response
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Internal Server Error")
            mock_request.return_value.__aenter__.return_value = mock_response

            async with channel:
                result = await channel.send_notification(test_notification)

            assert result is False
            assert channel.stats["failed_requests"] == 1

    @pytest.mark.asyncio
    async def test_timeout_error(self, channel, test_target, test_notification):
        """Test webhook delivery timeout."""
        channel.add_target(test_target)

        with patch("aiohttp.ClientSession.request") as mock_request:
            # Mock timeout error
            mock_request.side_effect = TimeoutError()

            async with channel:
                result = await channel.send_notification(test_notification)

            assert result is False
            assert channel.stats["failed_requests"] == 1

    @pytest.mark.asyncio
    async def test_connection_error(self, channel, test_target, test_notification):
        """Test webhook delivery connection error."""
        channel.add_target(test_target)

        with patch("aiohttp.ClientSession.request") as mock_request:
            # Mock connection error
            mock_request.side_effect = ClientError("Connection failed")

            async with channel:
                result = await channel.send_notification(test_notification)

            assert result is False
            assert channel.stats["failed_requests"] == 1

    @pytest.mark.asyncio
    async def test_retry_logic(self, channel, test_notification):
        """Test webhook delivery retry logic."""
        # Target with 2 retries
        target = WebhookTarget(
            name="retry-test",
            url="https://httpbin.org/post",
            max_retries=2,
            retry_delay=0.1,  # Fast retry for testing
            retry_exponential=True,
        )
        channel.add_target(target)

        with patch("aiohttp.ClientSession.request") as mock_request:
            # Mock failure then success
            mock_response_fail = AsyncMock()
            mock_response_fail.status = 500
            mock_response_fail.text = AsyncMock(return_value="Server Error")

            mock_response_success = AsyncMock()
            mock_response_success.status = 200
            mock_response_success.text = AsyncMock(return_value="OK")

            # First call fails, second succeeds
            mock_request.return_value.__aenter__.side_effect = [
                mock_response_fail,
                mock_response_success,
            ]

            async with channel:
                result = await channel.send_notification(test_notification)

            assert result is True
            assert channel.stats["retries"] == 1
            assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_targets(self, channel, test_notification):
        """Test delivery to multiple webhook targets."""
        # Add two targets
        target1 = WebhookTarget(name="target1", url="https://example.com/webhook1")
        target2 = WebhookTarget(name="target2", url="https://example.com/webhook2")
        channel.add_target(target1)
        channel.add_target(target2)

        with patch("aiohttp.ClientSession.request") as mock_request:
            # Mock success for both
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value="OK")
            mock_request.return_value.__aenter__.return_value = mock_response

            async with channel:
                result = await channel.send_notification(test_notification)

            assert result is True
            assert mock_request.call_count == 2  # One call per target

    @pytest.mark.asyncio
    async def test_partial_success(self, channel, test_notification):
        """Test delivery with partial success (one target succeeds, one fails)."""
        # Add two targets
        target1 = WebhookTarget(name="success", url="https://example.com/webhook1")
        target2 = WebhookTarget(name="failure", url="https://example.com/webhook2")
        channel.add_target(target1)
        channel.add_target(target2)

        with patch("aiohttp.ClientSession.request") as mock_request:
            # Mock success then failure
            mock_response_success = AsyncMock()
            mock_response_success.status = 200
            mock_response_success.text = AsyncMock(return_value="OK")

            mock_response_fail = AsyncMock()
            mock_response_fail.status = 500
            mock_response_fail.text = AsyncMock(return_value="Error")

            mock_request.return_value.__aenter__.side_effect = [
                mock_response_success,
                mock_response_fail,
            ]

            async with channel:
                result = await channel.send_notification(test_notification)

            # Should return True because at least one delivery succeeded
            assert result is True
            assert channel.stats["successful_requests"] == 1
            assert channel.stats["failed_requests"] == 1


class TestWebhookModuleFunctions:
    """Test module-level webhook functions."""

    @pytest.mark.asyncio
    async def test_send_webhook_notification(self):
        """Test send_webhook_notification function."""
        notification = NotificationPayload(
            message="Test function call",
            title="Function Test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.WEBHOOK],
        )

        with patch(
            "backend.integrations.notifications.channels.webhook.webhook_channel"
        ) as mock_channel:
            mock_channel.send_notification = AsyncMock(return_value=True)

            result = await send_webhook_notification(notification)

            assert result is True
            mock_channel.send_notification.assert_called_once_with(notification)

    @pytest.mark.asyncio
    async def test_test_webhook_channels(self):
        """Test test_webhook_channels function."""
        expected_results = {"webhook-1": True, "webhook-2": False}

        with patch(
            "backend.integrations.notifications.channels.webhook.webhook_channel"
        ) as mock_channel:
            mock_channel.test_connection = AsyncMock(return_value=expected_results)

            results = await test_webhook_channels()

            assert results == expected_results
            mock_channel.test_connection.assert_called_once()


@pytest.mark.integration
class TestWebhookIntegration:
    """Integration tests for webhook functionality (requires network)."""

    @pytest.mark.asyncio
    async def test_real_webhook_delivery(self):
        """Test delivery to a real webhook endpoint (httpbin.org)."""
        channel = WebhookNotificationChannel()
        target = WebhookTarget(
            name="httpbin-test",
            url="https://httpbin.org/post",
            timeout=10,
            max_retries=1,
        )
        channel.add_target(target)

        notification = NotificationPayload(
            message="Integration test notification",
            title="Integration Test",
            level=NotificationType.INFO,
            channels=[NotificationChannel.WEBHOOK],
            tags=["integration", "test"],
            source_component="WebhookIntegrationTest",
        )

        async with channel:
            result = await channel.send_notification(notification)

        # Should succeed with real endpoint
        assert result is True
        assert channel.stats["successful_requests"] >= 1

    @pytest.mark.asyncio
    async def test_unreachable_endpoint(self):
        """Test delivery to unreachable endpoint."""
        channel = WebhookNotificationChannel()
        target = WebhookTarget(
            name="unreachable",
            url="https://unreachable.example.invalid/webhook",
            timeout=2,
            max_retries=0,
        )
        channel.add_target(target)

        notification = NotificationPayload(
            message="Test unreachable endpoint",
            title="Unreachable Test",
            level=NotificationType.ERROR,
            channels=[NotificationChannel.WEBHOOK],
        )

        async with channel:
            result = await channel.send_notification(notification)

        # Should fail with unreachable endpoint
        assert result is False
        assert channel.stats["failed_requests"] >= 1
