"""Tests for MCP OAuth token endpoint."""

import base64
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.routers.mcp_oauth as mcp_oauth_router
from backend.api.routers.mcp_oauth import get_mcp_oauth_repository, router
from backend.services.auth.mcp_oauth_service import pkce_s256_challenge
from backend.services.auth.mcp_oauth_security import McpOAuthRateLimiter


class _Repository:
    """Fake repository for token endpoint tests."""

    def __init__(self) -> None:
        self.consumed_codes: set[str] = set()
        self.secret = "client-secret"
        self.minted = []

    async def get_client(self, client_id: str):
        """Return a fake DCR client."""
        if client_id != "client-1":
            return None
        return SimpleNamespace(client_id="client-1", client_secret_hash="hashed-secret")

    def verify_client_secret(self, _client, presented_secret: str | None) -> bool:
        """Verify the fake client secret."""
        return presented_secret == self.secret

    async def consume_authorization_code(self, code: str):
        """Consume a fake single-use authorization code."""
        if code != "as-auth-code" or code in self.consumed_codes:
            return None
        self.consumed_codes.add(code)
        return SimpleNamespace(
            client_id="client-1",
            redirect_uri="https://claude.ai/callback",
            user_id="local-user",
            code_challenge=pkce_s256_challenge("client-verifier"),
        )

    async def mint_access_token(self, **kwargs):
        """Mint a fake opaque token."""
        self.minted.append(kwargs)
        return SimpleNamespace(token_hash="hashed-token"), "ciqpat_token"


def _client_for(repository: _Repository) -> TestClient:
    """Create a test app with the MCP OAuth router mounted."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_mcp_oauth_repository] = lambda: repository
    mcp_oauth_router._token_rate_limiter = McpOAuthRateLimiter(limit=60, window_seconds=3600)
    return TestClient(app)


def _basic_header(client_id: str, secret: str) -> str:
    """Return a Basic auth header value."""
    encoded = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    return f"Basic {encoded}"


def test_token_endpoint_accepts_confidential_basic_client() -> None:
    """Token endpoint accepts HTTP Basic client credentials."""
    repository = _Repository()
    client = _client_for(repository)

    response = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": "as-auth-code",
            "redirect_uri": "https://claude.ai/callback",
            "code_verifier": "client-verifier",
        },
        headers={"Authorization": _basic_header("client-1", "client-secret")},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "access_token": "ciqpat_token",
        "token_type": "Bearer",
        "expires_in": 7776000,
        "scope": "openid email profile",
    }
    assert repository.minted[0]["client_id"] == "client-1"


def test_token_endpoint_accepts_public_none_client_with_pkce() -> None:
    """Token endpoint accepts no client secret when PKCE/code binding validates."""
    repository = _Repository()
    client = _client_for(repository)

    response = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "client-1",
            "code": "as-auth-code",
            "redirect_uri": "https://claude.ai/callback",
            "code_verifier": "client-verifier",
        },
    )

    assert response.status_code == 200
    assert response.json()["access_token"].startswith("ciqpat_")


def test_token_endpoint_rejects_bad_secret_without_oracle() -> None:
    """Bad confidential secret returns invalid_client."""
    client = _client_for(_Repository())

    response = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": "as-auth-code",
            "redirect_uri": "https://claude.ai/callback",
            "code_verifier": "client-verifier",
        },
        headers={"Authorization": _basic_header("client-1", "wrong-secret")},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_client"


def test_token_endpoint_rejects_pkce_mismatch_and_replay() -> None:
    """PKCE mismatch and auth-code replay return invalid_grant."""
    repository = _Repository()
    client = _client_for(repository)

    mismatch = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "client-1",
            "code": "as-auth-code",
            "redirect_uri": "https://claude.ai/callback",
            "code_verifier": "wrong-verifier",
        },
    )
    replay = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "client-1",
            "code": "as-auth-code",
            "redirect_uri": "https://claude.ai/callback",
            "code_verifier": "client-verifier",
        },
    )

    assert mismatch.status_code == 400
    assert mismatch.json()["error"] == "invalid_grant"
    assert replay.status_code == 400
    assert replay.json()["error"] == "invalid_grant"


def test_token_endpoint_rejects_refresh_grant_for_opaque_profile() -> None:
    """Opaque-no-refresh profile rejects refresh_token grant."""
    client = _client_for(_Repository())

    response = client.post(
        "/oauth/token",
        data={"grant_type": "refresh_token", "client_id": "client-1"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "unsupported_grant_type"
