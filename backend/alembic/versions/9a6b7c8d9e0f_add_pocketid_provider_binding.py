# ruff: noqa: INP001
"""Add PocketID provider binding constraint

Revision ID: 9a6b7c8d9e0f
Revises: 0078a61315c9
Create Date: 2026-07-01 02:10:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a6b7c8d9e0f"
down_revision: str | None = "0078a61315c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CONSTRAINT_NAME = "uq_user_auth_provider_identity"
_TABLE_NAME = "user_auth_providers"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        _CONSTRAINT_NAME,
        _TABLE_NAME,
        ["provider", "provider_user_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(_CONSTRAINT_NAME, _TABLE_NAME, type_="unique")
