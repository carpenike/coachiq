"""Authentication Repositories

Repositories for authentication data management including:
- User credentials and metadata
- Session/refresh token management
- MFA configuration and state
- Authentication event tracking
"""

import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class CredentialRepository(MonitoredRepository):
    """Repository for user credential management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage (would be database in production)
        self._credentials: dict[str, dict[str, Any]] = {}
        self._default_admin_username = "admin"

    @MonitoredRepository._monitored_operation("get_admin_credentials")
    async def get_admin_credentials(self) -> dict[str, Any] | None:
        """Get admin user credentials.

        Returns:
            Admin credentials or None if not set
        """
        return self._credentials.get(self._default_admin_username)

    @MonitoredRepository._monitored_operation("set_admin_credentials")
    async def set_admin_credentials(
        self, username: str, password_hash: str, metadata: dict[str, Any] | None = None
    ) -> bool:
        """Set admin user credentials.

        Args:
            username: Admin username
            password_hash: Hashed password
            metadata: Additional metadata

        Returns:
            True if successful
        """
        self._credentials[username] = {
            "username": username,
            "password_hash": password_hash,
            "is_admin": True,
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
            "password_retrieved": False,
        }

        logger.info(f"Admin credentials set for user: {username}")
        return True

    @MonitoredRepository._monitored_operation("get_credential_metadata")
    async def get_credential_metadata(self, username: str) -> dict[str, Any] | None:
        """Get credential metadata for a user.

        Args:
            username: Username to look up

        Returns:
            Credential metadata or None
        """
        creds = self._credentials.get(username)
        if creds:
            return {
                "username": username,
                "is_admin": creds.get("is_admin", False),
                "password_retrieved": creds.get("password_retrieved", False),
                "created_at": creds.get("created_at"),
                **creds.get("metadata", {}),
            }
        return None

    @MonitoredRepository._monitored_operation("update_credential_metadata")
    async def update_credential_metadata(self, username: str, metadata: dict[str, Any]) -> bool:
        """Update credential metadata.

        Args:
            username: Username to update
            metadata: Metadata updates

        Returns:
            True if updated successfully
        """
        if username in self._credentials:
            # Update specific metadata fields
            if "password_retrieved" in metadata:
                self._credentials[username]["password_retrieved"] = metadata["password_retrieved"]

            # Update generic metadata
            self._credentials[username]["metadata"].update(metadata)
            self._credentials[username]["updated_at"] = datetime.now(UTC).isoformat()

            return True
        return False


class SessionRepository(MonitoredRepository):
    """Repository for session and refresh token management.

    Refresh tokens are opaque and stored server-side. Sessions are persisted in
    the ``user_sessions`` table via :class:`AuthRepository` so they survive a
    backend restart — without this, every ``coachiq.service`` restart wiped all
    refresh sessions and bounced authenticated users back to /login.

    An in-memory fallback is retained for two cases where the database cannot
    hold the session: the ``null://memory`` persistence backend (dev/tests) and
    sessions whose ``user_id`` has no row in ``users`` (e.g. the synthetic
    single-user "admin"), which would violate the ``user_sessions`` FK. These
    fall back to the previous in-memory behaviour instead of failing outright.
    """

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # Persistent, restart-surviving session store.
        from backend.services.auth.repository import AuthRepository

        self._auth_repo = AuthRepository(database_manager)

        # In-memory fallback for sessions that cannot be persisted (null backend
        # or non-persistable user ids). Keyed by refresh_token.
        self._sessions: dict[str, dict[str, Any]] = {}
        self._user_sessions: dict[str, list[str]] = defaultdict(list)  # user_id -> [refresh_tokens]

    @staticmethod
    def _session_to_dict(session: "Any") -> dict[str, Any]:
        """Convert a persistent ``UserSession`` ORM row to the consumer dict shape."""
        return {
            "session_id": session.id,
            "user_id": session.user_id,
            "refresh_token": session.session_token,
            "device_info": session.device_info,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "expires_at": session.expires_at.isoformat() if session.expires_at else None,
            "last_used": (
                session.last_accessed_at.isoformat() if session.last_accessed_at else None
            ),
            "is_active": session.is_active,
        }

    @MonitoredRepository._monitored_operation("create_user_session")
    async def create_user_session(
        self, user_id: str, refresh_token: str, device_info: dict[str, Any], expires_at: datetime
    ) -> str:
        """Create a new user session.

        Args:
            user_id: User identifier
            refresh_token: Refresh token
            device_info: Device information
            expires_at: Token expiration time

        Returns:
            Session ID
        """
        # Persist to the database so the session survives a backend restart.
        persisted = await self._auth_repo.create_user_session(
            user_id=user_id,
            session_token=refresh_token,
            expires_at=expires_at,
            device_info=device_info,
        )
        if persisted is not None:
            logger.debug(f"Persisted session for user {user_id}")
            return persisted.id

        # Fallback: null backend or a user_id with no ``users`` row (FK). Keep the
        # previous in-memory behaviour rather than dropping the session entirely.
        session_id = str(uuid.uuid4())
        self._sessions[refresh_token] = {
            "session_id": session_id,
            "user_id": user_id,
            "refresh_token": refresh_token,
            "device_info": device_info,
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_used": datetime.now(UTC).isoformat(),
            "is_active": True,
        }
        self._user_sessions[user_id].append(refresh_token)
        logger.debug(f"Stored in-memory fallback session for user {user_id}")
        return session_id

    @MonitoredRepository._monitored_operation("get_user_session")
    async def get_user_session(self, refresh_token: str) -> dict[str, Any] | None:
        """Get session by refresh token.

        Args:
            refresh_token: Refresh token to look up

        Returns:
            Session data or None
        """
        now = datetime.now(UTC)

        # In-memory fallback sessions take precedence (they only exist when the
        # DB could not hold them).
        session = self._sessions.get(refresh_token)
        if session and session["is_active"]:
            expires_at = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
            if expires_at > now:
                session["last_used"] = now.isoformat()
                return session
            session["is_active"] = False
            return None

        # Persistent store. Normalize expiry to UTC-aware: SQLite may hand back a
        # naive datetime, which would raise when compared against an aware ``now``.
        persisted = await self._auth_repo.get_user_session(refresh_token)
        if persisted and persisted.is_active:
            expires_at = persisted.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at > now:
                await self._auth_repo.update_session_last_accessed(refresh_token)
                return self._session_to_dict(persisted)

        return None

    @MonitoredRepository._monitored_operation("get_user_sessions")
    async def get_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """Get all active sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            List of active sessions
        """
        sessions: list[dict[str, Any]] = []

        # In-memory fallback sessions.
        for token in list(self._user_sessions.get(user_id, [])):
            session = await self.get_user_session(token)
            if session:
                sessions.append(session)

        # Persistent sessions.
        for persisted in await self._auth_repo.get_active_user_sessions(user_id):
            sessions.append(self._session_to_dict(persisted))

        return sessions

    @MonitoredRepository._monitored_operation("revoke_user_session")
    async def revoke_user_session(self, refresh_token: str) -> bool:
        """Revoke a user session.

        Args:
            refresh_token: Token to revoke

        Returns:
            True if revoked successfully
        """
        if refresh_token in self._sessions:
            session = self._sessions[refresh_token]
            session["is_active"] = False
            session["revoked_at"] = datetime.now(UTC).isoformat()
            user_id = session["user_id"]
            if user_id in self._user_sessions:
                self._user_sessions[user_id] = [
                    t for t in self._user_sessions[user_id] if t != refresh_token
                ]
            logger.info(f"Revoked in-memory session for user {user_id}")
            return True

        return await self._auth_repo.revoke_user_session(refresh_token)

    @MonitoredRepository._monitored_operation("revoke_all_user_sessions")
    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions revoked
        """
        count = 0

        for token in list(self._user_sessions.get(user_id, [])):
            if await self.revoke_user_session(token):
                count += 1

        count += await self._auth_repo.revoke_all_user_sessions(user_id)

        if count > 0:
            logger.info(f"Revoked {count} sessions for user {user_id}")

        return count

    @MonitoredRepository._monitored_operation("cleanup_expired_sessions")
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions.

        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now(UTC)

        # In-memory fallback sessions.
        expired_tokens = [
            token
            for token, session in self._sessions.items()
            if datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00")) <= now
        ]
        for token in expired_tokens:
            await self.revoke_user_session(token)

        # Persistent sessions.
        db_cleaned = await self._auth_repo.cleanup_expired_sessions()

        total = len(expired_tokens) + db_cleaned
        if total:
            logger.info(f"Cleaned up {total} expired sessions")

        return total

    @MonitoredRepository._monitored_operation("get_active_session_count")
    async def get_active_session_count(self, user_id: str) -> int:
        """Get count of active sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of active sessions
        """
        sessions = await self.get_user_sessions(user_id)
        return len(sessions)


