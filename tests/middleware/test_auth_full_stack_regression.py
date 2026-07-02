"""Full-stack regressions for auth middleware deployment failures."""

import importlib
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Route

import backend.api.routers.mcp_oauth as mcp_oauth_router
import backend.services.entities.entity_initialization_service as initialization_module
from backend.api.domains import entities as entities_mod
from backend.api.routers import config as config_router_mod
from backend.api.routers import dashboard as dashboard_mod
from backend.api.routers.mcp_oauth import get_mcp_oauth_repository
from backend.api.routers.mcp_oauth import router as mcp_oauth_router_obj
from backend.core.config import McpSettings, ServerSettings, Settings
from backend.core.dependencies import get_entity_state_repository
from backend.core.exception_handlers import register_exception_handlers
from backend.core.performance import PerformanceMonitor
from backend.middleware.auth import AuthenticationMiddleware
from backend.middleware.csrf_protection import CSRFProtectionMiddleware
from backend.services.auth.manager import AuthMode, InvalidTokenError
from backend.services.auth.mcp_oauth_guard import mcp_www_authenticate_header
from backend.services.entities.entity_service import EntityService
from backend.services.system.dashboard_service import DashboardService
from tests._helpers.settings import isolated_env

if TYPE_CHECKING:
    from backend.repositories.entity_repository import EntityRuntimeStateRepository

pytestmark = pytest.mark.auth


class _AuthManager:
    """Fake enabled auth manager for full ASGI middleware tests."""

    auth_mode = AuthMode.SINGLE_USER

    def validate_token(self, _token: str):
        """Reject every token so protected route auth paths are deterministic."""
        raise InvalidTokenError("invalid token")


class _McpRepository:
    """Fake MCP repository that never validates a token."""

    async def validate_access_token(self, _token: str):
        """Reject all MCP tokens."""
        return


class _SpaAuthManager:
    """Fake auth manager that accepts one bearer token for SPA middleware tests."""

    auth_mode = AuthMode.SINGLE_USER

    def validate_token(self, credential: str):
        """Accept the known good token and reject everything else."""
        if credential == "good":
            return {"sub": "user", "username": "user", "role": "admin"}
        raise InvalidTokenError("invalid token")


