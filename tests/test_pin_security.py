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
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.auth import PINAttempt, PINSession, User, UserPIN
from backend.services.auth.pin_manager import PINConfig, PINManager
from backend.services.guardrails.command_guardrail_service import (
    CommandGuardrailService,
    SystemOperationalMode,
)
from backend.services.security.security_audit_service import SecurityAuditService


@pytest.fixture
async def mock_db_session():
    """Mock database session for testing.

    Configured so that ``await session.execute(...)`` returns a MagicMock
    whose query methods default to safe values:
      - scalar_one_or_none() → None    ('no row')
      - scalar() → 0                    (count = 0)
      - scalars().all() → []            (no rows)
    Individual tests can override these before calling.
    """
    session = AsyncMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    result_mock.scalar = MagicMock(return_value=0)
    result_mock.scalars.return_value.all = MagicMock(return_value=[])
    session.execute.return_value = result_mock
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
async def command_guardrail_service(pin_manager, security_audit_service):
    """Create safety service with PIN manager."""
    # Modern CommandGuardrailService takes a GuardrailCoordinator, not a feature_manager.
    # Use a permissive mock here since these tests exercise PIN-related paths,
    # not the registry-driven health checks.
    service_registry = MagicMock()
    service_registry.check_system_health = AsyncMock(return_value={"failed_critical": []})

    service = CommandGuardrailService(
        service_registry=service_registry,
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
        result = await pin_manager.set_pin(
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
        # set_pin raises ValueError on invalid format (rather than returning
        # False) so callers must handle the exception explicitly.
        # Too short
        with pytest.raises(ValueError, match="format"):
            await pin_manager.set_pin(
                user_id=mock_user.id,
                pin="123",
                pin_type="emergency",
            )

        # Too long
        with pytest.raises(ValueError, match="format"):
            await pin_manager.set_pin(
                user_id=mock_user.id,
                pin="123456789",
                pin_type="emergency",
            )

        # No numbers (required by config)
        with pytest.raises(ValueError, match="format"):
            await pin_manager.set_pin(
                user_id=mock_user.id,
                pin="abcd",
                pin_type="emergency",
            )

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
            use_count=0,
        )

        # Mock database queries
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_pin
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        # validate_pin computes hashed_pin = self._hash_pin(pin, pin_record.salt)
        # then compares to pin_record.pin_hash. Make _hash_pin return the
        # configured pin_hash so the comparison succeeds.
        with patch.object(pin_manager, "_hash_pin", return_value="hashed_pin"):
            result = await pin_manager.validate_pin(
                user_id=mock_user.id,
                pin="1234",
                pin_type="emergency",
                ip_address="127.0.0.1",
            )

        # validate_pin returns a PINValidationResult with the session id on success.
        assert result.success is True
        assert result.session_id is not None
        assert isinstance(result.session_id, str)
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
            use_count=0,
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

        # Mock database queries.
        # _is_user_locked_out runs:
        #   1. SELECT count(*) ...  -> result.scalar()  (failed-attempt count)
        #   2. SELECT attempted_at ORDER BY ... LIMIT 1 -> result.scalar()
        # Both go through the same execute() return_value, so mock scalar()
        # to return enough failed attempts to trigger lockout, then a recent
        # timestamp for the lockout-expiry calculation.
        mock_db_session.execute.return_value.scalar = MagicMock(
            side_effect=[3, datetime.now(UTC) - timedelta(minutes=5)]
        )
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_pin
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = recent_attempts

        # Try to validate PIN - should fail due to lockout
        result = await pin_manager.validate_pin(
            user_id=mock_user.id,
            pin="1234",
            pin_type="emergency",
        )

        assert result.success is False
        assert result.lockout_until is not None

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
            operation="halt_command_emission",
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
            operation="halt_command_emission",
            user_id="user-123",
        )

        assert result is False


