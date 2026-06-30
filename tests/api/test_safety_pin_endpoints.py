"""
Integration tests for PIN-based guardrails API endpoints.

Tests cover the complete request/response cycle for:
- PIN command halt endpoints
- Interlock override endpoints
- Maintenance mode endpoints
- Diagnostic mode endpoints
- Operational mode queries
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from backend.api.routers.guardrails import router
from backend.core.dependencies import (
    get_authenticated_admin,
    get_authenticated_user,
    get_command_guardrail_service,
)
from backend.services.guardrails.command_guardrail_service import (
    CommandPrecondition,
    SystemOperationalMode,
)


@pytest.fixture
def mock_command_guardrail_service():
    """Mock guardrails service for testing."""
    service = MagicMock()
    service._command_halt_active = False
    service._operational_mode = SystemOperationalMode.NORMAL
    service._interlocks = {}
    service._active_overrides = {}
    service.get_guardrail_status = MagicMock(
        return_value={
            "in_command_halt_state": False,
            "command_halt_active": False,
            "operational_mode": "normal",
            "mode_session": None,
            "active_overrides": {},
            "interlocks": {},
            "system_state": {},
            "audit_log_entries": 0,
            "halt_command_emission_reason": None,
            "active_guardrail_actions": [],
            "watchdog_timeout": 15.0,
            "time_since_last_kick": 1.0,
        }
    )
    return service


@pytest.fixture
def client(mock_command_guardrail_service):
    """Create test client with FastAPI dependency overrides.

    NOTE: We override the dependency callables at the FastAPI app level rather
    than patching module attributes. FastAPI captures the dependency callable
    at route-registration time, so monkey-patching the module attribute later
    does not affect routes that were already registered.
    """
    app = FastAPI()
    app.include_router(router)

    admin_user = {
        "user_id": "admin-123",
        "username": "admin",
        "email": "admin@example.com",
    }
    regular_user = {
        "user_id": "user-123",
        "username": "testuser",
        "email": "user@example.com",
    }

    app.dependency_overrides[get_command_guardrail_service] = lambda: mock_command_guardrail_service
    app.dependency_overrides[get_authenticated_admin] = lambda: admin_user
    app.dependency_overrides[get_authenticated_user] = lambda: regular_user

    yield TestClient(app)

    app.dependency_overrides.clear()


class TestPINCommandHaltEndpoints:
    """Test PIN-based command halt endpoints."""

    def test_pin_halt_command_emission_success(self, client, mock_command_guardrail_service):
        """Test successful PIN command halt."""
        # Mock the service method
        mock_command_guardrail_service.halt_command_emission_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/guardrails/pin/command-halt",
            json={
                "pin_session_id": "test-session-123",
                "reason": "Test command halt",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "halt_command_emission_activated"
        assert data["reason"] == "Test command halt"
        assert data["triggered_by"] == "admin"
        assert data["authorization_method"] == "pin_session"

        # Verify service method was called
        mock_command_guardrail_service.halt_command_emission_with_pin.assert_called_once_with(
            pin_session_id="test-session-123",
            reason="Test command halt",
            triggered_by="admin",
        )

    def test_pin_halt_command_emission_unauthorized(self, client, mock_command_guardrail_service):
        """Test command halt with invalid PIN."""
        # Mock failed authorization
        mock_command_guardrail_service.halt_command_emission_with_pin = AsyncMock(
            return_value=False
        )

        # Make request
        response = client.post(
            "/api/guardrails/pin/command-halt",
            json={
                "pin_session_id": "invalid-session",
                "reason": "Test command halt",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "PIN authorization failed for command halt"

    def test_pin_clear_command_halt_success(self, client, mock_command_guardrail_service):
        """Test successful PIN command halt clear."""
        # Mock the service method
        mock_command_guardrail_service.clear_command_halt_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/guardrails/pin/command-halt/clear",
            json={
                "pin_session_id": "test-session-123",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["cleared_by"] == "admin"
        assert data["authorization_method"] == "pin_session"


class TestInterlockOverrideEndpoints:
    """Test PIN-based interlock override endpoints."""

    def test_pin_override_interlock_success(self, client, mock_command_guardrail_service):
        """Test successful interlock override with PIN."""
        # Mock the service method
        mock_command_guardrail_service.override_interlock_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/guardrails/pin/interlocks/override",
            json={
                "pin_session_id": "test-session-123",
                "interlock_name": "slide_room_precondition",
                "reason": "Maintenance required",
                "duration_minutes": 60,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["interlock_name"] == "slide_room_precondition"
        assert data["overridden_by"] == "admin"
        assert data["duration_minutes"] == 60

        # Verify service method was called
        mock_command_guardrail_service.override_interlock_with_pin.assert_called_once_with(
            pin_session_id="test-session-123",
            interlock_name="slide_room_precondition",
            reason="Maintenance required",
            duration_minutes=60,
            overridden_by="admin",
        )

    def test_pin_override_interlock_invalid_duration(self, client):
        """Test interlock override with invalid duration."""
        # Make request with duration too long
        response = client.post(
            "/api/guardrails/pin/interlocks/override",
            json={
                "pin_session_id": "test-session-123",
                "interlock_name": "test_interlock",
                "reason": "Test",
                "duration_minutes": 500,  # > 480 max
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_clear_interlock_override_success(self, client, mock_command_guardrail_service):
        """Test clearing an interlock override."""
        # Mock the service method
        mock_command_guardrail_service.clear_interlock_override = MagicMock(return_value=True)

        # Make request
        response = client.post(
            "/api/guardrails/interlocks/clear-override",
            json={
                "interlock_name": "slide_room_precondition",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["interlock_name"] == "slide_room_precondition"
        assert data["cleared_by"] == "admin"

    def test_get_active_overrides(self, client, mock_command_guardrail_service):
        """Test getting active interlock overrides."""
        # Set up mock data
        test_interlock = CommandPrecondition(
            name="test_interlock",
            feature_name="test_feature",
            interlock_conditions=["vehicle_not_moving"],
        )
        test_interlock._is_overridden = True
        test_interlock._override_by = "admin"
        test_interlock._override_reason = "Testing"
        test_interlock._override_session_id = "session-123"

        mock_command_guardrail_service._interlocks = {"test_interlock": test_interlock}
        mock_command_guardrail_service.get_guardrail_status.return_value["active_overrides"] = {
            "test_interlock": datetime.now(UTC).isoformat()
        }

        # Mock get_override_info method
        test_interlock.get_override_info = MagicMock(
            return_value={
                "is_overridden": True,
                "session_id": "session-123",
                "reason": "Testing",
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "overridden_by": "admin",
            }
        )

        # Make request
        response = client.get("/api/guardrails/interlocks/overrides")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_overrides"] == 1
        assert len(data["overrides"]) == 1
        assert data["overrides"][0]["interlock_name"] == "test_interlock"
        assert data["overrides"][0]["overridden_by"] == "admin"


class TestMaintenanceModeEndpoints:
    """Test PIN-based maintenance mode endpoints."""

    def test_enter_maintenance_mode_success(self, client, mock_command_guardrail_service):
        """Test successful maintenance mode entry."""
        # Mock the service method
        mock_command_guardrail_service.enter_maintenance_mode_with_pin = AsyncMock(
            return_value=True
        )

        # Make request
        response = client.post(
            "/api/guardrails/pin/maintenance-mode/enter",
            json={
                "pin_session_id": "test-session-123",
                "reason": "Scheduled maintenance",
                "duration_minutes": 120,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["operational_mode"] == "maintenance"
        assert data["entered_by"] == "admin"
        assert data["duration_minutes"] == 120

    def test_exit_maintenance_mode_success(self, client, mock_command_guardrail_service):
        """Test successful maintenance mode exit."""
        # Mock the service method
        mock_command_guardrail_service.exit_maintenance_mode_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/guardrails/pin/maintenance-mode/exit",
            json={
                "pin_session_id": "test-session-123",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["operational_mode"] == "normal"
        assert data["exited_by"] == "admin"

    def test_maintenance_mode_invalid_duration(self, client):
        """Test maintenance mode with invalid duration."""
        # Too short
        response = client.post(
            "/api/guardrails/pin/maintenance-mode/enter",
            json={
                "pin_session_id": "test-session-123",
                "reason": "Test",
                "duration_minutes": 10,  # < 15 min
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestDiagnosticModeEndpoints:
    """Test PIN-based diagnostic mode endpoints."""

    def test_enter_diagnostic_mode_success(self, client, mock_command_guardrail_service):
        """Test successful diagnostic mode entry."""
        # Mock the service method
        mock_command_guardrail_service.enter_diagnostic_mode_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/guardrails/pin/diagnostic-mode/enter",
            json={
                "pin_session_id": "test-session-123",
                "reason": "System diagnostics",
                "duration_minutes": 60,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["operational_mode"] == "diagnostic"
        assert data["warning"] == "Guardrail constraints may be modified during diagnostics"

    def test_get_operational_mode(self, client, mock_command_guardrail_service):
        """Test getting current operational mode."""
        # Set up maintenance mode active
        mock_command_guardrail_service.get_guardrail_status.return_value.update(
            {
                "operational_mode": "maintenance",
                "mode_session": {
                    "session_id": "session-123",
                    "entered_by": "admin",
                    "entered_at": datetime.now(UTC).isoformat(),
                    "expires_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
                },
                "active_overrides": {"test_interlock": "2024-01-01T00:00:00"},
            }
        )

        # Make request
        response = client.get("/api/guardrails/operational-mode")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["operational_mode"] == "maintenance"
        assert data["is_normal_mode"] is False
        assert "session_details" in data
        assert data["active_overrides_count"] == 1


class TestGuardrailEndpointsAuthentication:
    """Test authentication requirements for guardrails endpoints."""

    def test_unauthenticated_access_denied(self, mock_command_guardrail_service):
        """Test that unauthenticated access is denied."""

        def _unauthorized():
            raise Exception("Unauthorized")

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_command_guardrail_service] = (
            lambda: mock_command_guardrail_service
        )
        app.dependency_overrides[get_authenticated_admin] = _unauthorized
        app.dependency_overrides[get_authenticated_user] = _unauthorized

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/guardrails/pin/command-halt",
            json={
                "pin_session_id": "test-session-123",
                "reason": "Test",
            },
        )

        app.dependency_overrides.clear()

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_non_admin_access_denied(self, mock_command_guardrail_service):
        """Test that non-admin users cannot access admin endpoints."""

        def _not_admin():
            raise Exception("Not admin")

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_command_guardrail_service] = (
            lambda: mock_command_guardrail_service
        )
        app.dependency_overrides[get_authenticated_admin] = _not_admin
        app.dependency_overrides[get_authenticated_user] = lambda: {
            "user_id": "user-123",
            "username": "testuser",
        }

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/guardrails/pin/maintenance-mode/enter",
            json={
                "pin_session_id": "test-session-123",
                "reason": "Test",
                "duration_minutes": 60,
            },
        )

        app.dependency_overrides.clear()

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestErrorHandling:
    """Test error handling in guardrails endpoints."""

    def test_service_error_handling(self, client, mock_command_guardrail_service):
        """Test handling of service errors."""
        # Mock service error
        mock_command_guardrail_service.halt_command_emission_with_pin = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        # Make request
        response = client.post(
            "/api/guardrails/pin/command-halt",
            json={
                "pin_session_id": "test-session-123",
                "reason": "Test",
            },
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database connection failed" in response.json()["detail"]

    def test_invalid_request_format(self, client):
        """Test handling of invalid request format."""
        # Missing required field
        response = client.post(
            "/api/guardrails/pin/command-halt",
            json={
                "reason": "Test",
                # Missing pin_session_id
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Invalid field type
        response = client.post(
            "/api/guardrails/pin/interlocks/override",
            json={
                "pin_session_id": "test-session-123",
                "interlock_name": "test",
                "reason": "Test",
                "duration_minutes": "sixty",  # Should be int
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
