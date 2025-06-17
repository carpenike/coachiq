"""
Persistence API Router

API endpoints for managing persistent data including configuration,
dashboards, backups, and storage information.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from backend.core.dependencies_v2 import (
    get_config_repository,
    get_dashboard_repository,
    get_persistence_service,
)
from backend.models.persistence import BackupInfo, StorageInfo
from backend.services.persistence_service import PersistenceService
from backend.services.repositories import ConfigRepository, DashboardRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/persistence", tags=["persistence"])


@router.get("/status", summary="Get persistence service status")
async def get_persistence_status(
    persistence_service: Annotated[PersistenceService, Depends(get_persistence_service)],
) -> dict[str, Any]:
    """
    Get the current status of the persistence service.

    Returns information about:
    - Service enabled/disabled status
    - Data directory information
    - Storage statistics
    - Database health check
    """

    try:
        # Get storage information
        storage_info = await persistence_service.get_storage_info()

        # Get database health if manager is available
        db_health = {}
        db_manager = getattr(persistence_service, "_db_manager", None)
        if db_manager:
            db_health = await db_manager.health_check()

        return {
            "enabled": True,
            "status": "healthy",
            "data_directory": str(persistence_service.data_dir),
            "storage": storage_info,
            "database": db_health,
        }

    except Exception as e:
        logger.exception("Error getting persistence status: %s", e)
        return {"enabled": True, "status": "unhealthy", "error": str(e)}


@router.get("/storage", response_model=StorageInfo, summary="Get storage information")
async def get_storage_info(
    persistence_service: Annotated[PersistenceService, Depends(get_persistence_service)],
) -> StorageInfo:
    """
    Get detailed information about persistent storage usage.

    Returns:
    - Directory sizes and file counts
    - Available space information
    - Backup statistics
    """
    return await persistence_service.get_storage_info()


@router.get("/backups", response_model=list[BackupInfo], summary="List available backups")
async def list_backups(
    persistence_service: Annotated[PersistenceService, Depends(get_persistence_service)],
) -> list[BackupInfo]:
    """
    List all available database backups.

    Returns a list of backup files with metadata including:
    - File name and path
    - Creation and modification timestamps
    - File size
    - Source database name
    """
    return await persistence_service.list_backups()


@router.post("/backups", response_model=BackupInfo | None, summary="Create database backup")
async def create_backup(
    persistence_service: Annotated[PersistenceService, Depends(get_persistence_service)],
    database_name: str = "coachiq.db",
    backup_name: str | None = None,
) -> BackupInfo | None:
    """
    Create a backup of the specified database.

    Args:
        database_name: Name of the database to backup (default: coachiq.db)
        backup_name: Optional custom backup name (auto-generated if not provided)

    Returns:
        Backup information if successful, None if failed
    """
    database_path = persistence_service._settings.get_database_dir() / database_name

    if not database_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database {database_name} not found",
        )

    backup_path = await persistence_service.backup_database(database_path, backup_name)

    if backup_path:
        # Return backup info
        backups = await persistence_service.list_backups()
        for backup in backups:
            if backup.path == str(backup_path):
                return backup

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to create backup",
    )


@router.delete("/backups/{backup_name}", summary="Delete a backup")
async def delete_backup(
    backup_name: str,
    persistence_service: Annotated[PersistenceService, Depends(get_persistence_service)],
) -> dict[str, str]:
    """
    Delete a specific backup file.

    Args:
        backup_name: Name of the backup file to delete

    Returns:
        Success message
    """
    success = await persistence_service.delete_backup(backup_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup {backup_name} not found",
        )

    return {"message": f"Backup {backup_name} deleted successfully"}


# Configuration endpoints
@router.get("/config/{namespace}", summary="Get configuration for namespace")
async def get_config_namespace(
    namespace: str,
    config_repo: Annotated[ConfigRepository, Depends(get_config_repository)],
) -> dict[str, Any]:
    """
    Get all configuration values for a specific namespace.

    Args:
        namespace: Configuration namespace (e.g., 'ui', 'system', 'user')

    Returns:
        Dictionary of configuration key-value pairs
    """
    return await config_repo.get_namespace(namespace)


@router.get("/config/{namespace}/{key}", summary="Get specific configuration value")
async def get_config_value(
    namespace: str,
    key: str,
    config_repo: Annotated[ConfigRepository, Depends(get_config_repository)],
) -> dict[str, Any]:
    """
    Get a specific configuration value.

    Args:
        namespace: Configuration namespace
        key: Configuration key

    Returns:
        Configuration data with metadata
    """
    config = await config_repo.get_by_id((namespace, key))

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration {namespace}.{key} not found",
        )

    return config


@router.put("/config/{namespace}/{key}", summary="Set configuration value")
async def set_config_value(
    namespace: str,
    key: str,
    value: Any,
    config_repo: Annotated[ConfigRepository, Depends(get_config_repository)],
) -> dict[str, Any]:
    """
    Set a configuration value.

    Args:
        namespace: Configuration namespace
        key: Configuration key
        value: Configuration value (will be converted to string)

    Returns:
        Updated configuration data
    """
    config_data = {"namespace": namespace, "key": key, "value": value}

    return await config_repo.create(config_data)


@router.delete("/config/{namespace}/{key}", summary="Delete configuration value")
async def delete_config_value(
    namespace: str,
    key: str,
    config_repo: Annotated[ConfigRepository, Depends(get_config_repository)],
) -> dict[str, str]:
    """
    Delete a specific configuration value.

    Args:
        namespace: Configuration namespace
        key: Configuration key

    Returns:
        Success message
    """
    success = await config_repo.delete((namespace, key))

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration {namespace}.{key} not found",
        )

    return {"message": f"Configuration {namespace}.{key} deleted successfully"}


@router.delete("/config/{namespace}", summary="Delete all configuration for namespace")
async def delete_config_namespace(
    namespace: str,
    config_repo: Annotated[ConfigRepository, Depends(get_config_repository)],
) -> dict[str, str]:
    """
    Delete all configuration values for a namespace.

    Args:
        namespace: Configuration namespace

    Returns:
        Success message with count of deleted entries
    """
    deleted_count = await config_repo.delete_namespace(namespace)

    return {"message": f"Deleted {deleted_count} configuration entries from namespace {namespace}"}


# Dashboard endpoints
@router.get("/dashboards", summary="List all dashboards")
async def list_dashboards(
    dashboard_repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> list[dict[str, Any]]:
    """
    Get a list of all dashboard configurations.

    Returns:
        List of dashboard configurations with metadata
    """
    return await dashboard_repo.list_all()


@router.get("/dashboards/default", summary="Get default dashboard")
async def get_default_dashboard(
    dashboard_repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> dict[str, Any]:
    """
    Get the default dashboard configuration.

    Returns:
        Default dashboard data
    """
    dashboard = await dashboard_repo.get_default()

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No default dashboard configured",
        )

    return dashboard


@router.get("/dashboards/{dashboard_id}", summary="Get dashboard by ID")
async def get_dashboard(
    dashboard_id: int,
    dashboard_repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> dict[str, Any]:
    """
    Get a specific dashboard by ID.

    Args:
        dashboard_id: Dashboard ID

    Returns:
        Dashboard configuration data
    """
    dashboard = await dashboard_repo.get_by_id(dashboard_id)

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard {dashboard_id} not found",
        )

    return dashboard


@router.post("/dashboards", summary="Create new dashboard")
async def create_dashboard(
    dashboard_data: dict[str, Any],
    dashboard_repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> dict[str, Any]:
    """
    Create a new dashboard configuration.

    Args:
        dashboard_data: Dashboard configuration including name, config, and optional is_default

    Returns:
        Created dashboard data with ID
    """
    if "name" not in dashboard_data or "config" not in dashboard_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dashboard name and config are required",
        )

    # Check if name already exists
    existing = await dashboard_repo.get_by_name(dashboard_data["name"])
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dashboard with name '{dashboard_data['name']}' already exists",
        )

    return await dashboard_repo.create(dashboard_data)


@router.put("/dashboards/{dashboard_id}", summary="Update dashboard")
async def update_dashboard(
    dashboard_id: int,
    dashboard_data: dict[str, Any],
    dashboard_repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> dict[str, Any]:
    """
    Update an existing dashboard configuration.

    Args:
        dashboard_id: Dashboard ID
        dashboard_data: Updated dashboard fields

    Returns:
        Updated dashboard data
    """
    # Verify dashboard exists
    existing = await dashboard_repo.get_by_id(dashboard_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard {dashboard_id} not found",
        )

    # Check for name conflicts if name is being updated
    if "name" in dashboard_data and dashboard_data["name"] != existing["name"]:
        name_conflict = await dashboard_repo.get_by_name(dashboard_data["name"])
        if name_conflict and name_conflict["id"] != dashboard_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Dashboard with name '{dashboard_data['name']}' already exists",
            )

    dashboard_data["id"] = dashboard_id
    return await dashboard_repo.update(dashboard_data)


@router.delete("/dashboards/{dashboard_id}", summary="Delete dashboard")
async def delete_dashboard(
    dashboard_id: int,
    dashboard_repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> dict[str, str]:
    """
    Delete a dashboard configuration.

    Args:
        dashboard_id: Dashboard ID

    Returns:
        Success message
    """
    success = await dashboard_repo.delete(dashboard_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dashboard {dashboard_id} not found",
        )

    return {"message": f"Dashboard {dashboard_id} deleted successfully"}
