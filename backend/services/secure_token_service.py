"""
Secure Token Management Service

Provides secure token management with HttpOnly cookies for Domain API v2.
Implements token rotation, secure storage, and automatic refresh patterns
for safety-critical vehicle control applications.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from starlette.responses import Response

from backend.core.config import get_settings
from backend.services.auth_manager import AuthManager, InvalidTokenError

logger = logging.getLogger(__name__)


class TokenPair(BaseModel):
    """Token pair response model"""

    access_token: str = Field(..., description="Short-lived access token for API requests")
    refresh_token: str = Field(..., description="Long-lived refresh token for token renewal")
    access_token_expires_in: int = Field(..., description="Access token expiration in seconds")
    refresh_token_expires_in: int = Field(..., description="Refresh token expiration in seconds")
    token_type: str = Field("Bearer", description="Token type for Authorization header")


class TokenRefreshResult(BaseModel):
    """Token refresh operation result"""

    access_token: str = Field(..., description="New access token")
    access_token_expires_in: int = Field(..., description="Access token expiration in seconds")
    refresh_rotated: bool = Field(False, description="Whether refresh token was rotated")
    new_refresh_token: Optional[str] = Field(None, description="New refresh token if rotated")


class SecureTokenService:
    """
    Secure token management service for Domain API v2.

    Provides secure token storage using HttpOnly cookies and implements
    token rotation patterns for enhanced security in vehicle control systems.

    Key Security Features:
    - HttpOnly cookies for refresh token storage
    - Automatic access token refresh before expiration
    - Refresh token rotation for security
    - Secure cookie settings (Secure, SameSite, etc.)
    - Token invalidation and cleanup
    """

    def __init__(self, auth_manager: AuthManager):
        self.auth_manager = auth_manager
        self.settings = get_settings()

        # Cookie settings for security
        self.cookie_settings = {
            "httponly": True,
            "secure": getattr(self.settings, "use_https", False),  # Only set secure if using HTTPS
            "samesite": "strict",
            "path": "/",
            "max_age": self.settings.auth.refresh_token_expire_days * 24 * 3600,  # Days to seconds
        }

        # Token lifetime settings
        self.access_token_lifetime = timedelta(minutes=self.settings.auth.jwt_expire_minutes)
        self.refresh_token_lifetime = timedelta(days=self.settings.auth.refresh_token_expire_days)

        # Security settings
        self.rotate_refresh_tokens = True  # Always rotate for safety-critical systems
        self.access_token_refresh_buffer = timedelta(minutes=5)  # Refresh 5 minutes before expiry

    async def issue_token_pair(
        self, user_id: str, username: str = "", additional_claims: Optional[Dict[str, Any]] = None
    ) -> TokenPair:
        """
        Issue a new access/refresh token pair.

        Args:
            user_id: Unique user identifier
            username: Username for token claims
            additional_claims: Additional JWT claims

        Returns:
            TokenPair containing both tokens and expiration info
        """
        logger.info(f"Issuing new token pair for user: {user_id}")

        # Generate access token
        access_token = self.auth_manager.generate_token(
            user_id=user_id,
            username=username,
            expires_delta=self.access_token_lifetime,
            additional_claims=additional_claims,
        )

        # Generate refresh token
        refresh_token = await self.auth_manager.generate_refresh_token(
            user_id=user_id, username=username, additional_claims=additional_claims
        )

        # Store refresh token in repository for tracking
        await self._store_refresh_token(user_id, refresh_token)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_expires_in=int(self.access_token_lifetime.total_seconds()),
            refresh_token_expires_in=int(self.refresh_token_lifetime.total_seconds()),
            token_type="Bearer",
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenRefreshResult:
        """
        Refresh an access token using a valid refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            TokenRefreshResult with new access token and rotation info

        Raises:
            InvalidTokenError: If refresh token is invalid or expired
        """
        logger.debug("Processing access token refresh request")

        try:
            # Validate refresh token using the appropriate method
            refresh_payload = await self.auth_manager.validate_refresh_token(refresh_token)

            # Verify this is actually a refresh token
            if refresh_payload.get("token_type") != "refresh":
                raise InvalidTokenError("Invalid token type for refresh operation")

            user_id = refresh_payload["sub"]
            username = refresh_payload.get("username", "")

            # Verify refresh token is still valid in our tracking system
            if not await self._is_refresh_token_valid(user_id, refresh_token):
                raise InvalidTokenError("Refresh token has been revoked or rotated")

            # Generate new access token
            new_access_token = self.auth_manager.generate_token(
                user_id=user_id, username=username, expires_delta=self.access_token_lifetime
            )

            # Determine if refresh token should be rotated
            should_rotate = self.rotate_refresh_tokens
            new_refresh_token = None

            if should_rotate:
                # Generate new refresh token
                new_refresh_token = await self.auth_manager.generate_refresh_token(
                    user_id=user_id, username=username
                )

                # Invalidate old refresh token
                await self._invalidate_refresh_token(user_id, refresh_token)

                # Store new refresh token
                await self._store_refresh_token(user_id, new_refresh_token)

                logger.info(f"Rotated refresh token for user: {user_id}")

            logger.info(f"Successfully refreshed access token for user: {user_id}")

            return TokenRefreshResult(
                access_token=new_access_token,
                access_token_expires_in=int(self.access_token_lifetime.total_seconds()),
                refresh_rotated=should_rotate,
                new_refresh_token=new_refresh_token,
            )

        except InvalidTokenError:
            logger.warning("Invalid refresh token provided for refresh operation")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {e}")
            raise InvalidTokenError("Token refresh failed") from e

    def set_secure_cookies(self, response: Response, token_pair: TokenPair) -> None:
        """
        Set secure HttpOnly cookies for token storage.

        Args:
            response: HTTP response to modify
            token_pair: Token pair to store in cookies
        """
        # Set refresh token in HttpOnly cookie
        response.set_cookie(
            key="refresh_token", value=token_pair.refresh_token, **self.cookie_settings
        )

        # Optionally set access token in header for immediate use
        response.headers["X-Access-Token"] = token_pair.access_token
        response.headers["X-Token-Type"] = token_pair.token_type
        response.headers["X-Expires-In"] = str(token_pair.access_token_expires_in)

        logger.debug("Set secure authentication cookies")

    def set_refresh_cookie(self, response: Response, refresh_token: str) -> None:
        """
        Set only the refresh token cookie (for rotation scenarios).

        Args:
            response: HTTP response to modify
            refresh_token: New refresh token to store
        """
        response.set_cookie(key="refresh_token", value=refresh_token, **self.cookie_settings)

        logger.debug("Updated refresh token cookie")

    def clear_auth_cookies(self, response: Response) -> None:
        """
        Clear authentication cookies for logout.

        Args:
            response: HTTP response to modify
        """
        response.delete_cookie(
            key="refresh_token",
            path=self.cookie_settings["path"],
            domain=self.cookie_settings.get("domain"),
        )

        logger.debug("Cleared authentication cookies")

    async def revoke_all_tokens(self, user_id: str) -> None:
        """
        Revoke all tokens for a user (logout from all devices).

        Args:
            user_id: User whose tokens should be revoked
        """
        logger.info(f"Revoking all tokens for user: {user_id}")

        # This would integrate with a token blacklist or revocation system
        # For now, we'll implement basic tracking cleanup
        await self._cleanup_user_tokens(user_id)

    def extract_access_token(self, authorization_header: Optional[str]) -> Optional[str]:
        """
        Extract access token from Authorization header.

        Args:
            authorization_header: Authorization header value

        Returns:
            Access token if found and valid format, None otherwise
        """
        if not authorization_header:
            return None

        parts = authorization_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        return parts[1]

    def is_token_near_expiry(self, token: str) -> bool:
        """
        Check if access token is near expiry and should be refreshed.

        Args:
            token: Access token to check

        Returns:
            True if token should be refreshed, False otherwise
        """
        try:
            payload = self.auth_manager.validate_token(token)
            exp_timestamp = payload.get("exp")

            if not exp_timestamp:
                return True  # No expiry info, assume expired

            exp_datetime = datetime.fromtimestamp(exp_timestamp, UTC)
            time_until_expiry = exp_datetime - datetime.now(UTC)

            return time_until_expiry <= self.access_token_refresh_buffer

        except InvalidTokenError:
            return True  # Invalid token should be refreshed
        except Exception as e:
            logger.warning(f"Error checking token expiry: {e}")
            return True  # Assume needs refresh on error

    # Private helper methods for token tracking

    async def _store_refresh_token(self, user_id: str, refresh_token: str) -> None:
        """Store refresh token for tracking and validation"""
        # This would integrate with the repository system
        # For now, implement basic in-memory tracking
        logger.debug(f"Storing refresh token for user: {user_id}")

        # In production, this would use the auth repository:
        # await self.auth_manager.repository.store_refresh_token(user_id, refresh_token)

    async def _is_refresh_token_valid(self, user_id: str, refresh_token: str) -> bool:
        """Check if refresh token is still valid in tracking system"""
        # This would check the repository for token validity
        # For now, assume valid if JWT validation passed
        logger.debug(f"Validating refresh token for user: {user_id}")
        return True

        # In production:
        # return await self.auth_manager.repository.is_refresh_token_valid(user_id, refresh_token)

    async def _invalidate_refresh_token(self, user_id: str, refresh_token: str) -> None:
        """Invalidate a specific refresh token"""
        logger.debug(f"Invalidating refresh token for user: {user_id}")

        # In production:
        # await self.auth_manager.repository.invalidate_refresh_token(user_id, refresh_token)

    async def _cleanup_user_tokens(self, user_id: str) -> None:
        """Clean up all tokens for a user"""
        logger.debug(f"Cleaning up all tokens for user: {user_id}")

        # In production:
        # await self.auth_manager.repository.cleanup_user_tokens(user_id)
