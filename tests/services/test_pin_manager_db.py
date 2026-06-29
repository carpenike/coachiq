"""
Database integration tests for PIN manager service.

Tests cover actual database operations including:
- PIN creation and storage
- PIN validation with database queries
- Session management
- Lockout protection
- Concurrent access handling
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.models.auth import Base, PINAttempt, PINSession, User, UserPIN
from backend.services.auth.pin_manager import PINConfig, PINManager


@pytest.fixture
async def async_engine():
    """Create async test database engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def async_session_factory(async_engine):
    """Create async session factory."""
    return sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
async def db_session(async_session_factory):
    """Create database session for testing."""
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def test_user(db_session):
    """Create test user in database."""
    user = User(
        id="test-user-123",
        email="test@example.com",
        username="testuser",
        is_active=True,
        is_admin=True,
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
def pin_config():
    """PIN configuration for testing.

    NOTE: ``PINConfig`` field names are ``min_pin_length`` /
    ``max_failed_attempts`` etc. — earlier revisions of this fixture used
    bare names (``min_length`` / ``max_attempts``) that Pydantic v2
    silently dropped because ``model_config`` allows extras, so the test
    config wasn't actually overriding production defaults. Fixed.

    ``max_concurrent_sessions`` is bumped to 10 so the concurrent-session
    test can mint 5 sessions in parallel without the LRU eviction in
    ``_create_session`` kicking in.
    """
    return PINConfig(
        min_pin_length=4,
        max_pin_length=8,
        require_numeric_only=True,
        session_timeout_minutes=60,
        max_failed_attempts=3,
        lockout_duration_minutes=15,
        max_concurrent_sessions=10,
    )


@pytest.fixture
async def pin_manager_with_db(pin_config, db_session):
    """Create PIN manager with real database session."""
    return PINManager(config=pin_config, db_session=db_session)


class TestPINCreationAndStorage:
    """Test PIN creation and database storage."""

    async def test_create_pin_stores_in_database(self, pin_manager_with_db, db_session, test_user):
        """Test that PIN is correctly stored in database."""
        # Create PIN
        result = await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
            description="Test emergency PIN",
        )

        assert result is True

        # Verify PIN was stored
        stmt = select(UserPIN).filter_by(user_id=test_user.id, pin_type="emergency")
        result = await db_session.execute(stmt)
        pin = result.scalar_one_or_none()

        assert pin is not None
        assert pin.user_id == test_user.id
        assert pin.pin_type == "emergency"
        assert pin.description == "Test emergency PIN"
        assert pin.is_active is True
        assert pin.pin_hash != "1234"  # Should be hashed
        assert pin.salt is not None

    async def test_create_duplicate_pin_type_updates_existing(
        self, pin_manager_with_db, db_session, test_user
    ):
        """Test that creating duplicate PIN type updates existing PIN."""
        # Create first PIN
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
            description="First PIN",
        )

        # Create second PIN with same type
        result = await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="5678",
            pin_type="emergency",
            description="Updated PIN",
        )

        assert result is True

        # Verify only one PIN exists and it's updated
        stmt = select(UserPIN).filter_by(user_id=test_user.id, pin_type="emergency")
        result = await db_session.execute(stmt)
        pins = result.scalars().all()

        assert len(pins) == 1
        assert pins[0].description == "Updated PIN"

        # Verify new PIN works.
        # NOTE: ``validate_pin`` returns a ``PINValidationResult`` Pydantic
        # model (``.success`` / ``.session_id`` / ``.error_message`` /
        # ``.lockout_until``); ``.session_id`` is None on any failure path.
        # Tests in this file unwrap to ``session_id`` for compactness; use
        # ``result.success`` directly when the session id isn't otherwise
        # needed.
        result = await pin_manager_with_db.validate_pin(
            user_id=test_user.id,
            pin="5678",
            pin_type="emergency",
        )
        session_id = result.session_id
        assert session_id is not None

    async def test_create_multiple_pin_types(self, pin_manager_with_db, db_session, test_user):
        """Test creating multiple PIN types for same user."""
        # Create different PIN types
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="5678",
            pin_type="override",
        )

        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="9012",
            pin_type="maintenance",
        )

        # Verify all PINs exist
        stmt = select(UserPIN).filter_by(user_id=test_user.id)
        result = await db_session.execute(stmt)
        pins = result.scalars().all()

        assert len(pins) == 3
        pin_types = {pin.pin_type for pin in pins}
        assert pin_types == {"emergency", "override", "maintenance"}


