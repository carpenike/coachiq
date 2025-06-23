"""Database Repositories

Repositories for database connection, session, and migration management.
These provide data access patterns for database infrastructure.
"""

import logging
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class DatabaseConnectionRepository(MonitoredRepository):
    """Repository for database connection metadata and health tracking."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage for connection events
        self._connection_events: list[dict[str, Any]] = []
        self._connection_metrics: dict[str, Any] = {
            "total_connections": 0,
            "successful_connections": 0,
            "failed_connections": 0,
            "current_pool_size": 0,
            "max_pool_size": 0,
            "last_health_check": None,
            "uptime_start": time.time(),
        }
        self._max_events = 1000

    @MonitoredRepository._monitored_operation("get_connection_status")
    async def get_connection_status(self) -> dict[str, Any]:
        """Get current connection status.

        Returns:
            Connection status information
        """
        return {
            "is_connected": self._connection_metrics.get("current_pool_size", 0) > 0,
            "pool_size": self._connection_metrics.get("current_pool_size", 0),
            "max_pool_size": self._connection_metrics.get("max_pool_size", 0),
            "last_health_check": self._connection_metrics.get("last_health_check"),
            "backend": getattr(self._db_manager, "backend", "unknown"),
            "uptime_seconds": time.time() - self._connection_metrics["uptime_start"],
        }

    @MonitoredRepository._monitored_operation("record_connection_event")
    async def record_connection_event(self, event_type: str, metadata: dict[str, Any]) -> str:
        """Record a connection event.

        Args:
            event_type: Type of connection event
            metadata: Event metadata

        Returns:
            Event ID
        """
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": metadata,
        }

        # Add to events list
        self._connection_events.append(event)

        # Update metrics based on event type
        if event_type == "connection_opened":
            self._connection_metrics["total_connections"] += 1
            self._connection_metrics["successful_connections"] += 1
            self._connection_metrics["current_pool_size"] = metadata.get("pool_size", 0)
        elif event_type == "connection_failed":
            self._connection_metrics["failed_connections"] += 1
        elif event_type == "connection_closed":
            self._connection_metrics["current_pool_size"] = metadata.get("pool_size", 0)
        elif event_type == "health_check":
            self._connection_metrics["last_health_check"] = datetime.now(UTC).isoformat()

        # Trim old events
        if len(self._connection_events) > self._max_events:
            self._connection_events = self._connection_events[-self._max_events :]

        logger.debug(f"Recorded connection event: {event_type}")
        return event_id

    @MonitoredRepository._monitored_operation("get_connection_history")
    async def get_connection_history(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get connection event history.

        Args:
            hours: Hours of history to retrieve

        Returns:
            List of connection events
        """
        cutoff = datetime.now(UTC).timestamp() - (hours * 3600)
        recent_events = []

        for event in reversed(self._connection_events):
            # Parse timestamp and check if within window
            event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            if event_time.timestamp() < cutoff:
                break
            recent_events.append(event)

        return recent_events

    @MonitoredRepository._monitored_operation("get_connection_metrics")
    async def get_connection_metrics(self) -> dict[str, Any]:
        """Get connection metrics summary.

        Returns:
            Connection metrics
        """
        # Calculate success rate
        total = self._connection_metrics["total_connections"]
        success_rate = (
            self._connection_metrics["successful_connections"] / total if total > 0 else 1.0
        )

        return {
            **self._connection_metrics,
            "success_rate": success_rate,
            "failure_rate": 1.0 - success_rate,
        }


