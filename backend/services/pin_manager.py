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
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.auth import UserPIN, PINSession as DBPINSession, PINAttempt as DBPINAttempt

logger = logging.getLogger(__name__)


class PINConfig(BaseModel):
    """PIN system configuration."""

    # PIN Requirements
    min_pin_length: int = Field(4, description="Minimum PIN length")
    max_pin_length: int = Field(8, description="Maximum PIN length")
    require_numeric_only: bool = Field(True, description="Require numeric PINs only")

    # Authorization Settings
    emergency_pin_expires_minutes: int = Field(5, description="Emergency PIN session timeout")
    max_failed_attempts: int = Field(3, description="Max failed PIN attempts before lockout")
    lockout_duration_minutes: int = Field(15, description="Lockout duration after max failures")

    # Session Management
    session_timeout_minutes: int = Field(30, description="General PIN session timeout")
    max_concurrent_sessions: int = Field(2, description="Max concurrent PIN sessions")

    # Security Features
    enable_pin_rotation: bool = Field(True, description="Enable automatic PIN rotation")
    pin_rotation_days: int = Field(30, description="Days between PIN rotation")
    require_pin_confirmation: bool = Field(True, description="Require PIN confirmation for critical ops")


class PINSessionData(BaseModel):
    """PIN session data for API responses."""

    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="User who created the session")
    pin_type: str = Field(..., description="Type of PIN: emergency, override, maintenance")
    created_at: datetime = Field(..., description="Session creation timestamp")
    expires_at: datetime = Field(..., description="Session expiration timestamp")
    operations_used: int = Field(0, description="Number of operations performed")
    max_operations: Optional[int] = Field(None, description="Maximum operations allowed")
    is_active: bool = Field(True, description="Whether session is active")


class PINAttemptData(BaseModel):
    """PIN attempt data for API responses."""

    user_id: Optional[str] = Field(None, description="User attempting PIN validation")
    pin_type: str = Field(..., description="Type of PIN attempted")
    timestamp: datetime = Field(..., description="Attempt timestamp")
    success: bool = Field(..., description="Whether attempt was successful")
    ip_address: Optional[str] = Field(None, description="Source IP address")
    session_id: Optional[str] = Field(None, description="Created session ID if successful")
    failure_reason: Optional[str] = Field(None, description="Reason for failure")


class PINValidationResult(BaseModel):
    """Result of PIN validation."""

    success: bool = Field(..., description="Whether validation was successful")
    session_id: Optional[str] = Field(None, description="Created session ID if successful")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    lockout_until: Optional[datetime] = Field(None, description="Lockout expiration if user is locked out")


