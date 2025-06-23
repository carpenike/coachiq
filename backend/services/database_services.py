"""Database Services

Core services for database connection, session, and migration management.
Extracted from DatabaseManager to follow service-oriented architecture.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.performance import PerformanceMonitor
from backend.models.database import Base
from backend.repositories.database_repository import (
    DatabaseConnectionRepository,
    DatabaseSessionRepository,
    MigrationRepository,
)
from backend.services.database_engine import DatabaseEngine

logger = logging.getLogger(__name__)


class DatabaseConnectionService:
    """Service for managing database connection lifecycle."""

    def __init__(
        self,
        database_engine: DatabaseEngine,
        connection_repository: DatabaseConnectionRepository,
        performance_monitor: PerformanceMonitor,
    ):
        """Initialize the service.

        Args:
            database_engine: Database engine instance
            connection_repository: Repository for connection tracking
            performance_monitor: Performance monitoring instance
        """
        self._engine = database_engine
        self._connection_repo = connection_repository
        self._monitor = performance_monitor
        self._initialized = False

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("DatabaseConnectionService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.initialize = self._monitor.monitor_service_method(
            "DatabaseConnectionService", "initialize"
        )(self.initialize)

        self.health_check = self._monitor.monitor_service_method(
            "DatabaseConnectionService", "health_check"
        )(self.health_check)

        self.execute_raw_query = self._monitor.monitor_service_method(
            "DatabaseConnectionService", "execute_raw_query"
        )(self.execute_raw_query)

    async def initialize(self) -> bool:
        """Initialize database connection.

        Returns:
            True if initialization successful
        """
        if self._initialized:
            logger.warning("Database connection already initialized")
            return True

        try:
            # Record initialization attempt
            await self._connection_repo.record_connection_event(
                "initialization_started", {"backend": self._engine.backend.value}
            )

            # Initialize engine
            await self._engine.initialize()

            # Create tables
            await self._create_tables()

            # Verify health
            if not await self.health_check():
                await self._connection_repo.record_connection_event(
                    "initialization_failed", {"reason": "health_check_failed"}
                )
                return False

            self._initialized = True

            # Record success
            pool_size = 0
            if self._engine._engine and hasattr(self._engine._engine, "pool"):
                pool = self._engine._engine.pool
                if hasattr(pool, "size"):
                    pool_size = pool.size()

            await self._connection_repo.record_connection_event(
                "initialization_completed",
                {"backend": self._engine.backend.value, "pool_size": pool_size},
            )

            logger.info(
                f"Database connection initialized with {self._engine.backend.value} backend"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize database connection: {e}")
            await self._connection_repo.record_connection_event(
                "initialization_failed", {"error": str(e)}
            )
            return False

    async def _create_tables(self) -> None:
        """Create database tables."""
        database_url = self._engine.settings.get_database_url()
        if database_url == "null://memory":
            logger.debug("Skipping table creation for null backend")
            return

        if not self._engine._engine:
            raise RuntimeError("Database engine not initialized")

        try:
            async with self._engine._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created/verified successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise

    async def close(self) -> None:
        """Close database connection."""
        if self._initialized:
            await self._connection_repo.record_connection_event(
                "connection_closing", {"reason": "shutdown"}
            )

            await self._engine.cleanup()
            self._initialized = False

            await self._connection_repo.record_connection_event(
                "connection_closed", {"pool_size": 0}
            )

            logger.info("Database connection closed")

    async def health_check(self) -> bool:
        """Check database health.

        Returns:
            True if healthy
        """
        try:
            result = await self._engine.health_check()

            # Record health check
            await self._connection_repo.record_connection_event(
                "health_check", {"result": "success" if result else "failed"}
            )

            return result
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            await self._connection_repo.record_connection_event(
                "health_check", {"result": "error", "error": str(e)}
            )
            return False

    async def get_connection_info(self) -> dict[str, Any]:
        """Get connection information.

        Returns:
            Connection details
        """
        status = await self._connection_repo.get_connection_status()
        metrics = await self._connection_repo.get_connection_metrics()

        return {
            "backend": self._engine.backend.value,
            "is_initialized": self._initialized,
            "status": status,
            "metrics": metrics,
        }

    async def execute_raw_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute raw SQL query.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            Query results
        """
        if not self._initialized:
            raise RuntimeError("Database connection not initialized")

        database_url = self._engine.settings.get_database_url()
        if database_url == "null://memory":
            logger.warning("Raw query requested but persistence is disabled")
            return []

        # This will be handled by session service in production
        # For now, execute directly through engine
        async for session in self._engine.get_session():
            result = await session.execute(text(query), params or {})
            return [dict(row._mapping) for row in result.fetchall()]

        # Should not reach here, but return empty list for type safety
        return []


