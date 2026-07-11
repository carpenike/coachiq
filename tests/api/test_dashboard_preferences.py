"""Tests for authenticated dashboard preference endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.domains import dashboard
from backend.core.dependencies import get_authenticated_user


def _client(service: AsyncMock) -> TestClient:
    """Build an isolated dashboard router client with authenticated dependencies."""
    app = FastAPI()
    app.include_router(dashboard.create_dashboard_router(), prefix="/api/v1/dashboard")
    app.dependency_overrides[dashboard.get_dashboard_service] = lambda: service
    app.dependency_overrides[get_authenticated_user] = lambda: {
        "user_id": "user-123",
        "role": "user",
        "authenticated": True,
    }
    return TestClient(app)


def test_get_preferences_returns_null_before_first_sync() -> None:
    """A new authenticated user can distinguish server defaults from saved preferences."""
    service = AsyncMock()
    service.get_dashboard_config.return_value = {
        "preferences": {"theme": "auto"},
        "updated_at": datetime(2026, 7, 8, tzinfo=UTC).isoformat(),
    }

    response = _client(service).get("/api/v1/dashboard/preferences")

    assert response.status_code == 200
    assert response.json()["home"] is None
    service.get_dashboard_config.assert_awaited_once_with("user-123")


def test_put_preferences_saves_typed_home_configuration() -> None:
    """Home customization is validated and saved under the authenticated user identity."""
    service = AsyncMock()
    saved_home = {
        "favoriteEntityIds": ["light-1"],
        "sectionOrder": ["zones", "alerts", "scenes", "power"],
        "hiddenSections": ["power"],
    }
    service.update_dashboard_preferences.return_value = {
        "preferences": {"home": saved_home},
        "updated_at": datetime(2026, 7, 8, tzinfo=UTC).isoformat(),
    }

    response = _client(service).put(
        "/api/v1/dashboard/preferences",
        json={"home": saved_home},
    )

    assert response.status_code == 200
    assert response.json()["home"] == saved_home
    service.update_dashboard_preferences.assert_awaited_once_with("user-123", {"home": saved_home})
