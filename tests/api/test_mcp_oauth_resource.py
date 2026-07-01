"""Tests for MCP-only OAuth resource enforcement."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.routers.mcp_oauth as mcp_oauth_router
from backend.api.routers.mcp_oauth import get_mcp_oauth_repository, router
from backend.core.config import McpSettings, ServerSettings, Settings
from backend.services.auth.mcp_oauth_guard import (
    mcp_www_authenticate_header,
    reject_mcp_token_on_rest,
)


class _Repository:
    """Fake MCP OAuth repository for resource tests."""

    async def validate_access_token(self, token: str):
        """Validate one deterministic MCP OAuth token."""
        if token != "ciqpat_valid":
            return None
        return SimpleNamespace(user_id="local-user", client_id="client-1", scope="openid")


def _settings() -> Settings:
    """Build settings with MCP AS enabled."""
    return Settings(
        testing=True,
        mcp=McpSettings(as_enabled=True, path="/api/mcp"),
        server=ServerSettings(public_origin="https://iq.holtel.io"),
    )


def _client_for(repository: _Repository) -> TestClient:
    """Create a test app with the MCP OAuth router mounted."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_mcp_oauth_repository] = lambda: repository
    mcp_oauth_router.get_settings = _settings
    return TestClient(app)


def test_mcp_resource_accepts_only_valid_ciqpat_token() -> None:
    """Minimal MCP resource accepts hashed-handle-validated ciqpat tokens."""
    client = _client_for(_Repository())

    response = client.post("/api/mcp", headers={"Authorization": "Bearer ciqpat_valid"})

    assert response.status_code == 200
    assert response.json()["result"]["authenticated"] is True
    assert response.json()["result"]["user_id"] == "local-user"


def test_mcp_resource_rejects_session_jwt_with_resource_metadata_hint() -> None:
    """Local session JWTs do not grant /api/mcp and receive the contract challenge."""
    client = _client_for(_Repository())

    response = client.post("/api/mcp", headers={"Authorization": "Bearer local.jwt.token"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == mcp_www_authenticate_header(_settings())
    assert "resource_metadata" in response.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_ciqpat_token_is_explicitly_rejected_on_rest_auth() -> None:
    """MCP OAuth tokens are rejected before REST JWT validation."""
    with pytest.raises(Exception) as exc_info:
        reject_mcp_token_on_rest("Bearer ciqpat_valid")

    assert getattr(exc_info.value, "status_code", None) == 401
    assert "only valid on the MCP resource path" in str(exc_info.value.detail)
