"""
Tests for the PersistenceService.

Tests persistence functionality including directory management,
database backup/restore, user configuration, and storage statistics.
"""

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.core.config import PersistenceSettings
from backend.core.performance import PerformanceMonitor
from backend.repositories.persistence_repository import PersistenceRepository
from backend.services.persistence_service import PersistenceService


def _build_persistence_service(settings: PersistenceSettings) -> PersistenceService:
    """Build a PersistenceService with a real PersistenceRepository.

    This integration-style helper is used by every test in this module so the
    boilerplate of wiring repository + monitor + database_manager stays in one
    place.
    """
    monitor = MagicMock(spec=PerformanceMonitor)
    monitor.monitor_service_method = MagicMock(return_value=lambda fn: fn)
    # MonitoredRepository (the repo's base class) wraps every operation via
    # monitor.monitor_repository_operation(repo_name, op_name)(func) — also a
    # decorator factory that must return the original function unchanged.
    monitor.monitor_repository_operation = MagicMock(return_value=lambda fn: fn)

    # PersistenceRepository expects a database_manager but never calls it
    # for the file-system / backup paths these tests exercise.
    database_manager = MagicMock()

    repository = PersistenceRepository(
        database_manager=database_manager,
        performance_monitor=monitor,
        data_dir=settings.data_dir,
        backup_enabled=settings.backup_enabled,
        max_backup_size_mb=settings.max_backup_size_mb,
        backup_retention_days=settings.backup_retention_days,
    )

    return PersistenceService(
        persistence_repository=repository,
        performance_monitor=monitor,
        settings=settings,
        database_manager=database_manager,
    )


