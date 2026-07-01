"""MCP OAuth AS discovery and protected-resource metadata routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from backend.core.config import Settings, get_settings
from backend.core.dependencies import get_composition_root
from backend.services.auth.mcp_contract import (
    MCP_AS_CODE_CHALLENGE_METHODS,
    MCP_AS_GRANT_TYPES,
    MCP_AS_RESPONSE_TYPES,
    MCP_AS_SCOPES_SUPPORTED,
    MCP_AS_TOKEN_AUTH_METHODS,
    MCP_DCR_REDIRECT_URI_PREFIXES,
)
from backend.services.auth.mcp_oauth_repository import McpOAuthRepository
from backend.services.auth.mcp_oauth_security import McpOAuthRateLimiter, audit_mcp_oauth_event

router = APIRouter(tags=["MCP OAuth"])
_dcr_rate_limiter = McpOAuthRateLimiter(limit=10, window_seconds=3600)


class ClientRegistrationRequest(BaseModel):
    """Dynamic client registration request."""

    redirect_uris: list[str] = Field(..., description="Requested redirect URIs")


class ClientRegistrationResponse(BaseModel):
    """Dynamic client registration response."""

    client_id: str
    client_secret: str
    client_secret_expires_at: int = 0
    redirect_uris: list[str]


def get_mcp_oauth_repository() -> McpOAuthRepository:
    """Return an MCP OAuth repository backed by the composition root database manager."""
    root = get_composition_root()
    return McpOAuthRepository(root.require_service("database_manager"))


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


@router.post(
    "/oauth/register",
    response_model=ClientRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_oauth_client(
    request: Request,
    response: Response,
    registration: ClientRegistrationRequest,
    repository: Annotated[McpOAuthRepository, Depends(get_mcp_oauth_repository)],
) -> ClientRegistrationResponse | JSONResponse:
    """Register an MCP OAuth client using allowlist-filtered redirect URIs."""
    source = request.client.host if request.client else "unknown"
    if not _dcr_rate_limiter.allow(source):
        return oauth_error_response(
            "temporarily_unavailable",
            "Dynamic client registration rate limit exceeded",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    redirect_uris = filter_allowed_redirect_uris(registration.redirect_uris)
    if not redirect_uris:
        audit_mcp_oauth_event("dcr_rejected", source=source, reason="invalid_redirect_uri")
        return oauth_error_response(
            "invalid_redirect_uri",
            "No redirect URIs matched the allowed MCP client prefixes",
            status.HTTP_400_BAD_REQUEST,
        )

    created = await repository.create_client(redirect_uris)
    if created is None:
        return oauth_error_response(
            "server_error",
            "Dynamic client registration failed",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    client, client_secret = created
    audit_mcp_oauth_event("dcr_registered", source=source, client_id=client.client_id)
    response.headers["Cache-Control"] = "no-store"
    return ClientRegistrationResponse(
        client_id=client.client_id,
        client_secret=client_secret,
        client_secret_expires_at=0,
        redirect_uris=redirect_uris,
    )


def filter_allowed_redirect_uris(redirect_uris: list[str]) -> list[str]:
    """Filter redirect URIs using the contract's allowed-prefix policy."""
    return [uri for uri in redirect_uris if _is_allowed_redirect_uri(uri)]


def _is_allowed_redirect_uri(redirect_uri: str) -> bool:
    """Return whether a redirect URI matches an allowed MCP client prefix."""
    return any(redirect_uri.startswith(prefix) for prefix in MCP_DCR_REDIRECT_URI_PREFIXES)


def oauth_error_response(
    error: str,
    error_description: str,
    status_code: int,
) -> JSONResponse:
    """Return a no-store OAuth JSON error response."""
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "error_description": error_description},
        headers={"Cache-Control": "no-store"},
    )
