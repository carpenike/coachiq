"""Tests for the v1 OIDC auth domain router."""

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.domains.auth import register_auth_domain_router
from backend.core.config import AuthenticationSettings
from backend.core.dependencies import get_auth_service
from backend.models.auth import UserRole
from backend.services.auth.oidc import (
    OIDCLoginState,
    OIDCProviderUnavailableError,
    OIDCSessionCodeStore,
)

ID_TOKEN = "id-token"  # noqa: S105
LOCAL_ACCESS_TOKEN = "local-access-token"  # noqa: S105
LOCAL_REFRESH_TOKEN = "local-refresh-token"  # noqa: S105
TEST_ACCESS_TOKEN = "access"  # noqa: S105
TEST_REFRESH_TOKEN = "refresh"  # noqa: S105
TOKEN_TYPE_BEARER = "bearer"  # noqa: S105
EXISTING_SESSION_TOKEN = "existing-session-token"  # noqa: S105


@dataclass
class _User:
    """Minimal user object returned by the fake auth repository."""

    id: str = "user-1"
    email: str = "user@example.test"
    username: str = "user"


class _AuthManagerSettings:
    """Minimal AuthManager settings for token lifetimes."""

    enable_refresh_tokens = True
    jwt_expire_minutes = 15
    refresh_token_expire_days = 7


class _AuthManager:
    """Minimal AuthManager facade for OIDC callback tests."""

    settings = _AuthManagerSettings()

    def generate_token(self, **_kwargs) -> str:
        """Return a deterministic access token."""
        return LOCAL_ACCESS_TOKEN

    async def generate_refresh_token(self, **_kwargs) -> str:
        """Return a deterministic refresh token."""
        return LOCAL_REFRESH_TOKEN

    def validate_token(self, token: str) -> dict[str, str]:
        """Return deterministic claims for an existing local session."""
        assert token == EXISTING_SESSION_TOKEN
        return {"sub": "local-user", "role": "admin"}


class _AuthRepository:
    """Minimal auth repository facade for OIDC callback tests."""

    async def upsert_federated_user(self, **_kwargs) -> _User:
        """Return a deterministic local user."""
        return _User()


class _OIDCClient:
    """Minimal OIDC client facade for callback tests."""

    async def exchange_code(self, code, login_state):
        """Return a token response for the fake authorization code."""
        assert code == "pocketid-code"
        assert login_state.nonce == "nonce-value"
        return {"id_token": ID_TOKEN}

    async def validate_id_token(self, id_token, nonce):
        """Return validated PocketID claims."""
        assert id_token == ID_TOKEN
        assert nonce == "nonce-value"
        return {
            "iss": "https://id.holthome.net",
            "sub": "pocketid-sub",
            "email": "user@example.test",
            "preferred_username": "user",
            "name": "Test User",
            "groups": ["coachiq-admins"],
        }

    def map_groups_to_role(self, groups):
        """Map the fake PocketID group to admin."""
        assert groups == ["coachiq-admins"]
        return UserRole.ADMIN


class _UnavailableOIDCClient:
    """OIDC client facade that simulates a PocketID outage."""

    async def get_authorization_url(self, _login_state):
        """Raise the same error as an unreachable discovery endpoint."""
        raise OIDCProviderUnavailableError("PocketID unavailable")


class _StateStore:
    """Minimal single-use state store facade."""

    def create(self, redirect_uri: str) -> OIDCLoginState:
        """Return a deterministic login state for login initiation."""
        return OIDCLoginState(
            state="state-value",
            nonce="nonce-value",
            code_verifier="verifier",
            redirect_uri=redirect_uri,
            expires_at=999999.0,
        )

    def consume(self, state: str) -> OIDCLoginState:
        """Return a deterministic login state."""
        assert state == "state-value"
        return OIDCLoginState(
            state="state-value",
            nonce="nonce-value",
            code_verifier="verifier",
            redirect_uri="/api/v1/auth/oidc/callback",
            expires_at=999999.0,
        )


