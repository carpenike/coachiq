"""Repository layer for database update management."""

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from backend.models.database_update import DatabaseBackup, MigrationHistory

logger = logging.getLogger(__name__)


class DatabaseBackupRepository:
    """
    Repository for database backup metadata.

    Direct SQLAlchemy implementation - no facades, no legacy support.
    """

    def __init__(self, session_factory):
        """Initialize with session factory only - no app_state."""
        self._session_factory = session_factory

    @asynccontextmanager
    async def get_session(self):
        """Get a database session."""
        async with self._session_factory() as session:
            yield session

    async def create_backup_record(
        self,
        backup_path: str,
        size_bytes: int,
        schema_version: str,
        backup_type: str = "manual",
    ) -> dict[str, Any]:
        """Record a new backup in the database."""
        async with self.get_session() as session:
            backup = DatabaseBackup(
                path=backup_path,
                size_bytes=size_bytes,
                schema_version=schema_version,
                backup_type=backup_type,
                created_at=datetime.now(UTC),
            )
            session.add(backup)
            await session.commit()
            await session.refresh(backup)
            return {
                "id": backup.id,
                "path": backup.path,
                "size_bytes": backup.size_bytes,
                "schema_version": backup.schema_version,
                "backup_type": backup.backup_type,
                "created_at": backup.created_at.isoformat(),
            }

    async def get_latest_backup(self) -> dict[str, Any] | None:
        """Get the most recent backup record."""
        async with self.get_session() as session:
            stmt = select(DatabaseBackup).order_by(DatabaseBackup.created_at.desc()).limit(1)
            result = await session.execute(stmt)
            backup = result.scalar_one_or_none()

            if backup:
                return {
                    "id": backup.id,
                    "path": backup.path,
                    "size_bytes": backup.size_bytes,
                    "schema_version": backup.schema_version,
                    "backup_type": backup.backup_type,
                    "created_at": backup.created_at.isoformat(),
                }
            return None

    async def cleanup_old_backups(self, retention_days: int) -> int:
        """Remove backup records older than retention period."""
        async with self.get_session() as session:
            cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)
            stmt = delete(DatabaseBackup).where(DatabaseBackup.created_at < cutoff_date)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount


class MigrationHistoryRepository:
    """
    Repository for migration execution history.

    Direct SQLAlchemy implementation - no facades, no legacy support.
    """

    def __init__(self, session_factory):
        """Initialize with session factory only - no app_state."""
        self._session_factory = session_factory

    @asynccontextmanager
    async def get_session(self):
        """Get a database session."""
        async with self._session_factory() as session:
            yield session

    async def record_migration_attempt(
        self,
        from_version: str,
        to_version: str,
        status: str,
        duration_ms: int,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a migration attempt."""
        async with self.get_session() as session:
            history = MigrationHistory(
                from_version=from_version,
                to_version=to_version,
                status=status,
                duration_ms=duration_ms,
                details=details or {},
                executed_at=datetime.now(UTC),
            )
            session.add(history)
            await session.commit()
            await session.refresh(history)
            return {
                "id": history.id,
                "from_version": history.from_version,
                "to_version": history.to_version,
                "status": history.status,
                "duration_ms": history.duration_ms,
                "details": history.details,
                "executed_at": history.executed_at.isoformat(),
            }

    async def get_migration_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent migration history."""
        async with self.get_session() as session:
            stmt = (
                select(MigrationHistory).order_by(MigrationHistory.executed_at.desc()).limit(limit)
            )
            result = await session.execute(stmt)

            return [
                {
                    "id": h.id,
                    "from_version": h.from_version,
                    "to_version": h.to_version,
                    "status": h.status,
                    "duration_ms": h.duration_ms,
                    "details": h.details,
                    "executed_at": h.executed_at.isoformat(),
                }
                for h in result.scalars()
            ]


class DatabaseConnectionRepository:
    """Repository for database connection management."""

    def __init__(self, session_factory, database_url: str, database_path: str):
        """Initialize with session factory and database info."""
        self._session_factory = session_factory
        self._database_url = database_url
        self._database_path = database_path

    @asynccontextmanager
    async def get_session(self):
        """Get a database session."""
        async with self._session_factory() as session:
            yield session

    async def get_database_url(self) -> str:
        """Get the database connection URL."""
        return self._database_url

    async def get_database_path(self) -> str:
        """Get the physical database file path."""
        return self._database_path

    async def check_health(self) -> dict[str, Any]:
        """Check database connection health."""
        try:
            async with self.get_session() as session:
                # Simple query to test connection
                await session.execute(select(1))
                return {"healthy": True, "status": "connected"}
        except Exception as e:
            logger.error("Database health check failed: %s", e)
            return {"healthy": False, "status": "error", "error": str(e)}

    async def close_all_connections(self) -> None:
        """Close all database connections."""
        # This would typically be handled by the session factory
        # For now, just log the intent
        logger.info("Closing all database connections")

    async def initialize(self) -> None:
        """Initialize database connections."""
        logger.info("Initializing database connections")


class DatabaseMigrationRepository:
    """Repository for Alembic migration information."""

    def __init__(self, session_factory, alembic_config):
        """Initialize with session factory and Alembic config."""
        self._session_factory = session_factory
        self._alembic_config = alembic_config

    @asynccontextmanager
    async def get_session(self):
        """Get a database session."""
        async with self._session_factory() as session:
            yield session

    async def get_current_version(self) -> str:
        """Get current database schema version from Alembic."""
        async with self.get_session() as session:
            # Query alembic_version table
            result = await session.execute("SELECT version_num FROM alembic_version")
            row = result.first()
            return row[0] if row else "base"

    async def get_target_version(self) -> str:
        """Get target/latest schema version from migration scripts."""
        # This would typically read from Alembic script directory
        # For now, return a placeholder
        return "head"

    async def get_pending_migrations(self) -> list[dict[str, str]]:
        """Get list of pending migrations."""
        # This would compare current version to available migrations
        # For now, return empty list
        return []


class SafetyRepository:
    """Repository for safety system state."""

    def __init__(self, session_factory):
        """Initialize with session factory only."""
        self._session_factory = session_factory

    @asynccontextmanager
    async def get_session(self):
        """Get a database session."""
        async with self._session_factory() as session:
            yield session

    async def get_current_state(self) -> dict[str, Any]:
        """Get current vehicle/system safety state."""
        # This would query actual safety system state
        # For now, return safe defaults for development
        return {
            "vehicle_speed": 0,
            "parking_brake": True,
            "engine_running": False,
            "transmission_gear": "PARK",
        }

    async def get_active_control_count(self) -> int:
        """Get count of active entity control operations."""
        # This would query active control operations
        return 0

    async def get_interlock_status(self) -> dict[str, Any]:
        """Get safety interlock status."""
        return {"all_satisfied": True, "violations": []}
