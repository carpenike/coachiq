"""
Safe Notification Manager with Queue, Rate Limiting, and Input Sanitization

This module provides a safety-hardened notification manager designed for
RV-C vehicle environments where reliability and security are critical.
Integrates persistent queuing, rate limiting, and template sanitization.

Key Features:
- Non-blocking async queue-based operations
- Token bucket rate limiting with CAN bus flood protection
- Notification debouncing to prevent spam
- Jinja2 template sanitization against injection attacks
- Comprehensive error handling and monitoring
- Pushover integration with priority mapping

Example:
    >>> manager = SafeNotificationManager(config)
    >>> await manager.initialize()
    >>> success = await manager.notify(
    ...     message="Water tank low",
    ...     level="warning",
    ...     channels=["pushover", "email"]
    ... )
"""

import logging
import re
from datetime import datetime
from typing import Any

try:
    from jinja2 import StrictUndefined, select_autoescape
    from jinja2.exceptions import SecurityError, TemplateError
    from jinja2.filters import FILTERS as DEFAULT_FILTERS
    from jinja2.sandbox import SandboxedEnvironment

    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

from backend.core.config import NotificationSettings
from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationStatus,
    NotificationType,
    QueueStatistics,
    RateLimitStatus,
)
from backend.services.email_template_manager import EmailTemplateManager
from backend.services.notification_queue import NotificationQueue
from backend.services.notification_rate_limiting import (
    ChannelSpecificRateLimiter,
    NotificationDebouncer,
    TokenBucketRateLimiter,
    create_message_hash,
)
from backend.services.notification_routing import NotificationRouter, SystemContext


