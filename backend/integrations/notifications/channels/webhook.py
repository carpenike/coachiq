"""
Webhook Notification Channel for External System Integration

This module provides webhook-based notification delivery for integrating with
external systems, APIs, and services. Supports multiple webhook targets,
retry logic, authentication, and comprehensive error handling.

Key Features:
- HTTP/HTTPS webhook delivery with configurable timeouts
- Multiple authentication methods (Bearer token, API key, Basic auth)
- Retry logic with exponential backoff
- Request/response logging and validation
- Webhook signature verification for security
- Template-based payload customization
- Rate limiting and circuit breaker patterns

Example Configuration:
    COACHIQ_NOTIFICATIONS__WEBHOOK__ENABLED=true
    COACHIQ_NOTIFICATIONS__WEBHOOK__DEFAULT_TIMEOUT=30
    COACHIQ_NOTIFICATIONS__WEBHOOK__MAX_RETRIES=3
    COACHIQ_NOTIFICATIONS__WEBHOOK__VERIFY_SSL=true
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Any

import aiohttp
from pydantic import BaseModel, Field, HttpUrl, validator

from backend.core.config import get_settings
from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationStatus,
    NotificationType,
)


class WebhookAuthConfig(BaseModel):
    """Authentication configuration for webhook requests."""

    type: str = Field("none", description="Authentication type (none, bearer, apikey, basic)")

    # Bearer token authentication
    bearer_token: str | None = Field(None, description="Bearer token for Authorization header")

    # API key authentication
    api_key: str | None = Field(None, description="API key value")
    api_key_header: str = Field("X-API-Key", description="Header name for API key")

    # Basic authentication
    username: str | None = Field(None, description="Username for basic auth")
    password: str | None = Field(None, description="Password for basic auth")

    # Custom headers
    custom_headers: dict[str, str] = Field(default_factory=dict, description="Additional headers")

    @validator("type")
    def validate_auth_type(cls, v):
        allowed_types = ["none", "bearer", "apikey", "basic"]
        if v not in allowed_types:
            msg = f"Authentication type must be one of: {allowed_types}"
            raise ValueError(msg)
        return v


class WebhookTarget(BaseModel):
    """Configuration for a webhook target endpoint."""

    name: str = Field(..., description="Unique name for webhook target")
    url: HttpUrl = Field(..., description="Webhook endpoint URL")
    enabled: bool = Field(True, description="Whether webhook is enabled")

    # Request configuration
    method: str = Field("POST", description="HTTP method")
    timeout: int = Field(30, description="Request timeout in seconds")
    verify_ssl: bool = Field(True, description="Whether to verify SSL certificates")

    # Authentication
    auth: WebhookAuthConfig = Field(default_factory=WebhookAuthConfig)

    # Payload configuration
    content_type: str = Field("application/json", description="Content-Type header")
    payload_template: str | None = Field(None, description="Custom payload template")

    # Retry configuration
    max_retries: int = Field(3, description="Maximum retry attempts")
    retry_delay: int = Field(1, description="Initial retry delay in seconds")
    retry_exponential: bool = Field(True, description="Use exponential backoff")

    # Security
    secret_key: str | None = Field(None, description="Secret key for signature verification")
    signature_header: str = Field("X-Webhook-Signature", description="Header for signature")

    # Filtering
    notification_types: list[str] = Field(
        default_factory=list, description="Filter by notification types"
    )
    tags_filter: list[str] = Field(default_factory=list, description="Filter by tags")

    @validator("method")
    def validate_method(cls, v):
        allowed_methods = ["GET", "POST", "PUT", "PATCH"]
        if v.upper() not in allowed_methods:
            msg = f"HTTP method must be one of: {allowed_methods}"
            raise ValueError(msg)
        return v.upper()


class WebhookDeliveryResult(BaseModel):
    """Result of webhook delivery attempt."""

    success: bool = Field(..., description="Whether delivery was successful")
    status_code: int | None = Field(None, description="HTTP response status code")
    response_body: str | None = Field(None, description="Response body (truncated)")
    error_message: str | None = Field(None, description="Error message if failed")
    duration_ms: float = Field(..., description="Request duration in milliseconds")
    attempt_number: int = Field(1, description="Attempt number (1-based)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Delivery timestamp")


class WebhookNotificationChannel:
    """
    Webhook notification channel for external system integration.

    Handles delivery of notifications to external HTTP endpoints with
    comprehensive retry logic, authentication, and security features.
    """

    def __init__(self):
        """Initialize webhook notification channel."""
        self.logger = logging.getLogger(f"{__name__}.WebhookNotificationChannel")
        self.settings = get_settings()

        # Channel configuration
        self.channel = NotificationChannel.WEBHOOK
        self.enabled = self._get_setting("enabled", True)
        self.default_timeout = self._get_setting("default_timeout", 30)
        self.max_retries = self._get_setting("max_retries", 3)
        self.verify_ssl = self._get_setting("verify_ssl", True)
        self.rate_limit_requests = self._get_setting("rate_limit_requests", 100)
        self.rate_limit_window = self._get_setting("rate_limit_window", 60)

        # Webhook targets
        self.targets: dict[str, WebhookTarget] = {}
        self._load_webhook_targets()

        # Rate limiting
        self._request_timestamps: list[float] = []

        # HTTP session
        self._session: aiohttp.ClientSession | None = None

        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "retries": 0,
            "rate_limited": 0,
            "last_success": None,
            "last_failure": None,
        }

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._close_session()

    def _get_setting(self, key: str, default: Any = None) -> Any:
        """Get webhook-specific setting."""
        return getattr(self.settings.notifications.webhook, key, default)

    def _load_webhook_targets(self) -> None:
        """Load webhook targets from configuration."""
        # Load from settings or configuration file
        # For now, using environment-based configuration
        try:
            webhook_config = self._get_setting("targets", {})
            for name, config in webhook_config.items():
                try:
                    target = WebhookTarget(name=name, **config)
                    self.targets[name] = target
                    self.logger.info(f"Loaded webhook target: {name} -> {target.url}")
                except Exception as e:
                    self.logger.error(f"Failed to load webhook target {name}: {e}")
        except Exception as e:
            self.logger.error(f"Failed to load webhook targets: {e}")

    async def _ensure_session(self) -> None:
        """Ensure HTTP session is available."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.default_timeout)
            connector = aiohttp.TCPConnector(verify_ssl=self.verify_ssl)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    "User-Agent": "CoachIQ-Webhook-Client/1.0",
                },
            )

    async def _close_session(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _check_rate_limit(self) -> bool:
        """Check if rate limit allows request."""
        current_time = time.time()

        # Remove old timestamps outside the window
        cutoff_time = current_time - self.rate_limit_window
        self._request_timestamps = [ts for ts in self._request_timestamps if ts > cutoff_time]

        # Check if we can make another request
        if len(self._request_timestamps) >= self.rate_limit_requests:
            self.stats["rate_limited"] += 1
            return False

        # Record this request
        self._request_timestamps.append(current_time)
        return True

    def _build_payload(
        self, notification: NotificationPayload, target: WebhookTarget
    ) -> dict[str, Any]:
        """Build webhook payload from notification."""
        if target.payload_template:
            # Use custom template (would implement Jinja2 rendering here)
            # For now, use default payload structure
            pass

        # Default payload structure
        payload = {
            "id": notification.id,
            "timestamp": notification.created_at.isoformat(),
            "event_type": "notification",
            "notification": {
                "title": notification.title,
                "message": notification.message,
                "level": notification.level.value,
                "tags": notification.tags,
                "recipient": notification.recipient,
                "source_component": notification.source_component,
                "correlation_id": notification.correlation_id,
            },
            "webhook": {
                "target": target.name,
                "delivery_attempt": notification.retry_count + 1,
            },
            "metadata": {
                "app_name": "CoachIQ",
                "version": "1.0",
                "environment": getattr(self.settings, "environment", "production"),
            },
        }

        # Add context data if available
        if notification.context:
            payload["notification"]["context"] = notification.context

        return payload

    def _build_headers(self, target: WebhookTarget, payload: dict[str, Any]) -> dict[str, str]:
        """Build HTTP headers for webhook request."""
        headers = {
            "Content-Type": target.content_type,
            "X-Webhook-Event": "notification",
            "X-Webhook-Target": target.name,
            "X-Webhook-Timestamp": str(int(time.time())),
        }

        # Authentication headers
        if target.auth.type == "bearer" and target.auth.bearer_token:
            headers["Authorization"] = f"Bearer {target.auth.bearer_token}"
        elif target.auth.type == "apikey" and target.auth.api_key:
            headers[target.auth.api_key_header] = target.auth.api_key
        elif target.auth.type == "basic" and target.auth.username and target.auth.password:
            import base64

            credentials = base64.b64encode(
                f"{target.auth.username}:{target.auth.password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {credentials}"

        # Custom headers
        headers.update(target.auth.custom_headers)

        # Signature header
        if target.secret_key:
            payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            signature = hmac.new(
                target.secret_key.encode(), payload_str.encode(), hashlib.sha256
            ).hexdigest()
            headers[target.signature_header] = f"sha256={signature}"

        return headers

    def _should_deliver_to_target(
        self, notification: NotificationPayload, target: WebhookTarget
    ) -> bool:
        """Check if notification should be delivered to target."""
        if not target.enabled:
            return False

        # Filter by notification types
        if target.notification_types and notification.level.value not in target.notification_types:
            return False

        # Filter by tags
        if target.tags_filter:
            if not any(tag in notification.tags for tag in target.tags_filter):
                return False

        return True

    async def _deliver_to_target(
        self, notification: NotificationPayload, target: WebhookTarget
    ) -> WebhookDeliveryResult:
        """Deliver notification to specific webhook target."""
        start_time = time.time()

        try:
            # Build payload and headers
            payload = self._build_payload(notification, target)
            headers = self._build_headers(target, payload)

            # Prepare request data
            if target.method in ["POST", "PUT", "PATCH"]:
                if target.content_type == "application/json":
                    request_data = json.dumps(payload)
                else:
                    request_data = str(payload)
            else:
                request_data = None

            # Make HTTP request
            await self._ensure_session()

            if self._session is None:
                raise RuntimeError("HTTP session not initialized")

            async with self._session.request(
                method=target.method,
                url=str(target.url),
                data=request_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=target.timeout),
            ) as response:
                response_body = await response.text()

                # Truncate long responses
                if len(response_body) > 1000:
                    response_body = response_body[:1000] + "... (truncated)"

                duration_ms = (time.time() - start_time) * 1000

                # Check if successful
                success = 200 <= response.status < 300

                if success:
                    self.stats["successful_requests"] += 1
                    self.stats["last_success"] = datetime.utcnow()
                else:
                    self.stats["failed_requests"] += 1
                    self.stats["last_failure"] = datetime.utcnow()

                return WebhookDeliveryResult(
                    success=success,
                    status_code=response.status,
                    response_body=response_body,
                    error_message=None if success else f"HTTP {response.status}",
                    duration_ms=duration_ms,
                    attempt_number=notification.retry_count + 1,
                )

        except TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            self.stats["failed_requests"] += 1
            self.stats["last_failure"] = datetime.utcnow()

            return WebhookDeliveryResult(
                success=False,
                status_code=None,
                response_body=None,
                error_message="Request timeout",
                duration_ms=duration_ms,
                attempt_number=notification.retry_count + 1,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.stats["failed_requests"] += 1
            self.stats["last_failure"] = datetime.utcnow()

            return WebhookDeliveryResult(
                success=False,
                status_code=None,
                response_body=None,
                error_message=str(e),
                duration_ms=duration_ms,
                attempt_number=notification.retry_count + 1,
            )

    async def send_notification(self, notification: NotificationPayload) -> bool:
        """
        Send notification via webhook to all configured targets.

        Args:
            notification: Notification payload to send

        Returns:
            bool: True if at least one webhook delivery succeeded
        """
        if not self.enabled:
            self.logger.debug("Webhook channel is disabled")
            return False

        if not self.targets:
            self.logger.warning("No webhook targets configured")
            return False

        # Check rate limiting
        if not self._check_rate_limit():
            self.logger.warning("Webhook rate limit exceeded")
            return False

        self.stats["total_requests"] += 1
        successful_deliveries = 0
        total_targets = 0

        # Deliver to all applicable targets
        for target_name, target in self.targets.items():
            if not self._should_deliver_to_target(notification, target):
                continue

            total_targets += 1
            max_attempts = target.max_retries + 1

            for attempt in range(max_attempts):
                if attempt > 0:
                    # Calculate retry delay
                    delay = target.retry_delay
                    if target.retry_exponential:
                        delay = target.retry_delay * (2 ** (attempt - 1))

                    self.logger.info(
                        f"Retrying webhook delivery to {target_name} "
                        f"(attempt {attempt + 1}/{max_attempts}) after {delay}s"
                    )
                    await asyncio.sleep(delay)
                    self.stats["retries"] += 1

                # Attempt delivery
                result = await self._deliver_to_target(notification, target)

                self.logger.info(
                    f"Webhook delivery to {target_name}: "
                    f"{'SUCCESS' if result.success else 'FAILED'} "
                    f"(status: {result.status_code}, duration: {result.duration_ms:.1f}ms)"
                )

                if result.success:
                    successful_deliveries += 1
                    break  # Success, no need to retry
                if attempt == max_attempts - 1:
                    # Final attempt failed
                    self.logger.error(
                        f"Webhook delivery to {target_name} failed after {max_attempts} attempts: "
                        f"{result.error_message}"
                    )

        # Return True if at least one delivery succeeded
        return successful_deliveries > 0

    async def test_connection(self) -> dict[str, bool]:
        """
        Test webhook connections to all configured targets.

        Returns:
            Dict mapping target names to test results
        """
        if not self.enabled:
            return {"webhook": False}

        results = {}

        # Create test notification
        test_notification = NotificationPayload(
            message="Test notification from CoachIQ webhook channel",
            title="Webhook Test",
            level=NotificationType.INFO,
            recipient=None,
            template=None,
            status=NotificationStatus.PENDING,
            retry_count=0,
            max_retries=3,
            scheduled_for=None,
            priority=1,
            last_error=None,
            last_attempt=None,
            source_component="WebhookNotificationChannel",
            correlation_id=None,
            pushover_priority=None,
            pushover_device=None,
            tags=["test", "webhook"],
        )

        for target_name, target in self.targets.items():
            try:
                result = await self._deliver_to_target(test_notification, target)
                results[target_name] = result.success

                if result.success:
                    self.logger.info(f"Webhook test to {target_name}: SUCCESS")
                else:
                    self.logger.warning(
                        f"Webhook test to {target_name}: FAILED - {result.error_message}"
                    )

            except Exception as e:
                self.logger.error(f"Webhook test to {target_name} failed: {e}")
                results[target_name] = False

        return results

    def get_status(self) -> dict[str, Any]:
        """Get webhook channel status and statistics."""
        return {
            "enabled": self.enabled,
            "targets_configured": len(self.targets),
            "targets_enabled": sum(1 for t in self.targets.values() if t.enabled),
            "rate_limit": {
                "requests_per_window": self.rate_limit_requests,
                "window_seconds": self.rate_limit_window,
                "current_requests": len(self._request_timestamps),
            },
            "statistics": self.stats.copy(),
            "session_active": self._session is not None and not self._session.closed,
        }

    def add_target(self, target: WebhookTarget) -> None:
        """Add or update webhook target."""
        self.targets[target.name] = target
        self.logger.info(f"Added webhook target: {target.name} -> {target.url}")

    def remove_target(self, name: str) -> bool:
        """Remove webhook target by name."""
        if name in self.targets:
            del self.targets[name]
            self.logger.info(f"Removed webhook target: {name}")
            return True
        return False

    def get_target(self, name: str) -> WebhookTarget | None:
        """Get webhook target by name."""
        return self.targets.get(name)

    def list_targets(self) -> list[str]:
        """List all webhook target names."""
        return list(self.targets.keys())


# Global webhook channel instance
webhook_channel = WebhookNotificationChannel()


async def send_webhook_notification(notification: NotificationPayload) -> bool:
    """
    Send notification via webhook channel.

    Args:
        notification: Notification to send

    Returns:
        bool: True if delivery succeeded
    """
    async with webhook_channel:
        return await webhook_channel.send_notification(notification)


async def test_webhook_channels() -> dict[str, bool]:
    """
    Test all webhook channels.

    Returns:
        Dict mapping webhook target names to test results
    """
    async with webhook_channel:
        return await webhook_channel.test_connection()
