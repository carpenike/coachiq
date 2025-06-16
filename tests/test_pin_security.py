"""
Comprehensive security tests for PIN-based safety operations.

Tests cover:
- PIN validation and session management
- Emergency stop with PIN authorization
- Safety interlock overrides with PIN
- Maintenance mode operations with PIN
- Diagnostic mode operations with PIN
- Rate limiting and lockout protection
- Audit logging and security events
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.auth import PINAttempt, PINSession, User, UserPIN
from backend.services.pin_manager import PINConfig, PINManager
from backend.services.safety_service import SafetyService, SystemOperationalMode
from backend.services.security_audit_service import SecurityAuditService


@pytest.fixture
async def mock_db_session():
    """Mock database session for testing."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
async def mock_user():
    """Mock user for testing."""
    user = User(
        id="test-user-123",
        email="test@example.com",
        username="testuser",
        is_active=True,
        is_admin=True,
    )
    return user


@pytest.fixture
async def pin_config():
    """PIN configuration for testing."""
    return PINConfig(
        min_length=4,
        max_length=8,
        require_numbers=True,
        require_letters=False,
        session_duration_minutes=60,
        max_attempts=3,
        lockout_duration_minutes=15,
    )


@pytest.fixture
async def pin_manager(pin_config, mock_db_session):
    """Create PIN manager for testing."""
    manager = PINManager(config=pin_config, db_session=mock_db_session)
    return manager


@pytest.fixture
async def security_audit_service():
    """Mock security audit service."""
    service = AsyncMock(spec=SecurityAuditService)
    service.log_security_event = AsyncMock()
    service.check_rate_limit = AsyncMock(return_value=True)
    return service


@pytest.fixture
async def safety_service(pin_manager, security_audit_service):
    """Create safety service with PIN manager."""
    feature_manager = MagicMock()
    feature_manager.features = {}
    feature_manager.check_system_health = AsyncMock(return_value={"failed_critical": []})

    service = SafetyService(
        feature_manager=feature_manager,
        pin_manager=pin_manager,
        security_audit_service=security_audit_service,
    )
    return service


