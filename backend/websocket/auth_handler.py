"""
WebSocket Authentication Handler

Integrates WebSocket connections with the existing AuthManager system.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketAuthHandler:
    """Handles authentication for WebSocket connections."""

    def __init__(self):
        # Import here to avoid circular imports
        from backend.core.config import get_settings

        self.settings = get_settings()
        self.authenticated_connections: dict[str, dict[str, Any]] = {}
        self._auth_manager = None

    @property
    def auth_manager(self):
        """Lazily get the auth manager from ServiceRegistry to avoid initialization issues."""
        if self._auth_manager is None:
            try:
                from backend.core.dependencies import get_service_registry

                service_registry = get_service_registry()
                if service_registry.has_service("auth_manager"):
                    auth_service = service_registry.get_service("auth_manager")
                    # AuthService has a get_auth_manager() method that returns the actual AuthManager
                    if hasattr(auth_service, "get_auth_manager"):
                        self._auth_manager = auth_service.get_auth_manager()
                        if not self._auth_manager:
                            logger.debug(
                                "AuthService.get_auth_manager() returned None - service may not be started yet"
                            )
                    else:
                        # Fallback if it's already an AuthManager
                        self._auth_manager = auth_service
                else:
                    logger.debug("Auth manager service not found in ServiceRegistry")
            except Exception as e:
                logger.debug("Could not get auth manager from ServiceRegistry: %s", e)
        return self._auth_manager

    async def authenticate_connection(  # noqa: C901
        self, websocket: WebSocket, token: str | None = None, require_auth: bool = True
    ) -> dict[str, Any] | None:
        """
        Authenticate a WebSocket connection.

        Args:
            websocket: The WebSocket connection
            token: JWT token (from query params or headers)
            require_auth: Whether authentication is required

        Returns:
            User info dict if authenticated, None if auth not required

        Raises:
            WebSocket closure if authentication fails
        """
        # Skip authentication if no auth manager available (same as middleware pattern)
        if not self.auth_manager:
            logger.debug("No auth manager available, skipping authentication")
            await websocket.accept()
            return {
                "user_id": "admin",
                "username": "admin",
                "email": "admin@localhost",
                "role": "admin",
                "authenticated": True,
            }

        # Skip authentication if mode is NONE (same as middleware pattern)
        from backend.services.auth_manager import AuthMode

        if self.auth_manager.auth_mode == AuthMode.NONE:
            logger.debug("Authentication mode is NONE, allowing WebSocket connection")
            await websocket.accept()
            return {
                "user_id": "admin",
                "username": "admin",
                "email": "admin@localhost",
                "role": "admin",
                "authenticated": True,
            }

        # If auth not required for this endpoint and no token provided
        if not require_auth and not token:
            await websocket.accept()
            return None

        # Extract token from various sources
        if not token:
            # Try to get token from query string
            # FastAPI WebSocket includes query params in the URL
            try:
                # Access the scope which is available in Starlette/FastAPI WebSockets
                scope = websocket.scope  # type: ignore[attr-defined]
                query_string = scope.get("query_string", b"").decode()
                if query_string:
                    from urllib.parse import parse_qs

                    query_params = parse_qs(query_string)
                    token_list = query_params.get("token", [])
                    if token_list:
                        token = token_list[0]
            except Exception:
                logger.debug("Failed to extract token from query string")

        # Validate token
        if not token:
            await websocket.close(code=1008)  # Policy violation
            logger.warning(
                "WebSocket connection rejected - missing token from %s", websocket.client
            )
            return None

        try:
            # Use existing auth manager to validate token
            if not self.auth_manager:
                msg = "AuthManager not initialized"
                raise ValueError(msg)
            payload = self.auth_manager.validate_token(token)

            # Create user info from token payload
            user_info = {
                "user_id": payload.get("sub"),
                "username": payload.get("username"),
                "email": payload.get("email"),
                "role": payload.get("role", "user"),
                "authenticated": True,
                "token_exp": payload.get("exp"),
                "connection_time": datetime.now(UTC).isoformat(),
            }

            # Store authenticated connection info
            connection_id = f"{websocket.client.host}:{websocket.client.port}"
            self.authenticated_connections[connection_id] = user_info

            # Accept the connection
            await websocket.accept()

            logger.info(
                "WebSocket authenticated for user %s from %s", user_info["username"], connection_id
            )

            return user_info

        except Exception as e:
            await websocket.close(code=1008)  # Policy violation
            logger.warning(
                "WebSocket connection rejected - invalid token from %s: %s",
                websocket.client,
                str(e),
            )
            return None

    async def check_token_expiry(self, websocket: WebSocket, user_info: dict[str, Any]) -> bool:
        """
        Check if the token has expired for an active connection.

        Args:
            websocket: The WebSocket connection
            user_info: User information including token expiry

        Returns:
            True if token is still valid, False if expired
        """
        if not user_info.get("authenticated", False):
            return True  # No expiry for unauthenticated connections

        token_exp = user_info.get("token_exp")
        if not token_exp:
            return True  # No expiry time set

        current_time = datetime.now(UTC).timestamp()
        if current_time >= token_exp:
            logger.info("Token expired for WebSocket user %s", user_info.get("username"))
            await websocket.close(code=1008)  # Policy violation - token expired
            return False

        return True

    def remove_connection(self, websocket: WebSocket) -> None:
        """Remove connection from authenticated connections tracking."""
        connection_id = f"{websocket.client.host}:{websocket.client.port}"
        if connection_id in self.authenticated_connections:
            user_info = self.authenticated_connections[connection_id]
            logger.info(
                "Removing authenticated WebSocket for user %s from %s",
                user_info.get("username"),
                connection_id,
            )
            del self.authenticated_connections[connection_id]

    async def require_permission(
        self,
        websocket: WebSocket,  # noqa: ARG002
        user_info: dict[str, Any],
        permission: str,
    ) -> bool:
        """
        Check if user has required permission for an operation.

        Args:
            websocket: The WebSocket connection
            user_info: User information
            permission: Required permission (e.g., "control_entities", "view_logs")

        Returns:
            True if permitted, False otherwise
        """
        # Admin users have all permissions
        if user_info.get("role") == "admin":
            return True

        # Define permission mappings
        role_permissions = {
            "user": ["view_entities", "control_entities", "view_status"],
            "readonly": ["view_entities", "view_status"],
        }

        user_role = user_info.get("role", "readonly")
        allowed_permissions = role_permissions.get(user_role, [])

        return permission in allowed_permissions


# Global instance
_websocket_auth_handler: WebSocketAuthHandler | None = None


def get_websocket_auth_handler() -> WebSocketAuthHandler:
    """Get the global WebSocket auth handler instance."""
    global _websocket_auth_handler  # noqa: PLW0603
    if _websocket_auth_handler is None:
        _websocket_auth_handler = WebSocketAuthHandler()
    return _websocket_auth_handler
