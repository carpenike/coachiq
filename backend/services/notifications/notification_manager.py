"""
Unified Notification Manager using Apprise

This module provides a centralized notification service using Apprise to support
multiple notification channels including SMTP, Slack, Discord, and more.

The NotificationManager handles:
- Multi-channel notification delivery
- Template rendering with Jinja2
- Notification logging and tracking
- Email-specific functionality for authentication flows
- Graceful failure handling and fallbacks

Example:
    >>> manager = NotificationManager(notification_settings)
    >>> await manager.send_notification(
    ...     message="Test notification",
    ...     title="Test",
    ...     tags=["system"]
    ... )
    >>> await manager.send_magic_link_email(
    ...     to_email="user@example.com",
    ...     magic_link="https://app.com/auth/magic?token=abc123"
    ... )
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

try:
    import apprise
    from jinja2 import Environment, FileSystemLoader, TemplateNotFound

    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False

from backend.core.config import NotificationSettings


class NotificationManager:
    """
    Unified notification manager using Apprise for multi-channel delivery.

    This manager provides a centralized interface for sending notifications
    across multiple channels (SMTP, Slack, Discord, etc.) with template
    support and comprehensive logging.
    """

    def __init__(self, config: NotificationSettings):
        """
        Initialize the NotificationManager.

        Args:
            config: NotificationSettings instance with channel configurations

        Raises:
            ImportError: If Apprise or Jinja2 dependencies are not available
        """
        if not DEPENDENCIES_AVAILABLE:
            msg = (
                "NotificationManager requires 'apprise' and 'jinja2' packages. "
                "Please install them with: pip install apprise jinja2"
            )
            raise ImportError(msg)

        self.config = config
        self.logger = logging.getLogger(f"{__name__}.NotificationManager")

        # Initialize Apprise instance
        self.apprise_obj = apprise.Apprise()

        # Initialize Jinja2 template environment
        self.template_env = None
        self._setup_templates()

        # Setup notification channels
        self._setup_channels()

        self.logger.info(
            f"NotificationManager initialized with {len(self.config.get_enabled_channels())} channels"
        )

    def _setup_templates(self) -> None:
        """Setup Jinja2 template environment for email templates."""
        try:
            template_path = Path(self.config.template_path)

            # Create template directory if it doesn't exist
            if not template_path.exists():
                template_path.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Created template directory: {template_path}")

            # Initialize Jinja2 environment
            self.template_env = Environment(
                loader=FileSystemLoader(str(template_path)),
                autoescape=True,  # Auto-escape for security
                trim_blocks=True,
                lstrip_blocks=True,
            )

            self.logger.debug(f"Template environment initialized with path: {template_path}")

        except Exception as e:
            self.logger.warning(f"Failed to setup template environment: {e}")
            # Create a minimal environment with string templates as fallback
            self.template_env = Environment(autoescape=True)

    def _setup_channels(self) -> None:
        """Setup notification channels based on configuration."""
        enabled_channels = self.config.get_enabled_channels()

        for channel_name, channel_url in enabled_channels:
            if channel_url != "dynamic":  # SMTP is handled separately
                try:
                    self.apprise_obj.add(channel_url, tag=channel_name)
                    self.logger.debug(f"Added {channel_name} notification channel")
                except Exception as e:
                    self.logger.error(f"Failed to add {channel_name} channel: {e}")

    async def send_notification(
        self,
        message: str,
        title: str | None = None,
        notify_type: str = "info",
        tags: list[str] | None = None,
        template: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """
        Send notification to configured channels.

        Args:
            message: Notification message body
            title: Optional notification title
            notify_type: Notification type (info, success, warning, failure)
            tags: Optional list of channel tags to target
            template: Optional template name for message rendering
            context: Optional context data for template rendering

        Returns:
            bool: True if notification was sent successfully to at least one channel
        """
        if not self.config.enabled:
            self.logger.debug("Notifications disabled, skipping send")
            return False

        try:
            # Use template if provided
            final_message = message
            if template and context and self.template_env:
                try:
                    final_message = self._render_template(template, context)
                except Exception as e:
                    self.logger.warning(f"Template rendering failed, using plain message: {e}")

            # Determine notification type for Apprise
            apprise_type = self._get_apprise_notify_type(notify_type)

            # Send notification
            result = await self._send_apprise_notification(
                body=final_message,
                title=title or self.config.default_title,
                notify_type=apprise_type,
                tag=tags,
            )

            # Log notification attempt
            if self.config.log_notifications:
                await self._log_notification(
                    message=final_message,
                    title=title,
                    notify_type=notify_type,
                    tags=tags,
                    success=result,
                )

            return result

        except Exception as e:
            self.logger.error(f"Failed to send notification: {e}")
            return False

    async def send_email(
        self,
        to_email: str,
        subject: str,
        template: str,
        context: dict[str, Any],
        from_email: str | None = None,
    ) -> bool:
        """
        Send templated email via SMTP.

        Args:
            to_email: Recipient email address
            subject: Email subject line
            template: Template name for email content
            context: Template context data
            from_email: Optional override for from email address

        Returns:
            bool: True if email was sent successfully
        """
        if not self.config.enabled or not self.config.smtp.enabled:
            self.logger.debug("Email notifications disabled, skipping send")
            return False

        try:
            # Generate SMTP URL for this specific email
            smtp_url = self.config.smtp.to_apprise_url(to_email)

            # Create temporary Apprise instance for this email
            email_apprise = apprise.Apprise()
            email_apprise.add(smtp_url)

            # Render email template
            html_content = self._render_template(template, context)

            # Send email
            result = await email_apprise.async_notify(
                body=html_content, title=subject, body_format=apprise.NotifyFormat.HTML
            )

            # Log email attempt
            if self.config.log_notifications:
                await self._log_notification(
                    message=f"Email to {to_email}: {subject}",
                    title="Email Notification",
                    notify_type="info",
                    tags=["email"],
                    success=result,
                )

            return result

        except Exception as e:
            self.logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    async def send_magic_link_email(
        self,
        to_email: str,
        magic_link: str,
        user_name: str | None = None,
        expires_minutes: int = 15,
    ) -> bool:
        """
        Send magic link authentication email.

        Args:
            to_email: Recipient email address
            magic_link: Magic link URL for authentication
            user_name: Optional user display name
            expires_minutes: Link expiration time in minutes

        Returns:
            bool: True if email was sent successfully
        """
        context = {
            "magic_link": magic_link,
            "user_name": user_name or "User",
            "app_name": "CoachIQ",
            "support_email": self.config.smtp.from_email or "support@coachiq.com",
            "expires_minutes": expires_minutes,
            "to_email": to_email,
        }

        return await self.send_email(
            to_email=to_email,
            subject="Your CoachIQ Login Link",
            template="magic_link",
            context=context,
        )

    async def send_system_notification(
        self, message: str, level: str = "info", component: str | None = None
    ) -> bool:
        """
        Send system notification (startup, shutdown, errors, etc.).

        Args:
            message: System notification message
            level: Notification level (info, warning, error, critical)
            component: Optional component name that generated the notification

        Returns:
            bool: True if notification was sent successfully
        """
        title = "CoachIQ System"
        if component:
            title += f" - {component}"

        tags = ["system"]
        if level in ["error", "critical"]:
            tags.append("alert")

        return await self.send_notification(
            message=message, title=title, notify_type=level, tags=tags
        )

    def _render_template(self, template_name: str, context: dict[str, Any]) -> str:
        """
        Render email template with context.

        Args:
            template_name: Name of the template file (without extension)
            context: Template context data

        Returns:
            str: Rendered template content

        Raises:
            TemplateNotFound: If template file is not found
        """
        try:
            template = self.template_env.get_template(f"{template_name}.html")
            return template.render(**context)
        except TemplateNotFound:
            # Try to create a basic template if magic_link template is missing
            if template_name == "magic_link":
                return self._get_default_magic_link_template(context)
            raise

    def _get_default_magic_link_template(self, context: dict[str, Any]) -> str:
        """Generate a default magic link email template."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{context.get("app_name", "CoachIQ")} - Login Link</title>