class TestPINValidation:
    """Test PIN validation and session management."""

    async def test_create_pin_success(self, pin_manager, mock_db_session, mock_user):
        """Test successful PIN creation."""
        # Mock database queries
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        # Create PIN
        result = await pin_manager.create_pin(
            user_id=mock_user.id,
            pin="1234",
            pin_type="emergency",
            description="Emergency PIN for testing",
        )

        assert result is True
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    async def test_create_pin_invalid_format(self, pin_manager, mock_user):
        """Test PIN creation with invalid format."""
        # Too short
        result = await pin_manager.create_pin(
            user_id=mock_user.id,
            pin="123",
            pin_type="emergency",
        )
        assert result is False

        # Too long
        result = await pin_manager.create_pin(
            user_id=mock_user.id,
            pin="123456789",
            pin_type="emergency",
        )
        assert result is False

        # No numbers (required by config)
        result = await pin_manager.create_pin(
            user_id=mock_user.id,
            pin="abcd",
            pin_type="emergency",
        )
        assert result is False

    async def test_validate_pin_success(self, pin_manager, mock_db_session, mock_user):
        """Test successful PIN validation and session creation."""
        # Create mock PIN
        mock_pin = UserPIN(
            id="pin-123",
            user_id=mock_user.id,
            pin_type="emergency",
            pin_hash="hashed_pin",
            salt="salt",
            is_active=True,
            lockout_after_failures=3,
            lockout_duration_minutes=15,
        )

        # Mock database queries
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_pin
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        # Mock PIN verification
        with patch.object(pin_manager, "_verify_pin", return_value=True):
            session_id = await pin_manager.validate_pin(
                user_id=mock_user.id,
                pin="1234",
                pin_type="emergency",
                ip_address="127.0.0.1",
            )

        assert session_id is not None
        assert isinstance(session_id, str)
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called()

    async def test_validate_pin_lockout(self, pin_manager, mock_db_session, mock_user):
        """Test PIN lockout after failed attempts."""
        # Create mock PIN
        mock_pin = UserPIN(
            id="pin-123",
            user_id=mock_user.id,
            pin_type="emergency",
            pin_hash="hashed_pin",
            salt="salt",
            is_active=True,
            lockout_after_failures=3,
            lockout_duration_minutes=15,
        )

        # Create recent failed attempts
        recent_attempts = [
            PINAttempt(
                id=f"attempt-{i}",
                user_pin_id=mock_pin.id,
                attempted_by_user_id=mock_user.id,
                success=False,
                attempted_at=datetime.now(UTC) - timedelta(minutes=5),
            )
            for i in range(3)
        ]

        # Mock database queries
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_pin
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = recent_attempts

        # Try to validate PIN - should fail due to lockout
        session_id = await pin_manager.validate_pin(
            user_id=mock_user.id,
            pin="1234",
            pin_type="emergency",
        )

        assert session_id is None

    async def test_authorize_operation_success(self, pin_manager, mock_db_session):
        """Test successful operation authorization."""
        # Create mock session
        mock_session = PINSession(
            id="session-123",
            session_id="test-session-id",
            user_pin_id="pin-123",
            created_by_user_id="user-123",
            is_active=True,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            operation_count=0,
            max_operations=None,
        )

        # Mock database query
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_session
        mock_db_session.commit = AsyncMock()

        # Authorize operation
        result = await pin_manager.authorize_operation(
            session_id="test-session-id",
            operation="emergency_stop",
            user_id="user-123",
        )

        assert result is True
        mock_db_session.commit.assert_called_once()

    async def test_authorize_operation_expired_session(self, pin_manager, mock_db_session):
        """Test operation authorization with expired session."""
        # Create expired session
        mock_session = PINSession(
            id="session-123",
            session_id="test-session-id",
            user_pin_id="pin-123",
            created_by_user_id="user-123",
            is_active=True,
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # Expired
        )

        # Mock database query
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_session

        # Try to authorize - should fail
        result = await pin_manager.authorize_operation(
            session_id="test-session-id",
            operation="emergency_stop",
            user_id="user-123",
        )

        assert result is False


class TestEmergencyStopWithPIN:
    """Test emergency stop operations with PIN authorization."""

    async def test_emergency_stop_with_pin_success(self, safety_service, pin_manager):
        """Test successful emergency stop with PIN."""
        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Trigger emergency stop
        result = await safety_service.emergency_stop_with_pin(
            pin_session_id="test-session-id",
            reason="Test emergency stop",
            triggered_by="testuser",
        )

        assert result is True
        assert safety_service._emergency_stop_active is True
        assert safety_service._emergency_stop_reason == "Test emergency stop"
        assert safety_service._emergency_stop_triggered_by == "testuser"

        # Verify PIN authorization was called
        pin_manager.authorize_operation.assert_called_once_with(
            session_id="test-session-id",
            operation="emergency_stop",
            user_id="testuser",
        )

    async def test_emergency_stop_with_pin_unauthorized(self, safety_service, pin_manager):
        """Test emergency stop with invalid PIN."""
        # Mock failed PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=False)

        # Try to trigger emergency stop
        result = await safety_service.emergency_stop_with_pin(
            pin_session_id="invalid-session",
            reason="Test emergency stop",
            triggered_by="testuser",
        )

        assert result is False
        assert safety_service._emergency_stop_active is False

    async def test_reset_emergency_stop_with_pin(self, safety_service, pin_manager):
        """Test emergency stop reset with PIN."""
        # First activate emergency stop
        safety_service._emergency_stop_active = True
        safety_service._emergency_stop_reason = "Test"
        safety_service._emergency_stop_triggered_by = "testuser"

        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Reset emergency stop
        result = await safety_service.reset_emergency_stop_with_pin(
            pin_session_id="test-session-id",
            reset_by="testuser",
        )

        assert result is True
        assert safety_service._emergency_stop_active is False
        assert safety_service._emergency_stop_reason is None


