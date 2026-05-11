"""
Type stubs for DatabaseManager
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.engine import Inspector
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.performance import PerformanceMonitor
from backend.models.database import Base
from backend.repositories.database_repository import (
    DatabaseConnectionRepository,
    DatabaseSessionRepository,
    MigrationRepository,
)
from backend.services.database_engine import DatabaseEngine, DatabaseSettings
from backend.services.database_services import (
    DatabaseConnectionService,
    DatabaseMigrationService,
    DatabaseSessionService,
)

class DatabaseManager:
    """
    Enhanced database manager with multi-backend support using SQLAlchemy 2.0.
    
    Provides a robust foundation for database operations with proper connection
    management, health monitoring, and migration support across different backends.
    
    Now operates as a facade over specialized services for better separation of concerns.
    """

    _engine: DatabaseEngine
    _initialized: bool
    _connection_service: DatabaseConnectionService | None
    _session_service: DatabaseSessionService | None
    _migration_service: DatabaseMigrationService | None
    _legacy_mode: bool

    def __init__(
        self,
        database_settings: DatabaseSettings | None = None,
        database_path: Path | None = None,
        connection_service: DatabaseConnectionService | None = None,
        session_service: DatabaseSessionService | None = None,
        migration_service: DatabaseMigrationService | None = None,
        connection_repository: DatabaseConnectionRepository | None = None,
        session_repository: DatabaseSessionRepository | None = None,
        migration_repository: MigrationRepository | None = None,
        performance_monitor: PerformanceMonitor | None = None,
    ) -> None: ...

    async def initialize(self, create_tables: bool = True) -> None: ...

    async def close(self) -> None: ...

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]: ...

    async def health_check(self) -> dict[str, Any]: ...

    async def get_table_info(self) -> list[dict[str, Any]]: ...

    async def run_migrations(self) -> None: ...

    async def validate_schema(self) -> bool: ...

    def get_engine(self) -> DatabaseEngine: ...

    def is_initialized(self) -> bool: ...

    @property
    def inspector(self) -> Inspector | None: ...

    async def execute_query(self, query: str) -> Any: ...

    async def get_database_size(self) -> int: ...

    async def vacuum_database(self) -> None: ...
