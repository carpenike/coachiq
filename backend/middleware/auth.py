"""
Authentication Middleware

This module provides authentication middleware for FastAPI applications.
It handles JWT token validation and request authentication based on the
configured authentication mode.
"""

import logging
from typing import Annotated, ClassVar

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security.utils import get_authorization_scheme_param
from starlette.middleware.base import BaseHTTPMiddleware

from backend.services.auth_manager import AuthManager, AuthMode, InvalidTokenError

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for FastAPI applications.

    This middleware handles authentication for all requests based on the
    configured authentication mode:
    - NONE: All requests are allowed (no authentication)
    - SINGLE_USER: JWT token required for protected endpoints
    - MULTI_USER: JWT token required for protected endpoints

    The middleware allows certain endpoints to be excluded from authentication
    requirements (e.g., login, status, documentation).
    """

    # Endpoints that don't require authentication
    EXCLUDED_PATHS: ClassVar[set[str]] = {
        # Health and documentation endpoints
        "/",
        "/health",
        "/healthz",
        "/readyz",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        # Initial authentication endpoints (users not yet authenticated)
        "/api/auth/login",
        "/api/auth/login-step",  # First step of MFA login flow
        "/api/auth/login-mfa",  # Complete login after MFA verification
        "/api/auth/status",  # Authentication system status (public info)
        "/api/auth/me",  # Current user info (returns 401 if not authenticated)
        # Token management (refresh tokens work when access token expires)
        "/api/auth/refresh",
        "/api/auth/revoke",
        "/api/auth/logout",  # Logout should work even with expired access token
        # Magic link authentication (passwordless auth flow)
        "/api/auth/magic-link",  # Request magic link
        "/api/auth/magic",  # Verify magic link token
        # User invitation flow (public access needed)
        "/api/auth/invitation/accept",  # Accept invitation via link
        # Admin credential retrieval (one-time display of auto-generated credentials)
        "/api/auth/admin/credentials",  # Auto-generated admin credentials
        # WebSocket endpoints (handled separately)
        "/ws",
    }

    # Path prefixes that don't require authentication
    EXCLUDED_PREFIXES: ClassVar[set[str]] = {
        "/static",
        "/assets",
        "/favicon",
    }

    def __init__(self, app, auth_manager: AuthManager | None = None):
        """
        Initialize the authentication middleware.

        Args:
            app: FastAPI application instance
            auth_manager: Authentication manager instance (optional)
        """
        super().__init__(app)
        self.auth_manager = auth_manager
        self._auth_service = None  # Cache the AuthService separately
        self.logger = logging.getLogger(__name__)

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process incoming requests and apply authentication as needed.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            Response: HTTP response from the route handler

        Raises:
            HTTPException: If authentication is required but fails
        """
        # Get auth manager from ServiceRegistry if not provided during init
        # We need to check this each time because AuthService might not be started initially
        auth_manager = self.auth_manager
        if not auth_manager or (
            hasattr(auth_manager, "get_auth_manager") and not isinstance(auth_manager, AuthManager)
        ):
            try:
                from backend.core.dependencies import get_service_registry

                service_registry = get_service_registry()
                if service_registry.has_service("auth_manager"):
                    # Get the service from registry
                    auth_service = service_registry.get_service("auth_manager")

                    # Try to get the actual AuthManager from AuthService
                    if hasattr(auth_service, "get_auth_manager"):
                        auth_mgr = auth_service.get_auth_manager()
                        if auth_mgr:
                            auth_manager = auth_mgr
                            self.auth_manager = auth_mgr  # Cache for next time
                            self.logger.debug("Got AuthManager from AuthService")
                        else:
                            # Service not started yet, skip auth for now
                            auth_manager = None
                            self.logger.debug(
                                "AuthService.get_auth_manager() returned None - service may not be started yet"
                            )
                    elif hasattr(auth_service, "auth_mode"):
                        # It's already an AuthManager
                        auth_manager = auth_service
                        self.auth_manager = auth_service
                        self.logger.debug("Using service directly as auth_manager")
                    else:
                        auth_manager = None
                        self.logger.debug("Service does not appear to be an AuthManager")
                else:
                    # No auth manager available
                    auth_manager = None
                    self.logger.debug("Auth manager service not found in ServiceRegistry")
            except Exception as e:
                auth_manager = None
                self.logger.debug(f"Could not get auth manager: {e}")

        # Skip authentication if no auth manager available
        if not auth_manager:
            self.logger.debug("No auth manager available, skipping authentication")
            return await call_next(request)

        # Skip authentication for excluded paths
        if self._is_excluded_path(request.url.path):
            self.logger.debug(f"Skipping authentication for excluded path: {request.url.path}")
            return await call_next(request)

        # Skip authentication if mode is NONE
        if auth_manager.auth_mode == AuthMode.NONE:
            self.logger.debug("Authentication mode is NONE, allowing request")
            # Add default user to request state for consistency
            request.state.user = {
                "user_id": "admin",
                "username": "admin",
                "email": "admin@localhost",
                "role": "admin",
                "authenticated": True,
            }
            return await call_next(request)

        # Extract and validate token
        try:
            token = self._extract_token_from_request(request)

            if not token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Validate token
            payload = auth_manager.validate_token(token)

            # Add user info to request state
            request.state.user = {
                "user_id": payload.get("sub"),
                "username": payload.get("username", ""),
                "email": payload.get("email", ""),
                "role": payload.get("role", "user"),
                "authenticated": True,
            }

            self.logger.debug(f"Authenticated user: {payload.get('sub')}")

        except InvalidTokenError as e:
            self.logger.warning(f"Invalid token for {request.url.path}: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            self.logger.error(f"Authentication error for {request.url.path}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service error",
            ) from e

        # Continue to the next middleware or route handler
        return await call_next(request)

    def _is_excluded_path(self, path: str) -> bool:
        """
        Check if a path should be excluded from authentication.

        Args:
            path: Request path

        Returns:
            bool: True if the path should be excluded
        """
        # Check exact matches
        if path in self.EXCLUDED_PATHS:
            return True

        # Check prefix matches
        return any(path.startswith(prefix) for prefix in self.EXCLUDED_PREFIXES)

    def _extract_token_from_request(self, request: Request) -> str | None:
        """
        Extract JWT token from the request Authorization header.

        Args:
            request: HTTP request

        Returns:
            Optional[str]: JWT token if present, None otherwise
        """
        authorization = request.headers.get("Authorization")
        if not authorization:
            return None

        scheme, param = get_authorization_scheme_param(authorization)
        if scheme.lower() != "bearer":
            return None

        return param


