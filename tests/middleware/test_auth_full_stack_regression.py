"""Full-stack regressions for auth middleware deployment failures."""

from fastapi import FastAPI
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
