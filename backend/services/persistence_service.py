"""
Persistence Service (Refactored with Repository Pattern)

Service for managing persistent data storage and backup operations.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import PersistenceSettings, get_persistence_settings
from backend.core.performance import PerformanceMonitor
from backend.models.persistence import (
    BackupInfo,
    BackupSettings,
    StorageInfo,
)
from backend.repositories.persistence_repository import PersistenceRepository
from backend.services.database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class PersistenceService:
    """
    Service for managing persistent data storage and backup operations.

    Refactored to use repository pattern with performance monitoring.
    """

    def __init__(
        self,
        persistence_repository: PersistenceRepository,
        performance_monitor: PerformanceMonitor,
        settings: PersistenceSettings | None = None,
        database_manager: DatabaseManager | None = None,
        config_repository: Any | None = None,
        dashboard_repository: Any | None = None,
    ):
        """
        Initialize the persistence service with repository.

        Args:
            persistence_repository: Repository for persistence operations
            performance_monitor: Performance monitoring instance
            settings: Persistence configuration settings
            database_manager: Optional database manager
            config_repository: Optional config repository
            dashboard_repository: Optional dashboard repository
        """
        self._repository = persistence_repository
        self._monitor = performance_monitor
        self._settings = settings or get_persistence_settings()
        self._initialized = False

        # Optional dependencies
        self._db_manager = database_manager
        self._config_repository = config_repository
        self._dashboard_repository = dashboard_repository

        # Apply performance monitoring
        self._apply_monitoring()

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        # Wrap methods with performance monitoring
        self.initialize = self._monitor.monitor_service_method("PersistenceService", "initialize")(
            self.initialize
        )

        self.get_database_path = self._monitor.monitor_service_method(
            "PersistenceService", "get_database_path"
        )(self.get_database_path)

        self.backup_database = self._monitor.monitor_service_method(
            "PersistenceService", "backup_database"
        )(self.backup_database)

        self.restore_database = self._monitor.monitor_service_method(
            "PersistenceService", "restore_database"
        )(self.restore_database)

        self.list_backups = self._monitor.monitor_service_method(
            "PersistenceService", "list_backups"
        )(self.list_backups)

        self.get_storage_info = self._monitor.monitor_service_method(
            "PersistenceService", "get_storage_info"
        )(self.get_storage_info)

        self.save_json_file = self._monitor.monitor_service_method(
            "PersistenceService", "save_json_file"
        )(self.save_json_file)

        self.load_json_file = self._monitor.monitor_service_method(
            "PersistenceService", "load_json_file"
        )(self.load_json_file)

    @property
    def settings(self) -> PersistenceSettings:
        """Get persistence settings."""
        return self._settings

    @property
    def data_dir(self) -> Path:
        """Get the base data directory."""
        return self._repository.get_data_dir()

    @property
    def enabled(self) -> bool:
        """Check if persistence is enabled."""
        return True  # Persistence is now mandatory

    @property
    def database_manager(self) -> DatabaseManager | None:
        """Get the database manager."""
        return self._db_manager

    @property
    def config_repository(self) -> Any | None:
        """Get the configuration repository."""
        return self._config_repository

    @property
    def dashboard_repository(self) -> Any | None:
        """Get the dashboard repository."""
        return self._dashboard_repository

    def set_database_manager(self, db_manager: DatabaseManager) -> None:
        """Set the database manager."""
        self._db_manager = db_manager

    async def initialize(self) -> bool:
        """
        Initialize the persistence service.

        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            return True

        try:
            # Verify directory permissions
            await self._verify_permissions()

            # Initialize database components if manager provided
            if self._db_manager:
                await self._initialize_database_components()

            # Clean up old backups if enabled
            if self._settings.backup_enabled:
                await self._repository.cleanup_old_backups()

            self._initialized = True
            logger.info(f"Persistence service initialized with data directory: {self.data_dir}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize persistence service: {e}")
            return False

    async def _initialize_database_components(self) -> None:
        """Initialize database repositories if available."""
        try:
            if self._db_manager and not self._config_repository:
                # Import here to avoid circular dependencies
                from backend.services.repositories import ConfigRepository, DashboardRepository

                self._config_repository = ConfigRepository(self._db_manager)
                self._dashboard_repository = DashboardRepository(self._db_manager)

                logger.info("Database repositories initialized")

        except Exception as e:
            logger.error(f"Failed to initialize database components: {e}")
            # Non-fatal - repositories are optional

    async def get_configuration(self, key: str, namespace: str = "default") -> str | None:
        """
        Get a configuration value from the database.

        Args:
            key: Configuration key
            namespace: Configuration namespace (defaults to "default")

        Returns:
            Configuration value if found, None otherwise
        """
        if not self._config_repository:
            return None
        return await self._config_repository.get(namespace, key)

    async def set_configuration(self, key: str, value: str, namespace: str = "default") -> bool:
        """
        Set a configuration value in the database.

        Args:
            key: Configuration key
            value: Configuration value
            namespace: Configuration namespace (defaults to "default")

        Returns:
            True if successful, False otherwise
        """
        if not self._config_repository:
            return False
        try:
            return await self._config_repository.set(namespace, key, value)
        except Exception as e:
            logger.error(f"Failed to set configuration {key}: {e}")
            return False

    async def get_dashboard_config(self, dashboard_id: str | None = None) -> dict[str, Any] | None:
        """
        Get dashboard configuration from the database.

        Args:
            dashboard_id: Dashboard ID, defaults to 'default'

        Returns:
            Dashboard configuration if found, None otherwise
        """
        if not self._dashboard_repository:
            return None

        dashboard_id = dashboard_id or "default"
        try:
            # Try to get by name first, then by ID if it's numeric
            dashboard = await self._dashboard_repository.get_by_name(dashboard_id)
            if not dashboard and dashboard_id.isdigit():
                dashboard = await self._dashboard_repository.get_by_id(int(dashboard_id))
            return dashboard
        except Exception as e:
            logger.error(f"Failed to get dashboard config {dashboard_id}: {e}")
            return None

    async def save_dashboard_config(
        self, config: dict[str, Any], dashboard_id: str | None = None
    ) -> bool:
        """
        Save dashboard configuration to the database.

        Args:
            config: Dashboard configuration
            dashboard_id: Dashboard ID, defaults to 'default'

        Returns:
            True if successful, False otherwise
        """
        if not self._dashboard_repository:
            return False

        dashboard_id = dashboard_id or "default"
        try:
            return await self._dashboard_repository.save_config(dashboard_id, config)
        except Exception as e:
            logger.error(f"Failed to save dashboard config {dashboard_id}: {e}")
            return False

    async def _verify_permissions(self) -> None:
        """Verify that we have read/write permissions to data directories."""
        test_file = self.data_dir / ".permission_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
        except (OSError, PermissionError) as e:
            logger.warning(f"Limited permissions for data directory {self.data_dir}: {e}")

    async def get_database_path(self, database_name: str) -> Path:
        """
        Get the path for a database file using repository.

        Args:
            database_name: Name of the database (without .db extension)

        Returns:
            Path to the database file
        """
        return await self._repository.get_database_path(database_name)

    async def backup_database(
        self, database_path: Path, backup_name: str | None = None
    ) -> Path | None:
        """
        Create a backup of a SQLite database using repository.

        Args:
            database_path: Path to the source database
            backup_name: Optional custom backup name

        Returns:
            Path to the backup file if successful, None otherwise
        """
        if not self.enabled:
            return None

        return await self._repository.backup_database(database_path, backup_name)

    async def restore_database(self, backup_path: Path, target_path: Path) -> bool:
        """
        Restore a database from backup using repository.

        Args:
            backup_path: Path to the backup file
            target_path: Path where to restore the database

        Returns:
            True if restore successful, False otherwise
        """
        if not self.enabled:
            return False

        return await self._repository.restore_database(backup_path, target_path)

    async def save_user_config(self, config_name: str, config_data: dict[str, Any]) -> bool:
        """
        Save user configuration data using repository.

        Args:
            config_name: Name of the configuration file
            config_data: Configuration data to save

        Returns:
            True if save successful, False otherwise
        """
        if not self.enabled:
            return False

        return await self._repository.save_json_file("config", config_name, config_data)

    async def load_user_config(self, config_name: str) -> dict[str, Any] | None:
        """
        Load user configuration data using repository.

        Args:
            config_name: Name of the configuration file

        Returns:
            Configuration data if successful, None otherwise
        """
        if not self.enabled:
            return None

        return await self._repository.load_json_file("config", config_name)

    async def save_json_file(self, subdirectory: str, filename: str, data: dict[str, Any]) -> bool:
        """
        Save JSON data to a file using repository.

        Args:
            subdirectory: Subdirectory under data_dir
            filename: Filename (with or without .json extension)
            data: Data to save

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        return await self._repository.save_json_file(subdirectory, filename, data)

    async def load_json_file(self, subdirectory: str, filename: str) -> dict[str, Any] | None:
        """
        Load JSON data from a file using repository.

        Args:
            subdirectory: Subdirectory under data_dir
            filename: Filename (with or without .json extension)

        Returns:
            Loaded data if successful, None otherwise
        """
        if not self.enabled:
            return None

        return await self._repository.load_json_file(subdirectory, filename)

    async def list_backups(self, database_name: str | None = None) -> list[BackupInfo]:
        """
        List available database backups using repository.

        Args:
            database_name: Optional filter by database name

        Returns:
            List of BackupInfo objects
        """
        if not self.enabled:
            return []

        return await self._repository.list_backups(database_name)

    async def delete_backup(self, backup_name: str) -> bool:
        """
        Delete a specific backup file.

        Args:
            backup_name: Name of the backup file to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            backup_path = self._repository.get_backup_dir() / backup_name

            if not backup_path.exists():
                logger.warning(f"Backup file {backup_name} not found")
                return False

            if not backup_path.is_file():
                logger.warning(f"Backup path {backup_name} is not a file")
                return False

            backup_path.unlink()
            logger.info(f"Successfully deleted backup: {backup_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete backup {backup_name}: {e}")
            return False

    async def get_storage_info(self) -> StorageInfo:
        """
        Get storage information and statistics using repository.

        Returns:
            StorageInfo model with storage statistics
        """
        if not self.enabled:
            return StorageInfo(
                enabled=False,
                data_dir=None,
                directories=None,
                disk_usage=None,
                backup_settings=BackupSettings(enabled=False, retention_days=0, max_size_mb=0),
                error="Persistence service not enabled",
            )

        # Get storage info from repository
        storage_info = await self._repository.get_storage_info()

        # Add backup settings
        backup_settings = BackupSettings(
            enabled=self._settings.backup_enabled,
            retention_days=self._settings.backup_retention_days,
            max_size_mb=self._settings.max_backup_size_mb,
        )

        return StorageInfo(
            enabled=True,
            data_dir=str(self.data_dir),
            directories=storage_info.directories,
            disk_usage=storage_info.disk_usage,
            backup_settings=backup_settings,
            error=None,
        )

    async def shutdown(self) -> None:
        """Clean shutdown of the persistence service."""
        if not self._initialized:
            return

        logger.info("Shutting down persistence service")

        # Shutdown database components
        if self._db_manager:
            try:
                # Close any open sessions/connections
                logger.debug("Shutting down database manager")
                # Note: DatabaseManager doesn't have an explicit shutdown method yet
                # but this is where we'd call it
                self._db_manager = None
                self._config_repository = None
                self._dashboard_repository = None
            except Exception as e:
                logger.warning(f"Error during database shutdown: {e}")

        # Perform final backup cleanup if enabled
        if self.enabled and self._settings.backup_enabled:
            await self._repository.cleanup_old_backups()

        self._initialized = False
