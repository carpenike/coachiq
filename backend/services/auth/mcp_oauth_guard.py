"""MCP-only OAuth token guard."""

from typing import Any

from fastapi import HTTPException, Request, status

from backend.core.config import Settings
from backend.services.auth.mcp_contract import MCP_TOKEN_PREFIX
from backend.services.auth.mcp_oauth_repository import McpOAuthRepository


def mcp_resource_metadata_url(settings: Settings) -> str:
    """Return the contract-required path-suffixed protected resource metadata URL."""
    return (
        f"{settings.server.public_origin.rstrip('/')}/.well-known/"
        f"oauth-protected-resource{settings.mcp.path}"
    )


def mcp_www_authenticate_header(settings: Settings) -> str:
    """Return the MCP OAuth Bearer challenge."""
    return f'Bearer resource_metadata="{mcp_resource_metadata_url(settings)}"'


async def require_mcp_oauth_token(
    request: Request,
    *,
    settings: Settings,
    repository: McpOAuthRepository,
) -> dict[str, Any]:
    """Validate an MCP-only `ciqpat_` token for the MCP resource path."""
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or not token.startswith(MCP_TOKEN_PREFIX):
        raise_mcp_unauthorized(settings)
    access_token = await repository.validate_access_token(token)
    if access_token is None:
        raise_mcp_unauthorized(settings)
    return {
        "user_id": access_token.user_id,
        "client_id": access_token.client_id,
        "scope": access_token.scope,
    }


def reject_mcp_token_on_rest(authorization: str | None) -> None:
    """Reject MCP-only OAuth tokens before REST JWT validation."""
    if not authorization:
        return
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.startswith(MCP_TOKEN_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MCP OAuth tokens are only valid on the MCP resource path",
            headers={"WWW-Authenticate": "Bearer"},
        )


def raise_mcp_unauthorized(settings: Settings) -> None:
    """Raise the MCP OAuth unauthorized challenge."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="MCP OAuth token required",
        headers={"WWW-Authenticate": mcp_www_authenticate_header(settings)},
    )