class OptionalAuthenticationMiddleware(AuthenticationMiddleware):
    """
    Optional authentication middleware that doesn't raise errors for missing tokens.

    This variant of the authentication middleware will attempt to authenticate
    requests but won't raise HTTP exceptions if authentication fails. Instead,
    it sets request.state.user to None for unauthenticated requests.

    This is useful for endpoints that can work with or without authentication.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process requests with optional authentication.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            Response: HTTP response from the route handler
        """
        # Get auth manager from ServiceRegistry if not provided during init
        # We need to check this each time because AuthService might not be started initially
        auth_manager = self.auth_manager
        if not auth_manager or (
            hasattr(auth_manager, "get_auth_manager") and not isinstance(auth_manager, AuthManager)
        ):
            try:
                from backend.core.dependencies import get_service_registry

                service_registry = get_service_registry()
                if service_registry.has_service("auth_manager"):
                    # Get the service from registry
                    auth_service = service_registry.get_service("auth_manager")

                    # Try to get the actual AuthManager from AuthService
                    if hasattr(auth_service, "get_auth_manager"):
                        auth_mgr = auth_service.get_auth_manager()
                        if auth_mgr:
                            auth_manager = auth_mgr
                            self.auth_manager = auth_mgr  # Cache for next time
                            self.logger.debug("Got AuthManager from AuthService (optional)")
                        else:
                            # Service not started yet, skip auth for now
                            auth_manager = None
                            self.logger.debug(
                                "AuthService.get_auth_manager() returned None - service may not be started yet (optional)"
                            )
                    elif hasattr(auth_service, "auth_mode"):
                        # It's already an AuthManager
                        auth_manager = auth_service
                        self.auth_manager = auth_service
                        self.logger.debug("Using service directly as auth_manager (optional)")
                    else:
                        auth_manager = None
                        self.logger.debug("Service does not appear to be an AuthManager (optional)")
                else:
                    # No auth manager available
                    auth_manager = None
                    self.logger.debug("Auth manager service not found in ServiceRegistry")
            except Exception as e:
                auth_manager = None
                self.logger.debug(f"Could not get auth manager: {e}")

        # Set default unauthenticated state
        request.state.user = None

        # Skip authentication if no auth manager available
        if not auth_manager:
            self.logger.debug("No auth manager available")
            return await call_next(request)

        # Skip authentication for excluded paths
        if self._is_excluded_path(request.url.path):
            return await call_next(request)

        # Always allow in NONE mode with default admin user
        if auth_manager.auth_mode == AuthMode.NONE:
            request.state.user = {
                "user_id": "admin",
                "username": "admin",
                "email": "admin@localhost",
                "role": "admin",
                "authenticated": True,
            }
            return await call_next(request)

        # Try to authenticate but don't fail if token is missing or invalid
        try:
            token = self._extract_token_from_request(request)

            if token:
                payload = auth_manager.validate_token(token)
                request.state.user = {
                    "user_id": payload.get("sub"),
                    "username": payload.get("username", ""),
                    "email": payload.get("email", ""),
                    "role": payload.get("role", "user"),
                    "authenticated": True,
                }
                self.logger.debug(f"Optionally authenticated user: {payload.get('sub')}")

        except (InvalidTokenError, Exception) as e:
            self.logger.debug(f"Optional authentication failed for {request.url.path}: {e}")
            # Keep request.state.user as None for failed authentication

        return await call_next(request)


# Modern dependency injection patterns for authentication
# These replace the legacy get_*_from_request functions


def get_current_user(request: Request) -> dict | None:
    """
    Get the current authenticated user from the request state.

    This is a modern dependency that can be used with FastAPI's
    dependency injection system.

    Args:
        request: FastAPI request object

    Returns:
        Optional[dict]: User information if authenticated, None otherwise
    """
    return getattr(request.state, "user", None)


def get_authenticated_user(request: Request) -> dict:
    """
    Get the authenticated user, raising an exception if not authenticated.

    This is a modern dependency that ensures authentication.

    Args:
        request: FastAPI request object

    Returns:
        dict: User information

    Raises:
        HTTPException: If the request is not authenticated
    """
    user = get_current_user(request)
    if not user or not user.get("authenticated"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return user


def get_admin_user(request: Request) -> dict:
    """
    Get the authenticated admin user, raising an exception if not admin.

    This is a modern dependency that ensures admin privileges.

    Args:
        request: FastAPI request object

    Returns:
        dict: Admin user information

    Raises:
        HTTPException: If the request is not authenticated or not admin
    """
    user = get_authenticated_user(request)
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return user


# Type aliases for cleaner usage with Annotated
CurrentUser = Annotated[dict | None, Depends(get_current_user)]
AuthenticatedUser = Annotated[dict, Depends(get_authenticated_user)]
AdminUser = Annotated[dict, Depends(get_admin_user)]