</head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h1 style="color: #333;">{context.get("app_name", "CoachIQ")}</h1>
    <h2 style="color: #666;">Sign in to your account</h2>

    <p>Hello {context.get("user_name", "User")},</p>

    <p>Click the button below to sign in to your {context.get("app_name", "CoachIQ")} account:</p>

    <div style="text-align: center; margin: 30px 0;">
        <a href="{context.get("magic_link", "#")}"
           style="background-color: #007bff; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 4px; display: inline-block;">
            Sign In to {context.get("app_name", "CoachIQ")}
        </a>
    </div>

    <p>Or copy and paste this link into your browser:</p>
    <p style="word-break: break-all; color: #666;">{context.get("magic_link", "#")}</p>

    <p><strong>This link will expire in {context.get("expires_minutes", 15)} minutes for security reasons.</strong></p>

    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">

    <p style="color: #666; font-size: 14px;">
        If you didn't request this login link, you can safely ignore this email.
        <br>
        Need help? Contact us at <a href="mailto:{context.get("support_email", "support@coachiq.com")}">{context.get("support_email", "support@coachiq.com")}</a>
    </p>
</body>
</html>
        """.strip()

    def _get_apprise_notify_type(self, notify_type: str) -> str:
        """Convert notification type to Apprise NotifyType."""
        type_mapping = {
            "info": apprise.NotifyType.INFO,
            "success": apprise.NotifyType.SUCCESS,
            "warning": apprise.NotifyType.WARNING,
            "error": apprise.NotifyType.FAILURE,
            "failure": apprise.NotifyType.FAILURE,
            "critical": apprise.NotifyType.FAILURE,
        }
        return type_mapping.get(notify_type.lower(), apprise.NotifyType.INFO)

    async def _send_apprise_notification(
        self, body: str, title: str, notify_type: str, tag: list[str] | None = None
    ) -> bool:
        """Send notification using Apprise (async wrapper)."""
        try:
            # Run Apprise notification in thread pool to avoid blocking
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: self.apprise_obj.notify(
                    body=body, title=title, notify_type=notify_type, tag=tag
                ),
            )
        except Exception as e:
            self.logger.error(f"Apprise notification failed: {e}")
            return False

    async def _log_notification(
        self,
        message: str,
        title: str | None,
        notify_type: str,
        tags: list[str] | None,
        success: bool,
    ) -> None:
        """Log notification attempt and result."""
        log_level = logging.INFO if success else logging.WARNING
        tag_str = f" [tags: {', '.join(tags)}]" if tags else ""
        status = "SUCCESS" if success else "FAILED"

        self.logger.log(
            log_level,
            f"Notification {status}: {title or 'No title'} - {message[:100]}{'...' if len(message) > 100 else ''}{tag_str}",
        )

    def get_channel_status(self) -> dict[str, Any]:
        """
        Get status of all configured notification channels.

        Returns:
            dict: Channel status information
        """
        channels = self.config.get_enabled_channels()
        status = {"enabled": self.config.enabled, "total_channels": len(channels), "channels": {}}

        for channel_name, channel_url in channels:
            status["channels"][channel_name] = {
                "enabled": True,
                "type": channel_name,
                "configured": channel_url != "dynamic"
                or (
                    channel_name == "smtp" and self.config.smtp.host and self.config.smtp.from_email
                ),
            }

        return status

    async def test_channels(self) -> dict[str, bool]:
        """
        Test all configured notification channels.

        Returns:
            dict: Test results for each channel
        """
        if not self.config.enabled:
            return {"error": "Notifications disabled"}

        results = {}
        test_message = "CoachIQ notification system test"
        test_title = "Test Notification"

        # Test each channel individually
        channels = self.config.get_enabled_channels()
        for channel_name, _ in channels:
            try:
                result = await self.send_notification(
                    message=test_message, title=test_title, tags=[channel_name]
                )
                results[channel_name] = result
            except Exception as e:
                self.logger.error(f"Test failed for {channel_name}: {e}")
                results[channel_name] = False

        return results