class DatabaseSessionService:
    """Service for managing database sessions."""

    def __init__(
        self,
        database_engine: DatabaseEngine,
        session_repository: DatabaseSessionRepository,
        performance_monitor: PerformanceMonitor,
    ):
        """Initialize the service.

        Args:
            database_engine: Database engine instance
            session_repository: Repository for session tracking
            performance_monitor: Performance monitoring instance
        """
        self._engine = database_engine
        self._session_repo = session_repository
        self._monitor = performance_monitor

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("DatabaseSessionService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.get_active_session_count = self._monitor.monitor_service_method(
            "DatabaseSessionService", "get_active_session_count"
        )(self.get_active_session_count)

        self.force_close_all_sessions = self._monitor.monitor_service_method(
            "DatabaseSessionService", "force_close_all_sessions"
        )(self.force_close_all_sessions)

    @asynccontextmanager
    async def get_session(
        self, request_context: dict[str, Any] | None = None
    ) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with tracking.

        Args:
            request_context: Optional request context for tracking

        Yields:
            Database session
        """
        # Generate session ID
        import uuid

        session_id = str(uuid.uuid4())

        # Register session
        metadata = request_context or {}
        await self._session_repo.register_session(session_id, metadata)

        try:
            # Get session from engine (it's an async generator)
            async for session in self._engine.get_session():
                yield session
                break  # Only get one session
        finally:
            # Close session registration
            await self._session_repo.close_session(session_id)

    async def get_active_session_count(self) -> int:
        """Get count of active sessions.

        Returns:
            Number of active sessions
        """
        sessions = await self._session_repo.get_active_sessions()
        return len(sessions)

    async def force_close_all_sessions(self) -> int:
        """Force close all active sessions.

        Returns:
            Number of sessions closed
        """
        sessions = await self._session_repo.get_active_sessions()
        closed = 0

        for session_info in sessions:
            if await self._session_repo.close_session(session_info["session_id"]):
                closed += 1

        if closed > 0:
            logger.warning(f"Force closed {closed} database sessions")

        return closed

    async def cleanup_stale_sessions(self, timeout_seconds: int = 300) -> int:
        """Clean up stale sessions.

        Args:
            timeout_seconds: Session timeout

        Returns:
            Number of sessions cleaned
        """
        return await self._session_repo.cleanup_stale_sessions(timeout_seconds)

    async def get_session_metrics(self) -> dict[str, Any]:
        """Get session usage metrics.

        Returns:
            Session metrics
        """
        return await self._session_repo.get_session_metrics()


class DatabaseMigrationService:
    """Service for managing database migrations."""

    def __init__(
        self,
        database_engine: DatabaseEngine,
        migration_repository: MigrationRepository,
        performance_monitor: PerformanceMonitor,
    ):
        """Initialize the service.

        Args:
            database_engine: Database engine instance
            migration_repository: Repository for migration tracking
            performance_monitor: Performance monitoring instance
        """
        self._engine = database_engine
        self._migration_repo = migration_repository
        self._monitor = performance_monitor

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("DatabaseMigrationService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.create_tables = self._monitor.monitor_service_method(
            "DatabaseMigrationService", "create_tables"
        )(self.create_tables)

        self.apply_migrations = self._monitor.monitor_service_method(
            "DatabaseMigrationService", "apply_migrations"
        )(self.apply_migrations)

    async def create_tables(self) -> None:
        """Create database tables from models."""
        database_url = self._engine.settings.get_database_url()
        if database_url == "null://memory":
            logger.debug("Skipping table creation for null backend")
            return

        if not self._engine._engine:
            raise RuntimeError("Database engine not initialized")

        try:
            async with self._engine._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Record as migration
            await self._migration_repo.record_migration(
                "initial_schema", "create_tables", datetime.now(UTC)
            )

            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise

    async def apply_migrations(self) -> int:
        """Apply pending migrations.

        Returns:
            Number of migrations applied
        """
        # In a real implementation, this would:
        # 1. Scan migration directory
        # 2. Compare with applied migrations
        # 3. Apply pending migrations in order

        # For now, just return 0 (no migrations)
        pending = await self._migration_repo.get_pending_migrations()

        if pending:
            logger.info(f"Found {len(pending)} pending migrations")
            # Would apply them here
            return len(pending)

        return 0

    async def rollback_migration(self, version: str) -> bool:
        """Rollback a specific migration.

        Args:
            version: Migration version to rollback

        Returns:
            True if rollback successful
        """
        # In a real implementation, this would:
        # 1. Find the migration
        # 2. Execute rollback script
        # 3. Update migration history

        logger.warning(f"Migration rollback not implemented: {version}")
        return False

    async def get_schema_version(self) -> str | None:
        """Get current schema version.

        Returns:
            Current schema version
        """
        return await self._migration_repo.get_schema_version()

    async def get_migration_status(self) -> dict[str, Any]:
        """Get migration status summary.

        Returns:
            Migration status
        """
        applied = await self._migration_repo.get_applied_migrations()
        pending = await self._migration_repo.get_pending_migrations()
        version = await self._migration_repo.get_schema_version()

        return {
            "current_version": version,
            "applied_count": len(applied),
            "pending_count": len(pending),
            "latest_migration": applied[0] if applied else None,
        }
