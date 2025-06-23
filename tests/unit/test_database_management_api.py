"""Tests for database management API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.services.database_update_service import DatabaseUpdateService
from backend.services.migration_safety_validator import MigrationSafetyValidator


@pytest.fixture
def mock_database_update_service():
    """Create mock DatabaseUpdateService."""
    service = AsyncMock(spec=DatabaseUpdateService)
    return service


@pytest.fixture
def mock_safety_validator():
    """Create mock MigrationSafetyValidator."""
    validator = AsyncMock(spec=MigrationSafetyValidator)
    return validator


@pytest.fixture
def mock_admin_user():
    """Mock admin authentication."""
    return True


class TestDatabaseManagementAPI:
    """Test suite for database management API endpoints."""

    @pytest.mark.asyncio
    async def test_get_database_status(
        self, test_client: TestClient, mock_database_update_service, mock_admin_user
    ):
        """Test GET /api/database/status endpoint."""
        # Setup mock response
        expected_status = {
            "current_version": "abc123",
            "target_version": "def456",
            "needs_update": True,
            "pending_migrations": [{"version": "def456", "description": "Add tables"}],
            "is_safe_to_migrate": True,
            "safety_issues": [],
            "latest_backup": {"path": "/backups/test.db"},
            "migration_in_progress": False,
            "current_job_id": None,
        }
        mock_database_update_service.get_migration_status.return_value = expected_status

        with patch(
            "backend.core.dependencies.get_service_from_registry",
            return_value=mock_database_update_service,
        ):
            with patch("backend.auth.dependencies.require_admin", return_value=mock_admin_user):
                response = test_client.get("/api/database/status")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["current_version"] == "abc123"
        assert data["target_version"] == "def456"
        assert data["needs_update"] is True
        assert len(data["pending_migrations"]) == 1

    @pytest.mark.asyncio
    async def test_start_migration_no_confirmation(
        self, test_client: TestClient, mock_database_update_service, mock_admin_user
    ):
        """Test POST /api/database/migrate without confirmation."""
        with patch(
            "backend.core.dependencies.get_service_from_registry",
            return_value=mock_database_update_service,
        ):
            with patch("backend.auth.dependencies.require_admin", return_value=mock_admin_user):
                response = test_client.post(
                    "/api/database/migrate",
                    json={"confirm": False},
                )

        # Assert
        assert response.status_code == 400
        assert "confirmation required" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_start_migration_success(
        self, test_client: TestClient, mock_database_update_service, mock_admin_user
    ):
        """Test successful migration start."""
        # Setup mock response
        mock_database_update_service.start_migration.return_value = {
            "success": True,
            "job_id": "test-job-123",
            "message": "Migration started",
        }

        with patch(
            "backend.core.dependencies.get_service_from_registry",
            return_value=mock_database_update_service,
        ):
            with patch("backend.auth.dependencies.require_admin", return_value=mock_admin_user):
                response = test_client.post(
                    "/api/database/migrate",
                    json={"confirm": True},
                )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == "test-job-123"
        assert data["message"] == "Migration started"

    @pytest.mark.asyncio
    async def test_start_migration_not_safe(
        self, test_client: TestClient, mock_database_update_service, mock_admin_user
    ):
        """Test migration start when system is not safe."""
        # Setup mock response
        mock_database_update_service.start_migration.return_value = {
            "success": False,
            "error": "System not in safe state for migration",
            "safety_issues": ["Vehicle is in motion"],
            "hint": "Use force=True to override (not recommended)",
        }

        with patch(
            "backend.core.dependencies.get_service_from_registry",
            return_value=mock_database_update_service,
        ):
            with patch("backend.auth.dependencies.require_admin", return_value=mock_admin_user):
                response = test_client.post(
                    "/api/database/migrate",
                    json={"confirm": True},
                )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "System not in safe state for migration"
        assert "Vehicle is in motion" in data["safety_issues"]

    @pytest.mark.asyncio
    async def test_get_migration_progress(
        self, test_client: TestClient, mock_database_update_service, mock_admin_user
    ):
        """Test GET /api/database/migrate/{job_id}/status endpoint."""
        # Setup mock response
        job_status = {
            "id": "test-job-123",
            "status": "migrating",
            "progress": 50,
            "started_at": "2024-01-01T00:00:00",
        }
        mock_database_update_service.get_job_status.return_value = job_status

        with patch(
            "backend.core.dependencies.get_service_from_registry",
            return_value=mock_database_update_service,
        ):
            with patch("backend.auth.dependencies.require_admin", return_value=mock_admin_user):
                response = test_client.get("/api/database/migrate/test-job-123/status")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-job-123"
        assert data["status"] == "migrating"
        assert data["progress"] == 50

    @pytest.mark.asyncio
    async def test_get_migration_progress_not_found(
        self, test_client: TestClient, mock_database_update_service, mock_admin_user
    ):
        """Test getting progress for non-existent job."""
        mock_database_update_service.get_job_status.return_value = None

        with patch(
            "backend.core.dependencies.get_service_from_registry",
            return_value=mock_database_update_service,
        ):
            with patch("backend.auth.dependencies.require_admin", return_value=mock_admin_user):
                response = test_client.get("/api/database/migrate/non-existent/status")

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_migration_history(
        self, test_client: TestClient, mock_database_update_service, mock_admin_user
    ):
        """Test GET /api/database/history endpoint."""
        # Setup mock response
        history = [
            {
                "id": 1,
                "from_version": "abc123",
                "to_version": "def456",
                "status": "success",
                "duration_ms": 5000,
                "executed_at": "2024-01-01T00:00:00",
            }
        ]
        mock_database_update_service.get_migration_history.return_value = history

        with patch(
            "backend.core.dependencies.get_service_from_registry",
            return_value=mock_database_update_service,
        ):
            with patch("backend.auth.dependencies.require_admin", return_value=mock_admin_user):
                response = test_client.get("/api/database/history?limit=5")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["from_version"] == "abc123"
        assert data[0]["to_version"] == "def456"
        assert data[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_check_migration_safety(
        self, test_client: TestClient, mock_safety_validator, mock_admin_user
    ):
        """Test GET /api/database/safety-check endpoint."""
        # Setup mock response
        safety_report = {
            "is_safe": True,
            "blocking_reasons": [],
            "system_state": {"vehicle_speed": 0, "parking_brake": True},
            "interlocks": {"all_satisfied": True, "violations": []},
            "recommendations": [],
        }
        mock_safety_validator.get_safety_report.return_value = safety_report

        with patch(
            "backend.core.dependencies.get_service_from_registry",
            return_value=mock_safety_validator,
        ):
            with patch("backend.auth.dependencies.require_admin", return_value=mock_admin_user):
                response = test_client.get("/api/database/safety-check")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["is_safe"] is True
        assert data["blocking_reasons"] == []
        assert data["system_state"]["vehicle_speed"] == 0

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, test_client: TestClient):
        """Test endpoints require admin authentication."""
        # Mock non-admin user
        with patch(
            "backend.auth.dependencies.require_admin", side_effect=Exception("Unauthorized")
        ):
            # Test each endpoint
            endpoints = [
                ("GET", "/api/database/status"),
                ("POST", "/api/database/migrate"),
                ("GET", "/api/database/migrate/test-job/status"),
                ("GET", "/api/database/history"),
                ("GET", "/api/database/safety-check"),
            ]

            for method, endpoint in endpoints:
                if method == "GET":
                    response = test_client.get(endpoint)
                else:
                    response = test_client.post(endpoint, json={})

                # All should fail with unauthorized
                assert response.status_code in [401, 403, 500]
