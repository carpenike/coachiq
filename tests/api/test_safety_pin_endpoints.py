"""
Integration tests for PIN-based safety API endpoints.

Tests cover the complete request/response cycle for:
- PIN emergency stop endpoints
- Interlock override endpoints
- Maintenance mode endpoints
- Diagnostic mode endpoints
- Operational mode queries
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from backend.api.routers.safety import router
from backend.services.safety_service import SafetyInterlock, SystemOperationalMode


@pytest.fixture
def mock_safety_service():
    """Mock safety service for testing."""
    service = MagicMock()
    service._emergency_stop_active = False
    service._operational_mode = SystemOperationalMode.NORMAL
    service._interlocks = {}
    service._active_overrides = {}
    service.get_safety_status = MagicMock(return_value={
        "in_safe_state": False,
        "emergency_stop_active": False,
        "operational_mode": "normal",
        "mode_session": None,
        "active_overrides": {},
        "interlocks": {},
        "system_state": {},
        "audit_log_entries": 0,
        "emergency_stop_reason": None,
        "active_safety_actions": [],
        "watchdog_timeout": 15.0,
        "time_since_last_kick": 1.0,
    })
    return service


@pytest.fixture
def mock_dependencies(mock_safety_service):
    """Mock dependencies for testing."""
    with patch("backend.api.routers.safety.get_safety_service", return_value=mock_safety_service):
        with patch("backend.api.routers.safety.get_authenticated_admin", return_value={
            "user_id": "admin-123",
            "username": "admin",
            "email": "admin@example.com",
        }):
            with patch("backend.api.routers.safety.get_authenticated_user", return_value={
                "user_id": "user-123",
                "username": "testuser",
                "email": "user@example.com",
            }):
                yield


@pytest.fixture
def client(mock_dependencies):
    """Create test client with mocked dependencies."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    return TestClient(app)


