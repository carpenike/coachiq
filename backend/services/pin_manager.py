"""
PIN Manager Service for RV Safety Operations

Provides PIN-based authorization for safety-critical operations including:
- Emergency stop authorization
- Safety override codes
- Temporary authorization sessions
- PIN validation and management

For RV deployment security with internet connectivity.
"""

import asyncio
import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, overload

from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.auth import PINAttempt as DBPINAttempt
from backend.models.auth import PINSession as DBPINSession
from backend.models.auth import UserPIN

logger = logging.getLogger(__name__)

# Number of default PINs minted per user (emergency / override / maintenance).
_DEFAULT_PIN_COUNT = 3


def _ensure_utc_aware(dt: datetime | None) -> datetime | None:
    """Coerce a datetime read back from the database to UTC-aware.

    SQLite has no native ``TIMESTAMP WITH TIME ZONE`` type. SQLAlchemy's
    ``DateTime(timezone=True)`` declaration is honoured by Postgres but
    silently degraded by the SQLite dialect: writes that go in tz-aware
    come back tz-naive. CoachIQ's reference deployment uses SQLite, so
    every Python-side comparison between ``datetime.now(UTC)`` and a
    value loaded from the DB is a latent ``TypeError: can't compare
    offset-naive and offset-aware datetimes`` waiting to fire.

    Treat naive datetimes as UTC (which is how the writer intended them)
    so authorization checks and lockout windows work identically on
    SQLite and Postgres. Returns ``None`` unchanged so callers can keep
    using nullable columns; the overload narrows the return type so
    non-nullable callers don't need a redundant ``assert``.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


@overload
def _coerce_utc_aware(dt: datetime) -> datetime: ...
@overload
def _coerce_utc_aware(dt: None) -> None: ...
def _coerce_utc_aware(dt: datetime | None) -> datetime | None:
    """Non-nullable-narrowing wrapper around ``_ensure_utc_aware``."""
    return _ensure_utc_aware(dt)


class PINConfig(BaseModel):
    """PIN system configuration."""

    # PIN Requirements
    min_pin_length: int = Field(default=4, description="Minimum PIN length")
    max_pin_length: int = Field(default=8, description="Maximum PIN length")
    require_numeric_only: bool = Field(default=True, description="Require numeric PINs only")

    # Authorization Settings
    emergency_pin_expires_minutes: int = Field(
        default=5, description="Emergency PIN session timeout"
    )
    max_failed_attempts: int = Field(
        default=3, description="Max failed PIN attempts before lockout"
    )
    lockout_duration_minutes: int = Field(
        default=15, description="Lockout duration after max failures"
    )

    # Session Management
    session_timeout_minutes: int = Field(default=30, description="General PIN session timeout")
    max_concurrent_sessions: int = Field(default=2, description="Max concurrent PIN sessions")

    # Security Features
    enable_pin_rotation: bool = Field(default=True, description="Enable automatic PIN rotation")
    pin_rotation_days: int = Field(default=30, description="Days between PIN rotation")
    require_pin_confirmation: bool = Field(
        default=True, description="Require PIN confirmation for critical ops"
    )


class PINSessionData(BaseModel):
    """PIN session data for API responses."""

    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="User who created the session")
    pin_type: str = Field(..., description="Type of PIN: emergency, override, maintenance")
    created_at: datetime = Field(..., description="Session creation timestamp")
    expires_at: datetime = Field(..., description="Session expiration timestamp")
    operations_used: int = Field(default=0, description="Number of operations performed")
    max_operations: int | None = Field(default=None, description="Maximum operations allowed")
    is_active: bool = Field(default=True, description="Whether session is active")


class PINAttemptData(BaseModel):
    """PIN attempt data for API responses."""

    user_id: str | None = Field(default=None, description="User attempting PIN validation")
    pin_type: str = Field(..., description="Type of PIN attempted")
    timestamp: datetime = Field(..., description="Attempt timestamp")
    success: bool = Field(..., description="Whether attempt was successful")
    ip_address: str | None = Field(default=None, description="Source IP address")
    session_id: str | None = Field(default=None, description="Created session ID if successful")
    failure_reason: str | None = Field(default=None, description="Reason for failure")


class PINValidationResult(BaseModel):
    """Result of PIN validation."""

    success: bool = Field(..., description="Whether validation was successful")
    session_id: str | None = Field(default=None, description="Created session ID if successful")
    error_message: str | None = Field(default=None, description="Error message if failed")
    lockout_until: datetime | None = Field(
        default=None, description="Lockout expiration if user is locked out"
    )


class PINManager:
    """
    Database-persistent PIN manager for RV safety operations.

    Provides secure PIN validation, session management, and audit logging
    using SQLAlchemy models for persistent storage.
    """

    def __init__(self, config: PINConfig | None = None, db_session: AsyncSession | None = None):
        """
        Initialize PIN manager with database persistence.

        Args:
            config: PIN system configuration
            db_session: Database session for PIN operations
        """
        self.config = config or PINConfig()
        self.db_session = db_session
        # SQLAlchemy AsyncSession is NOT safe for concurrent use: a flush in
        # one task colliding with a Session.add()/execute() in another task
        # produces "Session.add() within flush process" warnings and can
        # leave the session in an inconsistent state. The PIN flow on a real
        # request is single-threaded, but this manager can be exercised from
        # parallel WebSocket / API calls that share a request-scoped session
        # (and the test suite explicitly drives concurrent validate_pin /
        # authorize_operation calls). Serialise all DB-mutating public
        # methods through a per-instance lock to keep the threat model
        # honest: brute-force or burst-style PIN attempts must not corrupt
        # auth state.
        self._db_lock: asyncio.Lock = asyncio.Lock()

        logger.info("PIN Manager initialized with database persistence for RV safety operations")

    def set_db_session(self, db_session: AsyncSession) -> None:
        """Set the database session for PIN operations."""
        self.db_session = db_session

    async def initialize_default_pins(self, user_id: str) -> dict[str, str]:
        """
        Initialize default PINs for RV deployment.

        Args:
            user_id: ID of the user who will own the PINs

        Returns:
            dict: Generated PINs by type (for one-time display)
        """
        if not self.db_session:
            msg = "Database session not available"
            raise RuntimeError(msg)

        # Check if PINs already exist for this user
        existing_pins = await self.db_session.execute(
            select(UserPIN).where(UserPIN.user_id == user_id)
        )
        if existing_pins.scalars().first():
            logger.info("PINs already exist for user %s", user_id)
            return {}

        generated_pins = {}

        # Generate unique 4-digit PINs
        pin_values: set[str] = set()
        while len(pin_values) < _DEFAULT_PIN_COUNT:
            pin = secrets.randbelow(9000) + 1000  # 4-digit PIN
            pin_values.add(str(pin))

        pin_list = list(pin_values)
        pin_types = ["emergency", "override", "maintenance"]

        for pin_type, pin_value in zip(pin_types, pin_list, strict=False):
            generated_pins[pin_type] = pin_value
            await self.set_pin(user_id, pin_type, pin_value)

        logger.warning("Default PINs initialized for user %s", user_id)
        return generated_pins

    def _generate_salt(self) -> str:
        """Generate a random salt for PIN hashing."""
        return secrets.token_hex(16)

    def _hash_pin(self, pin: str, salt: str) -> str:
        """Hash a PIN with salt for secure storage."""
        return hashlib.sha256(f"{pin}{salt}".encode()).hexdigest()

    async def set_pin(
        self, user_id: str, pin_type: str, pin: str, description: str | None = None
    ) -> bool:
        """
        Set or update a PIN in the database.

        Args:
            user_id: ID of the user who owns the PIN
            pin_type: Type of PIN (emergency, override, maintenance)
            pin: New PIN value
            description: Optional description for the PIN

        Returns:
            bool: True if PIN was set successfully

        Raises:
            ValueError: If PIN doesn't meet requirements
            RuntimeError: If database session not available
        """
        if not self.db_session:
            msg = "Database session not available"
            raise RuntimeError(msg)

        if not self._validate_pin_format(pin):
            msg = "PIN doesn't meet format requirements"
            raise ValueError(msg)

        async with self._db_lock:
            # Generate salt and hash PIN
            salt = self._generate_salt()
            pin_hash = self._hash_pin(pin, salt)

            # Check if PIN already exists for this user and type
            existing_pin = await self.db_session.execute(
                select(UserPIN).where(
                    and_(UserPIN.user_id == user_id, UserPIN.pin_type == pin_type)
                )
            )
            existing = existing_pin.scalar_one_or_none()

            if existing:
                # Update existing PIN
                existing.pin_hash = pin_hash
                existing.salt = salt
                existing.updated_at = datetime.now(UTC)
                if description:
                    existing.description = description
            else:
                # Create new PIN
                new_pin = UserPIN(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    pin_type=pin_type,
                    pin_hash=pin_hash,
                    salt=salt,
                    description=description,
                    is_active=True,
                    use_count=0,
                    lockout_after_failures=self.config.max_failed_attempts,
                    lockout_duration_minutes=self.config.lockout_duration_minutes,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                self.db_session.add(new_pin)

            await self.db_session.commit()
            logger.info(
                "PIN %s for user %s, type: %s",
                "updated" if existing else "created",
                user_id,
                pin_type,
            )
            return True

    async def create_pin(
        self,
        user_id: str,
        pin: str,
        pin_type: str,
        description: str | None = None,
    ) -> bool:
        """
        Create a new PIN (or update if one of the same type exists).

        This is the operator-facing public API: callers spell their intent
        ("I'm creating a PIN") and the audit log records that, even though
        the underlying storage operation is the same set-or-update as
        ``set_pin``. The argument order (``user_id, pin, pin_type, ...``)
        matches the convention used by ``validate_pin`` and the broader
        PIN-management surface; ``set_pin`` predates this and uses
        ``(user_id, pin_type, pin, ...)`` for historical reasons.
        """
        return await self.set_pin(
            user_id=user_id, pin_type=pin_type, pin=pin, description=description
        )

    async def rotate_pin(
        self,
        user_id: str,
        pin_type: str,
        old_pin: str,
        new_pin: str,
    ) -> bool:
        """
        Rotate a PIN: verify the current PIN, then replace it with a new one.

        Verifying the old PIN before accepting the rotation prevents an
        attacker who only has session-level access (but not the current
        PIN) from silently changing it. This is the standard contract for
        end-user-driven credential rotation.

        Returns True on success, False if old_pin verification fails.
        """
        if not self.db_session:
            msg = "Database session not available"
            raise RuntimeError(msg)

        # Verify the current PIN by attempting to validate it. If validation
        # succeeds, the PIN was correct; revoke that throwaway session
        # immediately so we don't leave a side-effect from the rotation
        # flow. validate_pin returns a PINValidationResult with .success
        # and .session_id; .session_id is None on failure.
        validation = await self.validate_pin(user_id=user_id, pin=old_pin, pin_type=pin_type)
        if validation.session_id is None or not validation.success:
            logger.warning(
                "PIN rotation rejected for user %s type %s: old PIN verification failed",
                user_id,
                pin_type,
            )
            return False

        await self.revoke_session(validation.session_id)

        # Set the new PIN via the same set-or-update path used by create_pin.
        return await self.set_pin(user_id=user_id, pin_type=pin_type, pin=new_pin)

    async def deactivate_pin(self, user_id: str, pin_type: str) -> bool:
        """
        Deactivate (soft-delete) a PIN by clearing its is_active flag.

        Soft-deletion preserves the audit trail (the PIN row stays in the
        database with its hash and creation history) while ensuring
        ``validate_pin`` refuses to mint a session for it. Hard deletion
        would lose the audit signal.

        Returns True if a matching active PIN was found and deactivated,
        False if no active PIN of that type existed.
        """
        if not self.db_session:
            msg = "Database session not available"
            raise RuntimeError(msg)

        async with self._db_lock:
            result = await self.db_session.execute(
                select(UserPIN).where(
                    and_(
                        UserPIN.user_id == user_id,
                        UserPIN.pin_type == pin_type,
                        UserPIN.is_active.is_(True),
                    )
                )
            )
            pin = result.scalar_one_or_none()
            if pin is None:
                return False

            pin.is_active = False
            pin.updated_at = datetime.now(UTC)
            await self.db_session.commit()
            logger.info("PIN deactivated for user %s type %s", user_id, pin_type)
            return True

    def _validate_pin_format(self, pin: str) -> bool:
        """Validate PIN format requirements."""
        if len(pin) < self.config.min_pin_length or len(pin) > self.config.max_pin_length:
            return False

        return not (self.config.require_numeric_only and not pin.isdigit())

    async def _is_user_locked_out(self, user_id: str, pin_type: str) -> datetime | None:
        """
        Check if user is currently locked out for a specific PIN type.

        Returns:
            datetime: Lockout expiration time if locked out, None if not locked out
        """
        if not self.db_session:
            return None

        # Check recent failed attempts for this user and PIN type
        cutoff_time = datetime.now(UTC) - timedelta(minutes=self.config.lockout_duration_minutes)

        failed_attempts = await self.db_session.execute(
            select(func.count(DBPINAttempt.id)).where(
                and_(
                    DBPINAttempt.attempted_by_user_id == user_id,
                    DBPINAttempt.pin_type == pin_type,
                    # SQLAlchemy boolean negation: `~col` => `NOT col` in SQL.
                    # Don't use Python `not col` here — that evaluates the
                    # column object as a Python bool (always truthy) and the
                    # filter silently degenerates. Don't use `col.is_(False)`
                    # either: SQLite emits `IS 0`, which mis-evaluates Boolean
                    # columns in some dialects. ruff E712 nudges toward the
                    # wrong fixes here; the bitwise form is the correct SQLA
                    # idiom and survives across dialects.
                    ~DBPINAttempt.success,
                    DBPINAttempt.attempted_at > cutoff_time,
                )
            )
        )

        attempt_count = failed_attempts.scalar() or 0

        if attempt_count >= self.config.max_failed_attempts:
            # User is locked out - calculate when it expires
            last_attempt = await self.db_session.execute(
                select(DBPINAttempt.attempted_at)
                .where(
                    and_(
                        DBPINAttempt.attempted_by_user_id == user_id,
                        DBPINAttempt.pin_type == pin_type,
                        # See note on `~col` vs `not col` above.
                        ~DBPINAttempt.success,
                    )
                )
                .order_by(DBPINAttempt.attempted_at.desc())
                .limit(1)
            )

            last_attempt_time = last_attempt.scalar()
            if last_attempt_time:
                last_attempt_time = _coerce_utc_aware(last_attempt_time)
                lockout_until = last_attempt_time + timedelta(
                    minutes=self.config.lockout_duration_minutes
                )
                if datetime.now(UTC) < lockout_until:
                    return lockout_until

        return None

    async def _record_attempt(  # noqa: PLR0913 - audit trail needs full request context
        self,
        user_id: str | None,
        pin_type: str,
        success: bool,
        ip_address: str | None = None,
        user_agent: str | None = None,
        failure_reason: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Record a PIN attempt in the database."""
        if not self.db_session:
            return

        attempt = DBPINAttempt(
            id=str(uuid.uuid4()),
            attempted_by_user_id=user_id,
            pin_type=pin_type,
            success=success,
            ip_address=ip_address,
            user_agent=user_agent,
            failure_reason=failure_reason,
            session_id=session_id,
            attempted_at=datetime.now(UTC),
        )

        self.db_session.add(attempt)
        await self.db_session.commit()

    async def validate_pin(
        self,
        user_id: str,
        pin: str,
        pin_type: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PINValidationResult:
        """
        Validate a PIN and create authorization session.

        Args:
            user_id: User attempting validation
            pin: PIN to validate
            pin_type: Type of PIN (emergency, override, maintenance)
            ip_address: Source IP address for logging
            user_agent: User agent for logging

        Returns:
            PINValidationResult: Validation result with session info or error
        """
        if not self.db_session:
            # No DB session: nothing to serialize, but still record the attempt
            # via the (no-op) recorder for symmetry with the rest of the flow.
            await self._record_attempt(
                user_id, pin_type, False, ip_address, user_agent, "Database unavailable"
            )
            return PINValidationResult(success=False, error_message="Database service unavailable")

        async with self._db_lock:
            # Check if user is locked out
            lockout_until = await self._is_user_locked_out(user_id, pin_type)
            if lockout_until:
                logger.warning(
                    "PIN attempt blocked - user %s is locked out until %s",
                    user_id,
                    lockout_until,
                )
                await self._record_attempt(
                    user_id, pin_type, False, ip_address, user_agent, "User locked out"
                )
                return PINValidationResult(
                    success=False,
                    error_message="User is locked out due to failed attempts",
                    lockout_until=lockout_until,
                )

            # Get PIN from database
            user_pin = await self.db_session.execute(
                select(UserPIN).where(
                    and_(
                        UserPIN.user_id == user_id,
                        UserPIN.pin_type == pin_type,
                        UserPIN.is_active,
                    )
                )
            )
            pin_record = user_pin.scalar_one_or_none()

            if not pin_record:
                logger.warning("No active PIN found for user %s, type %s", user_id, pin_type)
                await self._record_attempt(
                    user_id, pin_type, False, ip_address, user_agent, "PIN not found"
                )
                return PINValidationResult(
                    success=False, error_message="PIN not configured or inactive"
                )

            # Validate PIN
            hashed_pin = self._hash_pin(pin, pin_record.salt)
            is_valid = hashed_pin == pin_record.pin_hash

            if not is_valid:
                logger.warning("Invalid PIN attempt by user %s for type %s", user_id, pin_type)
                await self._record_attempt(
                    user_id, pin_type, False, ip_address, user_agent, "Invalid PIN"
                )
                return PINValidationResult(success=False, error_message="Invalid PIN")

            # PIN is valid - create session
            session_id = await self._create_session(
                user_id, pin_type, pin_record, ip_address=ip_address, user_agent=user_agent
            )

            # Update PIN usage count
            pin_record.use_count += 1
            pin_record.last_used_at = datetime.now(UTC)
            await self.db_session.commit()

            # Record successful attempt
            await self._record_attempt(
                user_id, pin_type, True, ip_address, user_agent, session_id=session_id
            )

            logger.info("PIN validation successful for user %s, type %s", user_id, pin_type)
            return PINValidationResult(success=True, session_id=session_id)

    async def _create_session(
        self,
        user_id: str,
        pin_type: str,
        user_pin: UserPIN,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        """Create a new PIN authorization session in the database.

        ``ip_address`` / ``user_agent`` are propagated from the originating
        request so the audit trail on ``PINSession`` matches the audit
        trail on ``PINAttempt``. Earlier revisions accepted these on
        ``validate_pin`` but silently dropped them here, leaving the
        session row with NULL audit fields even when the caller supplied
        them — a real audit-completeness bug for the realistic threat
        model (see ``coachiq-architecture.md``: API-side abuse is the
        threat we actually defend against).
        """
        if not self.db_session:
            msg = "Database session not available"
            raise RuntimeError(msg)

        # Clean up expired sessions first
        await self._cleanup_expired_sessions()

        # Check session limits
        active_sessions = await self.db_session.execute(
            select(func.count(DBPINSession.id)).where(
                and_(
                    DBPINSession.created_by_user_id == user_id,
                    DBPINSession.is_active,
                    DBPINSession.expires_at > datetime.now(UTC),
                )
            )
        )

        session_count = active_sessions.scalar() or 0

        if session_count >= self.config.max_concurrent_sessions:
            # Remove oldest session
            oldest_session = await self.db_session.execute(
                select(DBPINSession)
                .where(and_(DBPINSession.created_by_user_id == user_id, DBPINSession.is_active))
                .order_by(DBPINSession.created_at)
                .limit(1)
            )

            oldest = oldest_session.scalar_one_or_none()
            if oldest:
                oldest.is_active = False
                oldest.terminated_at = datetime.now(UTC)
                logger.info("Removed oldest session for user %s due to limit", user_id)

        # Create new session
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(UTC)

        # Set expiration based on PIN type
        if pin_type == "emergency":
            expires_at = now + timedelta(minutes=self.config.emergency_pin_expires_minutes)
            max_operations = 1  # Emergency operations are single-use
        elif pin_type == "override":
            expires_at = now + timedelta(minutes=self.config.session_timeout_minutes)
            max_operations = 3  # Override can be used a few times
        else:  # maintenance
            expires_at = now + timedelta(minutes=self.config.session_timeout_minutes)
            max_operations = None  # Unlimited for maintenance

        new_session = DBPINSession(
            id=str(uuid.uuid4()),
            user_pin_id=user_pin.id,
            session_id=session_id,
            created_by_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            max_duration_minutes=self.config.session_timeout_minutes,
            max_operations=max_operations,
            operation_count=0,
            is_active=True,
            expires_at=expires_at,
            created_at=now,
            last_used_at=now,
        )

        self.db_session.add(new_session)
        await self.db_session.commit()

        logger.info("Created PIN session %s for user %s, type %s", session_id, user_id, pin_type)
        return session_id

    async def authorize_operation(
        self, session_id: str, operation: str, user_id: str | None = None
    ) -> bool:
        """
        Authorize an operation using PIN session.

        Args:
            session_id: PIN session ID
            operation: Operation to authorize
            user_id: User performing operation (for validation)

        Returns:
            bool: True if operation is authorized
        """
        if not self.db_session:
            logger.error("Database session not available for operation authorization")
            return False

        async with self._db_lock:
            # Get session from database
            session_query = await self.db_session.execute(
                select(DBPINSession).where(
                    and_(DBPINSession.session_id == session_id, DBPINSession.is_active)
                )
            )
            session = session_query.scalar_one_or_none()

            if not session:
                logger.warning("Unknown or inactive session ID: %s", session_id)
                return False

            # Check session expiration
            if datetime.now(UTC) > _coerce_utc_aware(session.expires_at):
                logger.warning("Expired session used: %s", session_id)
                session.is_active = False
                session.terminated_at = datetime.now(UTC)
                await self.db_session.commit()
                return False

            # Check user matches (if provided)
            if user_id and session.created_by_user_id != user_id:
                logger.warning(
                    "Session user mismatch: %s != %s",
                    session.created_by_user_id,
                    user_id,
                )
                return False

            # Check usage limits
            if session.max_operations and session.operation_count >= session.max_operations:
                logger.warning("Session %s usage limit exceeded", session_id)
                session.is_active = False
                session.terminated_at = datetime.now(UTC)
                await self.db_session.commit()
                return False

            # Authorize operation
            session.operation_count += 1
            session.last_used_at = datetime.now(UTC)

            # Terminate session if single-use
            if session.max_operations == 1:
                session.is_active = False
                session.terminated_at = datetime.now(UTC)
                logger.info("Terminated single-use session %s", session_id)

            await self.db_session.commit()
            logger.info("Authorized operation %s for session %s", operation, session_id)
            return True

    async def revoke_session(self, session_id: str) -> bool:
        """
        Revoke a PIN session.

        Args:
            session_id: Session to revoke

        Returns:
            bool: True if session was revoked
        """
        if not self.db_session:
            return False

        async with self._db_lock:
            session_query = await self.db_session.execute(
                select(DBPINSession).where(
                    and_(DBPINSession.session_id == session_id, DBPINSession.is_active)
                )
            )
            session = session_query.scalar_one_or_none()

            if session:
                session.is_active = False
                session.terminated_at = datetime.now(UTC)
                await self.db_session.commit()
                logger.info(
                    "Revoked PIN session %s for user %s",
                    session_id,
                    session.created_by_user_id,
                )
                return True

            return False

    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """
        Revoke all sessions for a user.

        Args:
            user_id: User whose sessions to revoke

        Returns:
            int: Number of sessions revoked
        """
        if not self.db_session:
            return 0

        async with self._db_lock:
            # Get all active sessions for user
            active_sessions = await self.db_session.execute(
                select(DBPINSession).where(
                    and_(
                        DBPINSession.created_by_user_id == user_id,
                        DBPINSession.is_active,
                    )
                )
            )

            sessions = active_sessions.scalars().all()
            revoked_count = 0

            for session in sessions:
                session.is_active = False
                session.terminated_at = datetime.now(UTC)
                revoked_count += 1

            if revoked_count > 0:
                await self.db_session.commit()
                logger.info("Revoked %s sessions for user %s", revoked_count, user_id)

            return revoked_count

    async def _cleanup_expired_sessions(self) -> None:
        """Clean up expired sessions."""
        if not self.db_session:
            return

        # Mark expired sessions as inactive
        expired_sessions = await self.db_session.execute(
            select(DBPINSession).where(
                and_(DBPINSession.is_active, DBPINSession.expires_at <= datetime.now(UTC))
            )
        )

        sessions = expired_sessions.scalars().all()
        for session in sessions:
            session.is_active = False
            session.terminated_at = datetime.now(UTC)

        if sessions:
            await self.db_session.commit()
            logger.info("Cleaned up %s expired sessions", len(sessions))

    async def get_session_info(self, session_id: str) -> PINSessionData | None:
        """Get information about a PIN session."""
        if not self.db_session:
            return None

        session_query = await self.db_session.execute(
            select(DBPINSession).where(DBPINSession.session_id == session_id)
        )
        session = session_query.scalar_one_or_none()

        if not session:
            return None

        # Get PIN type from related UserPIN
        pin_query = await self.db_session.execute(
            select(UserPIN.pin_type).where(UserPIN.id == session.user_pin_id)
        )
        pin_type = pin_query.scalar() or "unknown"

        return PINSessionData(
            session_id=session.session_id,
            user_id=session.created_by_user_id,
            pin_type=pin_type,
            created_at=session.created_at,
            expires_at=session.expires_at,
            operations_used=session.operation_count,
            max_operations=session.max_operations,
            is_active=session.is_active
            and datetime.now(UTC) < _coerce_utc_aware(session.expires_at),
        )

    async def get_user_status(self, user_id: str) -> dict[str, Any]:
        """Get PIN status for a user."""
        if not self.db_session:
            return {"error": "Database unavailable"}

        # Check if user is locked out for any PIN type
        lockout_times = {}
        for pin_type in ["emergency", "override", "maintenance"]:
            lockout_until = await self._is_user_locked_out(user_id, pin_type)
            if lockout_until:
                lockout_times[pin_type] = lockout_until

        # Get active sessions
        active_sessions_query = await self.db_session.execute(
            select(DBPINSession).where(
                and_(
                    DBPINSession.created_by_user_id == user_id,
                    DBPINSession.is_active,
                    DBPINSession.expires_at > datetime.now(UTC),
                )
            )
        )
        active_sessions = active_sessions_query.scalars().all()

        # Get recent attempts count
        recent_cutoff = datetime.now(UTC) - timedelta(hours=24)
        recent_attempts_query = await self.db_session.execute(
            select(func.count(DBPINAttempt.id)).where(
                and_(
                    DBPINAttempt.attempted_by_user_id == user_id,
                    DBPINAttempt.attempted_at > recent_cutoff,
                )
            )
        )
        recent_attempts = recent_attempts_query.scalar() or 0

        return {
            "user_id": user_id,
            "is_locked_out": len(lockout_times) > 0,
            "lockout_times": lockout_times,
            "active_sessions": len(active_sessions),
            "recent_attempts": recent_attempts,
            "can_use_pins": len(lockout_times) == 0,
        }

    async def get_system_status(self) -> dict[str, Any]:
        """Get overall PIN system status."""
        if not self.db_session:
            return {"error": "Database unavailable"}

        # Clean up expired sessions first
        await self._cleanup_expired_sessions()

        # Count active sessions
        active_sessions_query = await self.db_session.execute(
            select(func.count(DBPINSession.id)).where(
                and_(DBPINSession.is_active, DBPINSession.expires_at > datetime.now(UTC))
            )
        )
        active_sessions = active_sessions_query.scalar() or 0

        # Count configured PINs
        pins_query = await self.db_session.execute(
            select(func.count(UserPIN.id)).where(UserPIN.is_active)
        )
        configured_pins = pins_query.scalar() or 0

        # Count attempts today
        today_cutoff = datetime.now(UTC) - timedelta(hours=24)
        attempts_query = await self.db_session.execute(
            select(func.count(DBPINAttempt.id)).where(DBPINAttempt.attempted_at > today_cutoff)
        )
        attempts_today = attempts_query.scalar() or 0

        return {
            "configured_pins": configured_pins,
            "active_sessions": active_sessions,
            "attempts_today": attempts_today,
            "config": self.config.model_dump(),
            "healthy": True,
        }
