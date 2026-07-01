"""MCP OAuth Authorization Server persistence models."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.database import Base


class McpOAuthClient(Base):
    """Dynamically registered MCP OAuth client."""

    __tablename__ = "mcp_oauth_clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    client_secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class McpOAuthTransaction(Base):
    """Short-lived AS transaction for the client-to-AS and AS-to-PocketID legs."""

    __tablename__ = "mcp_oauth_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transaction_state: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    client_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    client_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_code_challenge: Mapped[str] = mapped_column(String(255), nullable=False)
    client_code_challenge_method: Mapped[str] = mapped_column(String(20), nullable=False)
    upstream_code_verifier: Mapped[str] = mapped_column(String(255), nullable=False)
    upstream_nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class McpOAuthAuthorizationCode(Base):
    """Single-use authorization code issued after PocketID federation."""

    __tablename__ = "mcp_oauth_authorization_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(255), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class McpOAuthAccessToken(Base):
    """Opaque MCP-only OAuth access token handle."""

    __tablename__ = "mcp_oauth_access_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    client_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    @property
    def is_active(self) -> bool:
        """Return whether the token is neither revoked nor expired."""
        return self.revoked_at is None and self.expires_at > datetime.now(UTC)