class TestPINEmergencyStopEndpoints:
    """Test PIN-based emergency stop endpoints."""

    def test_pin_emergency_stop_success(self, client, mock_safety_service):
        """Test successful PIN emergency stop."""
        # Mock the service method
        mock_safety_service.emergency_stop_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/safety/pin/emergency-stop",
            json={
                "pin_session_id": "test-session-123",
                "reason": "Test emergency stop",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "emergency_stop_activated"
        assert data["reason"] == "Test emergency stop"
        assert data["triggered_by"] == "admin"
        assert data["authorization_method"] == "pin_session"

        # Verify service method was called
        mock_safety_service.emergency_stop_with_pin.assert_called_once_with(
            pin_session_id="test-session-123",
            reason="Test emergency stop",
            triggered_by="admin",
        )

    def test_pin_emergency_stop_unauthorized(self, client, mock_safety_service):
        """Test emergency stop with invalid PIN."""
        # Mock failed authorization
        mock_safety_service.emergency_stop_with_pin = AsyncMock(return_value=False)

        # Make request
        response = client.post(
            "/api/safety/pin/emergency-stop",
            json={
                "pin_session_id": "invalid-session",
                "reason": "Test emergency stop",
            }
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "PIN authorization failed for emergency stop"

    def test_pin_emergency_reset_success(self, client, mock_safety_service):
        """Test successful PIN emergency stop reset."""
        # Mock the service method
        mock_safety_service.reset_emergency_stop_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/safety/pin/emergency-stop/reset",
            json={
                "pin_session_id": "test-session-123",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["reset_by"] == "admin"
        assert data["authorization_method"] == "pin_session"


class TestInterlockOverrideEndpoints:
    """Test PIN-based interlock override endpoints."""

    def test_pin_override_interlock_success(self, client, mock_safety_service):
        """Test successful interlock override with PIN."""
        # Mock the service method
        mock_safety_service.override_interlock_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/safety/pin/interlocks/override",
            json={
                "pin_session_id": "test-session-123",
                "interlock_name": "slide_room_safety",
                "reason": "Maintenance required",
                "duration_minutes": 60,
            }
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["interlock_name"] == "slide_room_safety"
        assert data["overridden_by"] == "admin"
        assert data["duration_minutes"] == 60

        # Verify service method was called
        mock_safety_service.override_interlock_with_pin.assert_called_once_with(
            pin_session_id="test-session-123",
            interlock_name="slide_room_safety",
            reason="Maintenance required",
            duration_minutes=60,
            overridden_by="admin",
        )

    def test_pin_override_interlock_invalid_duration(self, client):
        """Test interlock override with invalid duration."""
        # Make request with duration too long
        response = client.post(
            "/api/safety/pin/interlocks/override",
            json={
                "pin_session_id": "test-session-123",
                "interlock_name": "test_interlock",
                "reason": "Test",
                "duration_minutes": 500,  # > 480 max
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_clear_interlock_override_success(self, client, mock_safety_service):
        """Test clearing an interlock override."""
        # Mock the service method
        mock_safety_service.clear_interlock_override = MagicMock(return_value=True)

        # Make request
        response = client.post(
            "/api/safety/interlocks/clear-override",
            json={
                "interlock_name": "slide_room_safety",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["interlock_name"] == "slide_room_safety"
        assert data["cleared_by"] == "admin"

    def test_get_active_overrides(self, client, mock_safety_service):
        """Test getting active interlock overrides."""
        # Set up mock data
        test_interlock = SafetyInterlock(
            name="test_interlock",
            feature_name="test_feature",
            interlock_conditions=["vehicle_not_moving"],
        )
        test_interlock._is_overridden = True
        test_interlock._override_by = "admin"
        test_interlock._override_reason = "Testing"
        test_interlock._override_session_id = "session-123"

        mock_safety_service._interlocks = {"test_interlock": test_interlock}
        mock_safety_service.get_safety_status.return_value["active_overrides"] = {
            "test_interlock": datetime.now(UTC).isoformat()
        }

        # Mock get_override_info method
        test_interlock.get_override_info = MagicMock(return_value={
            "is_overridden": True,
            "session_id": "session-123",
            "reason": "Testing",
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
            "overridden_by": "admin",
        })

        # Make request
        response = client.get("/api/safety/interlocks/overrides")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_overrides"] == 1
        assert len(data["overrides"]) == 1
        assert data["overrides"][0]["interlock_name"] == "test_interlock"
        assert data["overrides"][0]["overridden_by"] == "admin"


class TestMaintenanceModeEndpoints:
    """Test PIN-based maintenance mode endpoints."""

    def test_enter_maintenance_mode_success(self, client, mock_safety_service):
        """Test successful maintenance mode entry."""
        # Mock the service method
        mock_safety_service.enter_maintenance_mode_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/safety/pin/maintenance-mode/enter",
            json={
                "pin_session_id": "test-session-123",
                "reason": "Scheduled maintenance",
                "duration_minutes": 120,
            }
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["operational_mode"] == "maintenance"
        assert data["entered_by"] == "admin"
        assert data["duration_minutes"] == 120

    def test_exit_maintenance_mode_success(self, client, mock_safety_service):
        """Test successful maintenance mode exit."""
        # Mock the service method
        mock_safety_service.exit_maintenance_mode_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/safety/pin/maintenance-mode/exit",
            json={
                "pin_session_id": "test-session-123",
            }
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
            "/api/safety/pin/maintenance-mode/enter",
            json={
                "pin_session_id": "test-session-123",
                "reason": "Test",
                "duration_minutes": 10,  # < 15 min
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestDiagnosticModeEndpoints:
    """Test PIN-based diagnostic mode endpoints."""

    def test_enter_diagnostic_mode_success(self, client, mock_safety_service):
        """Test successful diagnostic mode entry."""
        # Mock the service method
        mock_safety_service.enter_diagnostic_mode_with_pin = AsyncMock(return_value=True)

        # Make request
        response = client.post(
            "/api/safety/pin/diagnostic-mode/enter",
            json={
                "pin_session_id": "test-session-123",
                "reason": "System diagnostics",
                "duration_minutes": 60,
            }
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["operational_mode"] == "diagnostic"
        assert data["warning"] == "Safety constraints may be modified during diagnostics"

    def test_get_operational_mode(self, client, mock_safety_service):
        """Test getting current operational mode."""
        # Set up maintenance mode active
        mock_safety_service.get_safety_status.return_value.update({
            "operational_mode": "maintenance",
            "mode_session": {
                "session_id": "session-123",
                "entered_by": "admin",
                "entered_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            },
            "active_overrides": {"test_interlock": "2024-01-01T00:00:00"},
        })

        # Make request
        response = client.get("/api/safety/operational-mode")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["operational_mode"] == "maintenance"
        assert data["is_normal_mode"] is False
        assert "session_details" in data
        assert data["active_overrides_count"] == 1


class TestSafetyEndpointsAuthentication:
    """Test authentication requirements for safety endpoints."""

    def test_unauthenticated_access_denied(self, client):
        """Test that unauthenticated access is denied."""
        # Remove authentication mocks
        with patch("backend.api.routers.safety.get_authenticated_admin", side_effect=Exception("Unauthorized")):
            # Try PIN emergency stop
            response = client.post(
                "/api/safety/pin/emergency-stop",
                json={
                    "pin_session_id": "test-session-123",
                    "reason": "Test",
                }
            )

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_non_admin_access_denied(self, client):
        """Test that non-admin users cannot access admin endpoints."""
        # Mock non-admin user
        with patch("backend.api.routers.safety.get_authenticated_admin", side_effect=Exception("Not admin")):
            # Try maintenance mode entry
            response = client.post(
                "/api/safety/pin/maintenance-mode/enter",
                json={
                    "pin_session_id": "test-session-123",
                    "reason": "Test",
                    "duration_minutes": 60,
                }
            )

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestErrorHandling:
    """Test error handling in safety endpoints."""

    def test_service_error_handling(self, client, mock_safety_service):
        """Test handling of service errors."""
        # Mock service error
        mock_safety_service.emergency_stop_with_pin = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        # Make request
        response = client.post(
            "/api/safety/pin/emergency-stop",
            json={
                "pin_session_id": "test-session-123",
                "reason": "Test",
            }
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database connection failed" in response.json()["detail"]

    def test_invalid_request_format(self, client):
        """Test handling of invalid request format."""
        # Missing required field
        response = client.post(
            "/api/safety/pin/emergency-stop",
            json={
                "reason": "Test",
                # Missing pin_session_id
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Invalid field type
        response = client.post(
            "/api/safety/pin/interlocks/override",
            json={
                "pin_session_id": "test-session-123",
                "interlock_name": "test",
                "reason": "Test",
                "duration_minutes": "sixty",  # Should be int
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
