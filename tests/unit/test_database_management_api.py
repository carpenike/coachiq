"""Tests for database management API endpoints (``backend/api/routers/database_management.py``).

Rewritten 2026-05-12 (Pattern B). The previous version of this file
referenced a non-existent ``test_client`` fixture, patched a removed
``backend.auth.dependencies.require_admin`` shim, and patched a
non-existent ``backend.core.dependencies.get_service_from_registry``
helper. The router itself is healthy:

    @router.get("/status", response_model=DatabaseStatusResponse)
    async def get_database_status(
        update_service: Annotated[..., Depends(get_database_update_service)],
        _admin: Annotated[dict, Depends(get_authenticated_admin)],
    ) -> DatabaseStatusResponse: ...

so the right shape is to override the actual FastAPI dependencies
(``app.dependency_overrides``) with mocks rather than ``unittest.mock.patch``
of import paths that no longer exist.

Refs: PRs #109 (state.py removal), #111 (entity service disambiguation),
issue #105 (test sweep #2).
"""

from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.api.routers.database_management import (
    get_database_update_service,
    get_migration_safety_validator,
)
from backend.core.dependencies import get_authenticated_admin
from backend.main import app
from backend.services.database_update_service import DatabaseUpdateService
from backend.services.migration_safety_validator import MigrationSafetyValidator


@pytest.fixture
def mock_database_update_service() -> AsyncMock:
    """AsyncMock for ``DatabaseUpdateService`` (only the methods used by the
    router are exercised; ``spec=`` keeps typos honest)."""
    return AsyncMock(spec=DatabaseUpdateService)


@pytest.fixture
def mock_safety_validator() -> AsyncMock:
    """AsyncMock for ``MigrationSafetyValidator``."""
    return AsyncMock(spec=MigrationSafetyValidator)


@pytest.fixture
def admin_client(
    client: TestClient,
    mock_database_update_service: AsyncMock,
    mock_safety_validator: AsyncMock,
) -> Generator[TestClient, None, None]:
    """``TestClient`` with the database-management router's three
    dependencies overridden: the update service, the safety validator,
    and the admin-auth gate (always succeeds with a fake admin user).
    """
    app.dependency_overrides[get_database_update_service] = (  # type: ignore[attr-defined]
        lambda: mock_database_update_service
    )
    app.dependency_overrides[get_migration_safety_validator] = (  # type: ignore[attr-defined]
        lambda: mock_safety_validator
    )
    app.dependency_overrides[get_authenticated_admin] = (  # type: ignore[attr-defined]
        lambda: {"username": "test-admin", "role": "admin"}
    )
    try:
        yield client
    finally:
        for dep in (
            get_database_update_service,
            get_migration_safety_validator,
            get_authenticated_admin,
        ):
            app.dependency_overrides.pop(dep, None)  # type: ignore[attr-defined]