class _AuthService:
    """Minimal AuthService facade for the OIDC domain router."""

    def __init__(self, *, oidc_enabled: bool = True, oidc_unavailable: bool = False) -> None:
        """Initialize fake auth service."""
        self.settings = AuthenticationSettings(
            oidc_enabled=oidc_enabled,
            oidc_client_id="coachiq-client",
            oidc_client_secret="client-secret",
            oidc_group_role_map={"coachiq-admins": "admin"},
            oidc_failure_redirect_path="/login?oidc_error=sso_unavailable",
            oidc_frontend_callback_path="/auth/oidc/callback",
        )
        self.session_store = OIDCSessionCodeStore(ttl_seconds=60)
        self.oidc_unavailable = oidc_unavailable
        self.auth_manager = _AuthManager()

    def get_auth_settings(self):
        """Return fake typed auth settings."""
        return self.settings

    def get_oidc_client(self):
        """Return fake OIDC client when enabled."""
        if not self.settings.oidc_enabled:
            return None
        if self.oidc_unavailable:
            return _UnavailableOIDCClient()
        return _OIDCClient()

    def get_oidc_state_store(self):
        """Return fake OIDC state store when enabled."""
        return _StateStore() if self.settings.oidc_enabled else None

    def get_oidc_session_code_store(self):
        """Return real session-code store."""
        return self.session_store

    def get_auth_manager(self):
        """Return fake AuthManager."""
        return self.auth_manager

    def get_auth_repository(self):
        """Return fake auth repository."""
        return _AuthRepository()


def _client_for(auth_service: _AuthService) -> TestClient:
    """Create a test client with the auth domain router mounted."""
    app = FastAPI()
    app.include_router(register_auth_domain_router(), prefix="/api/v1/auth")
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    return TestClient(app, follow_redirects=False)


def test_oidc_login_unavailable_redirects_to_local_login() -> None:
    """PocketID outage/disabled state fails cleanly without a 500."""
    client = _client_for(_AuthService(oidc_enabled=False))

    response = client.get("/api/v1/auth/oidc/login")

    assert response.status_code == 307
    assert response.headers["location"] == (
        "/login?oidc_error=sso_unavailable&reason=sso_unavailable"
    )


def test_oidc_unreachable_preserves_existing_local_sessions() -> None:
    """PocketID outage only blocks fresh SSO and leaves local sessions valid."""
    auth_service = _AuthService(oidc_unavailable=True)
    client = _client_for(auth_service)

    response = client.get("/api/v1/auth/oidc/login")
    existing_session = auth_service.get_auth_manager().validate_token(EXISTING_SESSION_TOKEN)

    assert response.status_code == 307
    assert response.headers["location"] == (
        "/login?oidc_error=sso_unavailable&reason=sso_unavailable"
    )
    assert existing_session == {"sub": "local-user", "role": "admin"}


def test_oidc_session_code_exchange_is_single_use() -> None:
    """Frontend exchanges a one-time session code for local tokens."""
    auth_service = _AuthService()
    code = auth_service.session_store.create(
        access_token=TEST_ACCESS_TOKEN,
        refresh_token=TEST_REFRESH_TOKEN,
        token_type=TOKEN_TYPE_BEARER,
        expires_in=900,
        refresh_expires_in=604800,
    )
    client = _client_for(auth_service)

    response = client.get(f"/api/v1/auth/oidc/callback?session_code={code}")
    replay = client.get(f"/api/v1/auth/oidc/callback?session_code={code}")

    assert response.status_code == 200
    assert response.json()["access_token"] == TEST_ACCESS_TOKEN
    assert replay.status_code == 400


def test_oidc_callback_redirects_with_one_time_local_session_code() -> None:
    """Valid PocketID callback mints local tokens behind a one-time handoff code."""
    auth_service = _AuthService()
    client = _client_for(auth_service)

    response = client.get(
        "/api/v1/auth/oidc/callback?code=pocketid-code&state=state-value&iss=https://id.holthome.net"
    )

    assert response.status_code == 307
    assert response.headers["location"].startswith("/auth/oidc/callback?code=")
    handoff_code = response.headers["location"].split("code=", 1)[1]
    token_response = client.get(f"/api/v1/auth/oidc/callback?session_code={handoff_code}")
    assert token_response.status_code == 200
    assert token_response.json()["access_token"] == LOCAL_ACCESS_TOKEN
