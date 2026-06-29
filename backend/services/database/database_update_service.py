"""Database update service for safe schema migrations."""

import asyncio
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)


class DatabaseUpdateService:
    """
    Orchestrates database schema updates with safety guarantees.

    Target architecture: Clean service with repository injection only.
    NO app_state, NO adapters, NO backward compatibility.
    """

    def __init__(
        self,
        connection_repository,
        migration_repository,
        safety_validator,
        backup_repository,
        history_repository,
        websocket_repository=None,
        performance_monitor=None,
        backup_dir=None,
    ):
        """
        Initialize with repositories only.

        ALL dependencies via repository injection.
        NO app_state parameter!
        """
        # Required repositories
        self._connection_repo = connection_repository
        self._migration_repo = migration_repository
        self._safety_validator = safety_validator
        self._backup_repo = backup_repository
        self._history_repo = history_repository

        # Optional repositories
        self._websocket_repo = websocket_repository
        self._performance_monitor = performance_monitor

        # Internal state
        self._migration_in_progress = False
        self._current_job_id: str | None = None
        self._migration_jobs: dict[str, dict[str, Any]] = {}

        # Configuration (from settings)
        self._backup_dir = backup_dir or Path("/var/lib/coachiq/backups")
        self._require_explicit_consent = True
        self._backup_before_migrate = True
        self._migration_timeout_seconds = 300

        logger.info("DatabaseUpdateService initialized with repository injection")

    async def initialize(self) -> None:
        """Initialize the service."""
        # Ensure backup directory exists
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        # Check for incomplete migrations (only if table exists)
        try:
            recent_history = await self._history_repo.get_migration_history(limit=1)
            if recent_history and recent_history[0]["status"] == "in_progress":
                logger.warning("Found incomplete migration: %s", recent_history[0]["to_version"])
        except Exception as e:
            # Table might not exist yet during initial setup
            logger.debug("Could not check migration history during initialization: %s", e)

    async def get_migration_status(self) -> dict[str, Any]:
        """Get current database schema status."""
        current_version = await self._migration_repo.get_current_version()
        target_version = await self._migration_repo.get_target_version()
        pending_migrations = await self._migration_repo.get_pending_migrations()

        # Get safety status
        is_safe, safety_reasons = await self._safety_validator.validate_safe_for_migration()

        # Get backup info
        latest_backup = await self._backup_repo.get_latest_backup()

        return {
            "current_version": current_version,
            "target_version": target_version,
            "needs_update": current_version != target_version,
            "pending_migrations": pending_migrations,
            "is_safe_to_migrate": is_safe,
            "safety_issues": safety_reasons,
            "latest_backup": latest_backup,
            "migration_in_progress": self._migration_in_progress,
            "current_job_id": self._current_job_id,
        }

    async def start_migration(
        self,
        target_version: str | None = None,
        skip_backup: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Start database migration process.

        Args:
            target_version: Specific version to migrate to (default: latest)
            skip_backup: Skip backup creation (not recommended)
            force: Force migration even with safety warnings

        Returns:
            Dict with job_id and initial status
        """
        if self._migration_in_progress:
            return {
                "success": False,
                "error": "Migration already in progress",
                "job_id": self._current_job_id,
            }

        # Validate safety unless forced
        if not force:
            is_safe, reasons = await self._safety_validator.validate_safe_for_migration()
            if not is_safe:
                return {
                    "success": False,
                    "error": "System not in safe state for migration",
                    "safety_issues": reasons,
                    "hint": "Use force=True to override (not recommended)",
                }

        # Create job
        job_id = str(uuid.uuid4())
        self._current_job_id = job_id
        self._migration_in_progress = True

        # Initialize job tracking
        self._migration_jobs[job_id] = {
            "id": job_id,
            "status": "initializing",
            "started_at": datetime.now(UTC),
            "target_version": target_version,
            "progress": 0,
            "steps": [],
        }

        # Start migration in background
        task = asyncio.create_task(self._execute_migration(job_id, target_version, skip_backup))
        # Store reference to prevent garbage collection
        self._migration_jobs[job_id]["task"] = task

        return {"success": True, "job_id": job_id, "message": "Migration started"}

    async def _execute_migration(
        self, job_id: str, target_version: str | None, skip_backup: bool
    ) -> None:
        """Execute migration with all safety checks."""
        job = self._migration_jobs[job_id]
        start_time = datetime.now(UTC)
        current_version = None

        try:
            # Step 1: Create backup
            if not skip_backup and self._backup_before_migrate:
                await self._update_job_progress(job_id, "backing_up", 10)
                backup_path = await self._create_backup()
                job["backup_path"] = backup_path
                await self._update_job_progress(job_id, "backup_complete", 20)

            # Step 2: Get migration plan
            await self._update_job_progress(job_id, "planning", 30)
            current_version = await self._migration_repo.get_current_version()

            # Step 3: Execute migrations using Alembic
            await self._update_job_progress(job_id, "migrating", 40)

            # Get database URL from connection repository
            db_url = await self._connection_repo.get_database_url()

            # Run Alembic migration
            alembic_cfg = Config("backend/alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", db_url)

            # Create engine for migration
            engine = create_engine(db_url)

            # Execute migration
            with engine.connect() as connection:
                context = MigrationContext.configure(connection)
                script = ScriptDirectory.from_config(alembic_cfg)

                # Get target revision
                target_rev = target_version if target_version else script.get_current_head()

                # Run migration
                context.run_migrations(target_revision=target_rev)

            # Step 4: Verify
            await self._update_job_progress(job_id, "verifying", 85)
            new_version = await self._migration_repo.get_current_version()

            if new_version == current_version:
                msg = "Migration did not change schema version"
                raise Exception(msg)

            # Step 5: Complete
            await self._update_job_progress(job_id, "completed", 100)

            # Record success
            duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

            await self._history_repo.record_migration_attempt(
                from_version=current_version,
                to_version=new_version,
                status="success",
                duration_ms=duration_ms,
                details={"job_id": job_id, "backup_path": job.get("backup_path")},
            )

            job["status"] = "completed"
            job["completed_at"] = datetime.now(UTC)

        except Exception as e:
            logger.error("Migration failed: %s", e)

            # Record failure
            await self._history_repo.record_migration_attempt(
                from_version=current_version or "unknown",
                to_version=target_version or "latest",
                status="failed",
                duration_ms=int((datetime.now(UTC) - start_time).total_seconds() * 1000),
                details={
                    "job_id": job_id,
                    "error": str(e),
                    "backup_path": job.get("backup_path"),
                },
            )

            job["status"] = "failed"
            job["error"] = str(e)
            job["completed_at"] = datetime.now(UTC)

            # Attempt rollback if backup exists
            if job.get("backup_path"):
                await self._update_job_progress(job_id, "rolling_back", 90)
                try:
                    await self._restore_backup(job["backup_path"])
                    job["rollback_status"] = "success"
                except Exception as rollback_error:
                    logger.error("Rollback failed: %s", rollback_error)
                    job["rollback_status"] = "failed"
                    job["rollback_error"] = str(rollback_error)

        finally:
            self._migration_in_progress = False
            self._current_job_id = None

    async def _create_backup(self) -> str:
        """Create database backup."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_filename = f"coachiq_backup_{timestamp}.db"
        backup_path = self._backup_dir / backup_filename

        # Get database path from connection repository
        db_path = await self._connection_repo.get_database_path()

        # Copy database file
        shutil.copy2(db_path, backup_path)

        # Get file size
        size_bytes = backup_path.stat().st_size

        # Record in repository
        current_version = await self._migration_repo.get_current_version()
        await self._backup_repo.create_backup_record(
            backup_path=str(backup_path),
            size_bytes=size_bytes,
            schema_version=current_version,
            backup_type="pre_migration",
        )

        return str(backup_path)

    async def _restore_backup(self, backup_path: str) -> None:
        """Restore database from backup."""
        db_path = await self._connection_repo.get_database_path()

        # Close all connections
        await self._connection_repo.close_all_connections()

        # Restore backup
        shutil.copy2(backup_path, db_path)

        # Reinitialize connections
        await self._connection_repo.initialize()

    async def _update_job_progress(self, job_id: str, status: str, progress: int) -> None:
        """Update job progress and notify via WebSocket."""
        if job_id not in self._migration_jobs:
            return

        job = self._migration_jobs[job_id]
        job["status"] = status
        job["progress"] = progress
        job["steps"].append(
            {"status": status, "timestamp": datetime.now(UTC), "progress": progress}
        )

        # Send WebSocket notification if available
        if self._websocket_repo:
            await self._websocket_repo.broadcast_message(
                {
                    "type": "database_update_progress",
                    "job_id": job_id,
                    "status": status,
                    "progress": progress,
                }
            )

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Get status of a specific migration job."""
        return self._migration_jobs.get(job_id)

    async def get_migration_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent migration history."""
        return await self._history_repo.get_migration_history(limit)

    def get_health(self) -> dict[str, Any]:
        """Health check for the service."""
        return {
            "healthy": not self._migration_in_progress,
            "migration_in_progress": self._migration_in_progress,
            "current_job_id": self._current_job_id,
        }
