"""Tests for database update service and related components."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.repositories.database_update_repository import (
    DatabaseBackupRepository,
    DatabaseConnectionRepository,
    DatabaseMigrationRepository,
    MigrationHistoryRepository,
    SafetyRepository,
)
from backend.services.database_update_service import DatabaseUpdateService
from backend.services.migration_safety_validator import MigrationSafetyValidator


@pytest.fixture
def mock_repositories():
    """Create mock repositories for testing."""
    return {
        "connection_repo": AsyncMock(spec=DatabaseConnectionRepository),
        "migration_repo": AsyncMock(spec=DatabaseMigrationRepository),
        "safety_validator": AsyncMock(spec=MigrationSafetyValidator),
        "backup_repo": AsyncMock(spec=DatabaseBackupRepository),
        "history_repo": AsyncMock(spec=MigrationHistoryRepository),
        "websocket_repo": AsyncMock(),
        "performance_monitor": AsyncMock(),
    }


@pytest.fixture
def database_update_service(mock_repositories):
    """Create DatabaseUpdateService instance with mocked dependencies."""
    service = DatabaseUpdateService(
        connection_repository=mock_repositories["connection_repo"],
        migration_repository=mock_repositories["migration_repo"],
        safety_validator=mock_repositories["safety_validator"],
        backup_repository=mock_repositories["backup_repo"],
        history_repository=mock_repositories["history_repo"],
        websocket_repository=mock_repositories["websocket_repo"],
        performance_monitor=mock_repositories["performance_monitor"],
    )
    return service


class TestDatabaseUpdateService:
    """Test suite for DatabaseUpdateService."""

    @pytest.mark.asyncio
    async def test_get_migration_status(self, database_update_service, mock_repositories):
        """Test getting migration status."""
        # Setup mocks
        mock_repositories["migration_repo"].get_current_version.return_value = "abc123"
        mock_repositories["migration_repo"].get_target_version.return_value = "def456"
        mock_repositories["migration_repo"].get_pending_migrations.return_value = [
            {"version": "def456", "description": "Add new tables"}
        ]
        mock_repositories["safety_validator"].validate_safe_for_migration.return_value = (
            True,
            [],
        )
        mock_repositories["backup_repo"].get_latest_backup.return_value = {
            "id": 1,
            "path": "/backups/test.db",
            "created_at": "2024-01-01T00:00:00",
        }

        # Execute
        status = await database_update_service.get_migration_status()

        # Assert
        assert status["current_version"] == "abc123"
        assert status["target_version"] == "def456"
        assert status["needs_update"] is True
        assert len(status["pending_migrations"]) == 1
        assert status["is_safe_to_migrate"] is True
        assert status["safety_issues"] == []
        assert status["latest_backup"]["path"] == "/backups/test.db"
        assert status["migration_in_progress"] is False

    @pytest.mark.asyncio
    async def test_start_migration_not_safe(self, database_update_service, mock_repositories):
        """Test starting migration when system is not safe."""
        # Setup mocks
        mock_repositories["safety_validator"].validate_safe_for_migration.return_value = (
            False,
            ["Vehicle is in motion", "Engine is running"],
        )

        # Execute
        result = await database_update_service.start_migration()

        # Assert
        assert result["success"] is False
        assert result["error"] == "System not in safe state for migration"
        assert "Vehicle is in motion" in result["safety_issues"]
        assert "Engine is running" in result["safety_issues"]
        assert result["hint"] == "Use force=True to override (not recommended)"

    @pytest.mark.asyncio
    async def test_start_migration_already_in_progress(
        self, database_update_service, mock_repositories
    ):
        """Test starting migration when one is already in progress."""
        # Setup service state
        database_update_service._migration_in_progress = True
        database_update_service._current_job_id = "existing-job-123"

        # Execute
        result = await database_update_service.start_migration()

        # Assert
        assert result["success"] is False
        assert result["error"] == "Migration already in progress"
        assert result["job_id"] == "existing-job-123"

    @pytest.mark.asyncio
    async def test_start_migration_success(self, database_update_service, mock_repositories):
        """Test successful migration start."""
        # Setup mocks
        mock_repositories["safety_validator"].validate_safe_for_migration.return_value = (
            True,
            [],
        )

        # Execute
        with patch(
            "backend.services.database_update_service.asyncio.create_task"
        ) as mock_create_task:
            result = await database_update_service.start_migration()

        # Assert
        assert result["success"] is True
        assert "job_id" in result
        assert result["message"] == "Migration started"
        assert database_update_service._migration_in_progress is True
        mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_job_status(self, database_update_service):
        """Test getting job status."""
        # Setup job
        job_id = "test-job-123"
        database_update_service._migration_jobs[job_id] = {
            "id": job_id,
            "status": "migrating",
            "progress": 50,
        }

        # Execute
        status = await database_update_service.get_job_status(job_id)

        # Assert
        assert status["id"] == job_id
        assert status["status"] == "migrating"
        assert status["progress"] == 50

    @pytest.mark.asyncio
    async def test_get_job_status_not_found(self, database_update_service):
        """Test getting status for non-existent job."""
        result = await database_update_service.get_job_status("non-existent-job")
        assert result is None


class TestMigrationSafetyValidator:
    """Test suite for MigrationSafetyValidator."""

    @pytest.fixture
    def safety_validator(self):
        """Create MigrationSafetyValidator with mocked dependencies."""
        safety_repo = AsyncMock(spec=SafetyRepository)
        connection_repo = AsyncMock(spec=DatabaseConnectionRepository)

        validator = MigrationSafetyValidator(
            safety_repository=safety_repo,
            connection_repository=connection_repo,
        )
        return validator, safety_repo, connection_repo

    @pytest.mark.asyncio
    async def test_validate_safe_for_migration_all_safe(self, safety_validator):
        """Test validation when all safety checks pass."""
        validator, safety_repo, connection_repo = safety_validator

        # Setup mocks
        safety_repo.get_current_state.return_value = {
            "vehicle_speed": 0,
            "parking_brake": True,
            "engine_running": False,
            "transmission_gear": "PARK",
        }
        safety_repo.get_active_control_count.return_value = 0
        safety_repo.get_interlock_status.return_value = {
            "all_satisfied": True,
            "violations": [],
        }
        connection_repo.check_health.return_value = {"healthy": True}

        # Execute
        is_safe, reasons = await validator.validate_safe_for_migration()

        # Assert
        assert is_safe is True
        assert reasons == []

    @pytest.mark.asyncio
    async def test_validate_safe_for_migration_vehicle_moving(self, safety_validator):
        """Test validation when vehicle is moving."""
        validator, safety_repo, connection_repo = safety_validator

        # Setup mocks
        safety_repo.get_current_state.return_value = {
            "vehicle_speed": 25,  # Vehicle moving
            "parking_brake": False,
            "engine_running": True,
            "transmission_gear": "DRIVE",
        }
        safety_repo.get_active_control_count.return_value = 0
        safety_repo.get_interlock_status.return_value = {
            "all_satisfied": True,
            "violations": [],
        }
        connection_repo.check_health.return_value = {"healthy": True}

        # Execute
        is_safe, reasons = await validator.validate_safe_for_migration()

        # Assert
        assert is_safe is False
        assert "Vehicle is in motion" in reasons
        assert "Parking brake not engaged" in reasons
        assert "Engine is running - shutdown recommended" in reasons
        assert "Transmission not in PARK" in reasons

    @pytest.mark.asyncio
    async def test_get_safety_report(self, safety_validator):
        """Test getting detailed safety report."""
        validator, safety_repo, connection_repo = safety_validator

        # Setup mocks
        safety_state = {
            "vehicle_speed": 0,
            "parking_brake": True,
            "engine_running": False,
            "transmission_gear": "PARK",
        }
        safety_repo.get_current_state.return_value = safety_state
        safety_repo.get_active_control_count.return_value = 0
        interlocks = {"all_satisfied": True, "violations": []}
        safety_repo.get_interlock_status.return_value = interlocks
        connection_repo.check_health.return_value = {"healthy": True}

        # Execute
        report = await validator.get_safety_report()

        # Assert
        assert report["is_safe"] is True
        assert report["blocking_reasons"] == []
        assert report["system_state"] == safety_state
        assert report["interlocks"] == interlocks
        assert report["recommendations"] == []


class TestDatabaseBackupRepository:
    """Test suite for DatabaseBackupRepository."""

    @pytest.fixture
    def backup_repository(self):
        """Create DatabaseBackupRepository with mocked session."""
        session_factory = AsyncMock()
        repo = DatabaseBackupRepository(session_factory)
        return repo, session_factory

    @pytest.mark.asyncio
    async def test_create_backup_record(self, backup_repository):
        """Test creating a backup record."""
        repo, session_factory = backup_repository

        # Setup mock session
        mock_session = AsyncMock()
        session_factory.return_value.__aenter__.return_value = mock_session

        # Execute
        result = await repo.create_backup_record(
            backup_path="/backups/test.db",
            size_bytes=1024000,
            schema_version="abc123",
            backup_type="pre_migration",
        )

        # Assert
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        assert result["path"] == "/backups/test.db"
        assert result["size_bytes"] == 1024000
        assert result["schema_version"] == "abc123"
        assert result["backup_type"] == "pre_migration"
