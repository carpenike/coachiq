"""Add optimized indexes for Raspberry Pi deployment

Revision ID: add_rpi_indexes_001
Revises: 5537d057c7dd
Create Date: 2024-01-03

Adds minimal but effective indexes for SQLite on Raspberry Pi 4
with focus on the most common queries in an RV control system.
"""

from alembic import op

# revision identifiers
revision = "add_rpi_indexes_001"
down_revision = "5537d057c7dd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add optimized indexes for Raspberry Pi deployment."""

    # Entity states - Most frequently queried table
    op.create_index("idx_entity_states_entity_id", "entity_states", ["entity_id"])
    op.create_index("idx_entity_states_updated_at", "entity_states", ["updated_at"])
    op.create_index("idx_entity_states_device_type", "entity_states", ["device_type"])

    # Composite index for common query pattern: get latest state by device type
    op.create_index(
        "idx_entity_states_type_updated",
        "entity_states",
        ["device_type", "updated_at"]
    )

    # System settings - Frequent key lookups
    op.create_index("idx_system_settings_key", "system_settings", ["key"])

    # User settings - Key and category lookups
    op.create_index("idx_user_settings_key", "user_settings", ["key"])
    op.create_index("idx_user_settings_category", "user_settings", ["category"])

    # Configurations - Namespace and key lookups (already has unique constraint)
    # No additional index needed due to unique constraint

    # Dashboards - Default dashboard lookup
    op.create_index("idx_dashboards_is_default", "dashboards", ["is_default"])

    # Auth tables if they exist
    try:
        # Users table
        op.create_index("idx_users_username", "users", ["username"])
        op.create_index("idx_users_is_active", "users", ["is_active"])
    except Exception:
        pass  # Table might not exist yet

    try:
        # Sessions table
        op.create_index("idx_auth_sessions_token", "auth_sessions", ["session_token"])
        op.create_index("idx_auth_sessions_expires", "auth_sessions", ["expires_at"])
        op.create_index("idx_auth_sessions_user_id", "auth_sessions", ["user_id"])
    except Exception:
        pass  # Table might not exist yet

    try:
        # Security audit logs
        op.create_index("idx_security_audit_logs_timestamp", "security_audit_logs", ["timestamp"])
        op.create_index("idx_security_audit_logs_event_type", "security_audit_logs", ["event_type"])
    except Exception:
        pass  # Table might not exist yet


def downgrade() -> None:
    """Remove optimized indexes."""

    # Entity states
    op.drop_index("idx_entity_states_entity_id", "entity_states")
    op.drop_index("idx_entity_states_updated_at", "entity_states")
    op.drop_index("idx_entity_states_device_type", "entity_states")
    op.drop_index("idx_entity_states_type_updated", "entity_states")

    # System settings
    op.drop_index("idx_system_settings_key", "system_settings")

    # User settings
    op.drop_index("idx_user_settings_key", "user_settings")
    op.drop_index("idx_user_settings_category", "user_settings")

    # Dashboards
    op.drop_index("idx_dashboards_is_default", "dashboards")

    # Auth tables if they exist
    try:
        op.drop_index("idx_users_username", "users")
        op.drop_index("idx_users_is_active", "users")
    except Exception:
        pass

    try:
        op.drop_index("idx_auth_sessions_token", "auth_sessions")
        op.drop_index("idx_auth_sessions_expires", "auth_sessions")
        op.drop_index("idx_auth_sessions_user_id", "auth_sessions")
    except Exception:
        pass

    try:
        op.drop_index("idx_security_audit_logs_timestamp", "security_audit_logs")
        op.drop_index("idx_security_audit_logs_event_type", "security_audit_logs")
    except Exception:
        pass
