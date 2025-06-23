"""
Secure Authentication Middleware

Enhanced authentication middleware with HttpOnly cookie support for Domain API v2.
Provides automatic token refresh, secure cookie handling, and safety-critical
validation for vehicle control operations.
"""

import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.services.auth_manager import AuthManager, InvalidTokenError
from backend.services.secure_token_service import SecureTokenService

logger = logging.getLogger(__name__)


class SecureAuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Enhanced authentication middleware with secure token management.

    Features:
    - HttpOnly cookie authentication
    - Automatic access token refresh
    - Secure token rotation
    - Safety-critical endpoint protection
    - Transparent token renewal
    """

    # Endpoints that require authentication
    PROTECTED_ENDPOINTS = [
        "/api/v2/entities/control",
        "/api/v2/entities/bulk-control",
        "/api/v2/entities/control-safe",
        "/api/v2/entities/emergency-stop",
        "/api/v2/entities/clear-emergency-stop",
        "/api/schemas/validate/integrity",
    ]

    # Endpoints that bypass authentication
    PUBLIC_ENDPOINTS = [
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/auth/logout",
        "/api/schemas",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
        "/healthz",
        "/",
    ]

    def __init__(self, app):
        super().__init__(app)
        self.auth_manager: AuthManager | None = None
        self.token_service: SecureTokenService | None = None

    async def dispatch(self, request: Request, call_next):
        """Process request with secure authentication"""

        # Initialize services from ServiceRegistry if not already done
        if not self.auth_manager:
            try:
                from backend.core.dependencies import get_service_registry

                service_registry = get_service_registry()
                if service_registry.has_service("auth_manager"):
                    self.auth_manager = service_registry.get_service("auth_manager")
                    self.token_service = SecureTokenService(self.auth_manager)
                    logger.info("Secure authentication middleware initialized from ServiceRegistry")
            except Exception as e:
                logger.warning(f"Could not initialize secure auth middleware: {e}")

        # Skip authentication if services not available
        if not self.auth_manager or not self.token_service:
            logger.debug("Auth services not available, skipping authentication")
            return await call_next(request)

        # Check if endpoint requires authentication
        path = request.url.path

        # Public endpoints bypass authentication
        if any(path.startswith(endpoint) for endpoint in self.PUBLIC_ENDPOINTS):
            return await call_next(request)

        # Check if endpoint requires protection
        requires_auth = any(path.startswith(endpoint) for endpoint in self.PROTECTED_ENDPOINTS)

        if not requires_auth:
            # Non-protected endpoint, proceed without authentication
            return await call_next(request)

        # Perform authentication for protected endpoints
        auth_result = await self._authenticate_request(request)

        if not auth_result["authenticated"]:
            return self._create_auth_error_response(
                auth_result["error"], auth_result.get("status_code", 401)
            )

        # Add user info to request state
        request.state.user = auth_result["user"]
        request.state.token_refreshed = auth_result.get("token_refreshed", False)

        # Process the request
        response = await call_next(request)

        # Handle token refresh in response if needed
        if auth_result.get("new_tokens"):
            self._apply_token_refresh(response, auth_result["new_tokens"])

        return response

    async def _authenticate_request(self, request: Request) -> dict:
        """
        Authenticate a request using multiple token sources.

        Returns:
            Dict with authentication results and any new tokens
        """
        # Try Authorization header first
        auth_header = request.headers.get("Authorization")
        access_token = None
        if self.token_service:
            access_token = self.token_service.extract_access_token(auth_header)

        # If no Authorization header, check for refresh token in cookies
        refresh_token = None
        if not access_token:
            refresh_token = request.cookies.get("refresh_token")

        # Case 1: Valid access token provided
        if access_token and self.auth_manager:
            try:
                # Validate access token
                token_payload = self.auth_manager.validate_token(access_token)
                user_info = {
                    "user_id": token_payload["sub"],
                    "username": token_payload.get("username", ""),
                    "token_payload": token_payload,
                }

                # Check if token is near expiry and should be refreshed
                if self.token_service and self.token_service.is_token_near_expiry(access_token):
                    logger.debug("Access token near expiry, attempting refresh")

                    # Try to get refresh token from cookies for automatic refresh
                    cookie_refresh_token = request.cookies.get("refresh_token")
                    if cookie_refresh_token:
                        refresh_result = await self._attempt_token_refresh(cookie_refresh_token)
                        if refresh_result["success"]:
                            return {
                                "authenticated": True,
                                "user": user_info,
                                "token_refreshed": True,
                                "new_tokens": refresh_result["tokens"],
                            }

                return {"authenticated": True, "user": user_info, "token_refreshed": False}

            except InvalidTokenError as e:
                logger.debug(f"Access token validation failed: {e}")

                # Access token invalid, try refresh token if available
                if not refresh_token:
                    refresh_token = request.cookies.get("refresh_token")

        # Case 2: No valid access token, try refresh token
        if refresh_token:
            refresh_result = await self._attempt_token_refresh(refresh_token)
            if refresh_result["success"] and self.auth_manager:
                # Get user info from new access token
                new_access_token = refresh_result["tokens"]["access_token"]
                token_payload = self.auth_manager.validate_token(new_access_token)

                user_info = {
                    "user_id": token_payload["sub"],
                    "username": token_payload.get("username", ""),
                    "token_payload": token_payload,
                }

                return {
                    "authenticated": True,
                    "user": user_info,
                    "token_refreshed": True,
                    "new_tokens": refresh_result["tokens"],
                }
            return {
                "authenticated": False,
                "error": "Invalid or expired refresh token",
                "status_code": 401,
            }

        # Case 3: No valid tokens available
        return {"authenticated": False, "error": "Authentication required", "status_code": 401}

    async def _attempt_token_refresh(self, refresh_token: str) -> dict:
        """
        Attempt to refresh tokens using a refresh token.

        Returns:
            Dict with success status and new tokens if successful
        """
        try:
            if not self.token_service:
                return {"success": False, "error": "Token service not available"}

            refresh_result = await self.token_service.refresh_access_token(refresh_token)

            tokens = {
                "access_token": refresh_result.access_token,
                "access_token_expires_in": refresh_result.access_token_expires_in,
                "refresh_rotated": refresh_result.refresh_rotated,
                "new_refresh_token": refresh_result.new_refresh_token,
            }

            logger.info("Successfully refreshed access token")
            return {"success": True, "tokens": tokens}

        except InvalidTokenError as e:
            logger.warning(f"Token refresh failed: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {e}")
            return {"success": False, "error": "Token refresh system error"}

    def _apply_token_refresh(self, response: Response, tokens: dict) -> None:
        """
        Apply token refresh results to the response.

        Args:
            response: HTTP response to modify
            tokens: New token information
        """
        # Set new access token in header
        response.headers["X-Access-Token"] = tokens["access_token"]
        response.headers["X-Token-Type"] = "Bearer"
        response.headers["X-Expires-In"] = str(tokens["access_token_expires_in"])
        response.headers["X-Token-Refreshed"] = "true"

        # Update refresh token cookie if rotated
        if tokens["refresh_rotated"] and tokens["new_refresh_token"] and self.token_service:
            self.token_service.set_refresh_cookie(response, tokens["new_refresh_token"])
            response.headers["X-Refresh-Token-Rotated"] = "true"

        logger.debug("Applied token refresh to response")

    def _create_auth_error_response(
        self, error_message: str, status_code: int = 401
    ) -> JSONResponse:
        """Create standardized authentication error response"""

        return JSONResponse(
            status_code=status_code,
            content={
                "error": "authentication_required",
                "message": error_message,
                "safety_critical": True,
                "auth_endpoints": {"login": "/api/auth/login", "refresh": "/api/auth/refresh"},
            },
            headers={
                "WWW-Authenticate": "Bearer",
                "X-Auth-Required": "true",
                "X-Safety-Critical": "true",
            },
        )
