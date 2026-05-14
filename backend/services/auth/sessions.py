"""User session and refresh-token management.

Extracted from the historical ``backend/services/auth_services.py`` in
audit cycle 2026-05-13 PR A9. The :class:`SessionService` body is moved
verbatim; only the surrounding imports and module docstring are new.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.core.performance import PerformanceMonitor
from backend.repositories.auth_repository import SessionRepository
from backend.services.auth.tokens import TokenService

logger = logging.getLogger(__name__)


class SessionService:
    """Service for session and refresh token management."""

    def __init__(
        self,
        token_service: TokenService,
        session_repository: SessionRepository,
        performance_monitor: PerformanceMonitor,
        refresh_token_expire_days: int = 30,
        max_sessions_per_user: int = 5,
    ):
        """Initialize the session service.

        Args:
            token_service: Token service for token operations
            session_repository: Repository for session data
            performance_monitor: Performance monitoring instance
            refresh_token_expire_days: Refresh token expiration
            max_sessions_per_user: Maximum concurrent sessions
        """
        self._token_service = token_service
        self._session_repo = session_repository
        self._monitor = performance_monitor
        self._refresh_expire_days = refresh_token_expire_days
        self._max_sessions = max_sessions_per_user

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("SessionService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.create_session = self._monitor.monitor_service_method(
            "SessionService", "create_session"
        )(self.create_session)

        self.refresh_access_token = self._monitor.monitor_service_method(
            "SessionService", "refresh_access_token"
        )(self.refresh_access_token)

    async def create_session(
        self, user_id: str, device_info: dict[str, Any] | None = None, request=None
    ) -> tuple[str, str]:
        """Create a new user session.

        Args:
            user_id: User identifier
            device_info: Device/client information
            request: Optional request object for fingerprint calculation

        Returns:
            Tuple of (access_token, refresh_token)
        """
        # Check session limit
        active_count = await self._session_repo.get_active_session_count(user_id)
        if active_count >= self._max_sessions:
            logger.warning(f"User {user_id} exceeded session limit")
            # Optionally revoke oldest session
            sessions = await self._session_repo.get_user_sessions(user_id)
            if sessions:
                oldest = min(sessions, key=lambda s: s["created_at"])
                await self._session_repo.revoke_user_session(oldest["refresh_token"])

        # Generate tokens
        access_token = self._token_service.generate_access_token(user_id)
        refresh_token = self._token_service.generate_refresh_token()

        # Enhance device_info with fingerprint if request is provided
        enhanced_device_info = device_info or {}
        if request:
            # Calculate fingerprint for session security
            import hashlib

            user_agent = (
                request.headers.get("User-Agent", "") if hasattr(request, "headers") else ""
            )
            client_ip = request.client.host if hasattr(request, "client") and request.client else ""

            # Use IP subnet for flexibility
            ip_parts = client_ip.split(".")
            ip_subnet = ".".join(ip_parts[:3]) if len(ip_parts) >= 3 else client_ip

            fingerprint_data = f"{user_agent}|{ip_subnet}"
            fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
            enhanced_device_info["fingerprint"] = fingerprint
            enhanced_device_info["user_agent"] = user_agent
            enhanced_device_info["ip_subnet"] = ip_subnet

        # Create session
        expires_at = datetime.now(UTC) + timedelta(days=self._refresh_expire_days)
        await self._session_repo.create_user_session(
            user_id, refresh_token, enhanced_device_info, expires_at
        )

        logger.info(f"Created session for user {user_id}")
        return access_token, refresh_token

    async def refresh_access_token(self, refresh_token: str) -> str | None:
        """Refresh an access token using refresh token.

        Args:
            refresh_token: Refresh token

        Returns:
            New access token or None if invalid
        """
        # Get session
        session = await self._session_repo.get_user_session(refresh_token)
        if not session:
            logger.warning("Refresh token not found or expired")
            return None

        # Generate new access token
        user_id = session["user_id"]
        access_token = self._token_service.generate_access_token(user_id)

        logger.debug(f"Refreshed access token for user {user_id}")
        return access_token

    async def revoke_session(self, refresh_token: str) -> bool:
        """Revoke a user session.

        Args:
            refresh_token: Refresh token to revoke

        Returns:
            True if revoked successfully
        """
        return await self._session_repo.revoke_user_session(refresh_token)

    async def revoke_all_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions revoked
        """
        return await self._session_repo.revoke_all_user_sessions(user_id)

    async def get_active_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """Get active sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            List of active sessions
        """
        return await self._session_repo.get_user_sessions(user_id)

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions.

        Returns:
            Number of sessions cleaned
        """
        return await self._session_repo.cleanup_expired_sessions()