class TestPINValidationAndSessions:
    """Test PIN validation and session management."""

    async def test_validate_pin_creates_session(self, pin_manager_with_db, db_session, test_user):
        """Test that validating PIN creates a session."""
        # Create PIN
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        # Validate PIN
        result = await pin_manager_with_db.validate_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
            ip_address="127.0.0.1",
            user_agent="Test Agent",
        )
        session_id = result.session_id

        assert session_id is not None

        # Verify session was created
        stmt = select(PINSession).filter_by(session_id=session_id)
        result = await db_session.execute(stmt)
        session = result.scalar_one_or_none()

        assert session is not None
        assert session.created_by_user_id == test_user.id
        assert session.is_active is True
        assert session.ip_address == "127.0.0.1"
        assert session.user_agent == "Test Agent"
        # SQLite strips tzinfo on round-trip even with DateTime(timezone=True);
        # production code now coerces back to UTC-aware via _ensure_utc_aware
        # at every comparison site. Mirror that here so the test matches the
        # production contract instead of asserting a SQLAlchemy-dialect-quirk.
        session_expires_at = session.expires_at
        if session_expires_at.tzinfo is None:
            session_expires_at = session_expires_at.replace(tzinfo=UTC)
        assert session_expires_at > datetime.now(UTC)

    async def test_validate_wrong_pin_fails(self, pin_manager_with_db, db_session, test_user):
        """Test that wrong PIN validation fails."""
        # Create PIN
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        # Try wrong PIN
        result = await pin_manager_with_db.validate_pin(
            user_id=test_user.id,
            pin="5678",  # Wrong PIN
            pin_type="emergency",
        )

        assert result.session_id is None
        assert not result.success

        # Verify attempt was logged
        stmt = select(PINAttempt).filter_by(attempted_by_user_id=test_user.id)
        result_db = await db_session.execute(stmt)
        attempt = result_db.scalar_one_or_none()

        assert attempt is not None
        assert attempt.success is False
        # Production records human-readable failure reasons (not snake_case
        # codes); see PINManager._record_attempt call sites in
        # backend/services/pin_manager.py. Other failure_reasons used:
        # "Database unavailable", "User locked out", "PIN not found".
        assert attempt.failure_reason == "Invalid PIN"

    async def test_session_expiration(self, pin_manager_with_db, db_session, test_user):
        """Test that expired sessions are not valid."""
        # Create PIN
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        # Create session manually with past expiration
        expired_session = PINSession(
            id="expired-session-123",
            session_id="expired-session-id",
            user_pin_id="pin-123",  # Will be updated after PIN creation
            created_by_user_id=test_user.id,
            is_active=True,
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # Expired
            max_duration_minutes=60,
        )
        db_session.add(expired_session)
        await db_session.commit()

        # Try to authorize with expired session
        result = await pin_manager_with_db.authorize_operation(
            session_id="expired-session-id",
            operation="emergency_stop",
            user_id=test_user.id,
        )

        assert result is False


class TestLockoutProtection:
    """Test lockout protection after failed attempts."""

    async def test_lockout_after_failed_attempts(self, pin_manager_with_db, db_session, test_user):
        """Test that user is locked out after max failed attempts."""
        # Create PIN
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        # Make multiple failed attempts
        for _ in range(3):  # Max attempts = 3
            result = await pin_manager_with_db.validate_pin(
                user_id=test_user.id,
                pin="wrong",
                pin_type="emergency",
            )
            assert result.session_id is None

        # Next attempt should fail due to lockout
        result = await pin_manager_with_db.validate_pin(
            user_id=test_user.id,
            pin="1234",  # Even correct PIN should fail
            pin_type="emergency",
        )

        assert result.session_id is None
        assert result.lockout_until is not None  # locked out, not just rejected

        # Verify attempts were logged
        stmt = select(PINAttempt).filter_by(attempted_by_user_id=test_user.id)
        result = await db_session.execute(stmt)
        attempts = result.scalars().all()

        assert len(attempts) >= 3
        assert all(not attempt.success for attempt in attempts)

    async def test_lockout_expires_after_duration(self, pin_manager_with_db, db_session, test_user):
        """Test that lockout expires after configured duration."""
        # Create PIN
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        # Get the PIN to manipulate attempts
        stmt = select(UserPIN).filter_by(user_id=test_user.id, pin_type="emergency")
        result = await db_session.execute(stmt)
        pin = result.scalar_one()

        # Create old failed attempts (outside lockout window)
        old_time = datetime.now(UTC) - timedelta(minutes=20)  # Lockout = 15 min
        for i in range(3):
            attempt = PINAttempt(
                id=f"old-attempt-{i}",
                user_pin_id=pin.id,
                attempted_by_user_id=test_user.id,
                pin_type="emergency",
                success=False,
                failure_reason="invalid_pin",
                attempted_at=old_time,
            )
            db_session.add(attempt)

        await db_session.commit()

        # Should be able to validate now
        result = await pin_manager_with_db.validate_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        assert result.session_id is not None


