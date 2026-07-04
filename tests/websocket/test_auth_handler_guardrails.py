"""Tests for WebSocket authentication guardrail decisions."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.services.auth.manager import AuthMode
from backend.websocket.auth_handler import WebSocketAuthHandler

pytestmark = [pytest.mark.unit, pytest.mark.auth, pytest.mark.websocket]


class FakeWebSocket:
    """Minimal WebSocket double for auth handler tests."""

    def __init__(self, query_string: bytes = b"") -> None:
        self.scope = {"query_string": query_string}
        self.client = SimpleNamespace(host="127.0.0.1", port=4321)
        self.accepted = False
        self.closed_code: int | None = None
        self.closed_reason: str | None = None

    async def accept(self) -> None:
        """Record accepted connections."""
        self.accepted = True

    async def close(self, code: int, reason: str | None = None) -> None:
        """Record close codes."""
        self.closed_code = code
        self.closed_reason = reason


def make_handler(auth_manager: Mock | None) -> WebSocketAuthHandler:
    """Create a handler with a preloaded auth manager."""
    handler = WebSocketAuthHandler()
    handler._auth_manager = auth_manager
    return handler


async def test_no_auth_manager_allows_admin_fallback() -> None:
    """When auth services are unavailable, websocket auth follows middleware fallback."""
    websocket = FakeWebSocket()
    handler = make_handler(None)

    user = await handler.authenticate_connection(websocket)

    assert websocket.accepted is True
    assert user is not None
    assert user["role"] == "admin"
    assert user["authenticated"] is True


async def test_auth_mode_none_allows_connection() -> None:
    """AuthMode.NONE accepts connections without a token."""
    auth_manager = Mock(auth_mode=AuthMode.NONE)
    websocket = FakeWebSocket()
    handler = make_handler(auth_manager)

    user = await handler.authenticate_connection(websocket)

    assert websocket.accepted is True
    assert user is not None
    assert user["role"] == "admin"


async def test_optional_auth_without_token_accepts_anonymous_connection() -> None:
    """Endpoints that do not require auth can accept without user info."""
    auth_manager = Mock(auth_mode=AuthMode.SINGLE_USER)
    websocket = FakeWebSocket()
    handler = make_handler(auth_manager)

    user = await handler.authenticate_connection(websocket, require_auth=False)

    assert websocket.accepted is True
    assert user is None


async def test_missing_token_closes_connection() -> None:
    """Required-auth connections without a token get an auth close code.

    Accept-then-close is deliberate: rejecting the handshake pre-accept
    surfaces as HTTP 403 / opaque 1006 in browsers, so clients could not
    distinguish auth failure from an unreachable server.
    """
    auth_manager = Mock(auth_mode=AuthMode.SINGLE_USER)
    websocket = FakeWebSocket()
    handler = make_handler(auth_manager)

    user = await handler.authenticate_connection(websocket)

    assert user is None
    assert websocket.accepted is True
    assert websocket.closed_code == 4401


async def test_query_token_authenticates_and_tracks_connection() -> None:
    """A token in the query string is validated and tracked by connection id."""
    auth_manager = Mock(auth_mode=AuthMode.SINGLE_USER)
    auth_manager.validate_token.return_value = {
        "sub": "user-1",
        "username": "ryan",
        "email": "ryan@example.com",
        "role": "admin",
        "exp": datetime.now(UTC).timestamp() + 60,
    }
    websocket = FakeWebSocket(query_string=b"token=abc")
    handler = make_handler(auth_manager)

    user = await handler.authenticate_connection(websocket)

    assert websocket.accepted is True
    assert user is not None
    assert user["user_id"] == "user-1"
    assert handler.authenticated_connections["127.0.0.1:4321"] == user
    auth_manager.validate_token.assert_called_once_with("abc")


async def test_invalid_token_closes_connection() -> None:
    """Invalid tokens are denied and do not add connection state."""
    auth_manager = Mock(auth_mode=AuthMode.SINGLE_USER)
    auth_manager.validate_token.side_effect = ValueError("bad token")
    websocket = FakeWebSocket(query_string=b"token=bad")
    handler = make_handler(auth_manager)

    user = await handler.authenticate_connection(websocket)

    assert user is None
    assert websocket.accepted is True
    assert websocket.closed_code == 4401
    assert handler.authenticated_connections == {}


async def test_token_expiry_closes_expired_connection() -> None:
    """Expired authenticated websocket tokens are closed."""
    websocket = FakeWebSocket()
    handler = make_handler(Mock(auth_mode=AuthMode.SINGLE_USER))
    expired_user = {
        "authenticated": True,
        "username": "ryan",
        "token_exp": (datetime.now(UTC) - timedelta(seconds=1)).timestamp(),
    }

    still_valid = await handler.check_token_expiry(websocket, expired_user)

    assert still_valid is False
    assert websocket.closed_code == 1008


async def test_token_expiry_allows_missing_expiry_for_authenticated_user() -> None:
    """Authenticated websocket users without exp metadata are left connected."""
    handler = make_handler(Mock(auth_mode=AuthMode.SINGLE_USER))
    websocket = FakeWebSocket()

    assert await handler.check_token_expiry(websocket, {"authenticated": True}) is True
    assert websocket.closed_code is None


def test_remove_connection_deletes_tracked_user() -> None:
    """Connection removal clears tracked authenticated user info."""
    websocket = FakeWebSocket()
    handler = make_handler(Mock(auth_mode=AuthMode.SINGLE_USER))
    handler.authenticated_connections["127.0.0.1:4321"] = {"username": "ryan"}

    handler.remove_connection(websocket)

    assert handler.authenticated_connections == {}


async def test_require_permission_honors_admin_user_and_role_map() -> None:
    """Permission checks allow admin, allow mapped user roles, and deny readonly control."""
    websocket = FakeWebSocket()
    handler = make_handler(Mock(auth_mode=AuthMode.SINGLE_USER))

    assert await handler.require_permission(websocket, {"role": "admin"}, "anything") is True
    assert await handler.require_permission(websocket, {"role": "user"}, "control_entities") is True
    assert (
        await handler.require_permission(websocket, {"role": "readonly"}, "control_entities")
        is False
    )
