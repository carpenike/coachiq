"""MCP OAuth AS discovery and protected-resource metadata routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from backend.core.config import Settings, get_settings
from backend.core.dependencies import get_auth_service, get_composition_root
from backend.models.auth import AuthProvider
from backend.services.auth.mcp_contract import (
    MCP_AS_CODE_CHALLENGE_METHODS,
    MCP_AS_GRANT_TYPES,
    MCP_AS_RESPONSE_TYPES,
    MCP_AS_SCOPES_SUPPORTED,
    MCP_AS_TOKEN_AUTH_METHODS,
    MCP_DCR_REDIRECT_URI_PREFIXES,
)
from backend.services.auth.mcp_oauth_repository import McpOAuthRepository
from backend.services.auth.mcp_oauth_service import create_upstream_login_state
from backend.services.auth.mcp_oauth_security import McpOAuthRateLimiter, audit_mcp_oauth_event
from backend.services.auth.oidc import OIDCError, OIDCValidationError
from backend.services.auth.service import AuthService

router = APIRouter(tags=["MCP OAuth"])
_dcr_rate_limiter = McpOAuthRateLimiter(limit=10, window_seconds=3600)
_authorize_rate_limiter = McpOAuthRateLimiter(limit=30, window_seconds=3600)


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


def _oauth_callback_uri(settings: Settings) -> str:
    """Return the absolute AS callback URI."""
    return f"{_origin(settings)}/oauth/callback"


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


@router.get("/oauth/authorize", response_model=None)
async def authorize_oauth_client(  # noqa: PLR0913
    request: Request,
    repository: Annotated[McpOAuthRepository, Depends(get_mcp_oauth_repository)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    client_id: Annotated[str | None, Query()] = None,
    redirect_uri: Annotated[str | None, Query()] = None,
    response_type: Annotated[str | None, Query()] = None,
    scope: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    code_challenge: Annotated[str | None, Query()] = None,
    code_challenge_method: Annotated[str | None, Query()] = None,
) -> RedirectResponse | JSONResponse:
    """Validate client authorization request and redirect to PocketID."""
    source = request.client.host if request.client else "unknown"
    if not _authorize_rate_limiter.allow(source):
        return oauth_error_response(
            "temporarily_unavailable",
            "Authorization initiation rate limit exceeded",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if response_type != "code":
        return oauth_error_response(
            "unsupported_response_type",
            "Only response_type=code is supported",
            status.HTTP_400_BAD_REQUEST,
        )
    if not client_id or not redirect_uri or not code_challenge:
        return oauth_error_response(
            "invalid_request",
            "client_id, redirect_uri, and code_challenge are required",
            status.HTTP_400_BAD_REQUEST,
        )
    if code_challenge_method != "S256":
        return oauth_error_response(
            "invalid_request",
            "PKCE S256 code_challenge_method is required",
            status.HTTP_400_BAD_REQUEST,
        )
    client = await repository.get_client(client_id)
    if not client or redirect_uri not in client.redirect_uris:
        return oauth_error_response(
            "invalid_request",
            "Unknown client or redirect_uri",
            status.HTTP_400_BAD_REQUEST,
        )

    settings = get_settings()
    upstream_state = create_upstream_login_state(_oauth_callback_uri(settings))
    transaction = await repository.create_transaction(
        client_id=client_id,
        redirect_uri=redirect_uri,
        client_state=state,
        client_code_challenge=code_challenge,
        client_code_challenge_method=code_challenge_method,
        upstream_code_verifier=upstream_state.code_verifier,
        upstream_nonce=upstream_state.nonce,
        ttl_seconds=300,
    )
    if transaction is None:
        return oauth_error_response("server_error", "Unable to create AS transaction", 500)
    pocketid_state = type(upstream_state)(
        state=transaction.transaction_state,
        nonce=upstream_state.nonce,
        code_verifier=upstream_state.code_verifier,
        redirect_uri=upstream_state.redirect_uri,
        expires_at=upstream_state.expires_at,
    )
    oidc_client = auth_service.get_oidc_client()
    if not oidc_client:
        return oauth_error_response("temporarily_unavailable", "OIDC client unavailable", 503)
    authorization_url = await oidc_client.get_authorization_url(pocketid_state)
    audit_mcp_oauth_event("authorize_started", client_id=client_id, source=source, scope=scope)
    return RedirectResponse(authorization_url, status_code=status.HTTP_302_FOUND)


@router.get("/oauth/callback", response_model=None)
async def complete_oauth_federation(
    repository: Annotated[McpOAuthRepository, Depends(get_mcp_oauth_repository)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    iss: Annotated[str | None, Query()] = None,
) -> RedirectResponse | JSONResponse:
    """Complete the AS-to-PocketID leg and issue a client authorization code."""
    if not code or not state or not iss:
        return oauth_error_response("invalid_request", "code, state, and iss are required", 400)
    settings = get_settings()
    if iss.rstrip("/") != auth_service.get_auth_settings().oidc_issuer.rstrip("/"):
        return oauth_error_response("invalid_request", "Issuer mismatch", 400)
    transaction = await repository.consume_transaction(state)
    if transaction is None:
        return oauth_error_response("invalid_request", "Invalid or expired transaction", 400)

    oidc_client = auth_service.get_oidc_client()
    auth_repository = auth_service.get_auth_repository()
    if not oidc_client or not auth_repository:
        return oauth_error_response("temporarily_unavailable", "OIDC client unavailable", 503)
    try:
        login_state = type(create_upstream_login_state(_oauth_callback_uri(settings)))(
            state=state,
            nonce=transaction.upstream_nonce,
            code_verifier=transaction.upstream_code_verifier,
            redirect_uri=_oauth_callback_uri(settings),
            expires_at=0.0,
        )
        token_response = await oidc_client.exchange_code(code, login_state)
        claims = await oidc_client.validate_id_token(
            token_response["id_token"], transaction.upstream_nonce
        )
        groups = _claim_groups(claims.get("groups"))
        role = oidc_client.map_groups_to_role(groups)
        user = await auth_repository.upsert_federated_user(
            provider=AuthProvider.POCKETID,
            provider_user_id=str(claims["sub"]),
            email=_required_claim(claims, "email"),
            username=claims.get("preferred_username"),
            display_name=claims.get("name"),
            role=role,
            email_verified=claims.get("email_verified") is True,
            provider_data={"groups": groups, "email_verified": claims.get("email_verified")},
        )
        if user is None:
            raise OIDCValidationError("Unable to bind PocketID user")
        auth_code = await repository.create_authorization_code(
            user_id=user.id,
            client_id=transaction.client_id,
            redirect_uri=transaction.redirect_uri,
            code_challenge=transaction.client_code_challenge,
            code_challenge_method=transaction.client_code_challenge_method,
            ttl_seconds=300,
        )
        if auth_code is None:
            return oauth_error_response("server_error", "Unable to create authorization code", 500)
        audit_mcp_oauth_event("authorization_code_issued", client_id=transaction.client_id)
        return _redirect_with_code(transaction.redirect_uri, auth_code, transaction.client_state)
    except OIDCError as exc:
        return oauth_error_response("temporarily_unavailable", str(exc), 503)


def _redirect_with_code(redirect_uri: str, code: str, state: str | None) -> RedirectResponse:
    """Redirect back to the MCP client with an authorization code."""
    separator = "&" if "?" in redirect_uri else "?"
    state_part = f"&state={state}" if state else ""
    return RedirectResponse(
        f"{redirect_uri}{separator}code={code}{state_part}",
        status_code=status.HTTP_302_FOUND,
    )


def _claim_groups(value: Any) -> list[str]:
    """Normalize group claims to a list of strings."""
    if isinstance(value, list):
        return [str(group) for group in value]
    if isinstance(value, str):
        return [value]
    return []


def _required_claim(claims: dict[str, Any], claim_name: str) -> str:
    """Return a required non-empty string claim."""
    claim_value = claims.get(claim_name)
    if not claim_value:
        raise OIDCValidationError(f"Missing required claim: {claim_name}")
    return str(claim_value)
