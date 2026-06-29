"""
SQLite Persistence Implementation

Provides SQLite-based implementations of persistence interfaces for
when persistence is enabled.
"""

import logging

from backend.models.persistence import DashboardConfiguration
from backend.models.unmapped import UnmappedEntryModel
from backend.services.database.database_engine import DatabaseEngine, DatabaseSettings
from backend.services.persistence_interface import (
    ConfigRepositoryInterface,
    DashboardRepositoryInterface,
    PersistenceServiceInterface,
    UnmappedRepositoryInterface,
)
from backend.services.database.repositories import ConfigRepository, DashboardRepository

logger = logging.getLogger(__name__)


class SQLitePersistenceService(PersistenceServiceInterface):
    """SQLite-based persistence service for when persistence is enabled."""

    def __init__(self, database_path: str):
        """
        Initialize the SQLite persistence service.

        Args:
            database_path: Path to the SQLite database file
        """
        self.database_path = database_path
        self.engine: DatabaseEngine | None = None
        self._config_repo: SQLiteConfigRepository | None = None
        self._dashboard_repo: SQLiteDashboardRepository | None = None
        self._unmapped_repo: SQLiteUnmappedRepository | None = None

    async def initialize(self) -> None:
        """Initialize the persistence service."""
        try:
            # Create database settings with the specified path
            settings = DatabaseSettings()
            settings.sqlite_path = self.database_path

            # Initialize database engine
            self.engine = DatabaseEngine(settings)
            await self.engine.initialize()

            # Initialize repositories
            self._config_repo = SQLiteConfigRepository(self.engine)
            self._dashboard_repo = SQLiteDashboardRepository(self.engine)
            self._unmapped_repo = SQLiteUnmappedRepository(self.engine)

            logger.info(
                f"SQLite persistence service initialized with database: {self.database_path}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize SQLite persistence service: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if the persistence service is healthy."""
        if not self.engine:
            return False
        return await self.engine.health_check()

    async def close(self) -> None:
        """Close the persistence service."""
        if self.engine:
            await self.engine.close()
            self.engine = None
        logger.info("SQLite persistence service closed")

    async def shutdown(self) -> None:
        """Shutdown the persistence service."""
        await self.close()
        logger.info("SQLite persistence service shutdown")

    @property
    def config_repo(self) -> ConfigRepositoryInterface:
        """Get the configuration repository."""
        if self._config_repo is None:
            msg = "Persistence service not initialized"
            raise RuntimeError(msg)
        return self._config_repo

    @property
    def dashboard_repo(self) -> DashboardRepositoryInterface:
        """Get the dashboard repository."""
        if self._dashboard_repo is None:
            msg = "Persistence service not initialized"
            raise RuntimeError(msg)
        return self._dashboard_repo

    @property
    def unmapped_repo(self) -> UnmappedRepositoryInterface:
        """Get the unmapped repository."""
        if self._unmapped_repo is None:
            msg = "Persistence service not initialized"
            raise RuntimeError(msg)
        return self._unmapped_repo


class SQLiteConfigRepository(ConfigRepositoryInterface):
    """SQLite implementation of configuration repository."""

    def __init__(self, engine: DatabaseEngine):
        """Initialize the SQLite config repository."""
        self._config_repo = ConfigRepository(engine)

    async def get_user_config(self, key: str) -> str | None:
        """Get a user configuration value."""
        return await self._config_repo.get("default", key)

    async def set_user_config(self, key: str, value: str) -> None:
        """Set a user configuration value."""
        await self._config_repo.set("default", key, value)

    async def get_all_user_configs(self) -> dict[str, str]:
        """Get all user configuration values."""
        return await self._config_repo.get_all("default")

    async def delete_user_config(self, key: str) -> bool:
        """Delete a user configuration value."""
        return await self._config_repo.delete("default", key)


class SQLiteDashboardRepository(DashboardRepositoryInterface):
    """SQLite implementation of dashboard repository."""

    def __init__(self, engine: DatabaseEngine):
        """Initialize the SQLite dashboard repository."""
        self._dashboard_repo = DashboardRepository(engine)

    async def get_dashboard(self, dashboard_id: str) -> DashboardConfiguration | None:
        """Get a dashboard by ID."""
        config_data = await self._dashboard_repo.get_by_name(dashboard_id)
        if config_data:
            return DashboardConfiguration(config_name=dashboard_id, data=config_data)
        return None

    async def save_dashboard(self, dashboard: DashboardConfiguration) -> None:
        """Save a dashboard configuration."""
        config_data = dashboard.model_dump(exclude={"config_name"})
        await self._dashboard_repo.save_config(dashboard.config_name, config_data)

    async def list_dashboards(self) -> list[DashboardConfiguration]:
        """List all dashboards."""
        # Note: This would require extending the DashboardRepository to list all dashboards
        # For now, return empty list as this functionality isn't implemented in the existing repo
        return []

    async def delete_dashboard(self, dashboard_id: str) -> bool:
        """Delete a dashboard by ID."""
        return await self._dashboard_repo.delete_by_name(dashboard_id)


class SQLiteUnmappedRepository(UnmappedRepositoryInterface):
    """SQLite implementation of unmapped PGN repository."""

    def __init__(self, engine: DatabaseEngine):
        """Initialize the SQLite unmapped repository."""
        self.engine = engine

    async def get_unmapped_pgns(self) -> list[UnmappedEntryModel]:
        """Get all unmapped PGNs."""
        # Note: This would require creating a new repository for unmapped PGNs
        # For now, return empty list as this isn't implemented yet
        return []

    async def save_unmapped_pgn(self, pgn: UnmappedEntryModel) -> None:
        """Save an unmapped PGN."""
        # Note: This would require creating a new repository for unmapped PGNs

    async def delete_unmapped_pgn(self, pgn: int) -> bool:
        """Delete an unmapped PGN."""
        # Note: This would require creating a new repository for unmapped PGNs
        return False
