"""Secure Token Repository

Handles data access for secure token management including:
- Refresh token storage and validation
- Token rotation tracking
- Token blacklisting
- User session management
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Dict, List, Optional, Set

from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class SecureTokenRepository(MonitoredRepository):
    """Repository for secure token management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage (would be database tables in production)
        self._refresh_tokens: dict[str, set[str]] = {}  # user_id -> set of valid refresh tokens
        self._token_metadata: dict[str, dict[str, any]] = {}  # token -> metadata
        self._blacklisted_tokens: set[str] = set()  # Blacklisted access tokens
        self._user_sessions: dict[str, list[dict[str, any]]] = {}  # user_id -> active sessions

    @MonitoredRepository._monitored_operation("store_refresh_token")
    async def store_refresh_token(
        self,
        user_id: str,
        refresh_token: str,
        expires_at: datetime,
        device_info: dict[str, str] | None = None,
    ) -> bool:
        """Store a refresh token for a user.

        Args:
            user_id: User identifier
            refresh_token: Refresh token to store
            expires_at: Token expiration time
            device_info: Optional device/browser information

        Returns:
            True if stored successfully
        """
        if user_id not in self._refresh_tokens:
            self._refresh_tokens[user_id] = set()

        self._refresh_tokens[user_id].add(refresh_token)

        # Store metadata
        self._token_metadata[refresh_token] = {
            "user_id": user_id,
            "created_at": datetime.now(UTC),
            "expires_at": expires_at,
            "device_info": device_info or {},
            "rotated": False,
            "last_used": datetime.now(UTC),
        }

        # Add to user sessions
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []

        self._user_sessions[user_id].append(
            {
                "refresh_token": refresh_token,
                "created_at": datetime.now(UTC),
                "device_info": device_info or {},
                "active": True,
            }
        )

        logger.debug(f"Stored refresh token for user {user_id}")
        return True

    @MonitoredRepository._monitored_operation("is_refresh_token_valid")
    async def is_refresh_token_valid(self, user_id: str, refresh_token: str) -> bool:
        """Check if a refresh token is still valid.

        Args:
            user_id: User identifier
            refresh_token: Refresh token to validate

        Returns:
            True if token is valid and not expired
        """
        # Check if token exists for user
        if user_id not in self._refresh_tokens:
            return False

        if refresh_token not in self._refresh_tokens[user_id]:
            return False

        # Check metadata
        metadata = self._token_metadata.get(refresh_token)
        if not metadata:
            return False

        # Check expiration
        if metadata["expires_at"] < datetime.now(UTC):
            return False

        # Check if rotated
        if metadata.get("rotated", False):
            return False

        # Update last used time
        metadata["last_used"] = datetime.now(UTC)

        return True

    @MonitoredRepository._monitored_operation("invalidate_refresh_token")
    async def invalidate_refresh_token(self, user_id: str, refresh_token: str) -> bool:
        """Invalidate a specific refresh token.

        Args:
            user_id: User identifier
            refresh_token: Token to invalidate

        Returns:
            True if invalidated successfully
        """
        if user_id in self._refresh_tokens:
            self._refresh_tokens[user_id].discard(refresh_token)

        # Mark as rotated in metadata
        if refresh_token in self._token_metadata:
            self._token_metadata[refresh_token]["rotated"] = True
            self._token_metadata[refresh_token]["rotated_at"] = datetime.now(UTC)

        # Update session status
        if user_id in self._user_sessions:
            for session in self._user_sessions[user_id]:
                if session.get("refresh_token") == refresh_token:
                    session["active"] = False
                    session["invalidated_at"] = datetime.now(UTC)

        logger.debug(f"Invalidated refresh token for user {user_id}")
        return True

    @MonitoredRepository._monitored_operation("cleanup_user_tokens")
    async def cleanup_user_tokens(self, user_id: str) -> int:
        """Clean up all tokens for a user.

        Args:
            user_id: User to clean up tokens for

        Returns:
            Number of tokens cleaned up
        """
        count = 0

        # Remove all refresh tokens
        if user_id in self._refresh_tokens:
            count = len(self._refresh_tokens[user_id])

            # Clean up metadata
            for token in self._refresh_tokens[user_id]:
                self._token_metadata.pop(token, None)

            self._refresh_tokens.pop(user_id, None)

        # Clear user sessions
        if user_id in self._user_sessions:
            for session in self._user_sessions[user_id]:
                session["active"] = False
                session["invalidated_at"] = datetime.now(UTC)

        logger.info(f"Cleaned up {count} tokens for user {user_id}")
        return count

    @MonitoredRepository._monitored_operation("blacklist_access_token")
    async def blacklist_access_token(self, token_jti: str, expires_at: datetime) -> bool:
        """Add an access token to the blacklist.

        Args:
            token_jti: JWT ID of the token
            expires_at: Token expiration (for cleanup)

        Returns:
            True if blacklisted successfully
        """
        self._blacklisted_tokens.add(token_jti)

        # Schedule cleanup after expiration
        # In production, this would use a TTL index or scheduled job

        logger.debug(f"Blacklisted access token {token_jti}")
        return True

    @MonitoredRepository._monitored_operation("is_access_token_blacklisted")
    async def is_access_token_blacklisted(self, token_jti: str) -> bool:
        """Check if an access token is blacklisted.

        Args:
            token_jti: JWT ID to check

        Returns:
            True if token is blacklisted
        """
        return token_jti in self._blacklisted_tokens

    @MonitoredRepository._monitored_operation("get_user_sessions")
    async def get_user_sessions(self, user_id: str) -> list[dict[str, any]]:
        """Get all sessions for a user.

        Args:
            user_id: User to get sessions for

        Returns:
            List of session information
        """
        sessions = self._user_sessions.get(user_id, [])

        # Filter and enrich session data
        active_sessions = []
        for session in sessions:
            if session.get("active", False):
                # Get token metadata
                token = session.get("refresh_token")
                metadata = self._token_metadata.get(token, {})

                active_sessions.append(
                    {
                        "created_at": session["created_at"],
                        "last_used": metadata.get("last_used"),
                        "device_info": session.get("device_info", {}),
                        "expires_at": metadata.get("expires_at"),
                    }
                )

        return active_sessions

    @MonitoredRepository._monitored_operation("cleanup_expired_tokens")
    async def cleanup_expired_tokens(self) -> int:
        """Clean up expired tokens from storage.

        Returns:
            Number of tokens cleaned up
        """
        now = datetime.now(UTC)
        cleaned = 0

        # Find expired tokens
        expired_tokens = []
        for token, metadata in self._token_metadata.items():
            if metadata["expires_at"] < now:
                expired_tokens.append((token, metadata["user_id"]))

        # Remove expired tokens
        for token, user_id in expired_tokens:
            if user_id in self._refresh_tokens:
                self._refresh_tokens[user_id].discard(token)
                if not self._refresh_tokens[user_id]:
                    self._refresh_tokens.pop(user_id, None)

            self._token_metadata.pop(token, None)
            cleaned += 1

        # Clean up old blacklisted tokens
        # In production, this would be based on token expiration times

        logger.info(f"Cleaned up {cleaned} expired tokens")
        return cleaned

    @MonitoredRepository._monitored_operation("rotate_refresh_token")
    async def rotate_refresh_token(
        self, user_id: str, old_token: str, new_token: str, expires_at: datetime
    ) -> bool:
        """Rotate a refresh token.

        Args:
            user_id: User identifier
            old_token: Token being rotated
            new_token: New replacement token
            expires_at: New token expiration

        Returns:
            True if rotated successfully
        """
        # Invalidate old token
        await self.invalidate_refresh_token(user_id, old_token)

        # Get device info from old token
        old_metadata = self._token_metadata.get(old_token, {})
        device_info = old_metadata.get("device_info")

        # Store new token
        await self.store_refresh_token(user_id, new_token, expires_at, device_info)

        # Link tokens for audit trail
        if new_token in self._token_metadata:
            self._token_metadata[new_token]["rotated_from"] = old_token

        logger.debug(f"Rotated refresh token for user {user_id}")
        return True
