"""Regression tests: access tokens minted by ``SessionService`` keep identity.

The service-mode token lifecycle mints access tokens in :class:`SessionService`
(on session creation and on refresh). Historically both paths called
``TokenService.generate_access_token(user_id)`` with no claims, so a refreshed
token carried only ``sub``: ``/api/auth/me`` then reported an empty
username/email and defaulted ``role`` to ``"user"``. The UI rendered the bare
user_id (a UUID) in the sidebar and silently downgraded admins. These tests pin
the fix — identity claims stashed in the session's ``device_info`` are
re-attached to every minted access token.
"""

from datetime import UTC, datetime
from typing import Any

import jwt
import pytest

from backend.services.auth.sessions import SessionService
from backend.services.auth.tokens import TokenService

JWT_SECRET = "test-secret"  # noqa: S105
JWT_ALGORITHM = "HS256"


class _PassthroughMonitor:
    """Performance monitor stub: returns the method unwrapped."""

    def monitor_service_method(self, _service: str, _method: str, **_kwargs: Any):
        return lambda func: func


class _InMemorySessionRepo:
    """Minimal SessionRepository surface used by SessionService."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    async def get_active_session_count(self, _user_id: str) -> int:
        return 0

    async def get_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        return [s for s in self._sessions.values() if s["user_id"] == user_id]

    async def revoke_user_session(self, refresh_token: str) -> bool:
        return self._sessions.pop(refresh_token, None) is not None

    async def create_user_session(
        self,
        user_id: str,
        refresh_token: str,
        device_info: dict[str, Any],
        expires_at: datetime,
    ) -> bool:
        self._sessions[refresh_token] = {
            "user_id": user_id,
            "refresh_token": refresh_token,
            "device_info": device_info,
            "expires_at": expires_at,
            "created_at": datetime.now(UTC),
        }
        return True

    async def get_user_session(self, refresh_token: str) -> dict[str, Any] | None:
        return self._sessions.get(refresh_token)


def _decode(token: str) -> dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


@pytest.fixture
def service() -> SessionService:
    token_service = TokenService(
        jwt_secret=JWT_SECRET,
        jwt_algorithm=JWT_ALGORITHM,
        access_token_expire_minutes=15,
        magic_link_expire_minutes=15,
    )
    return SessionService(
        token_service=token_service,
        session_repository=_InMemorySessionRepo(),
        performance_monitor=_PassthroughMonitor(),
    )


DEVICE_INFO = {
    "username": "ryan",
    "email": "ryan@example.com",
    "role": "admin",
    "mode": "oidc",
    "provider": "pocketid",
    # Session bookkeeping that must NOT leak into the JWT.
    "fingerprint": "abc123",
    "user_agent": "pytest",
    "ip_subnet": "10.0.0",
}


@pytest.mark.asyncio
async def test_create_session_access_token_carries_identity(service: SessionService) -> None:
    access_token, _refresh = await service.create_session("user-uuid", dict(DEVICE_INFO))

    claims = _decode(access_token)
    assert claims["sub"] == "user-uuid"
    assert claims["username"] == "ryan"
    assert claims["email"] == "ryan@example.com"
    assert claims["role"] == "admin"
    assert claims["mode"] == "oidc"


@pytest.mark.asyncio
async def test_refreshed_access_token_preserves_identity(service: SessionService) -> None:
    _access, refresh_token = await service.create_session("user-uuid", dict(DEVICE_INFO))

    refreshed = await service.refresh_access_token(refresh_token)

    assert refreshed is not None
    claims = _decode(refreshed)
    # The whole point of the fix: a refresh must not degrade the identity.
    assert claims["sub"] == "user-uuid"
    assert claims["username"] == "ryan"
    assert claims["email"] == "ryan@example.com"
    assert claims["role"] == "admin"
    assert claims["mode"] == "oidc"


@pytest.mark.asyncio
async def test_minted_tokens_omit_session_bookkeeping(service: SessionService) -> None:
    access_token, refresh_token = await service.create_session("user-uuid", dict(DEVICE_INFO))
    refreshed = await service.refresh_access_token(refresh_token)

    for token in (access_token, refreshed):
        assert token is not None
        claims = _decode(token)
        assert "fingerprint" not in claims
        assert "user_agent" not in claims
        assert "ip_subnet" not in claims


@pytest.mark.asyncio
async def test_refresh_without_stored_identity_still_works(service: SessionService) -> None:
    # A session created without identity claims (e.g. a legacy row) must still
    # refresh; the token just falls back to bare defaults rather than crashing.
    _access, refresh_token = await service.create_session("user-uuid", {})

    refreshed = await service.refresh_access_token(refresh_token)

    assert refreshed is not None
    claims = _decode(refreshed)
    assert claims["sub"] == "user-uuid"
    assert "username" not in claims
