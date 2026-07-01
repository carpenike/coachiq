"""Tests for MCP OAuth discovery metadata."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routers.mcp_oauth import (
    build_authorization_server_metadata,
    build_protected_resource_metadata,
    router,
)
from backend.core.config import McpSettings, ServerSettings, Settings


def _settings() -> Settings:
    """Build settings with MCP AS enabled and contract default path."""
    return Settings(
        testing=True,
        mcp=McpSettings(as_enabled=True, path="/api/mcp"),
        server=ServerSettings(public_origin="https://iq.holtel.io"),
    )


def test_authorization_server_metadata_is_contract_exact_and_omits_jwks() -> None:
    """AS metadata uses load-bearing field names and omits jwks_uri for opaque tokens."""
    metadata = build_authorization_server_metadata(_settings())

    assert metadata == {
        "issuer": "https://iq.holtel.io",
        "authorization_endpoint": "https://iq.holtel.io/oauth/authorize",
        "token_endpoint": "https://iq.holtel.io/oauth/token",
        "registration_endpoint": "https://iq.holtel.io/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
            "none",
        ],
        "scopes_supported": ["openid", "email", "profile"],
    }
    assert "jwks_uri" not in metadata
    assert "groups" not in metadata["scopes_supported"]


def test_protected_resource_metadata_variants_byte_match_resources() -> None:
    """Both PRM variants derive resources from public_origin and mcp.path."""
    settings = _settings()

    root_metadata = build_protected_resource_metadata(settings)
    path_metadata = build_protected_resource_metadata(settings, settings.mcp.path)

    assert root_metadata == {
        "resource": "https://iq.holtel.io",
        "authorization_servers": ["https://iq.holtel.io"],
        "bearer_methods_supported": ["header"],
    }
    assert path_metadata == {
        "resource": "https://iq.holtel.io/api/mcp",
        "authorization_servers": ["https://iq.holtel.io"],
        "bearer_methods_supported": ["header"],
    }


def test_metadata_routes_are_mounted_at_contract_fixed_paths(monkeypatch) -> None:
    """Router serves AS metadata and both PRM variants outside /api/v1."""
    import backend.api.routers.mcp_oauth as mcp_oauth_router

    monkeypatch.setattr(mcp_oauth_router, "get_settings", _settings)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    as_response = client.get("/.well-known/oauth-authorization-server")
    root_prm = client.get("/.well-known/oauth-protected-resource")
    path_prm = client.get("/.well-known/oauth-protected-resource/api/mcp")
    wrong_prm = client.get("/.well-known/oauth-protected-resource/api/wrong")

    assert as_response.status_code == 200
    assert root_prm.status_code == 200
    assert path_prm.status_code == 200
    assert path_prm.json()["resource"] == "https://iq.holtel.io/api/mcp"
    assert wrong_prm.status_code == 404