class TestConcurrentOperations:
    """Test concurrent PIN operations."""

    async def test_concurrent_session_creation(self, pin_manager_with_db, db_session, test_user):
        """Test creating multiple sessions concurrently."""
        # Create PIN
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        # Create multiple concurrent validation tasks
        async def validate():
            return await pin_manager_with_db.validate_pin(
                user_id=test_user.id,
                pin="1234",
                pin_type="emergency",
            )

        # Run 5 concurrent validations
        tasks = [validate() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        session_ids = [r.session_id for r in results]

        # All should succeed with unique session IDs
        assert all(r.success for r in results)
        assert all(sid is not None for sid in session_ids)
        assert len(set(session_ids)) == 5  # All unique

        # Verify all sessions exist in database
        stmt = select(PINSession).filter(PINSession.session_id.in_(session_ids))
        db_result = await db_session.execute(stmt)
        sessions = db_result.scalars().all()

        assert len(sessions) == 5
        assert all(s.is_active for s in sessions)

    async def test_concurrent_authorization_with_max_operations(
        self, pin_manager_with_db, db_session, test_user
    ):
        """Test concurrent authorization with operation limits."""
        # Create PIN
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        # Create session with operation limit
        result = await pin_manager_with_db.validate_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )
        session_id = result.session_id
        assert session_id is not None

        # Update session to have max operations
        stmt = select(PINSession).filter_by(session_id=session_id)
        result = await db_session.execute(stmt)
        session = result.scalar_one()
        session.max_operations = 3
        await db_session.commit()

        # Try to authorize multiple operations concurrently
        async def authorize():
            return await pin_manager_with_db.authorize_operation(
                session_id=session_id,
                operation="test_operation",
                user_id=test_user.id,
            )

        # Run 5 concurrent authorizations
        tasks = [authorize() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # Only 3 should succeed due to operation limit
        success_count = sum(1 for r in results if r)
        assert success_count <= 3

        # Verify operation count in database
        await db_session.refresh(session)
        assert session.operation_count == 3


class TestPINRotationAndManagement:
    """Test PIN rotation and management operations."""

    async def test_rotate_pin(self, pin_manager_with_db, db_session, test_user):
        """Test rotating an existing PIN."""
        # Create initial PIN
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        # Validate old PIN works
        result = await pin_manager_with_db.validate_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )
        assert result.session_id is not None

        # Rotate PIN
        result_bool = await pin_manager_with_db.rotate_pin(
            user_id=test_user.id,
            pin_type="emergency",
            old_pin="1234",
            new_pin="5678",
        )
        assert result_bool is True

        # Old PIN should not work
        result = await pin_manager_with_db.validate_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )
        assert result.session_id is None

        # New PIN should work
        result = await pin_manager_with_db.validate_pin(
            user_id=test_user.id,
            pin="5678",
            pin_type="emergency",
        )
        assert result.session_id is not None

    async def test_deactivate_pin(self, pin_manager_with_db, db_session, test_user):
        """Test deactivating a PIN."""
        # Create PIN
        await pin_manager_with_db.create_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )

        # Deactivate PIN
        result_bool = await pin_manager_with_db.deactivate_pin(
            user_id=test_user.id,
            pin_type="emergency",
        )
        assert result_bool is True

        # PIN should not work
        result = await pin_manager_with_db.validate_pin(
            user_id=test_user.id,
            pin="1234",
            pin_type="emergency",
        )
        assert result.session_id is None

        # Verify PIN is inactive in database
        stmt = select(UserPIN).filter_by(user_id=test_user.id, pin_type="emergency")
        db_result = await db_session.execute(stmt)
        pin = db_result.scalar_one()
        assert pin.is_active is False
