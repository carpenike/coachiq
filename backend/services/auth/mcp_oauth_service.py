"""MCP OAuth AS protocol helpers."""

import base64
import hashlib
import secrets
from dataclasses import dataclass

from backend.services.auth.oidc import OIDCLoginState


@dataclass(frozen=True, slots=True)
class ClientPkceBinding:
    """Client-to-AS PKCE challenge binding."""

    code_challenge: str
    code_challenge_method: str


def create_upstream_login_state(redirect_uri: str) -> OIDCLoginState:
    """Create AS-to-PocketID OIDC login state with an independent PKCE verifier."""
    return OIDCLoginState(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        code_verifier=secrets.token_urlsafe(64),
        redirect_uri=redirect_uri,
        expires_at=0.0,
    )


def pkce_s256_challenge(verifier: str) -> str:
    """Return BASE64URL(SHA256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