class PINManager:
    """
    Database-persistent PIN manager for RV safety operations.

    Provides secure PIN validation, session management, and audit logging
    using SQLAlchemy models for persistent storage.
    """

    def __init__(self, config: PINConfig | None = None, db_session: Optional[AsyncSession] = None):
        """
        Initialize PIN manager with database persistence.

        Args:
            config: PIN system configuration
            db_session: Database session for PIN operations
        """
        self.config = config or PINConfig()
        self.db_session = db_session

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
            raise RuntimeError("Database session not available")

        # Check if PINs already exist for this user
        existing_pins = await self.db_session.execute(
            select(UserPIN).where(UserPIN.user_id == user_id)
        )
        if existing_pins.scalars().first():
            logger.info(f"PINs already exist for user {user_id}")
            return {}

        generated_pins = {}

        # Generate unique 4-digit PINs
        pin_values = set()
        while len(pin_values) < 3:
            pin = secrets.randbelow(9000) + 1000  # 4-digit PIN
            pin_values.add(str(pin))

        pin_list = list(pin_values)
        pin_types = ["emergency", "override", "maintenance"]

        for pin_type, pin_value in zip(pin_types, pin_list):
            generated_pins[pin_type] = pin_value
            await self.set_pin(user_id, pin_type, pin_value)

        logger.warning(f"Default PINs initialized for user {user_id}")
        return generated_pins

    def _generate_salt(self) -> str:
        """Generate a random salt for PIN hashing."""
        return secrets.token_hex(16)

    def _hash_pin(self, pin: str, salt: str) -> str:
        """Hash a PIN with salt for secure storage."""
        return hashlib.sha256(f"{pin}{salt}".encode()).hexdigest()

    async def set_pin(self, user_id: str, pin_type: str, pin: str, description: Optional[str] = None) -> bool:
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
            raise RuntimeError("Database session not available")

        if not self._validate_pin_format(pin):
            raise ValueError("PIN doesn't meet format requirements")

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
                updated_at=datetime.now(UTC)
            )
            self.db_session.add(new_pin)

        await self.db_session.commit()
        logger.info(f"PIN {'updated' if existing else 'created'} for user {user_id}, type: {pin_type}")
        return True

    def _validate_pin_format(self, pin: str) -> bool:
        """Validate PIN format requirements."""
        if len(pin) < self.config.min_pin_length or len(pin) > self.config.max_pin_length:
            return False

        if self.config.require_numeric_only and not pin.isdigit():
            return False

        return True

    async def _is_user_locked_out(self, user_id: str, pin_type: str) -> Optional[datetime]:
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
                    DBPINAttempt.success == False,
                    DBPINAttempt.attempted_at > cutoff_time
                )
            )
        )

        attempt_count = failed_attempts.scalar() or 0

        if attempt_count >= self.config.max_failed_attempts:
            # User is locked out - calculate when it expires
            last_attempt = await self.db_session.execute(
                select(DBPINAttempt.attempted_at).where(
                    and_(
                        DBPINAttempt.attempted_by_user_id == user_id,
                        DBPINAttempt.pin_type == pin_type,
                        DBPINAttempt.success == False
                    )
                ).order_by(DBPINAttempt.attempted_at.desc()).limit(1)
            )

            last_attempt_time = last_attempt.scalar()
            if last_attempt_time:
                lockout_until = last_attempt_time + timedelta(minutes=self.config.lockout_duration_minutes)
                if datetime.now(UTC) < lockout_until:
                    return lockout_until

        return None

    async def _record_attempt(
        self,
        user_id: Optional[str],
        pin_type: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None,
        session_id: Optional[str] = None
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
            attempted_at=datetime.now(UTC)
        )

        self.db_session.add(attempt)
        await self.db_session.commit()

    async def validate_pin(
        self,
        user_id: str,
        pin: str,
        pin_type: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
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
            await self._record_attempt(user_id, pin_type, False, ip_address, user_agent, "Database unavailable")
            return PINValidationResult(
                success=False,
                error_message="Database service unavailable"
            )

        # Check if user is locked out
        lockout_until = await self._is_user_locked_out(user_id, pin_type)
        if lockout_until:
            logger.warning(f"PIN attempt blocked - user {user_id} is locked out until {lockout_until}")
            await self._record_attempt(user_id, pin_type, False, ip_address, user_agent, "User locked out")
            return PINValidationResult(
                success=False,
                error_message="User is locked out due to failed attempts",
                lockout_until=lockout_until
            )

        # Get PIN from database
        user_pin = await self.db_session.execute(
            select(UserPIN).where(
                and_(
                    UserPIN.user_id == user_id,
                    UserPIN.pin_type == pin_type,
                    UserPIN.is_active == True
                )
            )
        )
        pin_record = user_pin.scalar_one_or_none()

        if not pin_record:
            logger.warning(f"No active PIN found for user {user_id}, type {pin_type}")
            await self._record_attempt(user_id, pin_type, False, ip_address, user_agent, "PIN not found")
            return PINValidationResult(
                success=False,
                error_message="PIN not configured or inactive"
            )

        # Validate PIN
        hashed_pin = self._hash_pin(pin, pin_record.salt)
        is_valid = hashed_pin == pin_record.pin_hash

        if not is_valid:
            logger.warning(f"Invalid PIN attempt by user {user_id} for type {pin_type}")
            await self._record_attempt(user_id, pin_type, False, ip_address, user_agent, "Invalid PIN")
            return PINValidationResult(
                success=False,
                error_message="Invalid PIN"
            )

        # PIN is valid - create session
        session_id = await self._create_session(user_id, pin_type, pin_record)

        # Update PIN usage count
        pin_record.use_count += 1
        pin_record.last_used_at = datetime.now(UTC)
        await self.db_session.commit()

        # Record successful attempt
        await self._record_attempt(user_id, pin_type, True, ip_address, user_agent, session_id=session_id)

        logger.info(f"PIN validation successful for user {user_id}, type {pin_type}")
        return PINValidationResult(
            success=True,
            session_id=session_id
        )

    async def _create_session(self, user_id: str, pin_type: str, user_pin: UserPIN) -> str:
        """Create a new PIN authorization session in the database."""
        if not self.db_session:
            raise RuntimeError("Database session not available")

        # Clean up expired sessions first
        await self._cleanup_expired_sessions()

        # Check session limits
        active_sessions = await self.db_session.execute(
            select(func.count(DBPINSession.id)).where(
                and_(
                    DBPINSession.created_by_user_id == user_id,
                    DBPINSession.is_active == True,
                    DBPINSession.expires_at > datetime.now(UTC)
                )
            )
        )

        session_count = active_sessions.scalar() or 0

        if session_count >= self.config.max_concurrent_sessions:
            # Remove oldest session
            oldest_session = await self.db_session.execute(
                select(DBPINSession).where(
                    and_(
                        DBPINSession.created_by_user_id == user_id,
                        DBPINSession.is_active == True
                    )
                ).order_by(DBPINSession.created_at).limit(1)
            )

            oldest = oldest_session.scalar_one_or_none()
            if oldest:
                oldest.is_active = False
                oldest.terminated_at = datetime.now(UTC)
                logger.info(f"Removed oldest session for user {user_id} due to limit")

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
            max_duration_minutes=self.config.session_timeout_minutes,
            max_operations=max_operations,
            operation_count=0,
            is_active=True,
            expires_at=expires_at,
            created_at=now,
            last_used_at=now
        )

        self.db_session.add(new_session)
        await self.db_session.commit()

        logger.info(f"Created PIN session {session_id} for user {user_id}, type {pin_type}")
        return session_id

    async def authorize_operation(
        self,
        session_id: str,
        operation: str,
        user_id: Optional[str] = None
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

        # Get session from database
        session_query = await self.db_session.execute(
            select(DBPINSession).where(
                and_(
                    DBPINSession.session_id == session_id,
                    DBPINSession.is_active == True
                )
            )
        )
        session = session_query.scalar_one_or_none()

        if not session:
            logger.warning(f"Unknown or inactive session ID: {session_id}")
            return False

        # Check session expiration
        if datetime.now(UTC) > session.expires_at:
            logger.warning(f"Expired session used: {session_id}")
            session.is_active = False
            session.terminated_at = datetime.now(UTC)
            await self.db_session.commit()
            return False

        # Check user matches (if provided)
        if user_id and session.created_by_user_id != user_id:
            logger.warning(f"Session user mismatch: {session.created_by_user_id} != {user_id}")
            return False

        # Check usage limits
        if session.max_operations and session.operation_count >= session.max_operations:
            logger.warning(f"Session {session_id} usage limit exceeded")
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
            logger.info(f"Terminated single-use session {session_id}")

        await self.db_session.commit()
        logger.info(f"Authorized operation {operation} for session {session_id}")
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

        session_query = await self.db_session.execute(
            select(DBPINSession).where(
                and_(
                    DBPINSession.session_id == session_id,
                    DBPINSession.is_active == True
                )
            )
        )
        session = session_query.scalar_one_or_none()

        if session:
            session.is_active = False
            session.terminated_at = datetime.now(UTC)
            await self.db_session.commit()
            logger.info(f"Revoked PIN session {session_id} for user {session.created_by_user_id}")
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

        # Get all active sessions for user
        active_sessions = await self.db_session.execute(
            select(DBPINSession).where(
                and_(
                    DBPINSession.created_by_user_id == user_id,
                    DBPINSession.is_active == True
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
            logger.info(f"Revoked {revoked_count} sessions for user {user_id}")

        return revoked_count

    async def _cleanup_expired_sessions(self) -> None:
        """Clean up expired sessions."""
        if not self.db_session:
            return

        # Mark expired sessions as inactive
        expired_sessions = await self.db_session.execute(
            select(DBPINSession).where(
                and_(
                    DBPINSession.is_active == True,
                    DBPINSession.expires_at <= datetime.now(UTC)
                )
            )
        )

        sessions = expired_sessions.scalars().all()
        for session in sessions:
            session.is_active = False
            session.terminated_at = datetime.now(UTC)

        if sessions:
            await self.db_session.commit()
            logger.info(f"Cleaned up {len(sessions)} expired sessions")

    async def get_session_info(self, session_id: str) -> Optional[PINSessionData]:
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
            is_active=session.is_active and datetime.now(UTC) < session.expires_at
        )

    async def get_user_status(self, user_id: str) -> dict:
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
                    DBPINSession.is_active == True,
                    DBPINSession.expires_at > datetime.now(UTC)
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
                    DBPINAttempt.attempted_at > recent_cutoff
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
            "can_use_pins": len(lockout_times) == 0
        }

    async def get_system_status(self) -> dict:
        """Get overall PIN system status."""
        if not self.db_session:
            return {"error": "Database unavailable"}

        # Clean up expired sessions first
        await self._cleanup_expired_sessions()

        # Count active sessions
        active_sessions_query = await self.db_session.execute(
            select(func.count(DBPINSession.id)).where(
                and_(
                    DBPINSession.is_active == True,
                    DBPINSession.expires_at > datetime.now(UTC)
                )
            )
        )
        active_sessions = active_sessions_query.scalar() or 0

        # Count configured PINs
        pins_query = await self.db_session.execute(
            select(func.count(UserPIN.id)).where(UserPIN.is_active == True)
        )
        configured_pins = pins_query.scalar() or 0

        # Count attempts today
        today_cutoff = datetime.now(UTC) - timedelta(hours=24)
        attempts_query = await self.db_session.execute(
            select(func.count(DBPINAttempt.id)).where(
                DBPINAttempt.attempted_at > today_cutoff
            )
        )
        attempts_today = attempts_query.scalar() or 0

        return {
            "configured_pins": configured_pins,
            "active_sessions": active_sessions,
            "attempts_today": attempts_today,
            "config": self.config.model_dump(),
            "healthy": True
        }
