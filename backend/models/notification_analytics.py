"""
Notification analytics data models and types.

This module defines models for tracking notification metrics, delivery statistics,
and performance analytics across all notification channels.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.database import Base, TimestampMixin
from backend.models.notification import NotificationChannel, NotificationType


class AggregationPeriod(str, Enum):
    """Time periods for metric aggregation."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class MetricType(str, Enum):
    """Types of notification metrics."""

    DELIVERY_COUNT = "delivery_count"
    SUCCESS_RATE = "success_rate"
    FAILURE_RATE = "failure_rate"
    RETRY_COUNT = "retry_count"
    AVERAGE_DELIVERY_TIME = "avg_delivery_time"
    CHANNEL_PERFORMANCE = "channel_performance"
    ERROR_RATE = "error_rate"
    ENGAGEMENT_RATE = "engagement_rate"


@dataclass
class NotificationMetric:
    """Data point for notification metrics."""

    timestamp: datetime
    metric_type: MetricType
    value: float
    channel: NotificationChannel | None = None
    notification_type: NotificationType | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelMetrics:
    """Metrics for a specific notification channel."""

    channel: NotificationChannel
    total_sent: int
    total_delivered: int
    total_failed: int
    total_retried: int
    success_rate: float
    average_delivery_time: float | None
    last_success: datetime | None
    last_failure: datetime | None
    error_breakdown: dict[str, int]


@dataclass
class NotificationReportData:
    """Comprehensive notification report data."""

    report_id: str
    start_date: datetime
    end_date: datetime
    total_notifications: int
    successful_deliveries: int
    failed_deliveries: int
    retry_attempts: int
    channel_metrics: list[ChannelMetrics]
    hourly_distribution: dict[int, int]
    type_distribution: dict[str, int]
    top_errors: list[tuple[str, int]]
    performance_trends: dict[str, list[float]]


# SQLAlchemy Models for Persistence


class NotificationDeliveryLog(Base, TimestampMixin):
    """
    SQLAlchemy model for notification delivery logs.

    Tracks individual notification delivery attempts and results
    for analytics and auditing purposes.
    """

    __tablename__ = "notification_delivery_logs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Primary key"
    )

    notification_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Unique notification ID"
    )

    channel: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="Delivery channel"
    )

    notification_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="Type of notification"
    )

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="Delivery status"
    )

    recipient: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="Recipient identifier"
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Actual delivery timestamp"
    )

    delivery_time_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Delivery time in milliseconds"
    )

    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of retry attempts"
    )

    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error message if failed"
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True, comment="Structured error code"
    )

    delivery_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Additional delivery metadata"
    )

    # User engagement tracking
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When notification was opened"
    )

    clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When notification was clicked"
    )

    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When notification was dismissed"
    )

    # Define table constraints and indexes
    __table_args__ = (
        Index("idx_delivery_logs_timestamp", "created_at"),
        Index("idx_delivery_logs_channel_status", "channel", "status"),
        Index("idx_delivery_logs_type_status", "notification_type", "status"),
        Index("idx_delivery_logs_error_code", "error_code"),
        Index("idx_delivery_logs_recipient", "recipient"),
    )


class NotificationMetricAggregate(Base, TimestampMixin):
    """
    SQLAlchemy model for aggregated notification metrics.

    Stores pre-computed metric aggregations for efficient querying
    and reporting.
    """

    __tablename__ = "notification_metric_aggregates"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Primary key"
    )

    metric_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Type of metric"
    )

    aggregation_period: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="Aggregation period"
    )

    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True, comment="Start of period"
    )

    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="End of period"
    )

    channel: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True, comment="Optional channel filter"
    )

    notification_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True, comment="Optional type filter"
    )

    value: Mapped[float] = mapped_column(Float, nullable=False, comment="Aggregated metric value")

    count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of data points"
    )

    min_value: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Minimum value in period"
    )

    max_value: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Maximum value in period"
    )

    std_deviation: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Standard deviation"
    )

    metric_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Additional metric metadata"
    )

    # Define table constraints and indexes
    __table_args__ = (
        Index("idx_metric_aggregates_period", "aggregation_period", "period_start"),
        Index(
            "idx_metric_aggregates_type_period", "metric_type", "aggregation_period", "period_start"
        ),
        Index("idx_metric_aggregates_channel", "channel", "period_start"),
    )


class NotificationErrorAnalysis(Base, TimestampMixin):
    """
    SQLAlchemy model for notification error analysis.

    Tracks and analyzes notification delivery errors for
    pattern detection and improvement.
    """

    __tablename__ = "notification_error_analysis"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Primary key"
    )

    error_code: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Error code"
    )

    error_message: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Error message pattern"
    )

    channel: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="Affected channel"
    )

    occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="Number of occurrences"
    )

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="First occurrence"
    )

    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Most recent occurrence"
    )

    affected_recipients: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of affected recipients"
    )

    retry_success_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="Success rate after retry"
    )

    recommended_action: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Recommended remediation"
    )

    is_resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Whether error is resolved"
    )

    resolution_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Resolution notes"
    )

    # Define table constraints and indexes
    __table_args__ = (
        Index("idx_error_analysis_code_channel", "error_code", "channel"),
        Index("idx_error_analysis_last_seen", "last_seen"),
        Index("idx_error_analysis_resolved", "is_resolved"),
    )


class NotificationQueueHealth(Base, TimestampMixin):
    """
    SQLAlchemy model for notification queue health metrics.

    Tracks queue performance and health indicators over time.
    """

    __tablename__ = "notification_queue_health"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Primary key"
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True, comment="Measurement timestamp"
    )

    queue_depth: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Number of pending notifications"
    )

    processing_rate: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Notifications per second"
    )

    success_rate: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Successful delivery rate"
    )

    average_wait_time: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Average queue wait time in seconds"
    )

    average_processing_time: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Average processing time in seconds"
    )

    dlq_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Dead letter queue size"
    )

    active_workers: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of active workers"
    )

    memory_usage_mb: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Queue memory usage in MB"
    )

    cpu_usage_percent: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="CPU usage percentage"
    )

    health_score: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Overall health score (0.0-1.0)"
    )

    # Define table constraints and indexes
    __table_args__ = (
        Index("idx_queue_health_timestamp", "timestamp"),
        Index("idx_queue_health_score", "health_score", "timestamp"),
    )


class NotificationReport(Base, TimestampMixin):
    """
    SQLAlchemy model for generated notification reports.

    Stores generated reports for historical access and audit trails.
    """

    __tablename__ = "notification_reports"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Primary key"
    )

    report_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, comment="Unique report ID"
    )

    report_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Type of report"
    )

    report_name: Mapped[str] = mapped_column(String(500), nullable=False, comment="Report name")

    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Report period start"
    )

    end_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Report period end"
    )

    generated_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="User who generated report"
    )

    format: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Report format (json, csv, pdf)"
    )

    file_path: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="Path to generated report file"
    )

    file_size_bytes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Report file size"
    )

    summary_data: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="Report summary data"
    )

    parameters: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Report generation parameters"
    )

    is_scheduled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="Whether report was scheduled"
    )

    schedule_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Schedule ID if scheduled"
    )

    # Define table constraints and indexes
    __table_args__ = (
        Index("idx_reports_type_date", "report_type", "created_at"),
        Index("idx_reports_generated_by", "generated_by"),
        Index("idx_reports_schedule", "is_scheduled", "schedule_id"),
    )
