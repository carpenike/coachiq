"""Persistence operations repository.

This repository manages data persistence, backup operations, and directory structure
using the repository pattern.
"""

import asyncio
import json
import logging
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.core.performance import PerformanceMonitor
from backend.models.persistence import (
    BackupInfo,
    BackupSettings,
    DirectoryInfo,
    DiskUsageInfo,
    StorageInfo,
)
from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class PersistenceRepository(MonitoredRepository):
    """Repository for persistence operations and backup management."""

    def __init__(
        self,
        database_manager,
        performance_monitor: PerformanceMonitor,
        data_dir: Path,
        backup_enabled: bool = True,
        max_backup_size_mb: float = 100,
        backup_retention_days: int = 7,
    ):
        """Initialize persistence repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
            data_dir: Base data directory
            backup_enabled: Whether backups are enabled
            max_backup_size_mb: Maximum backup size in MB
            backup_retention_days: Days to retain backups
        """
        super().__init__(database_manager, performance_monitor)
        self._data_dir = data_dir
        self._backup_enabled = backup_enabled
        self._max_backup_size_mb = max_backup_size_mb
        self._backup_retention_days = backup_retention_days
        self._lock = asyncio.Lock()

        # Ensure directories exist
        self._ensure_directories()

    def _ensure_directories(self) -> list[Path]:
        """Ensure all required directories exist.

        Returns:
            List of created directories
        """
        created = []
        directories = [
            self._data_dir,
            self._data_dir / "databases",
            self._data_dir / "backups",
            self._data_dir / "themes",
            self._data_dir / "dashboards",
            self._data_dir / "logs",
            self._data_dir / "temp",
        ]

        for directory in directories:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                created.append(directory)

        return created

    @MonitoredRepository._monitored_operation("get_database_path")
    async def get_database_path(self, database_name: str) -> Path:
        """Get the path for a database file.

        Args:
            database_name: Name of the database (without .db extension)

        Returns:
            Path to the database file
        """
        if not database_name.endswith(".db"):
            database_name += ".db"
        return self._data_dir / "databases" / database_name

    @MonitoredRepository._monitored_operation("backup_database")
    async def backup_database(
        self, database_path: Path, backup_name: str | None = None
    ) -> Path | None:
        """Create a backup of a SQLite database.

        Args:
            database_path: Path to the source database
            backup_name: Optional custom backup name

        Returns:
            Path to the backup file if successful, None otherwise
        """
        if not self._backup_enabled:
            return None

        if not database_path.exists():
            logger.warning(f"Database file {database_path} does not exist")
            return None

        try:
            # Generate backup filename
            if backup_name is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"{database_path.stem}_{timestamp}.db"
            elif not backup_name.endswith(".db"):
                backup_name += ".db"

            backup_path = self._data_dir / "backups" / backup_name

            # Check file size
            file_size_mb = database_path.stat().st_size / (1024 * 1024)
            if file_size_mb > self._max_backup_size_mb:
                logger.warning(
                    f"Database size ({file_size_mb:.1f}MB) exceeds limit "
                    f"({self._max_backup_size_mb}MB)"
                )
                return None

            # Perform backup
            await self._backup_sqlite_database(database_path, backup_path)

            logger.info(f"Database backup created: {backup_path}")
            return backup_path

        except Exception as e:
            logger.error(f"Failed to backup database: {e}")
            return None

    async def _backup_sqlite_database(self, source_path: Path, backup_path: Path) -> None:
        """Backup SQLite database using the backup API.

        Args:
            source_path: Source database path
            backup_path: Backup destination path
        """

        def backup_db():
            source_conn = sqlite3.connect(str(source_path))
            backup_conn = sqlite3.connect(str(backup_path))

            try:
                source_conn.backup(backup_conn)
            finally:
                source_conn.close()
                backup_conn.close()

        # Run in thread pool to avoid blocking
        await asyncio.get_running_loop().run_in_executor(None, backup_db)

    @MonitoredRepository._monitored_operation("restore_database")
    async def restore_database(self, backup_path: Path, target_path: Path) -> bool:
        """Restore a database from backup.

        Args:
            backup_path: Path to the backup file
            target_path: Path where to restore the database

        Returns:
            True if restore successful, False otherwise
        """
        if not backup_path.exists():
            logger.error(f"Backup file {backup_path} does not exist")
            return False

        try:
            # Create target directory if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy backup to target
            shutil.copy2(backup_path, target_path)

            logger.info(f"Database restored from {backup_path} to {target_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to restore database: {e}")
            return False

    @MonitoredRepository._monitored_operation("list_backups")
    async def list_backups(self, database_name: str | None = None) -> list[BackupInfo]:
        """List available backups.

        Args:
            database_name: Optional filter by database name

        Returns:
            List of backup information
        """
        backup_dir = self._data_dir / "backups"
        backups = []

        if not backup_dir.exists():
            return backups

        for backup_file in backup_dir.glob("*.db"):
            # Filter by database name if specified
            if database_name and not backup_file.name.startswith(database_name):
                continue

            stat = backup_file.stat()
            backups.append(
                BackupInfo(
                    name=backup_file.name,
                    path=backup_file,
                    size_bytes=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_ctime),
                    database_name=backup_file.stem.split("_")[0],
                )
            )

        # Sort by creation time, newest first
        backups.sort(key=lambda b: b.created_at, reverse=True)
        return backups

    @MonitoredRepository._monitored_operation("cleanup_old_backups")
    async def cleanup_old_backups(self) -> int:
        """Clean up backups older than retention period.

        Returns:
            Number of backups deleted
        """
        if not self._backup_enabled:
            return 0

        backup_dir = self._data_dir / "backups"
        if not backup_dir.exists():
            return 0

        cutoff_date = datetime.now() - timedelta(days=self._backup_retention_days)
        deleted_count = 0

        for backup_file in backup_dir.glob("*.db"):
            try:
                created_at = datetime.fromtimestamp(backup_file.stat().st_ctime)
                if created_at < cutoff_date:
                    backup_file.unlink()
                    deleted_count += 1
                    logger.debug(f"Deleted old backup: {backup_file}")
            except Exception as e:
                logger.warning(f"Failed to delete backup {backup_file}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old backups")

        return deleted_count

    @MonitoredRepository._monitored_operation("save_json_file")
    async def save_json_file(self, subdirectory: str, filename: str, data: dict[str, Any]) -> bool:
        """Save JSON data to a file.

        Args:
            subdirectory: Subdirectory under data_dir
            filename: Filename (with or without .json extension)
            data: Data to save

        Returns:
            True if successful, False otherwise
        """
        if not filename.endswith(".json"):
            filename += ".json"

        file_path = self._data_dir / subdirectory / filename

        try:
            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON data
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)

            return True

        except Exception as e:
            logger.error(f"Failed to save JSON file {file_path}: {e}")
            return False

    @MonitoredRepository._monitored_operation("load_json_file")
    async def load_json_file(self, subdirectory: str, filename: str) -> dict[str, Any] | None:
        """Load JSON data from a file.

        Args:
            subdirectory: Subdirectory under data_dir
            filename: Filename (with or without .json extension)

        Returns:
            Loaded data if successful, None otherwise
        """
        if not filename.endswith(".json"):
            filename += ".json"

        file_path = self._data_dir / subdirectory / filename

        if not file_path.exists():
            return None

        try:
            with open(file_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load JSON file {file_path}: {e}")
            return None

    @MonitoredRepository._monitored_operation("get_storage_info")
    async def get_storage_info(self) -> StorageInfo:
        """Get storage information and statistics.

        Returns:
            Storage information
        """
        total_size = 0
        file_count = 0
        directory_info = {}

        # Calculate sizes for each directory
        for subdir in ["databases", "backups", "themes", "dashboards", "logs"]:
            dir_path = self._data_dir / subdir
            if dir_path.exists():
                dir_size, dir_files = self._calculate_directory_size(dir_path)
                total_size += dir_size
                file_count += dir_files
                directory_info[subdir] = DirectoryInfo(
                    path=dir_path, size_bytes=dir_size, file_count=dir_files
                )

        # Get disk usage
        disk_usage = shutil.disk_usage(self._data_dir)

        return StorageInfo(
            total_size_bytes=total_size,
            total_file_count=file_count,
            directories=directory_info,
            disk_usage=DiskUsageInfo(
                total=disk_usage.total,
                used=disk_usage.used,
                free=disk_usage.free,
                percent=(disk_usage.used / disk_usage.total) * 100,
            ),
        )

    def _calculate_directory_size(self, path: Path) -> tuple[int, int]:
        """Calculate total size and file count for a directory.

        Args:
            path: Directory path

        Returns:
            Tuple of (total_size_bytes, file_count)
        """
        total_size = 0
        file_count = 0

        for item in path.rglob("*"):
            if item.is_file():
                total_size += item.stat().st_size
                file_count += 1

        return total_size, file_count

    def get_data_dir(self) -> Path:
        """Get the base data directory.

        Returns:
            Data directory path
        """
        return self._data_dir

    def get_backup_dir(self) -> Path:
        """Get the backup directory.

        Returns:
            Backup directory path
        """
        return self._data_dir / "backups"

    def get_database_dir(self) -> Path:
        """Get the database directory.

        Returns:
            Database directory path
        """
        return self._data_dir / "databases"