class DatabaseSessionRepository(MonitoredRepository):
    """Repository for database session tracking and management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory session tracking
        self._active_sessions: dict[str, dict[str, Any]] = {}
        self._session_metrics: dict[str, Any] = {
            "total_sessions": 0,
            "peak_concurrent": 0,
            "total_duration_ms": 0.0,
            "sessions_by_endpoint": defaultdict(int),
            "leaked_sessions": 0,
        }

    @MonitoredRepository._monitored_operation("register_session")
    async def register_session(self, session_id: str, metadata: dict[str, Any]) -> bool:
        """Register a new database session.

        Args:
            session_id: Unique session identifier
            metadata: Session metadata

        Returns:
            True if registered successfully
        """
        self._active_sessions[session_id] = {
            "session_id": session_id,
            "started_at": datetime.now(UTC).isoformat(),
            "endpoint": metadata.get("endpoint", "unknown"),
            "request_id": metadata.get("request_id"),
            **metadata,
        }

        # Update metrics
        self._session_metrics["total_sessions"] += 1
        current_concurrent = len(self._active_sessions)
        self._session_metrics["peak_concurrent"] = max(
            self._session_metrics["peak_concurrent"], current_concurrent
        )

        # Track by endpoint
        endpoint = metadata.get("endpoint", "unknown")
        self._session_metrics["sessions_by_endpoint"][endpoint] += 1

        logger.debug(f"Registered session: {session_id}")
        return True

    @MonitoredRepository._monitored_operation("close_session")
    async def close_session(self, session_id: str) -> bool:
        """Close a database session.

        Args:
            session_id: Session to close

        Returns:
            True if closed successfully
        """
        if session_id not in self._active_sessions:
            logger.warning(f"Attempted to close unknown session: {session_id}")
            return False

        session = self._active_sessions.pop(session_id)

        # Calculate duration
        started = datetime.fromisoformat(session["started_at"].replace("Z", "+00:00"))
        duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
        self._session_metrics["total_duration_ms"] += duration_ms

        logger.debug(f"Closed session: {session_id} (duration: {duration_ms:.2f}ms)")
        return True

    @MonitoredRepository._monitored_operation("get_active_sessions")
    async def get_active_sessions(self) -> list[dict[str, Any]]:
        """Get list of active sessions.

        Returns:
            List of active session information
        """
        sessions = []
        now = datetime.now(UTC)

        for session_id, session_data in self._active_sessions.items():
            started = datetime.fromisoformat(session_data["started_at"].replace("Z", "+00:00"))
            duration_seconds = (now - started).total_seconds()

            sessions.append(
                {
                    **session_data,
                    "duration_seconds": duration_seconds,
                    "is_stale": duration_seconds > 300,  # Over 5 minutes is considered stale
                }
            )

        return sorted(sessions, key=lambda x: x["duration_seconds"], reverse=True)

    @MonitoredRepository._monitored_operation("get_session_metrics")
    async def get_session_metrics(self) -> dict[str, Any]:
        """Get session usage metrics.

        Returns:
            Session metrics summary
        """
        total = self._session_metrics["total_sessions"]
        avg_duration = self._session_metrics["total_duration_ms"] / total if total > 0 else 0.0

        return {
            **self._session_metrics,
            "current_active": len(self._active_sessions),
            "average_duration_ms": avg_duration,
            "sessions_by_endpoint": dict(self._session_metrics["sessions_by_endpoint"]),
        }

    @MonitoredRepository._monitored_operation("cleanup_stale_sessions")
    async def cleanup_stale_sessions(self, timeout_seconds: int = 300) -> int:
        """Clean up stale sessions.

        Args:
            timeout_seconds: Session timeout in seconds

        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now(UTC)
        stale_sessions = []

        for session_id, session_data in self._active_sessions.items():
            started = datetime.fromisoformat(session_data["started_at"].replace("Z", "+00:00"))
            if (now - started).total_seconds() > timeout_seconds:
                stale_sessions.append(session_id)

        # Clean up stale sessions
        for session_id in stale_sessions:
            await self.close_session(session_id)
            self._session_metrics["leaked_sessions"] += 1

        if stale_sessions:
            logger.warning(f"Cleaned up {len(stale_sessions)} stale sessions")

        return len(stale_sessions)


class MigrationRepository(MonitoredRepository):
    """Repository for database migration tracking."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory migration tracking
        self._applied_migrations: dict[str, dict[str, Any]] = {}
        self._migration_history: list[dict[str, Any]] = []
        self._pending_migrations: dict[str, dict[str, Any]] = {}

    @MonitoredRepository._monitored_operation("get_applied_migrations")
    async def get_applied_migrations(self) -> list[dict[str, Any]]:
        """Get list of applied migrations.

        Returns:
            List of applied migrations
        """
        return sorted(
            self._applied_migrations.values(), key=lambda x: x.get("applied_at", ""), reverse=True
        )

    @MonitoredRepository._monitored_operation("record_migration")
    async def record_migration(
        self, version: str, script: str, applied_at: datetime | None = None
    ) -> str:
        """Record a migration execution.

        Args:
            version: Migration version
            script: Migration script name
            applied_at: When migration was applied

        Returns:
            Migration ID
        """
        migration_id = f"migration_{version}_{int(time.time() * 1000)}"
        applied_timestamp = applied_at or datetime.now(UTC)

        migration_record = {
            "migration_id": migration_id,
            "version": version,
            "script": script,
            "applied_at": applied_timestamp.isoformat(),
            "success": True,
        }

        # Add to applied migrations
        self._applied_migrations[version] = migration_record

        # Add to history
        self._migration_history.append({**migration_record, "event_type": "migration_applied"})

        # Remove from pending if exists
        self._pending_migrations.pop(version, None)

        logger.info(f"Recorded migration: {version} ({script})")
        return migration_id

    @MonitoredRepository._monitored_operation("get_pending_migrations")
    async def get_pending_migrations(self) -> list[dict[str, Any]]:
        """Get list of pending migrations.

        Returns:
            List of pending migrations
        """
        return sorted(self._pending_migrations.values(), key=lambda x: x.get("version", ""))

    @MonitoredRepository._monitored_operation("add_pending_migration")
    async def add_pending_migration(self, version: str, script: str) -> bool:
        """Add a pending migration.

        Args:
            version: Migration version
            script: Migration script

        Returns:
            True if added successfully
        """
        if version not in self._applied_migrations:
            self._pending_migrations[version] = {
                "version": version,
                "script": script,
                "detected_at": datetime.now(UTC).isoformat(),
            }
            return True
        return False

    @MonitoredRepository._monitored_operation("get_migration_history")
    async def get_migration_history(self) -> list[dict[str, Any]]:
        """Get complete migration history.

        Returns:
            List of migration events
        """
        return sorted(self._migration_history, key=lambda x: x.get("applied_at", ""), reverse=True)

    @MonitoredRepository._monitored_operation("get_schema_version")
    async def get_schema_version(self) -> str | None:
        """Get current schema version.

        Returns:
            Latest migration version or None
        """
        if not self._applied_migrations:
            return None

        # Get the latest migration version
        latest = max(self._applied_migrations.values(), key=lambda x: x.get("applied_at", ""))
        return latest.get("version")
