"""Authentication Domain API Router for OIDC login."""

import logging
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from backend.api.domains import register_domain_router
from backend.core.dependencies import get_auth_service
from backend.models.auth import AuthProvider
from backend.services.auth.oidc import (
    OIDCConfigurationError,
    OIDCError,
    OIDCProviderUnavailableError,
    OIDCStateError,
    OIDCValidationError,
)
from backend.services.auth.service import AuthService

logger = logging.getLogger(__name__)
TOKEN_TYPE_BEARER = "bearer"  # noqa: S105

router = APIRouter(tags=["Authentication"])


class TokenPair(BaseModel):
    """Access and refresh token pair response model."""

    access_token: str = Field(..., description="Local CoachIQ access token")
    refresh_token: str = Field(..., description="Local CoachIQ refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    refresh_expires_in: int = Field(..., description="Refresh token lifetime in seconds")


@register_domain_router("auth")
def register_auth_domain_router() -> APIRouter:
    """Register the authentication domain router."""
    return router


@router.get(
    "/oidc/login",
    summary="Start PocketID OIDC login",
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
async def start_oidc_login(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    """Start a PocketID OIDC authorization-code flow."""
    auth_settings = auth_service.get_auth_settings()
    oidc_client = auth_service.get_oidc_client()
    state_store = auth_service.get_oidc_state_store()
    if not oidc_client or not state_store:
        return _failure_redirect(auth_settings, "sso_unavailable")

    redirect_uri = _oidc_redirect_uri()
    login_state = state_store.create(redirect_uri)
    try:
        authorization_url = await oidc_client.get_authorization_url(login_state)
    except (OIDCConfigurationError, OIDCProviderUnavailableError) as exc:
        logger.warning("PocketID OIDC login unavailable from %s: %s", request.client, exc)
        return _failure_redirect(auth_settings, "sso_unavailable")

    return RedirectResponse(authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get(
    "/oidc/callback",
    response_model=TokenPair,
    summary="Complete PocketID OIDC login or local token handoff",
)
async def complete_oidc_login(  # noqa: PLR0911, PLR0913
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    code: Annotated[str | None, Query(description="PocketID authorization code")] = None,
    state: Annotated[str | None, Query(description="OIDC state value")] = None,
    iss: Annotated[str | None, Query(description="Authorization response issuer")] = None,
    session_code: Annotated[
        str | None, Query(description="One-time local session handoff code")
    ] = None,
    error: Annotated[str | None, Query(description="PocketID authorization error")] = None,
) -> TokenPair | Response:
    """Complete OIDC callback validation or exchange a one-time local session code."""
    auth_settings = auth_service.get_auth_settings()
    if session_code:
        return _consume_session_code(auth_service, session_code)

    if error:
        logger.info("PocketID returned authorization error: %s", error)
        return _failure_redirect(auth_settings, "sso_denied")
    if not code or not state or not iss:
        return _failure_redirect(auth_settings, "invalid_callback")

    oidc_client = auth_service.get_oidc_client()
    state_store = auth_service.get_oidc_state_store()
    session_store = auth_service.get_oidc_session_code_store()
    auth_manager = auth_service.get_auth_manager()
    auth_repository = auth_service.get_auth_repository()
    if not oidc_client or not state_store or not session_store or not auth_manager:
        return _failure_redirect(auth_settings, "sso_unavailable")
    if not auth_repository:
        return _failure_redirect(auth_settings, "sso_unavailable")

    try:
        login_state = state_store.consume(state)
        if iss.rstrip("/") != auth_settings.oidc_issuer.rstrip("/"):
            msg = "OIDC authorization response issuer does not match configured issuer"
            raise OIDCValidationError(msg)
        token_response = await oidc_client.exchange_code(code, login_state)
        claims = await oidc_client.validate_id_token(token_response["id_token"], login_state.nonce)
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
            provider_data={
                "groups": groups,
                "email_verified": claims.get("email_verified"),
                "issuer": claims.get("iss"),
            },
        )
        if user is None:
            msg = "Unable to bind PocketID user to a local CoachIQ account"
            raise OIDCValidationError(msg)

        access_token = auth_manager.generate_token(
            user_id=user.id,
            username=user.username or user.email,
            additional_claims={
                "email": user.email,
                "role": role.value,
                "mode": "oidc",
                "provider": AuthProvider.POCKETID.value,
            },
        )
        refresh_token = ""
        if auth_manager.settings.enable_refresh_tokens:
            refresh_token = await auth_manager.generate_refresh_token(
                user_id=user.id,
                username=user.username or user.email,
                additional_claims={
                    "email": user.email,
                    "role": role.value,
                    "mode": "oidc",
                    "provider": AuthProvider.POCKETID.value,
                },
            )
        local_session_code = session_store.create(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=TOKEN_TYPE_BEARER,
            expires_in=auth_manager.settings.jwt_expire_minutes * 60,
            refresh_expires_in=auth_manager.settings.refresh_token_expire_days * 24 * 60 * 60,
        )
        return _frontend_callback_redirect(auth_settings, local_session_code)
    except OIDCError as exc:
        logger.warning("PocketID OIDC callback failed for %s: %s", request.client, exc)
        return _failure_redirect(auth_settings, "sso_failed")


def _consume_session_code(auth_service: AuthService, session_code: str) -> TokenPair | JSONResponse:
    """Exchange a one-time session code for local tokens."""
    session_store = auth_service.get_oidc_session_code_store()
    if not session_store:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "OIDC session handoff is unavailable"},
        )
    try:
        token_payload = session_store.consume(session_code)
    except OIDCStateError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "OIDC session code is invalid or expired"},
        )
    return TokenPair(
        access_token=token_payload.access_token,
        refresh_token=token_payload.refresh_token,
        token_type=token_payload.token_type,
        expires_in=token_payload.expires_in,
        refresh_expires_in=token_payload.refresh_expires_in,
    )


