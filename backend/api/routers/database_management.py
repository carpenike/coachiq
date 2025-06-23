"""Database management API endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.core.dependencies import create_service_dependency

# Create service dependencies
get_database_update_service = create_service_dependency("database_update_service")
get_migration_safety_validator = create_service_dependency("migration_safety_validator")

# Import auth dependency
from backend.core.dependencies import get_authenticated_admin
from backend.services.database_update_service import DatabaseUpdateService
from backend.services.migration_safety_validator import MigrationSafetyValidator

router = APIRouter(prefix="/api/database", tags=["database", "admin"])


class DatabaseStatusResponse(BaseModel):
    """Database schema status."""

    current_version: str
    target_version: str
    needs_update: bool
    pending_migrations: list[dict]
    is_safe_to_migrate: bool
    safety_issues: list[str]
    latest_backup: dict | None
    migration_in_progress: bool
    current_job_id: str | None


class MigrationRequest(BaseModel):
    """Request to start migration."""

    target_version: str | None = Field(None, description="Target version")
    skip_backup: bool = Field(False, description="Skip backup creation")
    force: bool = Field(False, description="Force migration despite warnings")
    confirm: bool = Field(..., description="Explicit confirmation required")


class MigrationJobResponse(BaseModel):
    """Response for migration job status."""

    success: bool
    job_id: str | None = None
    message: str | None = None
    error: str | None = None
    safety_issues: list[str] | None = None
    hint: str | None = None


class SafetyReportResponse(BaseModel):
    """Safety validation report."""

    is_safe: bool
    blocking_reasons: list[str]
    system_state: dict[str, Any]
    interlocks: dict[str, Any]
    recommendations: list[str]


@router.get("/status", response_model=DatabaseStatusResponse)
async def get_database_status(
    update_service: Annotated[
        DatabaseUpdateService,
        Depends(get_database_update_service),
    ],
    _admin: Annotated[dict, Depends(get_authenticated_admin)],
) -> DatabaseStatusResponse:
    """Get current database schema status."""
    status = await update_service.get_migration_status()
    return DatabaseStatusResponse(**status)


@router.post("/migrate", response_model=MigrationJobResponse)
async def start_migration(
    request: MigrationRequest,
    update_service: Annotated[
        DatabaseUpdateService,
        Depends(get_database_update_service),
    ],
    _admin: Annotated[dict, Depends(get_authenticated_admin)],
) -> MigrationJobResponse:
    """Start database migration process."""
    if not request.confirm:
        raise HTTPException(400, "Explicit confirmation required")

    result = await update_service.start_migration(
        target_version=request.target_version,
        skip_backup=request.skip_backup,
        force=request.force,
    )

    return MigrationJobResponse(**result)


@router.get("/migrate/{job_id}/status")
async def get_migration_progress(
    job_id: str,
    update_service: Annotated[
        DatabaseUpdateService,
        Depends(get_database_update_service),
    ],
    _admin: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict:
    """Get migration job progress."""
    job_status = await update_service.get_job_status(job_id)
    if not job_status:
        raise HTTPException(404, f"Job {job_id} not found")
    return job_status


@router.get("/history")
async def get_migration_history(
    update_service: Annotated[
        DatabaseUpdateService,
        Depends(get_database_update_service),
    ],
    _admin: Annotated[dict, Depends(get_authenticated_admin)],
    limit: int = 10,
) -> list[dict]:
    """Get migration history."""
    return await update_service.get_migration_history(limit=limit)


@router.get("/safety-check", response_model=SafetyReportResponse)
async def check_migration_safety(
    validator: Annotated[
        MigrationSafetyValidator,
        Depends(get_migration_safety_validator),
    ],
    _admin: Annotated[dict, Depends(get_authenticated_admin)],
) -> SafetyReportResponse:
    """Get detailed safety check for migration."""
    report = await validator.get_safety_report()
    return SafetyReportResponse(**report)