class SafeNotificationManager:
    """
    Safety-hardened notification manager for RV-C environments.

    Provides all the functionality of the original NotificationManager
    but with enhanced safety features including:
    - Persistent queue for reliability
    - Rate limiting for CAN bus protection
    - Input sanitization for security
    - Non-blocking async operations
    """

    def __init__(self, config: NotificationSettings):
        """
        Initialize SafeNotificationManager.

        Args:
            config: NotificationSettings configuration
        """
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.SafeNotificationManager")

        # Core components
        self.queue: NotificationQueue | None = None
        self.rate_limiter: TokenBucketRateLimiter | None = None
        self.debouncer: NotificationDebouncer | None = None
        self.channel_rate_limiter: ChannelSpecificRateLimiter | None = None

        # Template management
        self.template_manager: EmailTemplateManager | None = None
        self.template_sandbox: Any | None = None
        self._setup_template_sandbox()

        # Advanced routing
        self.router: NotificationRouter | None = None

        # Pushover priority mapping
        self.pushover_priority_mapping = {
            NotificationType.CRITICAL: 1,  # High priority, bypass quiet hours
            NotificationType.ERROR: 1,  # High priority
            NotificationType.WARNING: 0,  # Normal priority
            NotificationType.INFO: -1,  # Low priority
            NotificationType.SUCCESS: -1,  # Low priority
        }

        # Statistics tracking
        self.stats = {
            "total_notifications": 0,
            "successful_notifications": 0,
            "rate_limited_notifications": 0,
            "debounced_notifications": 0,
            "failed_notifications": 0,
            "sanitization_failures": 0,
        }

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all components."""
        try:
            # Initialize queue. Fields below were previously read via
            # ``getattr(..., default)`` because they weren't defined on
            # ``NotificationSettings``; now that they are real fields,
            # access them directly so misconfiguration surfaces loudly.
            self.queue = NotificationQueue(self.config.queue_db_path)
            await self.queue.initialize()

            # Initialize rate limiting
            self.rate_limiter = TokenBucketRateLimiter(
                max_tokens=self.config.rate_limit_max_tokens,
                refill_rate=self.config.rate_limit_per_minute,
            )

            # Initialize debouncing
            self.debouncer = NotificationDebouncer(
                suppress_window_minutes=self.config.debounce_minutes
            )

            # Initialize per-channel rate limiting
            self.channel_rate_limiter = ChannelSpecificRateLimiter()

            # Initialize email template manager.
            # Earlier revisions only created this when ``self.config.smtp.enabled``,
            # which conflated "user wants to send via SMTP" with "user wants
            # to render templates". Templates are also useful for non-SMTP
            # channels (system log structured rendering, magic-link previews
            # in tests, etc.), and ``create_email_template`` /
            # ``render_template_preview`` failed silently when SMTP was off.
            # Always construct the template manager; it has no SMTP-specific
            # initialisation cost.
            self.template_manager = EmailTemplateManager(self.config)
            await self.template_manager.initialize()

            # Initialize notification router
            self.router = NotificationRouter()
            await self.router.initialize()

            self._initialized = True
            self.logger.info("SafeNotificationManager initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize SafeNotificationManager: {e}")
            raise

    async def notify(
        self,
        message: str,
        title: str | None = None,
        level: str | NotificationType = NotificationType.INFO,
        channels: list[str] | None = None,
        tags: list[str] | None = None,
        template: str | None = None,
        context: dict[str, Any] | None = None,
        recipient: str | None = None,
        priority: int = 1,
        scheduled_for: datetime | None = None,
        **kwargs,
    ) -> bool:
        """
        Send notification through safe queue-based system.

        Args:
            message: Notification message body
            title: Optional notification title
            level: Notification level (info, warning, error, critical)
            channels: Target channels (defaults to all enabled)
            tags: Optional notification tags
            template: Optional template name
            context: Template context data (will be sanitized)
            recipient: Primary recipient identifier
            priority: Priority level (1=highest, 10=lowest)
            scheduled_for: Optional scheduled delivery time
            **kwargs: Additional notification parameters

        Returns:
            bool: True if notification was queued successfully
        """
        if not self._initialized:
            await self.initialize()

        self.stats["total_notifications"] += 1

        try:
            # Normalize level
            if isinstance(level, str):
                level = NotificationType(level.lower())

            # Create message hash for rate limiting and deduplication
            message_hash = create_message_hash(message, context)

            # Apply rate limiting
            if self.rate_limiter and not await self.rate_limiter.allow(message_hash):
                self.stats["rate_limited_notifications"] += 1
                self.logger.warning(f"Rate limited notification: {message[:50]}...")
                return False

            # Apply debouncing
            debounce_key = f"{level.value}:{message_hash}"
            if self.debouncer and not await self.debouncer.allow(
                message, level.value, debounce_key
            ):
                self.stats["debounced_notifications"] += 1
                return False  # Suppressed duplicate

            # Sanitize template context if provided
            sanitized_context = {}
            if context:
                sanitized_context = await self._sanitize_context(context)
                if sanitized_context is None:
                    self.stats["sanitization_failures"] += 1
                    self.logger.error("Context sanitization failed, dropping notification")
                    return False

            # Create preliminary notification for routing
            preliminary_notification = NotificationPayload(
                message=message,
                title=title or self.config.default_title,
                level=level,
                channels=[],  # Will be determined by router
                tags=tags or [],
                recipient=recipient,
                template=template,
                context=sanitized_context,
                priority=priority,
                scheduled_for=scheduled_for,
                status=NotificationStatus.PENDING,
                retry_count=0,
                max_retries=3,
                last_error=None,
                last_attempt=None,
                source_component=kwargs.get("source_component"),
                correlation_id=kwargs.get("correlation_id"),
                pushover_priority=self._get_pushover_priority(level),
                pushover_device=kwargs.get("pushover_device"),
            )

            # Use router to determine optimal channels if available
            # AND the caller didn't explicitly request specific channels.
            # When ``channels`` is explicitly supplied, honour the
            # caller's intent rather than letting the router second-guess
            # them. Earlier revisions silently discarded the explicit
            # ``channels`` argument and let routing decide -- a real
            # API contract violation that broke any caller that wanted
            # to pin a notification to e.g. the local "system" channel
            # only (e.g. structured-log fan-out, integration tests).
            if self.router and not channels:
                system_context = SystemContext(
                    queue_depth=await self._get_queue_depth(),
                    connectivity_status=self._get_connectivity_status(),
                )

                routing_decision = await self.router.determine_route(
                    preliminary_notification,
                    user_id=kwargs.get("user_id"),
                    system_context=system_context,
                )

                target_channels = [ch.value for ch in routing_decision.target_channels]

                # Update notification with routing decision
                preliminary_notification.scheduled_for = routing_decision.scheduled_for

            else:
                # Caller-supplied channels OR no router available: use the
                # explicit channel list (or all enabled channels if not
                # supplied).
                target_channels = self._resolve_target_channels(channels)

            # Apply per-channel rate limiting
            allowed_channels = []
            for channel in target_channels:
                if self.channel_rate_limiter and await self.channel_rate_limiter.allow(
                    channel, message_hash
                ):
                    allowed_channels.append(channel)
                elif not self.channel_rate_limiter:
                    # No channel rate limiting configured, allow all
                    allowed_channels.append(channel)
                else:
                    self.logger.debug(f"Channel {channel} rate limited for: {message[:30]}...")

            if not allowed_channels:
                self.logger.warning("All channels rate limited, dropping notification")
                return False

            # Update preliminary notification with final channels
            preliminary_notification.channels = [NotificationChannel(ch) for ch in allowed_channels]

            # Queue for delivery
            if self.queue:
                notification_id = await self.queue.enqueue(preliminary_notification)
            else:
                notification_id = preliminary_notification.id

            self.stats["successful_notifications"] += 1
            self.logger.info(f"Queued notification {notification_id}: {message[:50]}...")

            return True

        except Exception as e:
            self.stats["failed_notifications"] += 1
            self.logger.error(f"Failed to queue notification: {e}")
            return False

    async def send_email(
        self,
        to_email: str,
        subject: str | None = None,
        template: str = "system_notification",
        context: dict[str, Any] | None = None,
        from_email: str | None = None,
        **kwargs,
    ) -> bool:
        """
        Send templated email notification with advanced template rendering.

        Args:
            to_email: Recipient email address
            subject: Email subject (if None, rendered from template)
            template: Template name (defaults to system_notification)
            context: Template context (will be sanitized)
            from_email: Optional from email override
            **kwargs: Additional parameters

        Returns:
            bool: True if email was queued successfully
        """
        if not context:
            context = {}

        # Add email-specific context
        email_context = {
            **context,
            "to_email": to_email,
            "from_email": from_email
            or getattr(self.config.smtp, "from_email", "noreply@coachiq.com"),
        }

        # Render subject from template if not provided
        if not subject and self.template_manager:
            try:
                subject = await self.template_manager.render_subject(template, email_context)
            except Exception as e:
                self.logger.warning(f"Failed to render email subject: {e}")
                subject = f"{self.config.default_title} - Notification"
        elif not subject:
            subject = f"{self.config.default_title} - Notification"

        # Add rendered subject to context
        email_context["subject"] = subject

        return await self.notify(
            message=f"Email to {to_email}: {subject}",
            title="Email Notification",
            level=NotificationType.INFO,
            channels=["smtp"],
            template=template,
            context=email_context,
            recipient=to_email,
            **kwargs,
        )

    async def send_magic_link_email(
        self,
        to_email: str,
        magic_link: str,
        user_name: str | None = None,
        expires_minutes: int = 15,
        **kwargs,
    ) -> bool:
        """
        Send magic link authentication email.

        Args:
            to_email: Recipient email
            magic_link: Magic link URL
            user_name: Optional user name
            expires_minutes: Link expiration time
            **kwargs: Additional parameters

        Returns:
            bool: True if email was queued successfully
        """
        context = {
            "magic_link": magic_link,
            "user_name": user_name or "User",
            "app_name": self.config.app_name,
            "support_email": self.config.smtp.from_email or "support@coachiq.com",
            "expires_minutes": expires_minutes,
        }

        return await self.send_email(
            to_email=to_email,
            subject="Your CoachIQ Login Link",
            template="magic_link",
            context=context,
            **kwargs,
        )

    async def send_system_notification(
        self,
        message: str,
        level: str | NotificationType = NotificationType.INFO,
        component: str | None = None,
        **kwargs,
    ) -> bool:
        """
        Send system notification.

        Args:
            message: System message
            level: Notification level
            component: Component name
            **kwargs: Additional parameters

        Returns:
            bool: True if notification was queued successfully
        """
        title = "CoachIQ System"
        if component:
            title += f" - {component}"

        tags = ["system"]
        level_enum = NotificationType(level.lower()) if isinstance(level, str) else level

        if level_enum in [NotificationType.ERROR, NotificationType.CRITICAL]:
            tags.append("alert")

        return await self.notify(
            message=message,
            title=title,
            level=level_enum,
            tags=tags,
            source_component=component,
            **kwargs,
        )

    async def send_pushover_notification(
        self,
        message: str,
        title: str | None = None,
        priority: int | None = None,
        device: str | None = None,
        sound: str | None = None,
        **kwargs,
    ) -> bool:
        """
        Send Pushover notification with specific parameters.

        Args:
            message: Message text
            title: Optional title
            priority: Pushover priority (-2 to 2)
            device: Specific device to target
            sound: Notification sound
            **kwargs: Additional parameters

        Returns:
            bool: True if notification was queued successfully
        """
        return await self.notify(
            message=message,
            title=title,
            channels=["pushover"],
            pushover_priority=priority,
            pushover_device=device,
            **kwargs,
        )

    async def get_queue_statistics(self) -> QueueStatistics:
        """Get comprehensive queue statistics."""
        if not self.queue:
            return QueueStatistics(
                pending_count=0,
                processing_count=0,
                completed_count=0,
                failed_count=0,
                dlq_count=0,
                avg_processing_time=None,
                success_rate=0.0,
                oldest_pending=None,
                last_success=None,
                last_failure=None,
                dispatcher_running=False,
                queue_size_bytes=None,
            )

        return await self.queue.get_statistics()

    async def get_rate_limit_status(self) -> RateLimitStatus:
        """Get rate limiting status."""
        if not self.rate_limiter:
            return RateLimitStatus(
                current_tokens=0,
                max_tokens=100,
                refill_rate=10.0,
                requests_last_minute=0,
                requests_blocked=0,
                active_debounces=0,
                healthy=True,
            )

        status = self.rate_limiter.get_status()

        # Add debouncer statistics
        if self.debouncer:
            debouncer_stats = self.debouncer.get_statistics()
            # Note: We can't modify the existing status object, so we create a new one
            return RateLimitStatus(
                current_tokens=status.current_tokens,
                max_tokens=status.max_tokens,
                refill_rate=status.refill_rate,
                requests_last_minute=status.requests_last_minute,
                requests_blocked=status.requests_blocked,
                active_debounces=debouncer_stats["active_suppressions"],
                healthy=status.healthy,
                last_reset=status.last_reset,
            )

        return status

    async def get_channel_status(self) -> dict[str, Any]:
        """Get status of all notification channels."""
        base_status = {
            "enabled": self.config.enabled,
            "queue_enabled": self._initialized,
            "rate_limiting_enabled": self.rate_limiter is not None,
            "debouncing_enabled": self.debouncer is not None,
        }

        # Add channel-specific rate limiting status
        if self.channel_rate_limiter:
            base_status["channel_rate_limits"] = self.channel_rate_limiter.get_all_channel_status()

        return base_status

    async def test_channels(self) -> dict[str, Any]:
        """Test notification delivery (queues test notifications)."""
        if not self.config.enabled:
            return {"error": "Notifications disabled"}

        results = {}
        test_message = "CoachIQ notification system test"
        test_title = "Test Notification"

        # Test each enabled channel
        enabled_channels = [ch[0] for ch in self.config.get_enabled_channels()]

        for channel in enabled_channels:
            try:
                result = await self.notify(
                    message=test_message,
                    title=test_title,
                    channels=[channel],
                    tags=["test"],
                    source_component="SafeNotificationManager",
                )
                results[channel] = result
            except Exception as e:
                self.logger.error(f"Test failed for {channel}: {e}")
                results[channel] = False

        return results

    def get_statistics(self) -> dict[str, Any]:
        """Get manager statistics."""
        stats = dict(self.stats)

        # Add efficiency metrics
        total = stats["total_notifications"]
        if total > 0:
            stats["success_rate"] = stats["successful_notifications"] / total
            stats["rate_limit_rate"] = stats["rate_limited_notifications"] / total
            stats["debounce_rate"] = stats["debounced_notifications"] / total
            stats["failure_rate"] = stats["failed_notifications"] / total

        return stats

    # Template management methods

    async def get_available_templates(self, language: str = "en") -> list[str]:
        """Get list of available email templates."""
        if not self.template_manager:
            return []
        return await self.template_manager.list_templates(language)

    async def validate_template(self, template_name: str, language: str = "en") -> bool:
        """Validate email template syntax and structure."""
        if not self.template_manager:
            return False
        try:
            return await self.template_manager.validate_template(template_name, language)
        except Exception as e:
            self.logger.error(f"Template validation failed: {e}")
            return False

    async def create_email_template(
        self,
        template_name: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        language: str = "en",
    ) -> bool:
        """Create new email template."""
        if not self.template_manager:
            self.logger.warning("Template manager not initialized")
            return False

        return await self.template_manager.create_template(
            template_name, subject, html_content, text_content, language
        )

    async def render_template_preview(
        self,
        template_name: str,
        context: dict[str, Any] | None = None,
        format_type: str = "html",
        language: str = "en",
    ) -> str | None:
        """Render template for preview with sample context."""
        if not self.template_manager:
            return None

        if not context:
            # Provide sample context for preview
            context = {
                "user_name": "John Doe",
                "app_name": self.config.app_name,
                "magic_link": "https://example.com/auth/magic/sample-token",
                "expires_minutes": 15,
                "support_email": "support@coachiq.com",
                "message": "This is a sample notification message for preview.",
                "title": "Sample Notification",
                "level": "info",
                "source_component": "NotificationSystem",
                "correlation_id": "preview-12345",
            }

        try:
            return await self.template_manager.render_template(
                template_name, context, format_type, language
            )
        except Exception as e:
            self.logger.error(f"Template preview failed: {e}")
            return None

    def get_template_cache_stats(self) -> dict[str, Any]:
        """Get email template cache statistics."""
        if not self.template_manager:
            return {"error": "Template manager not initialized"}
        return self.template_manager.get_cache_stats()

    def clear_template_cache(self) -> None:
        """Clear email template cache."""
        if self.template_manager:
            self.template_manager.clear_cache()

    async def cleanup(self) -> None:
        """Clean shutdown of manager."""
        try:
            if self.queue:
                await self.queue.close()

            self.logger.info("SafeNotificationManager cleanup complete")

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    # Private helper methods

    def _setup_template_sandbox(self) -> None:
        """Setup Jinja2 sandboxed environment for secure template rendering."""
        if not JINJA2_AVAILABLE:
            self.logger.warning("Jinja2 not available, template sanitization disabled")
            return

        try:
            self.template_sandbox = SandboxedEnvironment(
                autoescape=select_autoescape(["html", "xml"]),
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )

            # Disable dangerous features
            if self.template_sandbox and hasattr(self.template_sandbox, "globals"):
                self.template_sandbox.globals.clear()
            if self.template_sandbox and hasattr(self.template_sandbox, "filters"):
                self.template_sandbox.filters.clear()

                # Only allow safe built-in filters
                safe_filters = {
                    "escape",
                    "e",
                    "safe",
                    "length",
                    "string",
                    "int",
                    "float",
                    "upper",
                    "lower",
                    "title",
                    "capitalize",
                    "trim",
                    "truncate",
                    "wordwrap",
                    "center",
                    "default",
                    "d",
                }

                # Re-add only safe filters
                for name, filter_func in DEFAULT_FILTERS.items():
                    if name in safe_filters:
                        self.template_sandbox.filters[name] = filter_func

            self.logger.debug("Template sandbox initialized with security restrictions")

        except Exception as e:
            self.logger.error(f"Failed to setup template sandbox: {e}")
            self.template_sandbox = None

    async def _sanitize_context(self, context: dict[str, Any]) -> dict[str, Any] | None:
        """
        Sanitize template context to prevent injection attacks.

        Args:
            context: Raw template context

        Returns:
            Sanitized context or None if sanitization fails
        """
        if not self.template_sandbox:
            # If no sandbox available, apply basic sanitization
            return self._basic_sanitize_context(context)

        try:
            sanitized = {}

            for key, value in context.items():
                # Sanitize key (must be valid identifier)
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
                    self.logger.warning(f"Invalid context key: {key}")
                    continue

                # Sanitize value based on type
                if isinstance(value, str):
                    # Test string in sandbox to detect injection attempts
                    try:
                        test_template = self.template_sandbox.from_string("{{ test_var }}")
                        test_template.render(test_var=value)
                        sanitized[key] = value
                    except (TemplateError, SecurityError) as e:
                        self.logger.warning(
                            f"Blocked potentially unsafe context value for {key}: {e}"
                        )
                        sanitized[key] = str(value)  # Convert to safe string

                elif isinstance(value, int | float | bool):
                    sanitized[key] = value

                elif isinstance(value, list | tuple):
                    # Recursively sanitize list items
                    sanitized_list = []
                    for item in value[:100]:  # Limit list size
                        if isinstance(item, str | int | float | bool):
                            sanitized_list.append(item)
                    sanitized[key] = sanitized_list

                elif isinstance(value, dict):
                    # Recursively sanitize dict (limited depth)
                    if len(str(value)) < 10000:  # Size limit
                        nested_sanitized = await self._sanitize_context(value)
                        if nested_sanitized:
                            sanitized[key] = nested_sanitized

                else:
                    # Convert unknown types to string
                    sanitized[key] = str(value)[:1000]  # Limit length

            return sanitized

        except Exception as e:
            self.logger.error(f"Context sanitization failed: {e}")
            return None

    def _basic_sanitize_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Basic context sanitization when Jinja2 sandbox is not available."""
        sanitized = {}

        for key, value in context.items():
            # Basic key validation
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
                # Basic value sanitization
                if isinstance(value, str):
                    # Remove potentially dangerous characters
                    cleaned = re.sub(r"[{}\[\]();<>|&$`\\]", "", value)
                    sanitized[key] = cleaned[:1000]  # Limit length
                elif isinstance(value, int | float | bool):
                    sanitized[key] = value
                else:
                    sanitized[key] = str(value)[:1000]

        return sanitized

    def _resolve_target_channels(self, channels: list[str] | None) -> list[str]:
        """Resolve target channels from input or defaults."""
        if channels:
            return channels

        # Return all enabled channels
        enabled_channels = self.config.get_enabled_channels()
        return [ch[0] for ch in enabled_channels]

    def _get_pushover_priority(self, level: NotificationType) -> int:
        """Get Pushover priority for notification level."""
        return self.pushover_priority_mapping.get(level, 0)

    async def _get_queue_depth(self) -> int:
        """Get current notification queue depth."""
        if self.queue:
            stats = await self.queue.get_statistics()
            return stats.pending_count
        return 0

    def _get_connectivity_status(self) -> dict[str, bool]:
        """Get current connectivity status for different channels."""
        # Placeholder - would integrate with actual connectivity checks
        return {
            "smtp": True,
            "pushover": True,
            "system": True,
        }

    # Routing management methods

    async def add_routing_rule(self, rule_data: dict[str, Any]) -> bool:
        """Add custom routing rule."""
        if not self.router:
            return False

        from backend.services.notification_routing import RoutingRule

        try:
            rule = RoutingRule(**rule_data)
            return await self.router.add_routing_rule(rule)
        except Exception as e:
            self.logger.error(f"Failed to add routing rule: {e}")
            return False

    async def update_user_preferences(self, user_id: str, preferences: dict[str, Any]) -> bool:
        """Update user notification preferences."""
        if not self.router:
            return False

        from backend.services.notification_routing import UserNotificationPreferences

        try:
            prefs = UserNotificationPreferences(user_id=user_id, **preferences)
            return await self.router.update_user_preferences(user_id, prefs)
        except Exception as e:
            self.logger.error(f"Failed to update user preferences: {e}")
            return False

    def get_routing_statistics(self) -> dict[str, Any]:
        """Get routing engine statistics."""
        if not self.router:
            return {"error": "Router not initialized"}
        return self.router.get_statistics()