class _EntityStateRepositoryFake:
    """Seeded async entity repository fake matching the wired repository interface."""

    def __init__(self, states: dict[str, dict[str, Any]]) -> None:
        self._states = states

    async def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Return all seeded states."""
        return dict(self._states)

    async def get_entity_state(self, entity_id: str) -> dict[str, Any] | None:
        """Return one seeded state."""
        return self._states.get(entity_id)


class _DiagnosticsRepositoryFake:
    """Diagnostics fake for EntityService construction."""

    def get_unmapped_entries(self) -> dict[str, Any]:
        """Return no unmapped entries."""
        return {}

    def get_unknown_pgns(self) -> dict[str, Any]:
        """Return no unknown PGNs."""
        return {}


class _RVCConfigFacadeFake:
    """Config facade fake for application status endpoint."""

    async def get_config_status(self) -> dict[str, Any]:
        """Return loaded configuration status."""
        return {
            "spec_loaded": True,
            "spec_path": "config/rvc.json",
            "mapping_loaded": True,
            "mapping_path": "config/coach_mapping.default.yml",
        }


class _SpecMeta:
    """Minimal spec metadata object for live-app entity initialization."""

    def dict(self) -> dict[str, Any]:
        """Return empty spec metadata."""
        return {}


def _seeded_rvc_config() -> Any:
    """Return a minimal coach mapping payload for live-app startup."""
    entity_map = {
        "light": {
            "entity_id": "light_1",
            "device_type": "light",
            "suggested_area": "Kitchen",
            "friendly_name": "Kitchen Light",
            "capabilities": ["brightness"],
            "groups": ["main"],
        },
        "tank": {
            "entity_id": "tank_1",
            "device_type": "tank",
            "suggested_area": "Bay",
            "friendly_name": "Fresh Tank",
            "capabilities": ["level"],
            "groups": [],
        },
    }
    return type(
        "SeededRVCConfig",
        (),
        {
            "dgn_dict": {},
            "spec_meta": _SpecMeta(),
            "mapping_dict": {},
            "entity_map": entity_map,
            "entity_ids": list(entity_map),
            "inst_map": {},
            "unique_instances": [],
            "pgn_hex_to_name_map": {},
            "dgn_pairs": [],
            "coach_info": None,
        },
    )()


def _settings() -> Settings:
    """Build settings matching the deployed MCP path and public origin."""
    return Settings(
        testing=True,
        mcp=McpSettings(as_enabled=True, path="/api/mcp"),
        server=ServerSettings(public_origin="https://iq.holtel.io"),
    )


def _client() -> TestClient:
    """Build an app that exercises the real ASGI middleware stack."""
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(AuthenticationMiddleware, auth_manager=_AuthManager())
    app.add_middleware(CSRFProtectionMiddleware, secret_key="test-secret", secure_cookie=False)

    @app.get("/protected")
    async def protected_route() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/auth/oidc/login")
    async def oidc_login() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(mcp_oauth_router_obj)
    app.dependency_overrides[get_mcp_oauth_repository] = lambda: _McpRepository()
    mcp_oauth_router.get_settings = _settings
    return TestClient(app)


def _spa_client(*, mounted: bool = True) -> TestClient:
    """Build an auth-enabled app with a minimal SPA fallback route."""
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(AuthenticationMiddleware, auth_manager=_SpaAuthManager())

    if mounted:
        app.state.spa_static_dir = "mounted"
        app.state.spa_reserved_route_families = frozenset(
            {
                "/api",
                "/ws",
                "/oauth",
                "/.well-known",
                "/docs",
                "/redoc",
                "/openapi.json",
                "/health",
                "/healthz",
                "/readyz",
                "/startupz",
                "/metrics",
            }
        )

    @app.get("/api/v1/protected")
    async def protected_route() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/{path:path}")
    async def spa_fallback(path: str) -> HTMLResponse:
        return HTMLResponse(
            '<!doctype html><html><head><title>CoachIQ SPA</title></head><body id="spa-root"></body></html>'
        )

    return TestClient(app)


def _seeded_entity_states() -> dict[str, dict[str, Any]]:
    """Return known entity states for authenticated data endpoint regressions."""
    now = time.time()
    return {
        "light_1": {
            "entity_id": "light_1",
            "friendly_name": "Kitchen Light",
            "name": "Kitchen Light",
            "device_type": "light",
            "protocol": "rvc",
            "state": "on",
            "raw": {"operating_status": 200},
            "suggested_area": "Kitchen",
            "capabilities": ["brightness"],
            "groups": ["main"],
            "timestamp": now,
            "last_updated": "2026-07-02T14:00:00Z",
            "available": True,
        },
        "tank_1": {
            "entity_id": "tank_1",
            "friendly_name": "Fresh Tank",
            "name": "Fresh Tank",
            "device_type": "tank",
            "protocol": "rvc",
            "state": "unknown",
            "raw": {"level": 50},
            "suggested_area": "Bay",
            "capabilities": ["level"],
            "groups": [],
            "timestamp": now,
            "last_updated": "2026-07-02T14:00:00Z",
            "available": True,
        },
    }


def _authenticated_data_client() -> TestClient:
    """Build an enabled-auth app using real routers and seeded services."""
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(AuthenticationMiddleware, auth_manager=_SpaAuthManager())

    entity_repository = cast(
        "EntityRuntimeStateRepository",
        _EntityStateRepositoryFake(_seeded_entity_states()),
    )
    entity_service = EntityService(
        websocket_manager=cast("Any", None),
        entity_state_repository=entity_repository,
        rvc_config_repository=cast("Any", None),
        diagnostics_repository=cast("Any", _DiagnosticsRepositoryFake()),
    )
    dashboard_service = DashboardService(
        dashboard_repository=cast("Any", None),
        entity_repository=entity_repository,
        performance_monitor=PerformanceMonitor(),
    )

    app.include_router(entities_mod.create_entities_router(), prefix="/api/v1/entities")
    app.include_router(dashboard_mod.router)
    app.include_router(config_router_mod.router)
    app.dependency_overrides[entities_mod.get_entity_service] = lambda: entity_service
    app.dependency_overrides[dashboard_mod.get_dashboard_service] = lambda: dashboard_service
    app.dependency_overrides[get_entity_state_repository] = lambda: entity_repository
    app.dependency_overrides[config_router_mod.get_rvc_config_facade] = (
        lambda: _RVCConfigFacadeFake()
    )
    app.dependency_overrides[config_router_mod.get_can_tracking_repository] = lambda: object()
    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    """Return a valid bearer header for enabled-auth data endpoint tests."""
    return {"Accept": "application/json", "Authorization": "Bearer good"}


def _live_app_smoke_env(tmp_path: Path) -> dict[str, str]:
    """Return deterministic environment overrides for live-app auth smoke tests."""
    data_dir = tmp_path / "data"
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    return {
        "COACHIQ_TESTING": "true",
        "COACHIQ_ENVIRONMENT": "development",
        "COACHIQ_STATIC_DIR": str(static_dir),
        "COACHIQ_PERSISTENCE__DATA_DIR": str(data_dir),
        "COACHIQ_AUTH__ENABLED": "true",
        "COACHIQ_AUTH__SECRET_KEY": "test-secret-key-that-is-long-enough-for-hof-070",
        "COACHIQ_AUTH__ADMIN_USERNAME": "admin",
        "COACHIQ_AUTH__ADMIN_PASSWORD": "test-admin-password",
        "COACHIQ_AUTH__ENABLE_MAGIC_LINKS": "false",
        "COACHIQ_AUTH__OIDC_ENABLED": "false",
        "COACHIQ_AUTH__ENABLE_MFA": "false",
        "COACHIQ_AUTH__REQUIRE_MFA_FOR_ADMIN": "false",
        "COACHIQ_SECURITY__RATE_LIMIT_ENABLED": "false",
        "COACHIQ_CAN__INTERFACES": "",
        "COACHIQ_CAN__INTERFACE_MAPPINGS": "",
        "COACHIQ_FEATURES__ENABLE_NOTIFICATIONS": "false",
        "COACHIQ_FEATURES__ENABLE_VECTOR_SEARCH": "false",
        "COACHIQ_NOTIFICATIONS__ENABLED": "false",
    }


def _reset_live_app_globals() -> None:
    """Reset process globals touched by the live FastAPI app lifespan."""
    from backend.core import dependencies
    from backend.core.config import get_settings

    dependencies._composition_root = None
    get_settings.cache_clear()


def _requires_value(field: Any) -> bool:
    """Return whether a FastAPI dependant field is required."""
    is_required = getattr(field, "is_required", None)
    if callable(is_required):
        return bool(is_required())
    return bool(getattr(field, "required", False))


def _route_exclusion_reason(route: Route) -> str | None:
    """Return why a live route is outside the parameterless GET smoke scope."""
    methods = getattr(route, "methods", set()) or set()
    if "GET" not in methods:
        return "not-get"

    path = getattr(route, "path", "")
    if "{" in path:
        return "path-params"

    if isinstance(route, APIRoute):
        required_query_params = [
            field.name for field in route.dependant.query_params if _requires_value(field)
        ]
        if required_query_params:
            return f"required-query:{','.join(required_query_params)}"
        if route.body_field is not None:
            return "request-body"

    return None


def _parameterless_get_paths(app: FastAPI) -> tuple[list[str], list[str]]:
    """Enumerate covered and excluded GET routes from the live app route table."""
    covered: list[str] = []
    excluded: list[str] = []
    for route in app.routes:
        if not isinstance(route, Route):
            continue

        reason = _route_exclusion_reason(route)
        path = getattr(route, "path", "")
        if reason is None:
            covered.append(path)
        elif reason != "not-get":
            excluded.append(f"{path} ({reason})")

    return sorted(set(covered)), sorted(set(excluded))


@pytest.mark.integration
@pytest.mark.smoke
def test_live_authenticated_parameterless_get_routes_do_not_500(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Live app authed GET route sweep catches wiring/interface 500s."""
    _reset_live_app_globals()
    monkeypatch.setattr(initialization_module, "get_default_paths", lambda: ("spec", "mapping"))
    monkeypatch.setattr(
        initialization_module,
        "load_config_data_v2",
        lambda *_args: _seeded_rvc_config(),
    )

    with patch.dict(os.environ, isolated_env(_live_app_smoke_env(tmp_path)), clear=True):
        _reset_live_app_globals()
        main_module = importlib.import_module("backend.main")
        main_module = importlib.reload(main_module)
        covered_paths, excluded_routes = _parameterless_get_paths(main_module.app)

        expected_paths = {
            "/api/v1/entities",
            "/api/dashboard/summary",
            "/api/dashboard/analytics",
            "/api/status/application",
            "/api/config/settings",
        }
        assert expected_paths.issubset(set(covered_paths))

        failures: list[str] = []
        statuses: dict[str, int] = {}
        with TestClient(main_module.app) as client:
            from backend.core.dependencies import get_auth_manager

            token = get_auth_manager().generate_token(
                "admin-user",
                username="admin",
                additional_claims={"role": "admin", "user_id": "admin-user"},
            )
            headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}

            for path in covered_paths:
                try:
                    response = client.get(path, headers=headers)
                except Exception as exc:
                    failures.append(f"{path} -> {type(exc).__name__}: {exc}")
                    continue

                statuses[path] = response.status_code
                if response.status_code == 500:
                    failures.append(f"{path} -> HTTP {response.status_code}: {response.text[:500]}")

        try:
            assert not failures, (
                "500ing authenticated parameterless GET routes:\n"
                + "\n".join(failures)
                + "\n\nCovered routes:\n"
                + "\n".join(covered_paths)
                + "\n\nExcluded routes:\n"
                + "\n".join(excluded_routes)
            )
            assert statuses["/api/v1/entities"] != 500
            assert statuses["/api/dashboard/summary"] != 500
            assert statuses["/api/dashboard/analytics"] != 500
            assert statuses["/api/status/application"] != 500
            assert statuses["/api/config/settings"] != 500
        finally:
            _reset_live_app_globals()


