"""Create notification analytics tables

Revision ID: notification_analytics_001
Revises: 68ed601820ee
Create Date: 2024-01-01 00:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "notification_analytics_001"
down_revision: str | None = "68ed601820ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create notification_delivery_logs table
    op.create_table(
        "notification_delivery_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="Primary key"),
        sa.Column(
            "notification_id",
            sa.String(length=255),
            nullable=False,
            comment="Unique notification ID",
        ),
        sa.Column("channel", sa.String(length=50), nullable=False, comment="Delivery channel"),
        sa.Column(
            "notification_type",
            sa.String(length=50),
            nullable=False,
            comment="Type of notification",
        ),
        sa.Column("status", sa.String(length=50), nullable=False, comment="Delivery status"),
        sa.Column(
            "recipient", sa.String(length=255), nullable=True, comment="Recipient identifier"
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Actual delivery timestamp",
        ),
        sa.Column(
            "delivery_time_ms", sa.Integer(), nullable=True, comment="Delivery time in milliseconds"
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of retry attempts",
        ),
        sa.Column("error_message", sa.Text(), nullable=True, comment="Error message if failed"),
        sa.Column(
            "error_code", sa.String(length=100), nullable=True, comment="Structured error code"
        ),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="Additional delivery metadata"),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When notification was opened",
        ),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When notification was clicked",
        ),
        sa.Column(
            "dismissed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When notification was dismissed",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for notification_delivery_logs
    op.create_index(
        "idx_delivery_logs_notification_id", "notification_delivery_logs", ["notification_id"]
    )
    op.create_index("idx_delivery_logs_channel", "notification_delivery_logs", ["channel"])
    op.create_index(
        "idx_delivery_logs_notification_type", "notification_delivery_logs", ["notification_type"]
    )
    op.create_index("idx_delivery_logs_status", "notification_delivery_logs", ["status"])
    op.create_index("idx_delivery_logs_timestamp", "notification_delivery_logs", ["created_at"])
    op.create_index(
        "idx_delivery_logs_channel_status", "notification_delivery_logs", ["channel", "status"]
    )
    op.create_index(
        "idx_delivery_logs_type_status",
        "notification_delivery_logs",
        ["notification_type", "status"],
    )
    op.create_index("idx_delivery_logs_error_code", "notification_delivery_logs", ["error_code"])
    op.create_index("idx_delivery_logs_recipient", "notification_delivery_logs", ["recipient"])

    # Create notification_metric_aggregates table
    op.create_table(
        "notification_metric_aggregates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="Primary key"),
        sa.Column("metric_type", sa.String(length=100), nullable=False, comment="Type of metric"),
        sa.Column(
            "aggregation_period", sa.String(length=20), nullable=False, comment="Aggregation period"
        ),
        sa.Column(
            "period_start", sa.DateTime(timezone=True), nullable=False, comment="Start of period"
        ),
        sa.Column(
            "period_end", sa.DateTime(timezone=True), nullable=False, comment="End of period"
        ),
        sa.Column(
            "channel", sa.String(length=50), nullable=True, comment="Optional channel filter"
        ),
        sa.Column(
            "notification_type", sa.String(length=50), nullable=True, comment="Optional type filter"
        ),
        sa.Column("value", sa.Float(), nullable=False, comment="Aggregated metric value"),
        sa.Column(
            "count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of data points",
        ),
        sa.Column("min_value", sa.Float(), nullable=True, comment="Minimum value in period"),
        sa.Column("max_value", sa.Float(), nullable=True, comment="Maximum value in period"),
        sa.Column("std_deviation", sa.Float(), nullable=True, comment="Standard deviation"),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="Additional metric metadata"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for notification_metric_aggregates
    op.create_index(
        "idx_metric_aggregates_metric_type", "notification_metric_aggregates", ["metric_type"]
    )
    op.create_index(
        "idx_metric_aggregates_aggregation_period",
        "notification_metric_aggregates",
        ["aggregation_period"],
    )
    op.create_index(
        "idx_metric_aggregates_period_start", "notification_metric_aggregates", ["period_start"]
    )
    op.create_index(
        "idx_metric_aggregates_period",
        "notification_metric_aggregates",
        ["aggregation_period", "period_start"],
    )
    op.create_index(
        "idx_metric_aggregates_type_period",
        "notification_metric_aggregates",
        ["metric_type", "aggregation_period", "period_start"],
    )
    op.create_index(
        "idx_metric_aggregates_channel",
        "notification_metric_aggregates",
        ["channel", "period_start"],
    )

    # Create notification_error_analysis table
    op.create_table(
        "notification_error_analysis",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="Primary key"),
        sa.Column("error_code", sa.String(length=100), nullable=False, comment="Error code"),
        sa.Column("error_message", sa.Text(), nullable=False, comment="Error message pattern"),
        sa.Column("channel", sa.String(length=50), nullable=False, comment="Affected channel"),
        sa.Column(
            "occurrence_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Number of occurrences",
        ),
        sa.Column(
            "first_seen", sa.DateTime(timezone=True), nullable=False, comment="First occurrence"
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Most recent occurrence",
        ),
        sa.Column(
            "affected_recipients",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of affected recipients",
        ),
        sa.Column(
            "retry_success_rate",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Success rate after retry",
        ),
        sa.Column(
            "recommended_action", sa.Text(), nullable=True, comment="Recommended remediation"
        ),
        sa.Column(
            "is_resolved",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether error is resolved",
        ),
        sa.Column("resolution_notes", sa.Text(), nullable=True, comment="Resolution notes"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for notification_error_analysis
    op.create_index("idx_error_analysis_error_code", "notification_error_analysis", ["error_code"])
    op.create_index("idx_error_analysis_channel", "notification_error_analysis", ["channel"])
    op.create_index(
        "idx_error_analysis_code_channel", "notification_error_analysis", ["error_code", "channel"]
    )
    op.create_index("idx_error_analysis_last_seen", "notification_error_analysis", ["last_seen"])
    op.create_index("idx_error_analysis_resolved", "notification_error_analysis", ["is_resolved"])

    # Create notification_queue_health table
    op.create_table(
        "notification_queue_health",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="Primary key"),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, comment="Measurement timestamp"
        ),
        sa.Column(
            "queue_depth", sa.Integer(), nullable=False, comment="Number of pending notifications"
        ),
        sa.Column(
            "processing_rate", sa.Float(), nullable=False, comment="Notifications per second"
        ),
        sa.Column("success_rate", sa.Float(), nullable=False, comment="Successful delivery rate"),
        sa.Column(
            "average_wait_time",
            sa.Float(),
            nullable=False,
            comment="Average queue wait time in seconds",
        ),
        sa.Column(
            "average_processing_time",
            sa.Float(),
            nullable=False,
            comment="Average processing time in seconds",
        ),
        sa.Column(
            "dlq_size",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Dead letter queue size",
        ),
        sa.Column(
            "active_workers",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of active workers",
        ),
        sa.Column("memory_usage_mb", sa.Float(), nullable=True, comment="Queue memory usage in MB"),
        sa.Column("cpu_usage_percent", sa.Float(), nullable=True, comment="CPU usage percentage"),
        sa.Column(
            "health_score", sa.Float(), nullable=False, comment="Overall health score (0.0-1.0)"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for notification_queue_health
    op.create_index("idx_queue_health_timestamp", "notification_queue_health", ["timestamp"])
    op.create_index(
        "idx_queue_health_score", "notification_queue_health", ["health_score", "timestamp"]
    )

    # Create notification_reports table
    op.create_table(
        "notification_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="Primary key"),
        sa.Column("report_id", sa.String(length=255), nullable=False, comment="Unique report ID"),
        sa.Column("report_type", sa.String(length=100), nullable=False, comment="Type of report"),
        sa.Column("report_name", sa.String(length=500), nullable=False, comment="Report name"),
        sa.Column(
            "start_date", sa.DateTime(timezone=True), nullable=False, comment="Report period start"
        ),
        sa.Column(
            "end_date", sa.DateTime(timezone=True), nullable=False, comment="Report period end"
        ),
        sa.Column(
            "generated_by",
            sa.String(length=255),
            nullable=True,
            comment="User who generated report",
        ),
        sa.Column(
            "format", sa.String(length=20), nullable=False, comment="Report format (json, csv, pdf)"
        ),
        sa.Column(
            "file_path",
            sa.String(length=1000),
            nullable=True,
            comment="Path to generated report file",
        ),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True, comment="Report file size"),
        sa.Column("summary_data", sa.JSON(), nullable=False, comment="Report summary data"),
        sa.Column("parameters", sa.JSON(), nullable=True, comment="Report generation parameters"),
        sa.Column(
            "is_scheduled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether report was scheduled",
        ),
        sa.Column(
            "schedule_id", sa.String(length=255), nullable=True, comment="Schedule ID if scheduled"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Generated at timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id"),
    )

    # Create indexes for notification_reports
    op.create_index("idx_reports_report_type", "notification_reports", ["report_type"])
    op.create_index("idx_reports_type_date", "notification_reports", ["report_type", "created_at"])
    op.create_index("idx_reports_generated_by", "notification_reports", ["generated_by"])
    op.create_index("idx_reports_schedule", "notification_reports", ["is_scheduled", "schedule_id"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("notification_reports")
    op.drop_table("notification_queue_health")
    op.drop_table("notification_error_analysis")
    op.drop_table("notification_metric_aggregates")
    op.drop_table("notification_delivery_logs")
