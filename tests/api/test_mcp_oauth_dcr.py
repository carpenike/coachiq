"""Tests for MCP OAuth dynamic client registration."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.routers.mcp_oauth as mcp_oauth_router
from backend.api.routers.mcp_oauth import (
    filter_allowed_redirect_uris,
    get_mcp_oauth_repository,
    router,
)
from backend.services.auth.mcp_oauth_security import McpOAuthRateLimiter


class _FakeMcpOAuthRepository:
    """Fake repository for DCR route tests."""

    def __init__(self) -> None:
        self.redirect_uris: list[str] | None = None

    async def create_client(self, redirect_uris: list[str]):
        """Capture redirect URIs and return a deterministic client/secret pair."""
        self.redirect_uris = redirect_uris
        return SimpleNamespace(client_id="ciqclient_test"), "ciqsecret_test"


def _client_for(repository: _FakeMcpOAuthRepository) -> TestClient:
    """Create a test client with the MCP OAuth router mounted."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_mcp_oauth_repository] = lambda: repository
    mcp_oauth_router._dcr_rate_limiter = McpOAuthRateLimiter(limit=10, window_seconds=3600)
    return TestClient(app)


def test_redirect_uri_allowlist_filters_mixed_redirects_verbatim() -> None:
    """DCR redirect policy filters invalid URIs and preserves valid prefixes."""
    redirect_uris = [
        "https://claude.ai/api/mcp/callback",
        "https://claude.com/callback",
        "http://127.0.0.1:3456/callback",
        "http://127.0.0.1/callback",
        "http://localhost:5173/callback",
        "http://localhost/callback",
        "https://vscode.dev/redirect?state=abc",
        "https://insiders.vscode.dev/redirect?state=abc",
        "https://evil.example/callback",
    ]

    assert filter_allowed_redirect_uris(redirect_uris) == redirect_uris[:-1]


def test_redirect_uri_allowlist_rejects_loopback_evil_hosts() -> None:
    """Trailing ':' and '/' in loopback prefixes block naive evil-host matches."""
    redirect_uris = [
        "http://127.0.0.1.evil.com/callback",
        "http://localhost.evil.com/callback",
    ]

    assert filter_allowed_redirect_uris(redirect_uris) == []


def test_dcr_filters_redirect_uris_and_returns_hashed_secret_once() -> None:
    """DCR creates a client with only allowlisted redirect URIs."""
    repository = _FakeMcpOAuthRepository()
    client = _client_for(repository)

    response = client.post(
        "/oauth/register",
        json={
            "redirect_uris": [
                "https://claude.ai/callback",
                "https://evil.example/callback",
            ]
        },
    )

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "client_id": "ciqclient_test",
        "client_secret": "ciqsecret_test",
        "client_secret_expires_at": 0,
        "redirect_uris": ["https://claude.ai/callback"],
    }
    assert repository.redirect_uris == ["https://claude.ai/callback"]


def test_dcr_returns_invalid_redirect_uri_when_none_survive_filter() -> None:
    """DCR returns 400 only when all redirect URIs are filtered out."""
    client = _client_for(_FakeMcpOAuthRepository())

    response = client.post(
        "/oauth/register",
        json={"redirect_uris": ["https://evil.example/callback"]},
    )

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"] == "invalid_redirect_uri"