def test_unauthenticated_protected_route_returns_401_not_500() -> None:
    """Auth middleware returns 401 responses instead of raising into a 500."""
    response = _client().get("/protected")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "Authentication required"
    assert response.json()["error"]["message"] == "Authentication required"


def test_exempt_paths_are_reachable_without_auth_500() -> None:
    """OIDC and OAuth exempt paths bypass auth middleware failures."""
    client = _client()

    oidc_response = client.get("/api/v1/auth/oidc/login")
    metadata_response = client.get("/.well-known/oauth-authorization-server")
    dcr_response = client.post("/oauth/register", json={"redirect_uris": []})

    assert oidc_response.status_code == 200
    assert metadata_response.status_code == 200
    assert dcr_response.status_code in {400, 422}
    assert dcr_response.status_code != 500


def test_mcp_resource_returns_bearer_challenge_not_csrf_or_500() -> None:
    """MCP resource uses bearer-token auth and is CSRF-exempt."""
    response = _client().post("/api/mcp")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == mcp_www_authenticate_header(_settings())
    assert "resource_metadata" in response.headers["www-authenticate"]


@pytest.mark.parametrize("path", ["/dashboard", "/auth/oidc/callback"])
def test_spa_document_navigation_bypasses_auth_when_spa_is_mounted(path: str) -> None:
    """Mounted SPA document navigations reach the fallback without a bearer token."""
    response = _spa_client().get(path, headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "CoachIQ SPA" in response.text


def test_spa_json_fetch_does_not_bypass_auth() -> None:
    """Non-document requests to SPA paths still require authentication."""
    response = _spa_client().get("/dashboard", headers={"Accept": "application/json"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["message"] == "Authentication required"


@pytest.mark.parametrize("accept", ["text/html", "application/json"])
def test_protected_api_without_bearer_does_not_bypass_auth(accept: str) -> None:
    """Reserved API route families never use the SPA document exemption."""
    response = _spa_client().get("/api/v1/protected", headers={"Accept": accept})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["message"] == "Authentication required"


def test_protected_api_with_valid_bearer_still_reaches_route() -> None:
    """Bearer authentication still authorizes protected API routes."""
    response = _spa_client().get(
        "/api/v1/protected",
        headers={"Accept": "application/json", "Authorization": "Bearer good"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_unmounted_spa_keeps_current_auth_gating() -> None:
    """Without HOF-056 SPA state, document navigations remain auth-gated."""
    response = _spa_client(mounted=False).get("/dashboard", headers={"Accept": "text/html"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["message"] == "Authentication required"


def test_authenticated_entities_endpoint_returns_seeded_values() -> None:
    """Authenticated /api/v1/entities returns seeded entities instead of 500."""
    response = _authenticated_data_client().get("/api/v1/entities", headers=_auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 2
    assert payload["page"] == 1
    assert [entity["entity_id"] for entity in payload["entities"]] == ["light_1", "tank_1"]
    assert payload["entities"][0]["name"] == "Kitchen Light"
    assert payload["entities"][0]["device_type"] == "light"
    assert payload["entities"][0]["area"] == "Kitchen"


def test_authenticated_dashboard_summary_returns_seeded_counts() -> None:
    """Authenticated dashboard summary aggregates seeded entity states correctly."""
    response = _authenticated_data_client().get(
        "/api/dashboard/summary",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["entities"]["total_entities"] == 2
    assert payload["entities"]["online_entities"] == 2
    assert payload["entities"]["active_entities"] == 1
    assert payload["entities"]["device_type_counts"] == {"light": 1, "tank": 1}
    assert payload["entities"]["area_counts"] == {"Kitchen": 1, "Bay": 1}
    assert payload["quick_stats"]["entities_online_ratio"] == 1.0


def test_authenticated_dashboard_analytics_returns_seeded_health() -> None:
    """Authenticated dashboard analytics uses seeded entity health, not a 500."""
    response = _authenticated_data_client().get(
        "/api/dashboard/analytics",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["alerts"] == []
    assert payload["health_checks"]["entity_manager"] is True
    assert payload["recommendations"] == []


def test_authenticated_application_status_returns_seeded_entity_count() -> None:
    """Authenticated application status counts async repository states correctly."""
    response = _authenticated_data_client().get(
        "/api/status/application",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["known_entity_count"] == 2
    assert payload["active_entity_state_count"] == 2
    assert payload["can_listeners_status"] == "likely_active"
