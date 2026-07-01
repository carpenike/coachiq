"""Tests for MCP OAuth authorize and callback federation flow."""

from dataclasses import dataclass
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.routers.mcp_oauth as mcp_oauth_router
from backend.api.routers.mcp_oauth import get_mcp_oauth_repository, router
from backend.core.config import AuthenticationSettings
from backend.core.dependencies import get_auth_service
from backend.models.auth import UserRole
from backend.services.auth.mcp_oauth_security import McpOAuthRateLimiter


@dataclass
class _Transaction:
    """Minimal AS transaction object for tests."""

    transaction_state: str = "tx-state"
    client_id: str = "client-1"
    redirect_uri: str = "https://claude.ai/callback"
    client_state: str | None = "client-state"
    client_code_challenge: str = "client-challenge"
    client_code_challenge_method: str = "S256"
    upstream_code_verifier: str = "as-pocketid-verifier"
    upstream_nonce: str = "as-pocketid-nonce"


class _Repository:
    """Fake repository for authorize/callback tests."""

    def __init__(self) -> None:
        self.created_transaction = None
        self.consumed = False
        self.auth_code = "as-auth-code"

    async def get_client(self, client_id: str):
        """Return a registered client."""
        if client_id != "client-1":
            return None
        return SimpleNamespace(
            client_id="client-1",
            redirect_uris=["https://claude.ai/callback"],
        )

    async def create_transaction(self, **kwargs):
        """Capture transaction data and return stored state."""
        self.created_transaction = kwargs
        return _Transaction(
            transaction_state="tx-state",
            client_id=kwargs["client_id"],
            redirect_uri=kwargs["redirect_uri"],
            client_state=kwargs["client_state"],
            client_code_challenge=kwargs["client_code_challenge"],
            client_code_challenge_method=kwargs["client_code_challenge_method"],
            upstream_code_verifier=kwargs["upstream_code_verifier"],
            upstream_nonce=kwargs["upstream_nonce"],
        )

    async def consume_transaction(self, state: str):
        """Consume transaction once."""
        assert state == "tx-state"
        if self.consumed:
            return None
        self.consumed = True
        return _Transaction()

    async def create_authorization_code(self, **kwargs):
        """Return a deterministic authorization code."""
        assert kwargs["code_challenge"] == "client-challenge"
        assert kwargs["code_challenge_method"] == "S256"
        return self.auth_code


class _OidcClient:
    """Fake HOF-047 OIDC client for AS-to-PocketID federation tests."""

    def __init__(self) -> None:
        self.authorization_state = None
        self.exchange_state = None

    async def get_authorization_url(self, login_state):
        """Capture AS-generated upstream login state."""
        self.authorization_state = login_state
        return f"https://id.holthome.net/authorize?state={login_state.state}"

    async def exchange_code(self, code, login_state):
        """Capture callback exchange state."""
        assert code == "pocketid-code"
        self.exchange_state = login_state
        return {"id_token": "id-token"}

    async def validate_id_token(self, id_token, nonce):
        """Return validated PocketID claims."""
        assert id_token == "id-token"
        assert nonce == "as-pocketid-nonce"
        return {
            "iss": "https://id.holthome.net",
            "sub": "pocketid-sub",
            "email": "user@example.test",
            "email_verified": True,
            "preferred_username": "user",
            "name": "Test User",
            "groups": ["coachiq-users"],
        }

    def map_groups_to_role(self, groups):
        """Return mapped CoachIQ user role."""
        assert groups == ["coachiq-users"]
        return UserRole.USER


class _AuthRepository:
    """Fake auth repository that verifies provider binding call shape."""

    async def upsert_federated_user(self, **kwargs):
        """Return a deterministic local user."""
        assert kwargs["provider_user_id"] == "pocketid-sub"
        assert kwargs["email_verified"] is True
        return SimpleNamespace(id="local-user", email="user@example.test", username="user")


class _AuthService:
    """Fake AuthService exposing HOF-047 OIDC RP pieces."""

    def __init__(self, oidc_client: _OidcClient) -> None:
        self._oidc_client = oidc_client
        self._auth_repository = _AuthRepository()
        self._auth_settings = AuthenticationSettings(
            oidc_enabled=True,
            oidc_client_id="coachiq-client",
            oidc_client_secret="client-secret",
            oidc_group_role_map={"coachiq-users": "user"},
        )

    def get_oidc_client(self):
        """Return fake OIDC client."""
        return self._oidc_client

    def get_auth_repository(self):
        """Return fake auth repository."""
        return self._auth_repository

    def get_auth_settings(self):
        """Return fake auth settings."""
        return self._auth_settings


def _client_for(repository: _Repository, auth_service: _AuthService) -> TestClient:
    """Create a test app for MCP OAuth authorize/callback endpoints."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_mcp_oauth_repository] = lambda: repository
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    mcp_oauth_router._authorize_rate_limiter = McpOAuthRateLimiter(limit=30, window_seconds=3600)
    return TestClient(app, follow_redirects=False)


def test_authorize_creates_separate_as_transaction_and_redirects_to_pocketid() -> None:
    """Authorize stores client PKCE and separate AS-to-PocketID verifier."""
    repository = _Repository()
    oidc_client = _OidcClient()
    client = _client_for(repository, _AuthService(oidc_client))

    response = client.get(
        "/oauth/authorize",
        params={
            "client_id": "client-1",
            "redirect_uri": "https://claude.ai/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "state": "client-state",
            "code_challenge": "client-challenge",
            "code_challenge_method": "S256",
        },
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://id.holthome.net/authorize")
    assert repository.created_transaction is not None
    assert repository.created_transaction["client_code_challenge"] == "client-challenge"
    assert repository.created_transaction["upstream_code_verifier"] != "client-challenge"
    assert oidc_client.authorization_state is not None
    assert oidc_client.authorization_state.code_verifier == repository.created_transaction[
        "upstream_code_verifier"
    ]


def test_authorize_rejects_plain_or_missing_pkce() -> None:
    """Authorize requires PKCE S256."""
    client = _client_for(_Repository(), _AuthService(_OidcClient()))

    response = client.get(
        "/oauth/authorize",
        params={
            "client_id": "client-1",
            "redirect_uri": "https://claude.ai/callback",
            "response_type": "code",
            "code_challenge": "client-challenge",
            "code_challenge_method": "plain",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_callback_reuses_oidc_client_and_issues_single_use_as_code() -> None:
    """Callback exchanges with PocketID, binds provider, and redirects with AS auth code."""
    repository = _Repository()
    oidc_client = _OidcClient()
    client = _client_for(repository, _AuthService(oidc_client))

    response = client.get(
        "/oauth/callback",
        params={"code": "pocketid-code", "state": "tx-state", "iss": "https://id.holthome.net"},
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "https://claude.ai/callback?code=as-auth-code&state=client-state"
    )
    assert oidc_client.exchange_state is not None
    assert oidc_client.exchange_state.code_verifier == "as-pocketid-verifier"
    assert oidc_client.exchange_state.code_verifier != "client-challenge"


def test_callback_transaction_is_single_use() -> None:
    """Callback consumes AS transaction state exactly once."""
    repository = _Repository()
    client = _client_for(repository, _AuthService(_OidcClient()))

    first = client.get(
        "/oauth/callback",
        params={"code": "pocketid-code", "state": "tx-state", "iss": "https://id.holthome.net"},
    )
    second = client.get(
        "/oauth/callback",
        params={"code": "pocketid-code", "state": "tx-state", "iss": "https://id.holthome.net"},
    )

    assert first.status_code == 302
    assert second.status_code == 400
    assert second.json()["error"] == "invalid_request"