def _oidc_redirect_uri() -> str:
    """Return the absolute backend OIDC callback URI."""
    return f"{_server_public_origin()}/api/v1/auth/oidc/callback"


def _server_public_origin() -> str:
    """Look up public origin from the canonical settings object."""
    from backend.core.config import get_settings

    return get_settings().server.public_origin.rstrip("/")


def _frontend_callback_redirect(auth_settings: Any, session_code: str) -> RedirectResponse:
    """Redirect browser back to the frontend OIDC callback route with a one-time code."""
    target = _absolute_frontend_path(auth_settings.oidc_frontend_callback_path)
    return RedirectResponse(
        _append_query(target, {"code": session_code}),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


def _failure_redirect(auth_settings: Any, reason: str) -> RedirectResponse:
    """Redirect browser back to the frontend login route with a failure reason."""
    target = _absolute_frontend_path(auth_settings.oidc_failure_redirect_path)
    return RedirectResponse(
        _append_query(target, {"reason": reason}),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


def _absolute_frontend_path(path: str) -> str:
    """Return an absolute frontend redirect target."""
    if path.startswith(("http://", "https://")):
        return path
    return f"{_server_public_origin()}{path}"


def _append_query(target: str, values: dict[str, str]) -> str:
    """Append query values to a URL that may already have query parameters."""
    separator = "&" if "?" in target else "?"
    return f"{target}{separator}{urlencode(values)}"


def _claim_groups(value: Any) -> list[str]:
    """Normalize OIDC group claims to a list of strings."""
    if isinstance(value, list):
        return [str(group) for group in value]
    if isinstance(value, str):
        return [value]
    return []


def _required_claim(claims: dict[str, Any], claim_name: str) -> str:
    """Return a required non-empty string claim."""
    claim_value = claims.get(claim_name)
    if not claim_value:
        msg = f"OIDC ID token is missing required claim: {claim_name}"
        raise OIDCValidationError(msg)
    return str(claim_value)
