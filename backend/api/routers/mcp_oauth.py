"""MCP OAuth AS discovery and protected-resource metadata routes."""

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.core.config import Settings, get_settings
from backend.services.auth.mcp_contract import (
    MCP_AS_CODE_CHALLENGE_METHODS,
    MCP_AS_GRANT_TYPES,
    MCP_AS_RESPONSE_TYPES,
    MCP_AS_SCOPES_SUPPORTED,
    MCP_AS_TOKEN_AUTH_METHODS,
)

router = APIRouter(tags=["MCP OAuth"])


def _origin(settings: Settings) -> str:
    """Return the configured public origin without a trailing slash."""
    return settings.server.public_origin.rstrip("/")


def build_authorization_server_metadata(settings: Settings) -> dict[str, Any]:
    """Build RFC 8414 authorization-server metadata for the opaque profile."""
    origin = _origin(settings)
    return {
        "issuer": origin,
        "authorization_endpoint": f"{origin}/oauth/authorize",
        "token_endpoint": f"{origin}/oauth/token",
        "registration_endpoint": f"{origin}/oauth/register",
        "response_types_supported": list(MCP_AS_RESPONSE_TYPES),
        "grant_types_supported": list(MCP_AS_GRANT_TYPES),
        "code_challenge_methods_supported": list(MCP_AS_CODE_CHALLENGE_METHODS),
        "token_endpoint_auth_methods_supported": list(MCP_AS_TOKEN_AUTH_METHODS),
        "scopes_supported": list(MCP_AS_SCOPES_SUPPORTED),
    }


def build_protected_resource_metadata(
    settings: Settings, resource_path: str | None = None
) -> dict[str, Any]:
    """Build RFC 9728 protected-resource metadata for root or MCP-path variants."""
    origin = _origin(settings)
    resource = origin if resource_path is None else f"{origin}{resource_path}"
    return {
        "resource": resource,
        "authorization_servers": [origin],
        "bearer_methods_supported": ["header"],
    }


@router.get("/.well-known/oauth-authorization-server")
async def get_authorization_server_metadata() -> dict[str, Any]:
    """Return OAuth authorization-server metadata with contract-exact field names."""
    return build_authorization_server_metadata(get_settings())


@router.get("/.well-known/oauth-protected-resource")
async def get_origin_protected_resource_metadata() -> dict[str, Any]:
    """Return origin-root protected-resource metadata for older clients."""
    return build_protected_resource_metadata(get_settings())


@router.get("/.well-known/oauth-protected-resource{resource_path:path}")
async def get_path_protected_resource_metadata(resource_path: str) -> dict[str, Any]:
    """Return path-suffixed protected-resource metadata for spec-strict clients."""
    settings = get_settings()
    if resource_path != settings.mcp.path:
        raise HTTPException(status_code=404, detail="Unknown protected resource")
    return build_protected_resource_metadata(settings, resource_path)
