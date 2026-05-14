"""JWT token operations (stateless).

Extracted from the historical ``backend/services/auth_services.py`` in
audit cycle 2026-05-13 PR A9. The :class:`TokenService` body is moved
verbatim; only the surrounding imports and module docstring are new.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

logger = logging.getLogger(__name__)


class TokenService:
    """Service for JWT token operations (stateless)."""

    def __init__(
        self,
        jwt_secret: str,
        jwt_algorithm: str,
        access_token_expire_minutes: int,
        magic_link_expire_minutes: int,
    ):
        """Initialize the token service.

        Args:
            jwt_secret: Secret key for JWT signing
            jwt_algorithm: JWT algorithm to use
            access_token_expire_minutes: Access token expiration time
            magic_link_expire_minutes: Magic link token expiration time
        """
        self._jwt_secret = jwt_secret
        self._jwt_algorithm = jwt_algorithm
        self._access_token_expire_minutes = access_token_expire_minutes
        self._magic_link_expire_minutes = magic_link_expire_minutes

        logger.info("TokenService initialized")

    def generate_access_token(
        self,
        user_id: str,
        is_admin: bool = False,
        additional_claims: dict[str, Any] | None = None,
    ) -> str:
        """Generate a JWT access token.

        Args:
            user_id: User identifier
            is_admin: Whether user is admin
            additional_claims: Additional JWT claims

        Returns:
            JWT access token
        """
        expire = datetime.now(UTC) + timedelta(minutes=self._access_token_expire_minutes)

        claims = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.now(UTC),
            "type": "access",
            "admin": is_admin,
        }

        if additional_claims:
            claims.update(additional_claims)

        token = jwt.encode(claims, self._jwt_secret, algorithm=self._jwt_algorithm)

        logger.debug(f"Generated access token for user {user_id}")
        return token

    def validate_token(self, token: str) -> dict[str, Any] | None:
        """Validate and decode a JWT token.

        Args:
            token: JWT token to validate

        Returns:
            Decoded token claims or None if invalid
        """
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=[self._jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token validation failed: expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token validation failed: {e}")
            return None

    def generate_magic_link_token(self, email: str, expires_minutes: int | None = None) -> str:
        """Generate a magic link token.

        Args:
            email: Email address for the magic link
            expires_minutes: Custom expiration time

        Returns:
            Magic link token
        """
        expire_minutes = expires_minutes or self._magic_link_expire_minutes
        expire = datetime.now(UTC) + timedelta(minutes=expire_minutes)

        claims = {"sub": email, "exp": expire, "iat": datetime.now(UTC), "type": "magic_link"}

        token = jwt.encode(claims, self._jwt_secret, algorithm=self._jwt_algorithm)

        logger.debug(f"Generated magic link token for {email}")
        return token

    def decode_magic_link_token(self, token: str) -> str | None:
        """Decode a magic link token.

        Args:
            token: Magic link token

        Returns:
            Email address or None if invalid
        """
        payload = self.validate_token(token)

        if payload and payload.get("type") == "magic_link":
            return payload.get("sub")

        return None

    def generate_refresh_token(self) -> str:
        """Generate a secure refresh token.

        Returns:
            Refresh token
        """
        return secrets.token_urlsafe(32)
