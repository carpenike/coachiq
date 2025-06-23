"""Add database backup and migration history tables

Revision ID: f3c4a20601b2
Revises: security_events_20250614
Create Date: 2025-06-20 15:36:46.721605

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3c4a20601b2"
down_revision: str | None = "security_events_20250614"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create database_backups table
    op.create_table(
        "database_backups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("backup_type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create index on created_at for efficient cleanup queries
    op.create_index(
        "ix_database_backups_created_at", "database_backups", ["created_at"], unique=False
    )

    # Create migration_history table
    op.create_table(
        "migration_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_version", sa.String(), nullable=False),
        sa.Column("to_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create index on executed_at for efficient history queries
    op.create_index(
        "ix_migration_history_executed_at", "migration_history", ["executed_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop migration_history table and index
    op.drop_index("ix_migration_history_executed_at", table_name="migration_history")
    op.drop_table("migration_history")

    # Drop database_backups table and index
    op.drop_index("ix_database_backups_created_at", table_name="database_backups")
    op.drop_table("database_backups")
