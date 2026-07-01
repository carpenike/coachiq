"""PocketID OIDC relying-party helpers."""

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from backend.core.config import AuthenticationSettings
from backend.models.auth import UserRole


class OIDCError(Exception):
    """Base error for OIDC login failures."""


class OIDCProviderUnavailableError(OIDCError):
    """Raised when PocketID metadata, JWKS, or token exchange is unavailable."""


class OIDCConfigurationError(OIDCError):
    """Raised when OIDC is disabled or missing required configuration."""


class OIDCStateError(OIDCError):
    """Raised when OIDC callback state is missing, expired, or replayed."""


class OIDCValidationError(OIDCError):
    """Raised when an OIDC response or ID token fails validation."""


@dataclass(frozen=True, slots=True)
class OIDCProviderMetadata:
    """Fetched OIDC provider metadata."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None = None

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "OIDCProviderMetadata":
        """Build provider metadata from a discovery document."""
        required_fields = ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")
        missing = [field for field in required_fields if not document.get(field)]
        if missing:
            msg = f"OIDC discovery document missing required fields: {', '.join(missing)}"
            raise OIDCValidationError(msg)
        return cls(
            issuer=str(document["issuer"]),
            authorization_endpoint=str(document["authorization_endpoint"]),
            token_endpoint=str(document["token_endpoint"]),
            jwks_uri=str(document["jwks_uri"]),
            userinfo_endpoint=document.get("userinfo_endpoint"),
        )


@dataclass(frozen=True, slots=True)
class OIDCLoginState:
    """Server-side single-use state for an OIDC authorization request."""

    state: str
    nonce: str
    code_verifier: str
    redirect_uri: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class OIDCSessionCode:
    """Short-lived local session token handoff payload."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_expires_in: int
    expires_at: float


class OIDCStateStore:
    """In-memory single-use OIDC state and PKCE verifier store."""

    def __init__(self, ttl_seconds: int) -> None:
        """Initialize the state store."""
        self._ttl_seconds = ttl_seconds
        self._states: dict[str, OIDCLoginState] = {}

    def create(self, redirect_uri: str) -> OIDCLoginState:
        """Create and store an OIDC login state."""
        self._purge_expired()
        state_value = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        login_state = OIDCLoginState(
            state=state_value,
            nonce=nonce,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            expires_at=time.monotonic() + self._ttl_seconds,
        )
        self._states[state_value] = login_state
        return login_state

    def consume(self, state: str) -> OIDCLoginState:
        """Consume an OIDC state exactly once."""
        self._purge_expired()
        login_state = self._states.pop(state, None)
        if login_state is None:
            msg = "OIDC state is invalid, expired, or already used"
            raise OIDCStateError(msg)
        return login_state

    def _purge_expired(self) -> None:
        """Remove expired states."""
        now = time.monotonic()
        expired = [state for state, value in self._states.items() if value.expires_at <= now]
        for state in expired:
            self._states.pop(state, None)


class OIDCSessionCodeStore:
    """In-memory single-use local token handoff store."""

    def __init__(self, ttl_seconds: int) -> None:
        """Initialize the session-code store."""
        self._ttl_seconds = ttl_seconds
        self._codes: dict[str, OIDCSessionCode] = {}

    def create(
        self,
        *,
        access_token: str,
        refresh_token: str,
        token_type: str,
        expires_in: int,
        refresh_expires_in: int,
    ) -> str:
        """Store token payload behind a short-lived one-time code."""
        self._purge_expired()
        code_value = secrets.token_urlsafe(32)
        self._codes[code_value] = OIDCSessionCode(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            expires_in=expires_in,
            refresh_expires_in=refresh_expires_in,
            expires_at=time.monotonic() + self._ttl_seconds,
        )
        return code_value

    def consume(self, code: str) -> OIDCSessionCode:
        """Consume a local session handoff code exactly once."""
        self._purge_expired()
        session_code = self._codes.pop(code, None)
        if session_code is None:
            msg = "OIDC session code is invalid, expired, or already used"
            raise OIDCStateError(msg)
        return session_code

    def _purge_expired(self) -> None:
        """Remove expired codes."""
        now = time.monotonic()
        expired = [code for code, value in self._codes.items() if value.expires_at <= now]
        for code in expired:
            self._codes.pop(code, None)


