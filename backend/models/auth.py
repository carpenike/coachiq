"""
Authentication models for CoachIQ.

This module contains SQLAlchemy models for authentication-related data including
users, sessions, API keys, and authentication events.
"""

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.database import Base


class AuthMode(str, Enum):
    """Authentication modes supported by the system."""

    NONE = "none"
    SINGLE_USER = "single"
    MULTI_USER = "multi"


class UserRole(str, Enum):
    """User roles in the system."""

    ADMIN = "admin"
    USER = "user"
    READONLY = "readonly"


class AuthProvider(str, Enum):
    """Authentication providers."""

    MAGIC_LINK = "magic_link"
    GITHUB = "github"
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    PASSWORD = "password"


class User(Base):
    """User model for multi-user authentication."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # User status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[UserRole] = mapped_column(String(20), default=UserRole.USER, nullable=False)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # User preferences
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    auth_providers: Mapped[list["UserAuthProvider"]] = relationship(
        "UserAuthProvider", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey", back_populates="user", cascade="all, delete-orphan"
    )
    auth_events: Mapped[list["AuthEvent"]] = relationship(
        "AuthEvent", back_populates="user", cascade="all, delete-orphan"
    )
    mfa: Mapped["UserMFA | None"] = relationship(
        "UserMFA", back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    pins: Mapped[list["UserPIN"]] = relationship(
        "UserPIN", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"


class UserAuthProvider(Base):
    """Links users to their authentication providers (OAuth, magic link, etc.)."""

    __tablename__ = "user_auth_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    provider: Mapped[AuthProvider] = mapped_column(String(50), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Provider-specific data
    provider_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Status
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="auth_providers")

    def __repr__(self) -> str:
        return f"<UserAuthProvider(id={self.id}, user_id={self.user_id}, provider={self.provider})>"


class UserSession(Base):
    """User session tracking."""

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    session_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Session metadata
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 support
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Session status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<UserSession(id={self.id}, user_id={self.user_id}, active={self.is_active})>"


class APIKey(Base):
    """API keys for programmatic access."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # First few chars for identification

    # Key metadata
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Key status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Usage tracking
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rate_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Requests per hour

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name={self.name}, prefix={self.key_prefix})>"


class MagicLinkToken(Base):
    """Magic link tokens for passwordless authentication."""

    __tablename__ = "magic_link_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Token metadata
    redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Request metadata
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<MagicLinkToken(id={self.id}, email={self.email}, used={self.used})>"


class AuthEvent(Base):
    """Authentication events for audit logging."""

    __tablename__ = "auth_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )

    # Event details
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # login, logout, token_refresh, etc.
    provider: Mapped[AuthProvider | None] = mapped_column(String(50), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Request metadata
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )  # For failed attempts

    # Additional event data
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relationships
    user: Mapped[User | None] = relationship("User", back_populates="auth_events")

    def __repr__(self) -> str:
        return f"<AuthEvent(id={self.id}, type={self.event_type}, success={self.success})>"


class UserMFA(Base):
    """Multi-Factor Authentication settings for users."""

    __tablename__ = "user_mfa"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True, unique=True
    )

    # TOTP settings
    totp_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # MFA status
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    backup_codes_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Recovery codes (JSON array of strings)
    recovery_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="mfa")
    backup_codes: Mapped[list["UserMFABackupCode"]] = relationship(
        "UserMFABackupCode", back_populates="user_mfa", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<UserMFA(id={self.id}, user_id={self.user_id}, enabled={self.is_enabled})>"


class UserMFABackupCode(Base):
    """Backup codes for MFA recovery."""

    __tablename__ = "user_mfa_backup_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_mfa_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user_mfa.id"), nullable=False, index=True
    )

    # Backup code data
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user_mfa: Mapped[UserMFA] = relationship("UserMFA", back_populates="backup_codes")

    def __repr__(self) -> str:
        return f"<UserMFABackupCode(id={self.id}, used={self.is_used})>"


class UserPIN(Base):
    """PIN-based authorization for safety-critical operations."""

    __tablename__ = "user_pins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )

    # PIN configuration
    pin_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # emergency, override, maintenance
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    salt: Mapped[str] = mapped_column(String(255), nullable=False)

    # PIN metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # PIN status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Security settings
    lockout_after_failures: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    lockout_duration_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="pins")
    sessions: Mapped[list["PINSession"]] = relationship(
        "PINSession", back_populates="user_pin", cascade="all, delete-orphan"
    )
    attempts: Mapped[list["PINAttempt"]] = relationship(
        "PINAttempt", back_populates="user_pin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<UserPIN(id={self.id}, user_id={self.user_id}, type={self.pin_type})>"


class PINSession(Base):
    """Active PIN authorization sessions for safety operations."""

    __tablename__ = "pin_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_pin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user_pins.id"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Session metadata
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Session configuration
    max_duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    max_operations: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited
    operation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Session status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user_pin: Mapped[UserPIN] = relationship("UserPIN", back_populates="sessions")
    created_by: Mapped[User] = relationship("User", foreign_keys=[created_by_user_id])

    def __repr__(self) -> str:
        return f"<PINSession(id={self.id}, session_id={self.session_id}, active={self.is_active})>"


class PINAttempt(Base):
    """PIN validation attempts for security monitoring."""

    __tablename__ = "pin_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_pin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user_pins.id"), nullable=True, index=True
    )

    # Attempt metadata
    attempted_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Attempt details
    pin_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Security context
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operation_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit fields
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )

    # Relationships
    user_pin: Mapped[UserPIN | None] = relationship("UserPIN", back_populates="attempts")
    attempted_by: Mapped[User | None] = relationship("User", foreign_keys=[attempted_by_user_id])

    def __repr__(self) -> str:
        return f"<PINAttempt(id={self.id}, type={self.pin_type}, success={self.success})>"


class AdminSettings(Base):
    """System-wide authentication settings."""

    __tablename__ = "admin_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    setting_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    setting_type: Mapped[str] = mapped_column(
        String(20), default="string", nullable=False
    )  # string, boolean, integer, json

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # Sensitive data like API keys

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AdminSettings(key={self.setting_key}, type={self.setting_type})>"