class TestDatabaseManagementAPI:
    """Test suite for ``/api/database/*`` endpoints."""

    def test_get_database_status(
        self,
        admin_client: TestClient,
        mock_database_update_service: AsyncMock,
    ) -> None:
        """``GET /api/database/status`` returns the migration status payload."""
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

        response = admin_client.get("/api/database/status")

        assert response.status_code == 200
        data = response.json()
        assert data["current_version"] == "abc123"
        assert data["target_version"] == "def456"
        assert data["needs_update"] is True
        assert len(data["pending_migrations"]) == 1

    def test_start_migration_no_confirmation(
        self,
        admin_client: TestClient,
    ) -> None:
        """``POST /api/database/migrate`` rejects requests without ``confirm=True``.

        The project ships a custom ``http_exception_handler`` (see
        ``backend/core/exception_handlers.py``) that wraps errors as
        ``{"error": {"code": ..., "message": ...}}`` rather than the
        FastAPI default ``{"detail": ...}`` shape, so we assert against
        the wrapped envelope.
        """
        response = admin_client.post("/api/database/migrate", json={"confirm": False})
        assert response.status_code == 400
        assert "confirmation required" in response.json()["error"]["message"].lower()

    def test_start_migration_success(
        self,
        admin_client: TestClient,
        mock_database_update_service: AsyncMock,
    ) -> None:
        """A confirmed migration request returns the job descriptor."""
        mock_database_update_service.start_migration.return_value = {
            "success": True,
            "job_id": "test-job-123",
            "message": "Migration started",
            "error": None,
            "safety_issues": None,
            "hint": None,
        }

        response = admin_client.post("/api/database/migrate", json={"confirm": True})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == "test-job-123"
        assert data["message"] == "Migration started"

    def test_start_migration_not_safe(
        self,
        admin_client: TestClient,
        mock_database_update_service: AsyncMock,
    ) -> None:
        """An unsafe migration is reported with structured failure data."""
        mock_database_update_service.start_migration.return_value = {
            "success": False,
            "job_id": None,
            "message": None,
            "error": "System not in safe state for migration",
            "safety_issues": ["Vehicle is in motion"],
            "hint": "Use force=True to override (not recommended)",
        }

        response = admin_client.post("/api/database/migrate", json={"confirm": True})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "System not in safe state for migration"
        assert "Vehicle is in motion" in data["safety_issues"]

    def test_get_migration_progress(
        self,
        admin_client: TestClient,
        mock_database_update_service: AsyncMock,
    ) -> None:
        """``GET /api/database/migrate/{job_id}/status`` returns the job state."""
        job_status = {
            "id": "test-job-123",
            "status": "migrating",
            "progress": 50,
            "started_at": "2024-01-01T00:00:00",
        }
        mock_database_update_service.get_job_status.return_value = job_status

        response = admin_client.get("/api/database/migrate/test-job-123/status")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-job-123"
        assert data["status"] == "migrating"
        assert data["progress"] == 50

    def test_get_migration_progress_not_found(
        self,
        admin_client: TestClient,
        mock_database_update_service: AsyncMock,
    ) -> None:
        """A missing job ID returns 404."""
        mock_database_update_service.get_job_status.return_value = None

        response = admin_client.get("/api/database/migrate/non-existent/status")

        assert response.status_code == 404
        # See test_start_migration_no_confirmation for the wrapped error shape.
        assert "not found" in response.json()["error"]["message"].lower()

    def test_get_migration_history(
        self,
        admin_client: TestClient,
        mock_database_update_service: AsyncMock,
    ) -> None:
        """``GET /api/database/history?limit=N`` proxies through to the service."""
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

        response = admin_client.get("/api/database/history?limit=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["from_version"] == "abc123"
        assert data[0]["to_version"] == "def456"
        assert data[0]["status"] == "success"
        # Verify the limit query param was forwarded.
        mock_database_update_service.get_migration_history.assert_awaited_once_with(limit=5)

    def test_check_migration_safety(
        self,
        admin_client: TestClient,
        mock_safety_validator: AsyncMock,
    ) -> None:
        """``GET /api/database/safety-check`` returns the safety report."""
        safety_report = {
            "is_safe": True,
            "blocking_reasons": [],
            "system_state": {"vehicle_speed": 0, "parking_brake": True},
            "interlocks": {"all_satisfied": True, "violations": []},
            "recommendations": [],
        }
        mock_safety_validator.get_safety_report.return_value = safety_report

        response = admin_client.get("/api/database/safety-check")

        assert response.status_code == 200
        data = response.json()
        assert data["is_safe"] is True
        assert data["blocking_reasons"] == []
        assert data["system_state"]["vehicle_speed"] == 0

    def test_unauthorized_access(
        self,
        client: TestClient,
        mock_database_update_service: AsyncMock,
        mock_safety_validator: AsyncMock,
    ) -> None:
        """All endpoints require an admin user.

        We override the service deps but NOT ``get_authenticated_admin``, so
        the production auth chain runs against the unauthenticated TestClient
        and must reject. We accept anything in the auth-rejection family
        (401/403/422 from missing-bearer-token validation) but explicitly
        reject success codes.
        """
        app.dependency_overrides[get_database_update_service] = (  # type: ignore[attr-defined]
            lambda: mock_database_update_service
        )
        app.dependency_overrides[get_migration_safety_validator] = (  # type: ignore[attr-defined]
            lambda: mock_safety_validator
        )
        try:
            endpoints = [
                ("GET", "/api/database/status"),
                ("POST", "/api/database/migrate"),
                ("GET", "/api/database/migrate/test-job/status"),
                ("GET", "/api/database/history"),
                ("GET", "/api/database/safety-check"),
            ]
            for method, endpoint in endpoints:
                if method == "GET":
                    response = client.get(endpoint)
                else:
                    response = client.post(endpoint, json={"confirm": True})
                # Auth-rejection family. 422 covers missing required JSON body
                # combined with auth dependency ordering; we accept it but
                # forbid 2xx.
                assert response.status_code in (401, 403, 422), (
                    f"{method} {endpoint} returned {response.status_code} without "
                    "auth — admin gate may be missing"
                )
                assert response.status_code != 200, (
                    f"{method} {endpoint} unexpectedly succeeded without auth"
                )
        finally:
            for dep in (
                get_database_update_service,
                get_migration_safety_validator,
            ):
                app.dependency_overrides.pop(dep, None)  # type: ignore[attr-defined]
