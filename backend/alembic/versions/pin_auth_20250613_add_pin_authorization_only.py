"""add_pin_authorization_only

Revision ID: pin_auth_20250613
Revises: notification_analytics_001
Create Date: 2025-06-13 23:30:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "pin_auth_20250613"
down_revision: str | None = "notification_analytics_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema to add PIN authorization tables only."""
    # Create user_pins table
    op.create_table(
        "user_pins",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("pin_type", sa.String(length=20), nullable=False),
        sa.Column("pin_hash", sa.String(length=255), nullable=False),
        sa.Column("salt", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("lockout_after_failures", sa.Integer(), nullable=False),
        sa.Column("lockout_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_pins_pin_type"), "user_pins", ["pin_type"], unique=False)
    op.create_index(op.f("ix_user_pins_user_id"), "user_pins", ["user_id"], unique=False)

    # Create pin_sessions table
    op.create_table(
        "pin_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_pin_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("max_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("max_operations", sa.Integer(), nullable=True),
        sa.Column("operation_count", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_pin_id"],
            ["user_pins.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pin_sessions_created_by_user_id"),
        "pin_sessions",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_pin_sessions_session_id"), "pin_sessions", ["session_id"], unique=True)
    op.create_index(
        op.f("ix_pin_sessions_user_pin_id"), "pin_sessions", ["user_pin_id"], unique=False
    )

    # Create pin_attempts table
    op.create_table(
        "pin_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_pin_id", sa.String(length=36), nullable=True),
        sa.Column("attempted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("pin_type", sa.String(length=20), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(length=100), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("operation_context", sa.Text(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempted_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_pin_id"],
            ["user_pins.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pin_attempts_attempted_at"), "pin_attempts", ["attempted_at"], unique=False
    )
    op.create_index(
        op.f("ix_pin_attempts_attempted_by_user_id"),
        "pin_attempts",
        ["attempted_by_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_pin_attempts_pin_type"), "pin_attempts", ["pin_type"], unique=False)
    op.create_index(op.f("ix_pin_attempts_success"), "pin_attempts", ["success"], unique=False)
    op.create_index(
        op.f("ix_pin_attempts_user_pin_id"), "pin_attempts", ["user_pin_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema to remove PIN authorization tables."""
    op.drop_index(op.f("ix_pin_attempts_user_pin_id"), table_name="pin_attempts")
    op.drop_index(op.f("ix_pin_attempts_success"), table_name="pin_attempts")
    op.drop_index(op.f("ix_pin_attempts_pin_type"), table_name="pin_attempts")
    op.drop_index(op.f("ix_pin_attempts_attempted_by_user_id"), table_name="pin_attempts")
    op.drop_index(op.f("ix_pin_attempts_attempted_at"), table_name="pin_attempts")
    op.drop_table("pin_attempts")

    op.drop_index(op.f("ix_pin_sessions_user_pin_id"), table_name="pin_sessions")
    op.drop_index(op.f("ix_pin_sessions_session_id"), table_name="pin_sessions")
    op.drop_index(op.f("ix_pin_sessions_created_by_user_id"), table_name="pin_sessions")
    op.drop_table("pin_sessions")

    op.drop_index(op.f("ix_user_pins_user_id"), table_name="user_pins")
    op.drop_index(op.f("ix_user_pins_pin_type"), table_name="user_pins")
    op.drop_table("user_pins")
