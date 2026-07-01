# ruff: noqa: INP001
"""Add MCP OAuth AS tables

Revision ID: b4c7d8e9f012
Revises: 9a6b7c8d9e0f
Create Date: 2026-07-01 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c7d8e9f012"
down_revision: str | None = "9a6b7c8d9e0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "mcp_oauth_clients",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("client_id", sa.String(length=128), nullable=False),
        sa.Column("client_secret_hash", sa.String(length=64), nullable=False),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mcp_oauth_clients_client_id"),
        "mcp_oauth_clients",
        ["client_id"],
        unique=True,
    )
    op.create_table(
        "mcp_oauth_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transaction_state", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.String(length=128), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("client_state", sa.Text(), nullable=True),
        sa.Column("client_code_challenge", sa.String(length=255), nullable=False),
        sa.Column("client_code_challenge_method", sa.String(length=20), nullable=False),
        sa.Column("upstream_code_verifier", sa.String(length=255), nullable=False),
        sa.Column("upstream_nonce", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mcp_oauth_transactions_client_id"),
        "mcp_oauth_transactions",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mcp_oauth_transactions_transaction_state"),
        "mcp_oauth_transactions",
        ["transaction_state"],
        unique=True,
    )
    op.create_table(
        "mcp_oauth_authorization_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.String(length=255), nullable=False),
        sa.Column("code_challenge_method", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mcp_oauth_authorization_codes_client_id"),
        "mcp_oauth_authorization_codes",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mcp_oauth_authorization_codes_code_hash"),
        "mcp_oauth_authorization_codes",
        ["code_hash"],
        unique=True,
    )
    op.create_table(
        "mcp_oauth_access_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("client_id", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mcp_oauth_access_tokens_client_id"),
        "mcp_oauth_access_tokens",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mcp_oauth_access_tokens_token_hash"),
        "mcp_oauth_access_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_mcp_oauth_access_tokens_token_hash"),
        table_name="mcp_oauth_access_tokens",
    )
    op.drop_index(
        op.f("ix_mcp_oauth_access_tokens_client_id"),
        table_name="mcp_oauth_access_tokens",
    )
    op.drop_table("mcp_oauth_access_tokens")
    op.drop_index(
        op.f("ix_mcp_oauth_authorization_codes_code_hash"),
        table_name="mcp_oauth_authorization_codes",
    )
    op.drop_index(
        op.f("ix_mcp_oauth_authorization_codes_client_id"),
        table_name="mcp_oauth_authorization_codes",
    )
    op.drop_table("mcp_oauth_authorization_codes")
    op.drop_index(
        op.f("ix_mcp_oauth_transactions_transaction_state"),
        table_name="mcp_oauth_transactions",
    )
    op.drop_index(
        op.f("ix_mcp_oauth_transactions_client_id"),
        table_name="mcp_oauth_transactions",
    )
    op.drop_table("mcp_oauth_transactions")
    op.drop_index(op.f("ix_mcp_oauth_clients_client_id"), table_name="mcp_oauth_clients")
    op.drop_table("mcp_oauth_clients")
