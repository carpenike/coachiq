"""
Notification system models for tracking sent notifications and delivery status.

This module contains Pydantic models for the notification system including
notification logs, delivery tracking, template contexts, and queue operations.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class NotificationType(str, Enum):
    """Enumeration of notification types."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationChannel(str, Enum):
    """Enumeration of notification channels."""

    SMTP = "smtp"
    SLACK = "slack"
    DISCORD = "discord"
    PUSHOVER = "pushover"
    WEBHOOK = "webhook"
    SYSTEM = "system"


class NotificationStatus(str, Enum):
    """Enumeration of notification delivery status."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


class NotificationLog(BaseModel):
    """
    Model for tracking notification delivery attempts and results.

    This model is used for logging and auditing notification delivery
    across all channels and types.
    """

    id: str | None = Field(None, description="Unique notification ID")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Notification timestamp"
    )

    # Notification content
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message body")
    notification_type: NotificationType = Field(
        NotificationType.INFO, description="Type of notification"
    )

    # Delivery information
    channels: list[NotificationChannel] = Field(default_factory=list, description="Target channels")
    tags: list[str] = Field(default_factory=list, description="Notification tags")
    recipient: str | None = Field(None, description="Primary recipient (email, user ID, etc.)")

    # Status tracking
    status: NotificationStatus = Field(NotificationStatus.PENDING, description="Delivery status")
    delivery_attempts: int = Field(0, description="Number of delivery attempts")
    last_attempt: datetime | None = Field(None, description="Timestamp of last delivery attempt")

    # Results and errors
    success: bool = Field(False, description="Whether notification was successfully delivered")
    error_message: str | None = Field(None, description="Error message if delivery failed")
    delivery_details: dict[str, Any] = Field(
        default_factory=dict, description="Channel-specific delivery details"
    )

    # Template and context information
    template_name: str | None = Field(None, description="Template used for rendering")
    context_data: dict[str, Any] = Field(
        default_factory=dict, description="Template context data (sensitive data excluded)"
    )

    # Metadata
    source_component: str | None = Field(
        None, description="Component that triggered the notification"
    )
    correlation_id: str | None = Field(
        None, description="Correlation ID for tracking related notifications"
    )


class EmailNotificationContext(BaseModel):
    """
    Template context for email notifications.

    This model defines the standard context structure for email templates
    used in authentication and system notifications.
    """

    # Recipient information
    to_email: str = Field(..., description="Recipient email address")
    user_name: str | None = Field(None, description="Recipient display name")

    # Application branding
    app_name: str = Field("CoachIQ", description="Application name")
    app_logo_url: str | None = Field(None, description="Application logo URL")
    support_email: str = Field("support@coachiq.com", description="Support contact email")

    # Email content
    subject: str = Field(..., description="Email subject line")
    preheader: str | None = Field(None, description="Email preheader text")

    # Authentication-specific fields
    magic_link: str | None = Field(None, description="Magic link URL for authentication")
    verification_code: str | None = Field(None, description="Verification code")
    expires_minutes: int = Field(15, description="Link/code expiration time in minutes")

    # System notification fields
    system_component: str | None = Field(None, description="System component name")
    alert_level: str | None = Field(None, description="Alert severity level")
    action_required: bool = Field(False, description="Whether user action is required")
    action_url: str | None = Field(None, description="URL for required action")

    # Additional context data
    custom_data: dict[str, Any] = Field(default_factory=dict, description="Custom template data")


class MagicLinkContext(EmailNotificationContext):
    """
    Specialized context for magic link authentication emails.
    """

    magic_link: str = Field(..., description="Magic link URL for authentication")
    login_attempt_ip: str | None = Field(None, description="IP address of login attempt")
    login_attempt_location: str | None = Field(
        None, description="Geographic location of login attempt"
    )
    device_info: str | None = Field(None, description="Device/browser information")


class SystemNotificationContext(EmailNotificationContext):
    """
    Specialized context for system notification emails.
    """

    system_component: str = Field(..., description="System component name")
    alert_level: str = Field(..., description="Alert severity level")
    event_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )
    event_details: dict[str, Any] = Field(
        default_factory=dict, description="Event-specific details"
    )
    resolution_steps: list[str] = Field(
        default_factory=list, description="Suggested resolution steps"
    )


class NotificationTemplate(BaseModel):
    """
    Model for notification template metadata and configuration.
    """

    name: str = Field(..., description="Template name/identifier")
    display_name: str = Field(..., description="Human-readable template name")
    description: str | None = Field(None, description="Template description")

    # Template configuration
    template_type: str = Field("email", description="Template type (email, slack, etc.)")
    content_format: str = Field("html", description="Content format (html, text, markdown)")

    # Usage information
    category: str = Field("general", description="Template category (auth, system, user)")
    tags: list[str] = Field(default_factory=list, description="Template tags")

    # Validation and requirements
    required_context_fields: list[str] = Field(
        default_factory=list, description="Required context fields"
    )
    optional_context_fields: list[str] = Field(
        default_factory=list, description="Optional context fields"
    )

    # Template metadata
    version: str = Field("1.0", description="Template version")
    author: str | None = Field(None, description="Template author")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )


class NotificationPreferences(BaseModel):
    """
    Model for user notification preferences.

    This model will be used in the authentication system to store
    user preferences for different types of notifications.
    """

    user_id: str = Field(..., description="User identifier")

    # Channel preferences
    email_enabled: bool = Field(True, description="Enable email notifications")
    slack_enabled: bool = Field(False, description="Enable Slack notifications")
    discord_enabled: bool = Field(False, description="Enable Discord notifications")

    # Notification type preferences
    security_alerts: bool = Field(True, description="Receive security alerts")
    system_notifications: bool = Field(True, description="Receive system notifications")
    maintenance_notifications: bool = Field(False, description="Receive maintenance notifications")
    feature_announcements: bool = Field(False, description="Receive feature announcements")

    # Delivery preferences
    digest_mode: bool = Field(
        False, description="Receive digest instead of individual notifications"
    )
    digest_frequency: str = Field("daily", description="Digest frequency (hourly, daily, weekly)")
    quiet_hours_enabled: bool = Field(False, description="Enable quiet hours")
    quiet_hours_start: str | None = Field(None, description="Quiet hours start time (HH:MM)")
    quiet_hours_end: str | None = Field(None, description="Quiet hours end time (HH:MM)")

    # Metadata
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Preferences creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )


class NotificationChannelStatus(BaseModel):
    """
    Model for tracking notification channel health and status.
    """

    channel: NotificationChannel = Field(..., description="Notification channel")
    enabled: bool = Field(True, description="Whether channel is enabled")

    # Health information
    healthy: bool = Field(True, description="Whether channel is healthy")
    last_success: datetime | None = Field(None, description="Last successful delivery")
    last_failure: datetime | None = Field(None, description="Last delivery failure")
    consecutive_failures: int = Field(0, description="Number of consecutive failures")

    # Configuration status
    configured: bool = Field(False, description="Whether channel is properly configured")
    configuration_errors: list[str] = Field(
        default_factory=list, description="Configuration error messages"
    )

    # Performance metrics
    total_sent: int = Field(0, description="Total notifications sent")
    total_failures: int = Field(0, description="Total delivery failures")
    success_rate: float = Field(0.0, description="Success rate (0.0-1.0)")
    average_delivery_time: float | None = Field(
        None, description="Average delivery time in seconds"
    )

    # Status timestamps
    checked_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last status check timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )


# Queue-based notification models for Phase 1 modernization


class NotificationPayload(BaseModel):
    """
    Payload model for queue-based notification system.

    This model represents a notification in the persistent queue,
    containing all information needed for delivery.
    """

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique notification ID")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    # Content
    message: str = Field(..., description="Notification message body")
    title: str | None = Field(None, description="Notification title")
    level: NotificationType = Field(NotificationType.INFO, description="Notification level")

    # Delivery configuration
    channels: list[NotificationChannel] = Field(default_factory=list, description="Target channels")
    tags: list[str] = Field(default_factory=list, description="Notification tags")
    recipient: str | None = Field(None, description="Primary recipient identifier")

    # Template and context
    template: str | None = Field(None, description="Template name for rendering")
    context: dict[str, Any] = Field(default_factory=dict, description="Sanitized template context")

    # Queue management
    status: NotificationStatus = Field(NotificationStatus.PENDING, description="Processing status")
    retry_count: int = Field(0, description="Number of retry attempts")
    max_retries: int = Field(3, description="Maximum retry attempts")

    # Scheduling
    scheduled_for: datetime | None = Field(None, description="Scheduled delivery time")
    priority: int = Field(1, description="Priority level (1=highest, 10=lowest)")

    # Error tracking
    last_error: str | None = Field(None, description="Last error message")
    last_attempt: datetime | None = Field(None, description="Last processing attempt")

    # Source tracking
    source_component: str | None = Field(None, description="Component that created notification")
    correlation_id: str | None = Field(None, description="Correlation ID for tracking")

    # Pushover-specific fields
    pushover_priority: int | None = Field(None, description="Pushover priority level")
    pushover_device: str | None = Field(None, description="Specific Pushover device")


class QueueStatistics(BaseModel):
    """Statistics about the notification queue."""

    pending_count: int = Field(0, description="Number of pending notifications")
    processing_count: int = Field(0, description="Number of notifications being processed")
    completed_count: int = Field(0, description="Number of completed notifications (24h)")
    failed_count: int = Field(0, description="Number of failed notifications (24h)")
    dlq_count: int = Field(0, description="Number of notifications in dead letter queue")

    # Performance metrics
    avg_processing_time: float | None = Field(
        None, description="Average processing time in seconds"
    )
    success_rate: float = Field(0.0, description="Success rate (0.0-1.0) over last 24h")

    # Queue health
    oldest_pending: datetime | None = Field(
        None, description="Timestamp of oldest pending notification"
    )
    last_success: datetime | None = Field(None, description="Last successful delivery")
    last_failure: datetime | None = Field(None, description="Last delivery failure")

    # System status
    dispatcher_running: bool = Field(False, description="Whether background dispatcher is running")
    queue_size_bytes: int | None = Field(
        None, description="Approximate queue database size in bytes"
    )

    # Generated at
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Statistics generation time"
    )


class RateLimitStatus(BaseModel):
    """Status of the rate limiting system."""

    current_tokens: int = Field(0, description="Current available tokens")
    max_tokens: int = Field(100, description="Maximum tokens in bucket")
    refill_rate: float = Field(10.0, description="Token refill rate per minute")

    # Recent activity
    requests_last_minute: int = Field(0, description="Requests in last minute")
    requests_blocked: int = Field(0, description="Requests blocked by rate limiting")

    # Debouncing status
    active_debounces: int = Field(0, description="Number of active debounce suppressions")

    # Status
    healthy: bool = Field(True, description="Whether rate limiting is functioning properly")
    last_reset: datetime = Field(
        default_factory=datetime.utcnow, description="Last token bucket reset"
    )


class DeadLetterEntry(BaseModel):
    """Entry in the dead letter queue for permanently failed notifications."""

    id: str = Field(..., description="Unique entry ID")
    original_notification: NotificationPayload = Field(
        ..., description="Original notification payload"
    )

    # Failure information
    failed_at: datetime = Field(
        default_factory=datetime.utcnow, description="When notification finally failed"
    )
    failure_reason: str = Field(..., description="Final failure reason")
    total_attempts: int = Field(0, description="Total delivery attempts made")

    # Error history
    error_history: list[str] = Field(default_factory=list, description="History of error messages")

    # Management
    reviewed: bool = Field(False, description="Whether failure has been reviewed")
    can_retry: bool = Field(True, description="Whether notification can be retried")
    retry_after: datetime | None = Field(None, description="Earliest time for retry")


class NotificationBatch(BaseModel):
    """Batch of notifications for efficient processing."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Batch ID")
    notifications: list[NotificationPayload] = Field(..., description="Notifications in batch")

    # Batch metadata
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Batch creation time")
    batch_size: int = Field(0, description="Number of notifications in batch")

    # Processing status
    status: str = Field("pending", description="Batch processing status")
    started_at: datetime | None = Field(None, description="Processing start time")
    completed_at: datetime | None = Field(None, description="Processing completion time")

    # Results
    successful_count: int = Field(0, description="Number of successful deliveries")
    failed_count: int = Field(0, description="Number of failed deliveries")
    errors: list[str] = Field(default_factory=list, description="Batch processing errors")
