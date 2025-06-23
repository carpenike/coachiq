"""add_security_events_table

Revision ID: security_events_20250614
Revises: pin_auth_20250613
Create Date: 2025-06-14 12:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "security_events_20250614"
down_revision: str | None = "pin_auth_20250613"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - add security events table."""
    # Create security_events table
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="Primary key"),
        sa.Column(
            "event_id", sa.String(length=255), nullable=False, comment="Unique event identifier"
        ),
        sa.Column("event_uuid", sa.String(length=36), nullable=False, comment="UUID for event"),
        sa.Column(
            "timestamp", sa.Float(), nullable=False, comment="Event timestamp (Unix timestamp)"
        ),
        sa.Column(
            "timestamp_ms",
            sa.BigInteger(),
            nullable=False,
            comment="Event timestamp in milliseconds",
        ),
        sa.Column(
            "source_component",
            sa.String(length=100),
            nullable=False,
            comment="Component that generated the event",
        ),
        sa.Column(
            "event_type", sa.String(length=100), nullable=False, comment="Type of security event"
        ),
        sa.Column("severity", sa.String(length=20), nullable=False, comment="Event severity level"),
        sa.Column(
            "title", sa.String(length=500), nullable=False, comment="Human-readable event title"
        ),
        sa.Column("description", sa.Text(), nullable=False, comment="Detailed event description"),
        sa.Column("payload", sa.JSON(), nullable=False, comment="Event-specific data payload"),
        sa.Column(
            "event_metadata", sa.JSON(), nullable=True, comment="Additional context and metadata"
        ),
        sa.Column(
            "incident_id", sa.String(length=255), nullable=True, comment="Associated incident ID"
        ),
        sa.Column(
            "correlation_id", sa.String(length=255), nullable=True, comment="Event correlation ID"
        ),
        sa.Column(
            "acknowledged",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether event has been acknowledged",
        ),
        sa.Column(
            "acknowledged_by",
            sa.String(length=255),
            nullable=True,
            comment="User who acknowledged event",
        ),
        sa.Column("acknowledged_at", sa.Float(), nullable=True, comment="Acknowledgment timestamp"),
        sa.Column("evidence_data", sa.JSON(), nullable=True, comment="Supporting evidence"),
        sa.Column("remediation_action", sa.Text(), nullable=True, comment="Suggested remediation"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
        sa.UniqueConstraint("event_uuid"),
        comment="Security events from all system components",
    )

    # Create indexes for security_events table
    op.create_index("idx_security_events_timestamp", "security_events", ["timestamp"])
    op.create_index("idx_security_events_event_type", "security_events", ["event_type"])
    op.create_index("idx_security_events_severity", "security_events", ["severity"])
    op.create_index("idx_security_events_source_component", "security_events", ["source_component"])
    op.create_index(
        "idx_security_events_type_severity", "security_events", ["event_type", "severity"]
    )
    op.create_index(
        "idx_security_events_component_timestamp",
        "security_events",
        ["source_component", "timestamp"],
    )
    op.create_index(
        "idx_security_events_severity_timestamp", "security_events", ["severity", "timestamp"]
    )
    op.create_index("idx_security_events_acknowledged", "security_events", ["acknowledged"])
    op.create_index("idx_security_events_incident_id", "security_events", ["incident_id"])
    op.create_index("idx_security_events_correlation_id", "security_events", ["correlation_id"])
    op.create_index("idx_security_events_timestamp_ms", "security_events", ["timestamp_ms"])

    # Create security_incidents table
    op.create_table(
        "security_incidents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="Primary key"),
        sa.Column(
            "incident_id",
            sa.String(length=255),
            nullable=False,
            comment="Unique incident identifier",
        ),
        sa.Column(
            "incident_uuid", sa.String(length=36), nullable=False, comment="UUID for incident"
        ),
        sa.Column("created_at", sa.Float(), nullable=False, comment="Incident creation timestamp"),
        sa.Column("updated_at", sa.Float(), nullable=False, comment="Last update timestamp"),
        sa.Column("closed_at", sa.Float(), nullable=True, comment="Incident closure timestamp"),
        sa.Column(
            "title", sa.String(length=500), nullable=False, comment="Human-readable incident title"
        ),
        sa.Column(
            "description", sa.Text(), nullable=False, comment="Detailed incident description"
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="open",
            comment="Incident status",
        ),
        sa.Column(
            "severity", sa.String(length=20), nullable=False, comment="Incident severity level"
        ),
        sa.Column("category", sa.String(length=100), nullable=False, comment="Incident category"),
        sa.Column(
            "assigned_to", sa.String(length=255), nullable=True, comment="Assigned investigator"
        ),
        sa.Column("investigation_notes", sa.Text(), nullable=True, comment="Investigation notes"),
        sa.Column(
            "event_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of associated events",
        ),
        sa.Column(
            "primary_event_id",
            sa.String(length=255),
            nullable=True,
            comment="Primary triggering event",
        ),
        sa.Column("resolution", sa.Text(), nullable=True, comment="Incident resolution"),
        sa.Column("remediation_actions", sa.JSON(), nullable=True, comment="Actions taken"),
        sa.Column(
            "db_created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "db_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id"),
        sa.UniqueConstraint("incident_uuid"),
        comment="Security incidents for grouping related events",
    )

    # Create indexes for security_incidents table
    op.create_index("idx_security_incidents_created_at", "security_incidents", ["created_at"])
    op.create_index("idx_security_incidents_status", "security_incidents", ["status"])
    op.create_index("idx_security_incidents_severity", "security_incidents", ["severity"])
    op.create_index("idx_security_incidents_category", "security_incidents", ["category"])
    op.create_index("idx_security_incidents_assigned_to", "security_incidents", ["assigned_to"])
    op.create_index(
        "idx_security_incidents_status_severity", "security_incidents", ["status", "severity"]
    )
    op.create_index(
        "idx_security_incidents_primary_event", "security_incidents", ["primary_event_id"]
    )


def downgrade() -> None:
    """Downgrade schema - remove security events table."""
    # Drop security_incidents table and indexes
    op.drop_index("idx_security_incidents_primary_event", table_name="security_incidents")
    op.drop_index("idx_security_incidents_status_severity", table_name="security_incidents")
    op.drop_index("idx_security_incidents_assigned_to", table_name="security_incidents")
    op.drop_index("idx_security_incidents_category", table_name="security_incidents")
    op.drop_index("idx_security_incidents_severity", table_name="security_incidents")
    op.drop_index("idx_security_incidents_status", table_name="security_incidents")
    op.drop_index("idx_security_incidents_created_at", table_name="security_incidents")
    op.drop_table("security_incidents")

    # Drop security_events table and indexes
    op.drop_index("idx_security_events_timestamp_ms", table_name="security_events")
    op.drop_index("idx_security_events_correlation_id", table_name="security_events")
    op.drop_index("idx_security_events_incident_id", table_name="security_events")
    op.drop_index("idx_security_events_acknowledged", table_name="security_events")
    op.drop_index("idx_security_events_severity_timestamp", table_name="security_events")
    op.drop_index("idx_security_events_component_timestamp", table_name="security_events")
    op.drop_index("idx_security_events_type_severity", table_name="security_events")
    op.drop_index("idx_security_events_source_component", table_name="security_events")
    op.drop_index("idx_security_events_severity", table_name="security_events")
    op.drop_index("idx_security_events_event_type", table_name="security_events")
    op.drop_index("idx_security_events_timestamp", table_name="security_events")
    op.drop_table("security_events")
