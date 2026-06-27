"""Tests for secure authentication middleware guardrail decisions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from backend.core.custom_exceptions import InvalidTokenError
from backend.middleware.secure_auth import SecureAuthenticationMiddleware

pytestmark = [pytest.mark.unit, pytest.mark.auth]


async def app(scope: dict, receive: object, send: object) -> None:
    """Minimal ASGI app placeholder for middleware construction."""


def make_request(
    path: str,
    *,
    authorization: str | None = None,
    cookie: str | None = None,
) -> Request:
    """Create a Starlette Request for middleware unit tests."""
    headers: list[tuple[bytes, bytes]] = []
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("127.0.0.1", 1234),
        }
    )


@pytest.fixture
def middleware() -> SecureAuthenticationMiddleware:
    """Create middleware with explicit auth/token mocks."""
    instance = SecureAuthenticationMiddleware(app)
    instance.auth_manager = Mock()
    instance.token_service = Mock()
    return instance


async def call_next(request: Request) -> Response:
    """Return a basic successful response and expose request state."""
    response = Response("ok", status_code=200)
    if hasattr(request.state, "user"):
        response.headers["X-Test-User"] = request.state.user["user_id"]
    return response


@pytest.mark.asyncio
async def test_public_endpoint_bypasses_authentication(
    middleware: SecureAuthenticationMiddleware,
) -> None:
    """Public paths bypass token checks entirely."""
    response = await middleware.dispatch(make_request("/api/auth/login"), call_next)

    assert response.status_code == 200
    middleware.token_service.extract_access_token.assert_not_called()


@pytest.mark.asyncio
async def test_unprotected_endpoint_bypasses_authentication(
    middleware: SecureAuthenticationMiddleware,
) -> None:
    """Non-protected paths continue without auth even when services exist."""
    response = await middleware.dispatch(make_request("/api/v2/entities"), call_next)

    assert response.status_code == 200
    middleware.token_service.extract_access_token.assert_not_called()


@pytest.mark.asyncio
async def test_protected_endpoint_without_tokens_returns_auth_error(
    middleware: SecureAuthenticationMiddleware,
) -> None:
    """Protected endpoints require either an access token or refresh token."""
    middleware.token_service.extract_access_token.return_value = None

    auth_result = await middleware._authenticate_request(
        make_request("/api/v2/entities/bulk-control")
    )
    response = middleware._create_auth_error_response(
        auth_result["error"], auth_result["status_code"]
    )

    assert auth_result["authenticated"] is False
    assert response.status_code == 401
    assert response.headers["X-Auth-Required"] == "true"
    assert response.headers["X-Safety-Critical"] == "true"


@pytest.mark.asyncio
async def test_bearer_access_token_authenticates_request(
    middleware: SecureAuthenticationMiddleware,
) -> None:
    """Valid bearer tokens populate request state and call the endpoint."""
    middleware.token_service.extract_access_token.return_value = "access-token"
    middleware.token_service.is_token_near_expiry.return_value = False
    middleware.auth_manager.validate_token.return_value = {"sub": "user-1", "username": "ryan"}

    auth_result = await middleware._authenticate_request(
        make_request("/api/v2/entities/bulk-control", authorization="Bearer access-token")
    )

    assert auth_result["authenticated"] is True
    assert auth_result["user"]["user_id"] == "user-1"
    middleware.auth_manager.validate_token.assert_called_once_with("access-token")


@pytest.mark.asyncio
async def test_invalid_access_token_falls_back_to_refresh_cookie(
    middleware: SecureAuthenticationMiddleware,
) -> None:
    """Invalid access tokens can still authenticate via a valid refresh cookie."""
    middleware.token_service.extract_access_token.return_value = "bad-access"
    middleware.auth_manager.validate_token.side_effect = [
        InvalidTokenError("bad access"),
        {"sub": "user-2", "username": "new"},
    ]
    middleware.token_service.refresh_access_token = AsyncMock(
        return_value=SimpleNamespace(
            access_token="new-access",
            access_token_expires_in=900,
            refresh_rotated=False,
            new_refresh_token=None,
        )
    )

    auth_result = await middleware._authenticate_request(
        make_request(
            "/api/v2/entities/bulk-control",
            authorization="Bearer bad-access",
            cookie="refresh_token=refresh-1",
        )
    )
    response = Response("ok")
    middleware._apply_token_refresh(response, auth_result["new_tokens"])

    assert auth_result["authenticated"] is True
    assert auth_result["token_refreshed"] is True
    assert response.headers["X-Access-Token"] == "new-access"
    assert response.headers["X-Token-Refreshed"] == "true"


@pytest.mark.asyncio
async def test_refresh_failure_returns_auth_error(
    middleware: SecureAuthenticationMiddleware,
) -> None:
    """Invalid refresh tokens deny protected requests."""
    middleware.token_service.extract_access_token.return_value = None
    middleware.token_service.refresh_access_token = AsyncMock(
        side_effect=InvalidTokenError("bad refresh")
    )

    auth_result = await middleware._authenticate_request(
        make_request("/api/v2/entities/bulk-control", cookie="refresh_token=bad")
    )
    response = middleware._create_auth_error_response(
        auth_result["error"], auth_result["status_code"]
    )

    assert auth_result["authenticated"] is False
    assert response.status_code == 401
    assert b"Invalid or expired refresh token" in response.body


def test_apply_token_refresh_sets_headers_and_rotated_cookie(
    middleware: SecureAuthenticationMiddleware,
) -> None:
    """Token refresh response metadata is applied to outgoing responses."""
    response = Response("ok")
    middleware.token_service.set_refresh_cookie = Mock()

    middleware._apply_token_refresh(
        response,
        {
            "access_token": "access",
            "access_token_expires_in": 900,
            "refresh_rotated": True,
            "new_refresh_token": "refresh-2",
        },
    )

    assert response.headers["X-Access-Token"] == "access"
    assert response.headers["X-Refresh-Token-Rotated"] == "true"
    middleware.token_service.set_refresh_cookie.assert_called_once_with(response, "refresh-2")
