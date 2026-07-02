"""Full-stack regressions for auth middleware deployment failures."""

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

import backend.api.routers.mcp_oauth as mcp_oauth_router
from backend.api.routers.mcp_oauth import get_mcp_oauth_repository
from backend.api.routers.mcp_oauth import router as mcp_oauth_router_obj
from backend.core.config import McpSettings, ServerSettings, Settings
from backend.core.exception_handlers import register_exception_handlers
from backend.middleware.auth import AuthenticationMiddleware
from backend.middleware.csrf_protection import CSRFProtectionMiddleware
from backend.services.auth.manager import AuthMode, InvalidTokenError
from backend.services.auth.mcp_oauth_guard import mcp_www_authenticate_header

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
