"""Tests for PocketID OIDC client helpers."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.core.config import AuthenticationSettings
from backend.models.auth import UserRole
from backend.services.auth.oidc import (
    OIDCClient,
    OIDCStateError,
    OIDCStateStore,
    OIDCValidationError,
)


def _oidc_settings(**overrides: object) -> AuthenticationSettings:
    """Create enabled OIDC settings for tests."""
    values = {
        "oidc_enabled": True,
        "oidc_client_id": "coachiq-client",
        "oidc_client_secret": "client-secret",
        "oidc_group_role_map": {"coachiq-admins": "admin", "coachiq-users": "user"},
        "oidc_request_timeout_seconds": 1.0,
        "oidc_discovery_ttl_seconds": 300,
        "oidc_jwks_ttl_seconds": 300,
    }
    values.update(overrides)
    return AuthenticationSettings(**values)


@pytest.mark.asyncio
async def test_discovery_document_is_fetched_and_cached() -> None:
    """Discovery is fetched at runtime and cached within its TTL."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/.well-known/openid-configuration"
        return httpx.Response(
            200,
            json={
                "issuer": "https://id.holthome.net",
                "authorization_endpoint": "https://id.holthome.net/authorize",
                "token_endpoint": "https://id.holthome.net/api/oidc/token",
                "jwks_uri": "https://id.holthome.net/.well-known/jwks.json",
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OIDCClient(_oidc_settings(), http_client=http_client)

    first = await client.get_metadata()
    second = await client.get_metadata()

    assert first is second
    assert first.issuer == "https://id.holthome.net"
    assert calls == 1
    await http_client.aclose()


@pytest.mark.asyncio
async def test_id_token_validation_refreshes_jwks_for_unknown_kid() -> None:
    """Unknown ID-token kid triggers one JWKS refresh before failing/succeeding."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "current-key", "use": "sig", "alg": "RS256"})
    stale_key = dict(public_jwk)
    stale_key["kid"] = "stale-key"
    id_token = jwt.encode(
        {
            "iss": "https://id.holthome.net",
            "aud": "coachiq-client",
            "sub": "pocketid-sub",
            "nonce": "nonce-value",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "current-key"},
    )
    jwks_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal jwks_calls
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": "https://id.holthome.net",
                    "authorization_endpoint": "https://id.holthome.net/authorize",
                    "token_endpoint": "https://id.holthome.net/api/oidc/token",
                    "jwks_uri": "https://id.holthome.net/.well-known/jwks.json",
                },
            )
        if request.url.path == "/.well-known/jwks.json":
            jwks_calls += 1
            keys = [stale_key] if jwks_calls == 1 else [public_jwk]
            return httpx.Response(200, json={"keys": keys})
        return httpx.Response(404)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OIDCClient(_oidc_settings(), http_client=http_client)

    claims = await client.validate_id_token(id_token, nonce="nonce-value")

    assert claims["sub"] == "pocketid-sub"
    assert jwks_calls == 2
    await http_client.aclose()


def test_group_role_map_is_fail_closed_and_uses_highest_role() -> None:
    """Mapped groups are required and the highest mapped role wins."""
    client = OIDCClient(_oidc_settings())

    assert client.map_groups_to_role(["coachiq-users", "coachiq-admins"]) == UserRole.ADMIN
    with pytest.raises(OIDCValidationError):
        client.map_groups_to_role(["unmapped"])


@pytest.mark.asyncio
async def test_state_store_is_single_use() -> None:
    """OIDC state records are consumed exactly once."""
    store = OIDCStateStore(ttl_seconds=60)
    login_state = store.create("https://iq.holtel.io/api/v1/auth/oidc/callback")

    assert store.consume(login_state.state) == login_state
    with pytest.raises(OIDCStateError):
        store.consume(login_state.state)