class TestEmergencyStopWithPIN:
    """Test emergency stop operations with PIN authorization."""

    async def test_halt_command_emission_with_pin_success(
        self, command_guardrail_service, pin_manager
    ):
        """Test successful emergency stop with PIN."""
        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Trigger emergency stop
        result = await command_guardrail_service.halt_command_emission_with_pin(
            pin_session_id="test-session-id",
            reason="Test emergency stop",
            triggered_by="testuser",
        )

        assert result is True
        assert command_guardrail_service._command_halt_active is True
        assert command_guardrail_service._halt_command_emission_reason == "Test emergency stop"
        assert command_guardrail_service._halt_command_emission_triggered_by == "testuser"

        # Verify PIN authorization was called
        pin_manager.authorize_operation.assert_called_once_with(
            session_id="test-session-id",
            operation="halt_command_emission",
            user_id="testuser",
        )

    async def test_halt_command_emission_with_pin_unauthorized(
        self, command_guardrail_service, pin_manager
    ):
        """Test emergency stop with invalid PIN."""
        # Mock failed PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=False)

        # Try to trigger emergency stop
        result = await command_guardrail_service.halt_command_emission_with_pin(
            pin_session_id="invalid-session",
            reason="Test emergency stop",
            triggered_by="testuser",
        )

        assert result is False
        assert command_guardrail_service._command_halt_active is False

    async def test_clear_command_halt_with_pin(self, command_guardrail_service, pin_manager):
        """Test emergency stop reset with PIN."""
        # First activate emergency stop
        command_guardrail_service._command_halt_active = True
        command_guardrail_service._halt_command_emission_reason = "Test"
        command_guardrail_service._halt_command_emission_triggered_by = "testuser"

        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Reset emergency stop
        result = await command_guardrail_service.clear_command_halt_with_pin(
            pin_session_id="test-session-id",
            reset_by="testuser",
        )

        assert result is True
        assert command_guardrail_service._command_halt_active is False
        assert command_guardrail_service._halt_command_emission_reason is None