class MfaRepository(MonitoredRepository):
    """Repository for MFA configuration and state."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage
        self._mfa_configs: dict[str, dict[str, Any]] = {}  # user_id -> mfa config

    @MonitoredRepository._monitored_operation("create_user_mfa")
    async def create_user_mfa(
        self, user_id: str, secret: str, backup_codes_hash: list[str]
    ) -> bool:
        """Create MFA configuration for a user.

        Args:
            user_id: User identifier
            secret: TOTP secret
            backup_codes_hash: Hashed backup codes

        Returns:
            True if created successfully
        """
        self._mfa_configs[user_id] = {
            "user_id": user_id,
            "secret": secret,
            "backup_codes_hash": backup_codes_hash,
            "backup_codes_used": [],
            "enabled": False,
            "created_at": datetime.now(UTC).isoformat(),
            "last_used": None,
        }

        logger.info(f"Created MFA config for user {user_id}")
        return True

    @MonitoredRepository._monitored_operation("get_user_mfa")
    async def get_user_mfa(self, user_id: str) -> dict[str, Any] | None:
        """Get MFA configuration for a user.

        Args:
            user_id: User identifier

        Returns:
            MFA configuration or None
        """
        return self._mfa_configs.get(user_id)

    @MonitoredRepository._monitored_operation("update_user_mfa")
    async def update_user_mfa(self, user_id: str, updates: dict[str, Any]) -> bool:
        """Update MFA configuration.

        Args:
            user_id: User identifier
            updates: Configuration updates

        Returns:
            True if updated successfully
        """
        if user_id in self._mfa_configs:
            config = self._mfa_configs[user_id]

            # Update allowed fields
            if "enabled" in updates:
                config["enabled"] = updates["enabled"]
                if updates["enabled"]:
                    config["enabled_at"] = datetime.now(UTC).isoformat()

            if "last_used" in updates:
                config["last_used"] = updates["last_used"]

            config["updated_at"] = datetime.now(UTC).isoformat()

            return True

        return False

    @MonitoredRepository._monitored_operation("delete_user_mfa")
    async def delete_user_mfa(self, user_id: str) -> bool:
        """Delete MFA configuration for a user.

        Args:
            user_id: User identifier

        Returns:
            True if deleted successfully
        """
        if user_id in self._mfa_configs:
            del self._mfa_configs[user_id]
            logger.info(f"Deleted MFA config for user {user_id}")
            return True

        return False

    @MonitoredRepository._monitored_operation("mark_backup_code_used")
    async def mark_backup_code_used(self, user_id: str, code_hash: str) -> bool:
        """Mark a backup code as used.

        Args:
            user_id: User identifier
            code_hash: Hash of the backup code

        Returns:
            True if marked successfully
        """
        config = self._mfa_configs.get(user_id)

        if config and code_hash in config["backup_codes_hash"]:
            if code_hash not in config["backup_codes_used"]:
                config["backup_codes_used"].append(code_hash)
                config["last_backup_code_used"] = datetime.now(UTC).isoformat()
                return True

        return False


class AuthEventRepository(MonitoredRepository):
    """Repository for authentication event tracking."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage
        self._auth_events: list[dict[str, Any]] = []
        self._events_by_user: dict[str, list[int]] = defaultdict(list)  # username -> indices
        self._max_events = 10000

    @MonitoredRepository._monitored_operation("create_auth_event")
    async def create_auth_event(
        self,
        username: str,
        event_type: str,
        success: bool,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create an authentication event.

        Args:
            username: Username involved
            event_type: Type of auth event
            success: Whether the event was successful
            metadata: Additional event data

        Returns:
            Event ID
        """
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "username": username,
            "event_type": event_type,
            "success": success,
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
        }

        # Add to storage
        index = len(self._auth_events)
        self._auth_events.append(event)
        self._events_by_user[username].append(index)

        # Trim if necessary
        if len(self._auth_events) > self._max_events:
            self._trim_old_events()

        logger.debug(f"Created auth event: {event_type} for {username} (success={success})")
        return event_id

    @MonitoredRepository._monitored_operation("get_auth_events_for_user")
    async def get_auth_events_for_user(
        self, username: str, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Get authentication events for a user.

        Args:
            username: Username to look up
            since: Only return events after this time

        Returns:
            List of auth events
        """
        events = []

        for index in reversed(self._events_by_user.get(username, [])):
            if index < len(self._auth_events):
                event = self._auth_events[index]

                if since:
                    event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                    if event_time < since:
                        break

                events.append(event)

        return events

    @MonitoredRepository._monitored_operation("get_failed_attempts_count")
    async def get_failed_attempts_count(self, username: str, window_minutes: int = 15) -> int:
        """Get count of failed login attempts within time window.

        Args:
            username: Username to check
            window_minutes: Time window in minutes

        Returns:
            Number of failed attempts
        """
        since = datetime.now(UTC).timestamp() - (window_minutes * 60)
        count = 0

        for index in reversed(self._events_by_user.get(username, [])):
            if index < len(self._auth_events):
                event = self._auth_events[index]

                # Check timestamp
                event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                if event_time.timestamp() < since:
                    break

                # Count failed login attempts
                if event["event_type"] == "login" and not event["success"]:
                    count += 1

        return count

    @MonitoredRepository._monitored_operation("clear_failed_attempts")
    async def clear_failed_attempts(self, username: str) -> bool:
        """Clear failed login attempts for a user.

        This is typically called after a successful login.

        Args:
            username: Username to clear

        Returns:
            True if cleared
        """
        # In a real implementation, we might mark events as cleared
        # For now, just record a clear event
        await self.create_auth_event(
            username, "failed_attempts_cleared", True, {"reason": "successful_login"}
        )

        return True

    @MonitoredRepository._monitored_operation("get_auth_events_by_criteria")
    async def get_auth_events_by_criteria(
        self,
        user_id: str | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get auth events by multiple criteria.

        Args:
            user_id: Filter by user_id in metadata
            event_type: Filter by event type
            since: Only return events after this time
            limit: Maximum number of events to return

        Returns:
            List of matching auth events
        """
        events = []
        count = 0

        # Iterate through events in reverse order (most recent first)
        for i in range(len(self._auth_events) - 1, -1, -1):
            if count >= limit:
                break

            event = self._auth_events[i]

            # Apply filters
            if since:
                event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                if event_time < since:
                    # Since we're going backwards in time, we can stop here
                    break

            if event_type and event.get("event_type") != event_type:
                continue

            if user_id and event.get("metadata", {}).get("user_id") != user_id:
                continue

            events.append(event)
            count += 1

        return events

    def _trim_old_events(self) -> None:
        """Trim old events when at capacity."""
        # Keep most recent events
        trim_count = len(self._auth_events) - self._max_events + 1000

        if trim_count > 0:
            self._auth_events = self._auth_events[trim_count:]

            # Rebuild indices
            self._events_by_user.clear()
            for idx, event in enumerate(self._auth_events):
                self._events_by_user[event["username"]].append(idx)

            logger.info(f"Trimmed {trim_count} old auth events")

    @MonitoredRepository._monitored_operation("get_auth_events_summary")
    async def get_auth_events_summary(
        self,
        user_id: str | None = None,
        username: str | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        """Get aggregated summary of auth events without fetching full records.

        Args:
            user_id: Filter by user ID
            username: Filter by username
            event_type: Filter by event type
            since: Filter events after this time

        Returns:
            Summary with counts by status, type, unique users, and IPs
        """
        summary = {
            "total_attempts": 0,
            "successful_attempts": 0,
            "failed_attempts": 0,
            "by_type": {},
            "by_status": {},
            "unique_users": set(),
            "unique_ips": set(),
        }

        # Process events in reverse order (newest first)
        for i in range(len(self._auth_events) - 1, -1, -1):
            event = self._auth_events[i]

            # Apply filters
            if since:
                event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                if event_time < since:
                    break

            if event_type and event.get("event_type") != event_type:
                continue

            if user_id and event.get("metadata", {}).get("user_id") != user_id:
                continue

            if username and event.get("username") != username:
                continue

            # Update summary
            summary["total_attempts"] += 1

            if event.get("success"):
                summary["successful_attempts"] += 1
                summary["by_status"]["success"] = summary["by_status"].get("success", 0) + 1
            else:
                summary["failed_attempts"] += 1
                summary["by_status"]["failed"] = summary["by_status"].get("failed", 0) + 1

            evt_type = event.get("event_type", "unknown")
            summary["by_type"][evt_type] = summary["by_type"].get(evt_type, 0) + 1

            # Track unique identifiers
            if event.get("username"):
                summary["unique_users"].add(event["username"])
            if event.get("metadata", {}).get("ip_address"):
                summary["unique_ips"].add(event["metadata"]["ip_address"])

        # Convert sets to counts
        summary["unique_users"] = len(summary["unique_users"])
        summary["unique_ips"] = len(summary["unique_ips"])

        return summary