class OIDCClient:
    """PocketID OIDC client with bounded in-process metadata and JWKS caches."""

    def __init__(
        self,
        settings: AuthenticationSettings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the OIDC client."""
        self._settings = settings
        self._http_client = http_client or httpx.AsyncClient(
            timeout=settings.oidc_request_timeout_seconds,
            headers={"Accept": "application/json"},
        )
        self._owns_http_client = http_client is None
        self._metadata: OIDCProviderMetadata | None = None
        self._metadata_expires_at = 0.0
        self._jwks: dict[str, Any] | None = None
        self._jwks_expires_at = 0.0

    async def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_http_client:
            await self._http_client.aclose()

    async def get_authorization_url(self, login_state: OIDCLoginState) -> str:
        """Build the PocketID authorization URL using fetched discovery metadata."""
        self._ensure_enabled()
        metadata = await self.get_metadata()
        challenge = _pkce_challenge(login_state.code_verifier)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._settings.oidc_client_id,
                "redirect_uri": login_state.redirect_uri,
                "scope": " ".join(self._settings.oidc_scopes),
                "state": login_state.state,
                "nonce": login_state.nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{metadata.authorization_endpoint}?{query}"

    async def exchange_code(self, code: str, login_state: OIDCLoginState) -> dict[str, Any]:
        """Exchange an authorization code for PocketID tokens."""
        self._ensure_enabled()
        metadata = await self.get_metadata()
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": login_state.redirect_uri,
            "client_id": self._settings.oidc_client_id,
            "code_verifier": login_state.code_verifier,
        }
        if self._settings.oidc_client_secret:
            data["client_secret"] = self._settings.oidc_client_secret

        try:
            response = await self._http_client.post(metadata.token_endpoint, data=data)
            response.raise_for_status()
            token_response = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            msg = "PocketID token exchange failed"
            raise OIDCProviderUnavailableError(msg) from exc

        if not token_response.get("id_token"):
            msg = "PocketID token response did not include an ID token"
            raise OIDCValidationError(msg)
        return token_response

    async def validate_id_token(self, id_token: str, nonce: str) -> dict[str, Any]:
        """Validate an RS256 ID token using the fetched JWKS."""
        self._ensure_enabled()
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.InvalidTokenError as exc:
            msg = "ID token header is invalid"
            raise OIDCValidationError(msg) from exc

        if header.get("alg") != "RS256":
            msg = "ID token must use RS256"
            raise OIDCValidationError(msg)
        kid = header.get("kid")
        if not kid:
            msg = "ID token is missing a key id"
            raise OIDCValidationError(msg)

        signing_key = await self._get_signing_key(str(kid), refresh=False)
        if signing_key is None:
            signing_key = await self._get_signing_key(str(kid), refresh=True)
        if signing_key is None:
            msg = "No matching JWKS key found for ID token"
            raise OIDCValidationError(msg)

        try:
            claims = jwt.decode(
                id_token,
                signing_key,
                algorithms=["RS256"],
                audience=self._settings.oidc_client_id,
                issuer=self._settings.oidc_issuer.rstrip("/"),
                options={"require": ["aud", "exp", "iat", "iss", "nonce", "sub"]},
            )
        except jwt.InvalidTokenError as exc:
            msg = "ID token validation failed"
            raise OIDCValidationError(msg) from exc

        if claims.get("nonce") != nonce:
            msg = "ID token nonce does not match login state"
            raise OIDCValidationError(msg)
        return claims

    async def get_metadata(self, *, refresh: bool = False) -> OIDCProviderMetadata:
        """Fetch or return cached OIDC provider metadata."""
        self._ensure_enabled()
        now = time.monotonic()
        if not refresh and self._metadata and self._metadata_expires_at > now:
            return self._metadata

        discovery_url = f"{self._settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
        try:
            response = await self._http_client.get(discovery_url)
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            msg = "PocketID discovery is unavailable"
            raise OIDCProviderUnavailableError(msg) from exc

        metadata = OIDCProviderMetadata.from_document(document)
        if metadata.issuer.rstrip("/") != self._settings.oidc_issuer.rstrip("/"):
            msg = "PocketID discovery issuer does not match configured issuer"
            raise OIDCValidationError(msg)

        self._metadata = metadata
        self._metadata_expires_at = now + self._settings.oidc_discovery_ttl_seconds
        return metadata

    async def get_jwks(self, *, refresh: bool = False) -> dict[str, Any]:
        """Fetch or return cached JWKS."""
        self._ensure_enabled()
        now = time.monotonic()
        if not refresh and self._jwks and self._jwks_expires_at > now:
            return self._jwks

        metadata = await self.get_metadata()
        try:
            response = await self._http_client.get(metadata.jwks_uri)
            response.raise_for_status()
            jwks = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            msg = "PocketID JWKS is unavailable"
            raise OIDCProviderUnavailableError(msg) from exc

        if not isinstance(jwks.get("keys"), list):
            msg = "PocketID JWKS response is missing keys"
            raise OIDCValidationError(msg)
        self._jwks = jwks
        self._jwks_expires_at = now + self._settings.oidc_jwks_ttl_seconds
        return jwks

    def map_groups_to_role(self, groups: list[str]) -> UserRole:
        """Map PocketID groups to the highest configured CoachIQ role."""
        role_rank = {UserRole.READONLY: 0, UserRole.USER: 1, UserRole.ADMIN: 2}
        matched_roles = []
        for group in groups:
            mapped_role = self._settings.oidc_group_role_map.get(group)
            if mapped_role:
                matched_roles.append(UserRole(mapped_role))
        if not matched_roles:
            msg = "PocketID user is not a member of any authorized CoachIQ group"
            raise OIDCValidationError(msg)
        return max(matched_roles, key=lambda role: role_rank[role])

    async def _get_signing_key(self, kid: str, *, refresh: bool) -> Any | None:
        """Return the signing key for a JWKS key id."""
        jwks = await self.get_jwks(refresh=refresh)
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid:
                return jwt.PyJWK.from_dict(jwk).key
        return None

    def _ensure_enabled(self) -> None:
        """Ensure OIDC is enabled and minimally configured."""
        if not self._settings.oidc_enabled:
            msg = "OIDC login is disabled"
            raise OIDCConfigurationError(msg)
        if not self._settings.oidc_issuer or not self._settings.oidc_client_id:
            msg = "OIDC issuer and client ID are required when OIDC is enabled"
            raise OIDCConfigurationError(msg)


def _pkce_challenge(verifier: str) -> str:
    """Create an S256 PKCE challenge for a verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