class TestInterlockOverrideWithPIN:
    """Test safety interlock override operations with PIN."""

    async def test_override_interlock_with_pin_success(self, safety_service, pin_manager):
        """Test successful interlock override with PIN."""
        # Add a test interlock
        from backend.services.safety_service import SafetyInterlock

        test_interlock = SafetyInterlock(
            name="test_interlock",
            feature_name="test_feature",
            interlock_conditions=["vehicle_not_moving"],
        )
        safety_service._interlocks["test_interlock"] = test_interlock

        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Override interlock
        result = await safety_service.override_interlock_with_pin(
            pin_session_id="test-session-id",
            interlock_name="test_interlock",
            reason="Testing override",
            duration_minutes=30,
            overridden_by="testuser",
        )

        assert result is True
        assert test_interlock._is_overridden is True
        assert test_interlock._override_reason == "Testing override"
        assert test_interlock._override_by == "testuser"
        assert "test_interlock" in safety_service._active_overrides

    async def test_override_nonexistent_interlock(self, safety_service, pin_manager):
        """Test override attempt on non-existent interlock."""
        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Try to override non-existent interlock
        result = await safety_service.override_interlock_with_pin(
            pin_session_id="test-session-id",
            interlock_name="nonexistent",
            reason="Testing",
            duration_minutes=30,
            overridden_by="testuser",
        )

        assert result is False

    async def test_clear_interlock_override(self, safety_service):
        """Test clearing an interlock override."""
        # Add a test interlock with override
        from backend.services.safety_service import SafetyInterlock

        test_interlock = SafetyInterlock(
            name="test_interlock",
            feature_name="test_feature",
            interlock_conditions=["vehicle_not_moving"],
        )
        test_interlock._is_overridden = True
        test_interlock._override_reason = "Test"
        safety_service._interlocks["test_interlock"] = test_interlock
        safety_service._active_overrides["test_interlock"] = datetime.now(UTC)

        # Clear override
        result = safety_service.clear_interlock_override("test_interlock")

        assert result is True
        assert test_interlock._is_overridden is False
        assert "test_interlock" not in safety_service._active_overrides


class TestMaintenanceModeWithPIN:
    """Test maintenance mode operations with PIN."""

    async def test_enter_maintenance_mode_success(self, safety_service, pin_manager):
        """Test successful entry into maintenance mode."""
        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Enter maintenance mode
        result = await safety_service.enter_maintenance_mode_with_pin(
            pin_session_id="test-session-id",
            reason="Scheduled maintenance",
            duration_minutes=120,
            entered_by="testuser",
        )

        assert result is True
        assert safety_service._operational_mode == SystemOperationalMode.MAINTENANCE
        assert safety_service._mode_entered_by == "testuser"
        assert safety_service._mode_session_id == "test-session-id"

    async def test_exit_maintenance_mode_success(self, safety_service, pin_manager):
        """Test successful exit from maintenance mode."""
        # Set up maintenance mode
        safety_service._operational_mode = SystemOperationalMode.MAINTENANCE
        safety_service._mode_entered_by = "testuser"
        safety_service._mode_entered_at = datetime.now(UTC)

        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Exit maintenance mode
        result = await safety_service.exit_maintenance_mode_with_pin(
            pin_session_id="test-session-id",
            exited_by="testuser",
        )

        assert result is True
        assert safety_service._operational_mode == SystemOperationalMode.NORMAL
        assert safety_service._mode_entered_by is None

    async def test_maintenance_mode_already_active(self, safety_service, pin_manager):
        """Test entering maintenance mode when already active."""
        # Set maintenance mode active
        safety_service._operational_mode = SystemOperationalMode.MAINTENANCE

        # Try to enter again
        result = await safety_service.enter_maintenance_mode_with_pin(
            pin_session_id="test-session-id",
            reason="Another maintenance",
            duration_minutes=60,
            entered_by="testuser",
        )

        assert result is False