class TestInterlockOverrideWithPIN:
    """Test safety interlock override operations with PIN."""

    async def test_override_interlock_with_pin_success(
        self, command_guardrail_service, pin_manager
    ):
        """Test successful interlock override with PIN."""
        # Add a test interlock
        from backend.services.guardrails.command_guardrail_service import CommandPrecondition

        test_interlock = CommandPrecondition(
            name="test_interlock",
            feature_name="test_feature",
            interlock_conditions=["vehicle_not_moving"],
        )
        command_guardrail_service._interlocks["test_interlock"] = test_interlock

        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Override interlock
        result = await command_guardrail_service.override_interlock_with_pin(
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
        assert "test_interlock" in command_guardrail_service._active_overrides

    async def test_override_nonexistent_interlock(self, command_guardrail_service, pin_manager):
        """Test override attempt on non-existent interlock."""
        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Try to override non-existent interlock
        result = await command_guardrail_service.override_interlock_with_pin(
            pin_session_id="test-session-id",
            interlock_name="nonexistent",
            reason="Testing",
            duration_minutes=30,
            overridden_by="testuser",
        )

        assert result is False

    async def test_clear_interlock_override(self, command_guardrail_service):
        """Test clearing an interlock override."""
        # Add a test interlock with override
        from backend.services.guardrails.command_guardrail_service import CommandPrecondition

        test_interlock = CommandPrecondition(
            name="test_interlock",
            feature_name="test_feature",
            interlock_conditions=["vehicle_not_moving"],
        )
        test_interlock._is_overridden = True
        test_interlock._override_reason = "Test"
        command_guardrail_service._interlocks["test_interlock"] = test_interlock
        command_guardrail_service._active_overrides["test_interlock"] = datetime.now(UTC)

        # Clear override
        result = command_guardrail_service.clear_interlock_override("test_interlock")

        assert result is True
        assert test_interlock._is_overridden is False
        assert "test_interlock" not in command_guardrail_service._active_overrides


class TestMaintenanceModeWithPIN:
    """Test maintenance mode operations with PIN."""

    async def test_enter_maintenance_mode_success(self, command_guardrail_service, pin_manager):
        """Test successful entry into maintenance mode."""
        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Enter maintenance mode
        result = await command_guardrail_service.enter_maintenance_mode_with_pin(
            pin_session_id="test-session-id",
            reason="Scheduled maintenance",
            duration_minutes=120,
            entered_by="testuser",
        )

        assert result is True
        assert command_guardrail_service._operational_mode == SystemOperationalMode.MAINTENANCE
        assert command_guardrail_service._mode_entered_by == "testuser"
        assert command_guardrail_service._mode_session_id == "test-session-id"

    async def test_exit_maintenance_mode_success(self, command_guardrail_service, pin_manager):
        """Test successful exit from maintenance mode."""
        # Set up maintenance mode
        command_guardrail_service._operational_mode = SystemOperationalMode.MAINTENANCE
        command_guardrail_service._mode_entered_by = "testuser"
        command_guardrail_service._mode_entered_at = datetime.now(UTC)

        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Exit maintenance mode
        result = await command_guardrail_service.exit_maintenance_mode_with_pin(
            pin_session_id="test-session-id",
            exited_by="testuser",
        )

        assert result is True
        assert command_guardrail_service._operational_mode == SystemOperationalMode.NORMAL
        assert command_guardrail_service._mode_entered_by is None

    async def test_maintenance_mode_already_active(self, command_guardrail_service, pin_manager):
        """Test entering maintenance mode when already active."""
        # Set maintenance mode active
        command_guardrail_service._operational_mode = SystemOperationalMode.MAINTENANCE

        # Try to enter again
        result = await command_guardrail_service.enter_maintenance_mode_with_pin(
            pin_session_id="test-session-id",
            reason="Another maintenance",
            duration_minutes=60,
            entered_by="testuser",
        )

        assert result is False


class TestDiagnosticModeWithPIN:
    """Test diagnostic mode operations with PIN."""

    async def test_enter_diagnostic_mode_success(self, command_guardrail_service, pin_manager):
        """Test successful entry into diagnostic mode."""
        # Mock PIN authorization
        pin_manager.authorize_operation = AsyncMock(return_value=True)

        # Enter diagnostic mode
        result = await command_guardrail_service.enter_diagnostic_mode_with_pin(
            pin_session_id="test-session-id",
            reason="System diagnostics",
            duration_minutes=60,
            entered_by="testuser",
        )

        assert result is True
        assert command_guardrail_service._operational_mode == SystemOperationalMode.DIAGNOSTIC
        assert command_guardrail_service._mode_entered_by == "testuser"

    async def test_mode_expiration(self, command_guardrail_service):
        """Test automatic mode expiration."""
        # Set up expired diagnostic mode
        command_guardrail_service._operational_mode = SystemOperationalMode.DIAGNOSTIC
        command_guardrail_service._mode_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        command_guardrail_service._mode_entered_by = "testuser"

        # Add an active override
        command_guardrail_service._active_overrides["test_interlock"] = datetime.now(UTC)

        # Check expiration
        command_guardrail_service.check_mode_expiration()

        assert command_guardrail_service._operational_mode == SystemOperationalMode.NORMAL
        assert command_guardrail_service._mode_expires_at is None
        assert len(command_guardrail_service._active_overrides) == 0


class TestSecurityAuditIntegration:
    """Test security audit logging integration."""

    async def test_security_audit_on_failed_pin(
        self, command_guardrail_service, security_audit_service
    ):
        """Test security audit logging on failed PIN attempts."""
        # Mock failed PIN authorization
        command_guardrail_service.pin_manager.authorize_operation = AsyncMock(return_value=False)

        # Try emergency stop with invalid PIN
        await command_guardrail_service.halt_command_emission_with_pin(
            pin_session_id="invalid",
            reason="Test",
            triggered_by="testuser",
        )

        # Verify security audit was called.
        # The audit call passes emergency_context=True because the operation
        # being attempted IS an emergency stop, regardless of whether the PIN
        # check succeeded.
        security_audit_service.log_security_event.assert_called_with(
            event_type="unauthorized_access",
            severity="high",
            user_id="testuser",
            details={
                "attempted_operation": "halt_command_emission_with_pin",
                "failure_reason": "pin_authorization_failed",
                "pin_session_id": "invalid",
            },
            emergency_context=True,
        )

    async def test_rate_limiting_integration(
        self, command_guardrail_service, security_audit_service
    ):
        """Test rate limiting integration."""
        # Configure rate limit to fail
        security_audit_service.check_rate_limit = AsyncMock(return_value=False)

        # Try safety operation
        result = await command_guardrail_service.validate_safety_operation(
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
            use_count=0,
        )

        mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_pin
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        # validate_pin uses _hash_pin (the older _verify_pin was removed during
        # the repo-pattern refactor). Mock it to return the configured pin_hash
        # so every concurrent attempt's PIN comparison succeeds.
        with patch.object(pin_manager, "_hash_pin", return_value="hashed_pin"):
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

        # All should succeed with unique session IDs.
        assert all(r.success for r in results)
        session_ids = [r.session_id for r in results]
        assert all(sid is not None for sid in session_ids)
        assert len(set(session_ids)) == 5  # All unique session IDs
