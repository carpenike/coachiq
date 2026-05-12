"""
Email Template Management System with Jinja2 Templating

This module provides a comprehensive template management system for email notifications
in the RV-C environment. Features secure Jinja2 templating, template validation,
caching, and dynamic template loading with fallback support.

Key Features:
- Sandboxed Jinja2 environment for security
- Template validation and syntax checking
- File-based and database template storage
- Template caching for performance
- Fallback template support
- Multi-language template support
- Template versioning and A/B testing capabilities

Example:
    >>> manager = EmailTemplateManager()
    >>> await manager.initialize()
    >>> rendered = await manager.render_template(
    ...     "magic_link",
    ...     {"magic_link": "https://...", "user_name": "John"}
    ... )
"""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from jinja2 import (
        Environment,
        FileSystemLoader,
        StrictUndefined,
        select_autoescape,
    )
    from jinja2.exceptions import TemplateNotFound
    from jinja2.filters import FILTERS as DEFAULT_FILTERS
    from jinja2.sandbox import SandboxedEnvironment

    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

from backend.core.config import NotificationSettings


class TemplateValidationError(Exception):
    """Raised when template validation fails."""


class TemplateRenderingError(Exception):
    """Raised when template rendering fails."""


class EmailTemplateManager:
    """
    Secure email template management system for RV-C notifications.

    Provides comprehensive template management with security features,
    caching, and fallback support for reliable email delivery.
    """

    def __init__(
        self,
        config: NotificationSettings,
        template_dir: str | None = None,
        cache_ttl_minutes: int = 60,
        enable_template_caching: bool = True,
    ):
        """
        Initialize email template manager.

        Args:
            config: NotificationSettings configuration
            template_dir: Optional override for the directory containing
                email templates. When None (the typical case), the
                directory is read from ``config.template_path`` so
                operators can relocate templates via env var without
                having to subclass. Earlier revisions hardcoded
                ``backend/templates/email`` and ignored the config
                field, which made the ``COACHIQ_NOTIFICATIONS__TEMPLATE_PATH``
                env var a no-op AND caused tests to scribble into the
                real shipped templates directory.
            cache_ttl_minutes: Template cache TTL in minutes
            enable_template_caching: Whether to enable template caching
        """
        self.config = config
        self.template_dir = Path(template_dir or config.template_path)
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.enable_caching = enable_template_caching

        self.logger = logging.getLogger(f"{__name__}.EmailTemplateManager")

        # Template environment and cache
        self.jinja_env: Environment | None = None
        self.template_cache: dict[str, dict[str, Any]] = {}

        # Built-in templates as fallbacks
        self.builtin_templates = {
            "magic_link": {
                "subject": "{{app_name}} - Your Login Link",
                "html": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{{app_name}} Login</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #2c3e50; color: white; padding: 20px; text-align: center; }
        .content { background: #f8f9fa; padding: 30px; }
        .button { background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block; margin: 20px 0; }
        .footer { background: #e9ecef; padding: 20px; font-size: 0.9em; color: #6c757d; }
        .warning { background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; margin: 20px 0; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{app_name}}</h1>
        </div>
        <div class="content">
            <h2>Hello {{user_name}}!</h2>
            <p>You requested a login link for your {{app_name}} account. Click the button below to sign in:</p>
            <a href="{{magic_link}}" class="button">Sign In to {{app_name}}</a>
            <div class="warning">
                <strong>Security Notice:</strong> This link will expire in {{expires_minutes}} minutes.
                If you didn't request this login, please ignore this email.
            </div>
            <p><strong>Alternative:</strong> If the button doesn't work, copy and paste this URL into your browser:</p>
            <p style="word-break: break-all; background: #f1f3f4; padding: 10px; border-radius: 4px;">{{magic_link}}</p>
        </div>
        <div class="footer">
            <p>This email was sent from {{app_name}}. If you need help, contact {{support_email}}.</p>
            <p>You're receiving this because you requested a login link for your account.</p>
        </div>
    </div>
</body>
</html>
                """,
                "text": """
{{app_name}} - Login Link

Hello {{user_name}}!

You requested a login link for your {{app_name}} account.

Sign in here: {{magic_link}}

SECURITY NOTICE: This link will expire in {{expires_minutes}} minutes.
If you didn't request this login, please ignore this email.

Need help? Contact {{support_email}}.

This email was sent from {{app_name}}.
                """,
            },
            "system_notification": {
                "subject": "{{app_name}} System Alert - {{level|title}}",
                "html": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{{app_name}} System Alert</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { padding: 20px; text-align: center; }
        .header.info { background: #d1ecf1; border: 1px solid #bee5eb; }
        .header.warning { background: #fff3cd; border: 1px solid #ffeaa7; }
        .header.error { background: #f8d7da; border: 1px solid #f5c6cb; }
        .header.critical { background: #d1ecf1; border: 1px solid #b21f2d; color: #721c24; }
        .content { background: #f8f9fa; padding: 30px; }
        .footer { background: #e9ecef; padding: 20px; font-size: 0.9em; color: #6c757d; }
        .timestamp { font-size: 0.9em; color: #6c757d; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header {{level}}">
            <h1>{{app_name}} System Alert</h1>
            <h2>{{level|title}}: {{title}}</h2>
        </div>
        <div class="content">
            <p>{{message}}</p>
            {% if source_component %}
            <p><strong>Component:</strong> {{source_component}}</p>
            {% endif %}
            {% if correlation_id %}
            <p><strong>Event ID:</strong> {{correlation_id}}</p>
            {% endif %}
            <div class="timestamp">
                <strong>Timestamp:</strong> {{timestamp|default(now())}}
            </div>
        </div>
        <div class="footer">
            <p>This is an automated message from {{app_name}} monitoring system.</p>
            <p>For support, contact {{support_email}}.</p>
        </div>
    </div>
</body>
</html>
                """,
                "text": """
{{app_name}} SYSTEM ALERT

{{level|upper}}: {{title}}

{{message}}

{% if source_component %}Component: {{source_component}}{% endif %}
{% if correlation_id %}Event ID: {{correlation_id}}{% endif %}

Timestamp: {{timestamp|default(now())}}

This is an automated message from {{app_name}} monitoring system.
For support, contact {{support_email}}.
                """,
            },
            "test_notification": {
                "subject": "{{app_name}} Test Notification",
                "html": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Test Notification</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #28a745; color: white; padding: 20px; text-align: center; }
        .content { background: #f8f9fa; padding: 30px; }
        .footer { background: #e9ecef; padding: 20px; font-size: 0.9em; color: #6c757d; }
        .success { background: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>✅ {{app_name}} Test</h1>
        </div>
        <div class="content">
            <div class="success">
                <h2>Email System Test Successful!</h2>
                <p>{{message}}</p>
            </div>
            <p><strong>Test Details:</strong></p>
            <ul>
                <li>Template Engine: Working ✅</li>
                <li>Email Delivery: Working ✅</li>
                <li>Time: {{timestamp|default(now())}}</li>
            </ul>
        </div>
        <div class="footer">
            <p>This is a test message from {{app_name}}. No action required.</p>
        </div>
    </div>
</body>
</html>
                """,
                "text": """
{{app_name}} EMAIL TEST

✅ Email System Test Successful!

{{message}}

Test Details:
- Template Engine: Working ✅
- Email Delivery: Working ✅
- Time: {{timestamp|default(now())}}

This is a test message from {{app_name}}. No action required.
                """,
            },
        }

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize template management system."""
        if not JINJA2_AVAILABLE:
            raise TemplateValidationError("Jinja2 not available - template management disabled")

        try:
            # Create template directory if it doesn't exist
            self.template_dir.mkdir(parents=True, exist_ok=True)

            # Set up sandboxed Jinja2 environment
            self._setup_jinja_environment()

            # Write built-in templates to disk if they don't exist
            await self._ensure_builtin_templates()

            # Validate existing templates
            await self._validate_all_templates()

            self._initialized = True
            self.logger.info(f"EmailTemplateManager initialized: {self.template_dir}")

        except Exception as e:
            self.logger.error(f"Failed to initialize EmailTemplateManager: {e}")
            raise

    async def render_template(
        self,
        template_name: str,
        context: dict[str, Any],
        format_type: str = "html",
        language: str = "en",
    ) -> str:
        """
        Render email template with provided context.

        Args:
            template_name: Name of template to render
            context: Template context variables
            format_type: "html" or "text" format
            language: Language code for localization

        Returns:
            str: Rendered template content

        Raises:
            TemplateRenderingError: If rendering fails
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Get template from cache or load
            template_data = await self._get_template(template_name, language)

            if format_type not in template_data:
                raise TemplateRenderingError(
                    f"Format '{format_type}' not available for template '{template_name}'"
                )

            # Prepare secure context
            safe_context = await self._prepare_template_context(context)

            # Render template
            template_content = template_data[format_type]
            if isinstance(template_content, str):
                # String template - render with Jinja2
                if self.jinja_env:
                    template = self.jinja_env.from_string(template_content)
                    return template.render(**safe_context)
                return template_content  # Fallback if no Jinja2
            # Already a Template object
            return template_content.render(**safe_context)

        except Exception as e:
            self.logger.error(f"Template rendering failed for '{template_name}': {e}")
            raise TemplateRenderingError(f"Failed to render template '{template_name}': {e}")

    async def render_subject(
        self, template_name: str, context: dict[str, Any], language: str = "en"
    ) -> str:
        """
        Render email subject line for template.

        Args:
            template_name: Name of template
            context: Template context variables
            language: Language code

        Returns:
            str: Rendered subject line
        """
        if not self._initialized:
            await self.initialize()

        try:
            template_data = await self._get_template(template_name, language)

            if "subject" not in template_data:
                return f"{self.config.default_title} - Notification"

            safe_context = await self._prepare_template_context(context)

            subject_template = template_data["subject"]
            if isinstance(subject_template, str):
                if self.jinja_env:
                    template = self.jinja_env.from_string(subject_template)
                    return template.render(**safe_context)
                return subject_template  # Fallback if no Jinja2
            return subject_template.render(**safe_context)

        except Exception as e:
            self.logger.error(f"Subject rendering failed for '{template_name}': {e}")
            return f"{self.config.default_title} - Notification"

    async def validate_template(self, template_name: str, language: str = "en") -> bool:
        """
        Validate template syntax and required variables.

        Args:
            template_name: Name of template to validate
            language: Language code

        Returns:
            bool: True if template is valid

        Raises:
            TemplateValidationError: If validation fails
        """
        try:
            template_data = await self._get_template(template_name, language)

            # Validate each format
            for format_type, content in template_data.items():
                if isinstance(content, str) and self.jinja_env:
                    # Parse template to check syntax
                    self.jinja_env.parse(content)

            # Test render with minimal context
            test_context = {
                "app_name": "TestApp",
                "user_name": "TestUser",
                "support_email": "test@example.com",
                "timestamp": datetime.utcnow().isoformat(),
            }

            await self.render_template(template_name, test_context, "html", language)
            await self.render_subject(template_name, test_context, language)

            return True

        except Exception as e:
            raise TemplateValidationError(f"Template validation failed: {e}")

    async def list_templates(self, language: str = "en") -> list[str]:
        """
        Get list of available templates.

        Args:
            language: Language code

        Returns:
            List of template names
        """
        templates = set()

        # Add built-in templates
        templates.update(self.builtin_templates.keys())

        # Add file-based templates
        lang_dir = self.template_dir / language
        if lang_dir.exists():
            for template_file in lang_dir.glob("*.html"):
                templates.add(template_file.stem)

        return sorted(templates)

    async def create_template(
        self,
        template_name: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        language: str = "en",
    ) -> bool:
        """
        Create new email template.

        Args:
            template_name: Unique template name
            subject: Subject line template
            html_content: HTML template content
            text_content: Optional text template content
            language: Language code

        Returns:
            bool: True if created successfully
        """
        try:
            # Validate template syntax. Surface syntax errors as exceptions
            # rather than swallowing them and returning False -- a silent
            # False here hid programmer errors (typos in templates) behind
            # a generic boolean return for a long time. Render-time
            # ``StrictUndefined`` violations remain a separate concern.
            from jinja2 import TemplateSyntaxError

            if self.jinja_env:
                try:
                    self.jinja_env.parse(subject)
                    self.jinja_env.parse(html_content)
                    if text_content:
                        self.jinja_env.parse(text_content)
                except TemplateSyntaxError:
                    self.logger.exception("Template syntax error creating '%s'", template_name)
                    raise

            # Create template directory
            lang_dir = self.template_dir / language
            lang_dir.mkdir(parents=True, exist_ok=True)

            # Write template files
            template_data = {"subject": subject, "html": html_content}
            if text_content:
                template_data["text"] = text_content

            # Save as individual files for better management
            (lang_dir / f"{template_name}_subject.html").write_text(subject)
            (lang_dir / f"{template_name}.html").write_text(html_content)
            if text_content:
                (lang_dir / f"{template_name}.txt").write_text(text_content)

            # Clear cache
            cache_key = f"{template_name}:{language}"
            if cache_key in self.template_cache:
                del self.template_cache[cache_key]

            self.logger.info(f"Created template '{template_name}' for language '{language}'")
            return True

        except Exception as e:
            self.logger.error(f"Failed to create template '{template_name}': {e}")
            # Re-raise template syntax errors so callers can react; swallow
            # other (probably-IO) failures with a False return for backward
            # compat.
            from jinja2 import TemplateSyntaxError

            if isinstance(e, TemplateSyntaxError):
                raise
            return False

    def clear_cache(self) -> None:
        """Clear template cache."""
        self.template_cache.clear()
        self.logger.info("Template cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get template cache statistics."""
        return {
            "cache_size": len(self.template_cache),
            "cache_enabled": self.enable_caching,
            "cache_ttl_minutes": self.cache_ttl.total_seconds() / 60,
            "cached_templates": list(self.template_cache.keys()),
        }

    # Private helper methods

    def _setup_jinja_environment(self) -> None:
        """Set up secure Jinja2 environment."""
        # Create sandboxed environment for security
        self.jinja_env = SandboxedEnvironment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Clear dangerous globals and filters
        self.jinja_env.globals.clear()

        # Add safe custom filters and functions
        self._add_safe_template_functions()

        self.logger.debug("Jinja2 sandboxed environment configured")

    def _add_safe_template_functions(self) -> None:
        """Add safe custom functions and filters to template environment."""
        # Add safe built-in filters
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
            "replace",
            "join",
            "split",
        }

        # Clear all filters first
        if self.jinja_env:
            self.jinja_env.filters.clear()

            # Re-add only safe filters
            for name, filter_func in DEFAULT_FILTERS.items():
                if name in safe_filters:
                    self.jinja_env.filters[name] = filter_func

            # Add custom safe functions
            self.jinja_env.globals["now"] = datetime.utcnow

            # Add custom filters
            self.jinja_env.filters["format_timestamp"] = self._format_timestamp
            self.jinja_env.filters["truncate_middle"] = self._truncate_middle

    def _format_timestamp(self, timestamp: Any, format_str: str = "%Y-%m-%d %H:%M UTC") -> str:
        """Format timestamp for email display."""
        try:
            if isinstance(timestamp, str):
                # Try to parse ISO format
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elif isinstance(timestamp, datetime):
                dt = timestamp
            else:
                return str(timestamp)

            return dt.strftime(format_str)
        except Exception:
            return str(timestamp)

    def _truncate_middle(self, text: str, max_length: int = 50) -> str:
        """Truncate text in the middle for long strings."""
        if len(text) <= max_length:
            return text

        if max_length < 10:
            return text[:max_length]

        start_length = (max_length - 3) // 2
        end_length = max_length - 3 - start_length

        return f"{text[:start_length]}...{text[-end_length:]}"

    async def _get_template(self, template_name: str, language: str) -> dict[str, Any]:
        """Get template data from cache or load from storage."""
        cache_key = f"{template_name}:{language}"

        # Check cache first
        if self.enable_caching and cache_key in self.template_cache:
            cached_entry = self.template_cache[cache_key]
            if datetime.utcnow() < cached_entry["expires"]:
                return cached_entry["data"]
            # Cache expired
            del self.template_cache[cache_key]

        # Load template
        template_data = await self._load_template(template_name, language)

        # Cache if enabled
        if self.enable_caching:
            self.template_cache[cache_key] = {
                "data": template_data,
                "expires": datetime.utcnow() + self.cache_ttl,
            }

        return template_data

    async def _load_template(self, template_name: str, language: str) -> dict[str, Any]:
        """Load template from file system or built-ins."""
        # Try file-based template first
        lang_dir = self.template_dir / language
        if lang_dir.exists():
            template_data = {}

            # Load subject
            subject_file = lang_dir / f"{template_name}_subject.html"
            if subject_file.exists():
                template_data["subject"] = subject_file.read_text()

            # Load HTML
            html_file = lang_dir / f"{template_name}.html"
            if html_file.exists():
                template_data["html"] = html_file.read_text()

            # Load text
            text_file = lang_dir / f"{template_name}.txt"
            if text_file.exists():
                template_data["text"] = text_file.read_text()

            if template_data:
                return template_data

        # Fall back to built-in templates
        if template_name in self.builtin_templates:
            return self.builtin_templates[template_name].copy()

        raise TemplateNotFound(f"Template '{template_name}' not found for language '{language}'")

    async def _prepare_template_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Prepare and sanitize template context."""
        safe_context = {}

        # Add default context
        safe_context.update(
            {
                "app_name": getattr(self.config, "app_name", "CoachIQ"),
                "support_email": getattr(self.config, "support_email", "support@coachiq.com"),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        # Sanitize user-provided context
        for key, value in context.items():
            # Validate key
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
                continue

            # Sanitize value
            if isinstance(value, str | int | float | bool):
                safe_context[key] = value
            elif isinstance(value, list | tuple):
                # Limit list size and sanitize items
                safe_list = []
                for item in value[:50]:  # Limit to 50 items
                    if isinstance(item, str | int | float | bool):
                        safe_list.append(item)
                safe_context[key] = safe_list
            elif isinstance(value, dict):
                # Shallow sanitization for dicts
                safe_dict = {}
                for k, v in value.items():
                    if isinstance(k, str) and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k):
                        if isinstance(v, str | int | float | bool):
                            safe_dict[k] = v
                safe_context[key] = safe_dict
            else:
                # Convert to string
                safe_context[key] = str(value)[:1000]

        return safe_context

    async def _ensure_builtin_templates(self) -> None:
        """Write built-in templates to disk if they don't exist."""
        for template_name, template_data in self.builtin_templates.items():
            lang_dir = self.template_dir / "en"
            lang_dir.mkdir(parents=True, exist_ok=True)

            # Write templates if they don't exist
            subject_file = lang_dir / f"{template_name}_subject.html"
            if not subject_file.exists():
                subject_file.write_text(template_data["subject"])

            html_file = lang_dir / f"{template_name}.html"
            if not html_file.exists():
                html_file.write_text(template_data["html"])

            if "text" in template_data:
                text_file = lang_dir / f"{template_name}.txt"
                if not text_file.exists():
                    text_file.write_text(template_data["text"])

    async def _validate_all_templates(self) -> None:
        """Validate all available templates."""
        templates = await self.list_templates()
        validation_errors = []

        for template_name in templates:
            try:
                await self.validate_template(template_name)
                self.logger.debug(f"Template '{template_name}' validated successfully")
            except TemplateValidationError as e:
                validation_errors.append(f"{template_name}: {e}")

        if validation_errors:
            self.logger.warning(f"Template validation errors: {validation_errors}")