class TestDiagnosticModeWithPIN:
    """Test diagnostic mode operations with PIN."""

    async def test_enter_diagnostic_mode_success(self, safety_service, pin_manager):
        """Test successful entry into diagnostic mode."""
        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Enter diagnostic mode
        result = await safety_service.enter_diagnostic_mode_with_pin(
            pin_session_id="test-session-id",
            reason="System diagnostics",
            duration_minutes=60,
            entered_by="testuser",
        )

        assert result is True
        assert safety_service._operational_mode == SystemOperationalMode.DIAGNOSTIC
        assert safety_service._mode_entered_by == "testuser"

    async def test_mode_expiration(self, safety_service):
        """Test automatic mode expiration."""
        # Set up expired diagnostic mode
        safety_service._operational_mode = SystemOperationalMode.DIAGNOSTIC
        safety_service._mode_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        safety_service._mode_entered_by = "testuser"

        # Add an active override
        safety_service._active_overrides["test_interlock"] = datetime.now(UTC)

        # Check expiration
        safety_service.check_mode_expiration()

        assert safety_service._operational_mode == SystemOperationalMode.NORMAL
        assert safety_service._mode_expires_at is None
        assert len(safety_service._active_overrides) == 0


class TestSecurityAuditIntegration:
    """Test security audit logging integration."""

    async def test_security_audit_on_failed_pin(self, safety_service, security_audit_service):
        """Test security audit logging on failed PIN attempts."""
        # Mock failed PIN authorization
        safety_service.pin_manager.authorize_operation = AsyncMock(return_value=False)

        # Try emergency stop with invalid PIN
        await safety_service.emergency_stop_with_pin(
            pin_session_id="invalid",
            reason="Test",
            triggered_by="testuser",
        )

        # Verify security audit was called
        security_audit_service.log_security_event.assert_called_with(
            event_type="unauthorized_access",
            severity="high",
            user_id="testuser",
            details={
                "attempted_operation": "emergency_stop_with_pin",
                "failure_reason": "pin_authorization_failed",
                "pin_session_id": "invalid",
            },
            emergency_context=False,
        )

    async def test_rate_limiting_integration(self, safety_service, security_audit_service):
        """Test rate limiting integration."""
        # Configure rate limit to fail
        security_audit_service.check_rate_limit = AsyncMock(return_value=False)

        # Try safety operation
        result = await safety_service.validate_safety_operation(
            operation_type="emergency",
            user_id="testuser",
            source_ip="127.0.0.1",
        )

        assert result is False

        # Verify rate limit was checked
        security_audit_service.check_rate_limit.assert_called_once()

        # Verify security event was logged
        security_audit_service.log_security_event.assert_called_with(
            event_type="rate_limit_exceeded",
            severity="medium",
            user_id="testuser",
            source_ip="127.0.0.1",
            details={
                "operation_type": "emergency",
                "category": "emergency",
                "entity_id": None,
                "blocked_reason": "rate_limit_exceeded",
            },
        )


@pytest.mark.asyncio
class TestConcurrentPINOperations:
    """Test concurrent PIN operations and race conditions."""

    async def test_concurrent_pin_validation(self, pin_manager, mock_db_session, mock_user):
        """Test concurrent PIN validation attempts."""
        # Mock database queries
        mock_pin = UserPIN(
            id="pin-123",
            user_id=mock_user.id,
            pin_type="emergency",
            pin_hash="hashed_pin",
            salt="salt",
            is_active=True,
        )

        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_pin
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        # Mock PIN verification
        with patch.object(pin_manager, "_verify_pin", return_value=True):
            # Create multiple concurrent validation attempts
            tasks = [
                pin_manager.validate_pin(
                    user_id=mock_user.id,
                    pin="1234",
                    pin_type="emergency",
                )
                for _ in range(5)
            ]

            # Run concurrently
            results = await asyncio.gather(*tasks)

        # All should succeed with different session IDs
        assert all(r is not None for r in results)
        assert len(set(results)) == 5  # All unique session IDs