class TestPersistenceService:
    """Test cases for PersistenceService."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def test_settings(self, temp_data_dir):
        """Create test persistence settings with temporary directory."""
        return PersistenceSettings(
            data_dir=temp_data_dir,
            create_dirs=True,
            backup_enabled=True,
            backup_retention_days=7,
            max_backup_size_mb=100,
        )

    @pytest.fixture
    def persistence_service(self, test_settings):
        """Create a PersistenceService instance with test settings."""
        return _build_persistence_service(test_settings)

    @pytest.fixture
    def test_database(self, temp_data_dir):
        """Create a test SQLite database."""
        db_path = temp_data_dir / "test.db"
        conn = sqlite3.connect(str(db_path))

        # Create a simple test table with data
        conn.execute(
            """
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                value INTEGER
            )
        """
        )

        # Insert test data
        conn.execute("INSERT INTO test_table (name, value) VALUES (?, ?)", ("test1", 100))
        conn.execute("INSERT INTO test_table (name, value) VALUES (?, ?)", ("test2", 200))
        conn.commit()
        conn.close()

        return db_path

    async def test_initialization_enabled(self, persistence_service):
        """Test successful initialization when persistence is enabled."""
        success = await persistence_service.initialize()

        assert success is True
        assert persistence_service._initialized is True
        assert persistence_service.data_dir.exists()

    async def test_directory_creation(self, persistence_service):
        """Test that all required directories are created."""
        await persistence_service.initialize()

        # Check that all directories exist
        assert persistence_service.settings.get_database_dir().exists()
        assert persistence_service.settings.get_backup_dir().exists()
        assert persistence_service.settings.get_config_dir().exists()
        assert persistence_service.settings.get_themes_dir().exists()
        assert persistence_service.settings.get_dashboards_dir().exists()
        assert persistence_service.settings.get_logs_dir().exists()

    async def test_get_database_path(self, persistence_service):
        """Test database path generation."""
        db_path = await persistence_service.get_database_path("test_db")

        expected_path = persistence_service.settings.get_database_dir() / "test_db.db"
        assert db_path == expected_path

    async def test_database_backup_success(self, persistence_service, test_database):
        """Test successful database backup."""
        await persistence_service.initialize()

        backup_path = await persistence_service.backup_database(test_database)

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.suffix == ".db"
        assert backup_path.parent == persistence_service.settings.get_backup_dir()

    async def test_database_backup_custom_name(self, persistence_service, test_database):
        """Test database backup with custom name."""
        await persistence_service.initialize()

        custom_name = "custom_backup"
        backup_path = await persistence_service.backup_database(test_database, custom_name)

        assert backup_path is not None
        assert backup_path.name == "custom_backup.db"

    async def test_database_backup_nonexistent_file(self, persistence_service, temp_data_dir):
        """Test backup of non-existent database file."""
        await persistence_service.initialize()

        nonexistent_db = temp_data_dir / "nonexistent.db"
        backup_path = await persistence_service.backup_database(nonexistent_db)

        assert backup_path is None

    async def test_database_backup_disabled(self, temp_data_dir, test_database):
        """Test backup when backup is disabled."""
        settings = PersistenceSettings(data_dir=temp_data_dir, backup_enabled=False)
        service = _build_persistence_service(settings)
        await service.initialize()

        backup_path = await service.backup_database(test_database)

        assert backup_path is None

    async def test_database_restore_success(self, persistence_service, test_database):
        """Test successful database restore."""
        await persistence_service.initialize()

        # Create a backup first
        backup_path = await persistence_service.backup_database(test_database)
        assert backup_path is not None

        # Create target path
        target_path = persistence_service.settings.get_database_dir() / "restored.db"

        # Restore the database
        success = await persistence_service.restore_database(backup_path, target_path)

        assert success is True
        assert target_path.exists()

        # Verify the restored database has the same data
        conn = sqlite3.connect(str(target_path))
        cursor = conn.execute("SELECT COUNT(*) FROM test_table")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 2

    async def test_save_user_config(self, persistence_service):
        """Test saving user configuration."""
        await persistence_service.initialize()

        config_data = {
            "theme": "dark",
            "language": "en",
            "preferences": {"auto_refresh": True, "refresh_interval": 30},
        }

        success = await persistence_service.save_user_config("user_settings", config_data)

        assert success is True

        # Verify file was created
        config_file = persistence_service.settings.get_config_dir() / "user_settings.json"
        assert config_file.exists()

        # Verify content
        with open(config_file, encoding="utf-8") as f:
            saved_data = json.load(f)

        assert saved_data == config_data

    async def test_load_user_config(self, persistence_service):
        """Test loading user configuration."""
        await persistence_service.initialize()

        config_data = {"test": "data", "number": 42}

        # Save config first
        await persistence_service.save_user_config("test_config", config_data)

        # Load config
        loaded_data = await persistence_service.load_user_config("test_config")

        assert loaded_data == config_data

    async def test_load_nonexistent_config(self, persistence_service):
        """Test loading non-existent configuration."""
        await persistence_service.initialize()

        loaded_data = await persistence_service.load_user_config("nonexistent")

        assert loaded_data is None

    async def test_list_backups(self, persistence_service, test_database):
        """Test listing database backups."""
        await persistence_service.initialize()

        # Create multiple backups
        backup1 = await persistence_service.backup_database(test_database, "backup1")
        backup2 = await persistence_service.backup_database(test_database, "backup2")

        assert backup1 is not None
        assert backup2 is not None

        # List all backups
        backups = await persistence_service.list_backups()

        assert len(backups) >= 2
        backup_names = [b.name for b in backups]
        assert "backup1.db" in backup_names
        assert "backup2.db" in backup_names

    async def test_list_backups_filtered(self, persistence_service, test_database):
        """Test listing backups filtered by database name."""
        await persistence_service.initialize()

        # Create backups with different database names
        await persistence_service.backup_database(test_database, "test_backup1")
        await persistence_service.backup_database(test_database, "other_backup1")

        # List backups filtered by database name
        test_backups = await persistence_service.list_backups("test")

        # Should only return backups starting with "test_"
        assert len(test_backups) >= 1
        for backup in test_backups:
            assert backup.name.startswith("test_")

    async def test_get_storage_info(self, persistence_service):
        """Test getting storage information."""
        await persistence_service.initialize()

        storage_info = await persistence_service.get_storage_info()

        # storage_info is a StorageInfo Pydantic model.
        assert storage_info.enabled is True
        assert storage_info.data_dir is not None
        assert storage_info.directories is not None
        assert storage_info.disk_usage is not None
        assert storage_info.backup_settings is not None

        # Check directory information. Note: subdirectory key is plural
        # ('databases') to match the on-disk layout produced by
        # PersistenceRepository._ensure_directories().
        directories = storage_info.directories
        assert "databases" in directories
        assert "backups" in directories
        assert "logs" in directories

    async def test_shutdown(self, persistence_service):
        """Test service shutdown."""
        await persistence_service.initialize()

        # Should not raise any exceptions
        await persistence_service.shutdown()

        assert persistence_service._initialized is False

    @patch("backend.services.persistence_service.logger")
    async def test_initialization_error_handling(self, mock_logger, temp_data_dir):
        """Test error handling during initialization."""
        # Create settings with invalid directory (read-only)
        settings = PersistenceSettings(
            data_dir=Path("/invalid/readonly/path"), create_dirs=True
        )
        service = _build_persistence_service(settings)

        # Should handle permission errors gracefully
        success = await service.initialize()

        # Should still return True but log warnings
        assert success is True
        assert mock_logger.warning.called

    async def test_backup_cleanup(self, persistence_service, test_database):
        """Test automatic backup cleanup based on retention policy."""
        # Set short retention for testing — both on settings (used by service)
        # and on the underlying repository (which captured the original value
        # at construction time).
        persistence_service.settings.backup_retention_days = 1
        persistence_service._repository._backup_retention_days = 1
        await persistence_service.initialize()

        # Create a backup
        backup_path = await persistence_service.backup_database(test_database, "old_backup")
        assert backup_path is not None

        # Manually set the file modification time to be old. cleanup_old_backups
        # uses st_mtime (which os.utime can update); st_ctime is not portable
        # to set from userspace.
        import os
        import time

        old_time = time.time() - (2 * 24 * 60 * 60)  # 2 days ago
        os.utime(backup_path, (old_time, old_time))

        # Trigger cleanup by calling the public method
        await persistence_service.cleanup_old_backups()

        # Old backup should be removed
        assert not backup_path.exists()

    async def test_permissions_verification(self, persistence_service):
        """Test directory permissions verification."""
        await persistence_service.initialize()

        # Should complete without errors when permissions are correct
        await persistence_service._verify_permissions()

        # Test file should not exist after verification
        test_file = persistence_service.data_dir / ".permission_test"
        assert not test_file.exists()


class TestPersistenceServiceEdgeCases:
    """Test edge cases and error conditions for PersistenceService."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    async def test_backup_oversized_database(self, temp_data_dir):
        """Test backup rejection for oversized databases."""
        settings = PersistenceSettings(
            data_dir=temp_data_dir,
            backup_enabled=True,
            max_backup_size_mb=1,  # Very small limit
        )
        service = _build_persistence_service(settings)
        await service.initialize()

        # Create a database larger than the limit
        large_db = temp_data_dir / "large.db"
        with open(large_db, "wb") as f:
            f.write(b"0" * (2 * 1024 * 1024))  # 2MB file

        backup_path = await service.backup_database(large_db)

        assert backup_path is None

    async def test_concurrent_operations(self, temp_data_dir):
        """Test concurrent persistence operations."""
        settings = PersistenceSettings(data_dir=temp_data_dir)
        service = _build_persistence_service(settings)
        await service.initialize()

        # Test concurrent config saves
        async def save_config(index):
            return await service.save_user_config(f"config_{index}", {"data": index})

        tasks = [save_config(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All saves should succeed
        assert all(results)

        # All config files should exist
        for i in range(10):
            config_file = service.settings.get_config_dir() / f"config_{i}.json"
            assert config_file.exists()

    async def test_invalid_json_config_handling(self, temp_data_dir):
        """Test handling of corrupted JSON config files."""
        settings = PersistenceSettings(data_dir=temp_data_dir)
        service = _build_persistence_service(settings)
        await service.initialize()

        # Create an invalid JSON file
        config_file = service.settings.get_config_dir() / "invalid.json"
        config_file.write_text("{ invalid json content", encoding="utf-8")

        # Should return None for corrupted config
        config_data = await service.load_user_config("invalid")
        assert config_data is None
