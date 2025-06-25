"""
Config and Status API Router

FastAPI router for configuration and status monitoring.
This router delegates business logic to appropriate services.

Routes:
- GET /config/device_mapping: Get device mapping configuration
- GET /config/spec: Get RV-C specification configuration
- GET /status/server: Get server status information
- GET /status/application: Get application status information
- GET /status/latest_release: Get latest GitHub release information
- POST /status/force_update_check: Force GitHub update check

Note: Health endpoints (/healthz, /readyz, /metrics) are at root level in main.py
Note: WebSocket endpoints are handled by backend.websocket.routes
"""

import logging
import os
import time
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from backend.core.config import get_settings
from backend.core.dependencies import (
    create_service_dependency,
    get_config_service,
    get_entity_state_repository,
)
from backend.models.github_update import GitHubUpdateStatus
from backend.repositories.can_tracking_repository import CANTrackingRepository
from backend.repositories.entity_state_repository import EntityStateRepository
from backend.services.config_service import ConfigService
from backend.services.github_update_checker import GitHubUpdateChecker

# Create missing dependencies
get_can_interface_service = create_service_dependency("can_interface_service")
get_github_update_checker = create_service_dependency("github_update_checker")
get_can_tracking_repository = create_service_dependency("can_tracking_repository")

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter(prefix="/api", tags=["config", "status"])

# Store startup time for status endpoints
SERVER_START_TIME = time.time()


@router.get(
    "/config/device_mapping",
    response_class=PlainTextResponse,
    summary="Get device mapping configuration",
    description="Returns the current device mapping configuration file content.",
)
async def get_device_mapping_config(
    config_service: Annotated[ConfigService, Depends(get_config_service)],
) -> PlainTextResponse:
    """Get device mapping configuration content."""
    logger.info("GET /config/device_mapping - Retrieving device mapping configuration")
    try:
        content = await config_service.get_device_mapping_content()
        logger.info(
            f"Device mapping configuration retrieved successfully - {len(content)} characters"
        )
        return PlainTextResponse(content)
    except FileNotFoundError as e:
        logger.error(f"Device mapping file not found: {e}")
        raise HTTPException(status_code=404, detail="Device mapping file not found") from e
    except Exception as e:
        logger.error(f"Error reading device mapping file: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error reading device mapping file: {e}"
        ) from e


@router.get(
    "/config/spec",
    response_class=PlainTextResponse,
    summary="Get RV-C specification configuration",
    description="Returns the current RV-C specification file content.",
)
async def get_spec_config(
    config_service: Annotated[ConfigService, Depends(get_config_service)],
) -> PlainTextResponse:
    """Get RV-C specification configuration content."""
    logger.info("GET /config/spec - Retrieving RV-C specification configuration")
    try:
        content = await config_service.get_spec_content()
        logger.info(
            f"RV-C specification configuration retrieved successfully - {len(content)} characters"
        )
        return PlainTextResponse(content)
    except FileNotFoundError as e:
        logger.error(f"Spec file not found: {e}")
        raise HTTPException(status_code=404, detail="RV-C specification file not found") from e
    except Exception as e:
        logger.error(f"Error reading spec file: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading spec file: {e}") from e


@router.get(
    "/status/server",
    response_model=dict[str, Any],
    summary="Get server status",
    description="Returns basic server status information including uptime and version.",
)
async def get_server_status() -> dict[str, Any]:
    """Returns basic server status information."""
    logger.debug("GET /status/server - Server status requested")
    uptime_seconds = time.time() - SERVER_START_TIME

    # Import VERSION here to avoid circular imports
    try:
        from backend.core.version import VERSION

        version = VERSION
    except ImportError:
        version = "unknown"

    status_data = {
        "status": "ok",
        "version": version,
        "server_start_time_unix": SERVER_START_TIME,
        "uptime_seconds": uptime_seconds,
        "message": "coachiq server is running.",
    }

    logger.info(f"Server status retrieved - uptime: {uptime_seconds:.1f}s, version: {version}")
    return status_data


@router.get(
    "/status/application",
    response_model=dict[str, Any],
    summary="Get application status",
    description="Returns application-specific status information including configuration and entity counts.",
)
async def get_application_status(
    config_service: Annotated[ConfigService, Depends(get_config_service)],
    entity_state_repo: Annotated[EntityStateRepository, Depends(get_entity_state_repository)],
    can_tracking_repo: Annotated[CANTrackingRepository, Depends(get_can_tracking_repository)],
) -> dict[str, Any]:
    """Returns application-specific status information."""
    logger.debug("GET /status/application - Application status requested")

    # Get configuration status
    config_status = await config_service.get_config_status()

    # Basic check for CAN listeners (simple proxy: if entities exist, listeners likely ran)
    entity_count = 0
    if entity_state_repo:
        entity_count = len(entity_state_repo.get_all_entity_ids())
    else:
        # If repository not available, default to 0
        entity_count = 0
    can_listeners_active = entity_count > 0

    status_data = {
        "status": "ok",
        "rvc_spec_file_loaded": config_status["spec_loaded"],
        "rvc_spec_file_path": config_status.get("spec_path"),
        "device_mapping_file_loaded": config_status["mapping_loaded"],
        "device_mapping_file_path": config_status.get("mapping_path"),
        "known_entity_count": entity_count,
        "active_entity_state_count": entity_count,
        "unmapped_entry_count": 0,  # Deprecated - tracking moved to service layer
        "unknown_pgn_count": 0,  # Deprecated - tracking moved to service layer
        "can_listeners_status": (
            "likely_active" if can_listeners_active else "unknown_or_inactive"
        ),
        "websocket_clients": {
            "data_clients": 0,  # Will be updated once WebSocket manager is properly integrated
            "log_clients": 0,
            "status_clients": 0,
            "features_clients": 0,
            "can_sniffer_clients": 0,
        },
    }

    logger.info(
        f"Application status retrieved - entities: {entity_count}, "
        f"unmapped: 0, "  # Deprecated
        f"unknown_pgns: 0, "  # Deprecated
        f"spec_loaded: {config_status['spec_loaded']}, "
        f"mapping_loaded: {config_status['mapping_loaded']}"
    )

    return status_data


@router.get(
    "/status/latest_release",
    response_model=GitHubUpdateStatus,
    summary="Get latest GitHub release",
    description="Returns the latest GitHub release version and metadata.",
)
async def get_latest_github_release(
    update_checker: Annotated[GitHubUpdateChecker | None, Depends(get_github_update_checker)],
) -> GitHubUpdateStatus:
    """Returns the latest GitHub release version and metadata."""
    logger.debug("GET /status/latest_release - GitHub release status requested")
    if not update_checker:
        raise HTTPException(status_code=503, detail="GitHub update checker not available")
    status_data = update_checker.get_status()

    logger.info(
        f"GitHub release status retrieved - current: {status_data.get('current_version')}, "
        f"latest: {status_data.get('latest_version')}, "
        f"update_available: {status_data.get('update_available')}"
    )

    return GitHubUpdateStatus.parse_obj(status_data)


@router.post(
    "/status/force_update_check",
    response_model=GitHubUpdateStatus,
    summary="Force GitHub update check",
    description="Forces an immediate GitHub update check and returns the new status.",
)
async def force_github_update_check(
    background_tasks: BackgroundTasks,
    update_checker: Annotated[GitHubUpdateChecker | None, Depends(get_github_update_checker)],
) -> GitHubUpdateStatus:
    """Forces an immediate GitHub update check and returns the new status."""
    logger.info("POST /status/force_update_check - Forcing GitHub update check")
    if not update_checker:
        raise HTTPException(status_code=503, detail="GitHub update checker not available")

    try:
        await update_checker.force_check()
        status_data = update_checker.get_status()

        logger.info(
            f"GitHub update check completed - current: {status_data.get('current_version')}, "
            f"latest: {status_data.get('latest_version')}, "
            f"update_available: {status_data.get('update_available')}"
        )

        return GitHubUpdateStatus.parse_obj(status_data)
    except Exception as e:
        logger.error(f"Failed to force GitHub update check: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check for updates: {e}") from e


@router.get(
    "/status/features",
    response_model=dict[str, Any],
    summary="Get feature status",
    description="Returns the current status of all services in the system.",
    response_description="Dictionary containing service states and metadata",
)
async def get_feature_status() -> dict[str, Any]:
    """
    Returns the current status of all services in the system.

    This endpoint provides information about available services
    and their health status.
    """
    logger.debug("GET /status/features - Service status requested")

    # In v2, all services are always enabled
    # This endpoint is kept for backward compatibility
    feature_status = {
        "total_features": 0,
        "enabled_count": 0,
        "core_count": 0,
        "optional_count": 0,
        "features": {},
        "message": "Feature flags have been removed. All services are available through ServiceRegistry.",
    }

    logger.info("Feature status endpoint called - returning deprecation notice")

    return feature_status


# Note: WebSocket endpoints have been moved to backend.websocket.routes
# The endpoints /ws, /ws/logs, /ws/can-sniffer, /ws/features, and /ws/status
# are now handled by the proper WebSocket manager with feature integration


# Enhanced Configuration Management Endpoints


@router.get("/config/settings")
async def get_settings_overview():
    """
    Get current application settings with source information.

    Returns configuration values showing which come from environment
    variables vs defaults, without exposing sensitive information.
    """
    settings = get_settings()

    # Get all settings sections
    response = {
        "sections": {
            "server": {
                "host": settings.server.host,
                "port": settings.server.port,
                "workers": settings.server.workers,
                "reload": settings.server.reload,
                "debug": settings.server.debug,
                "root_path": settings.server.root_path,
            },
            "security": {
                "allowed_hosts": settings.security.allowed_hosts,
                "enable_csrf": settings.security.enable_csrf,
                "enable_xss_protection": settings.security.enable_xss_protection,
                "enable_content_security_policy": settings.security.enable_content_security_policy,
                "max_upload_size": settings.security.max_upload_size,
                "rate_limit_enabled": settings.security.rate_limit_enabled,
                "rate_limit_requests": settings.security.rate_limit_requests,
                "rate_limit_window": settings.security.rate_limit_window,
            },
            "logging": {
                "level": settings.logging.level,
                "format": settings.logging.format,
                "file_enabled": settings.logging.file_enabled,
                "file_path": str(settings.logging.file_path)
                if settings.logging.file_path
                else None,
                "max_file_size": settings.logging.max_file_size,
                "backup_count": settings.logging.backup_count,
                "console_enabled": settings.logging.console_enabled,
            },
            "can": {
                "interfaces": settings.can.interfaces,
                "bitrate": settings.can.bitrate,
                "timeout": settings.can.timeout,
                "buffer_size": settings.can.buffer_size,
                "enable_statistics": settings.can.enable_statistics,
                "enable_error_frames": settings.can.enable_error_frames,
                "enable_fd": settings.can.enable_fd,
                "fd_bitrate": settings.can.fd_bitrate,
            },
            "rvc": {
                "enable_encoder": settings.rvc.enable_encoder,
                "enable_decoder": settings.rvc.enable_decoder,
                "spec_file": settings.rvc.spec_file,
                "message_timeout": settings.rvc.message_timeout,
                "enable_caching": settings.rvc.enable_caching,
                "cache_ttl": settings.rvc.cache_ttl,
                "enable_validation": settings.rvc.enable_validation,
                "strict_validation": settings.rvc.strict_validation,
            },
            "persistence": {
                "enabled": settings.persistence.enabled,
                "backend_type": settings.persistence.backend_type.value,
                "data_dir": str(settings.persistence.data_dir),
                "persistent_data_dir": str(settings.persistence.persistent_data_dir),
                "enable_compression": settings.persistence.enable_compression,
                "sync_interval": settings.persistence.sync_interval,
                "max_file_size": settings.persistence.max_file_size,
                "retention_days": settings.persistence.retention_days,
            },
            "notifications": {
                "enabled": settings.notifications.enabled,
                "max_history": settings.notifications.max_history,
                "default_severity": settings.notifications.default_severity,
                "batch_interval": settings.notifications.batch_interval,
                "rate_limit_per_minute": settings.notifications.rate_limit_per_minute,
            },
            "auth": {
                "enabled": settings.auth.enabled,
                "provider": settings.auth.provider,
                "session_timeout": settings.auth.session_timeout,
                "refresh_enabled": settings.auth.refresh_enabled,
                "refresh_timeout": settings.auth.refresh_timeout,
                "max_sessions": settings.auth.max_sessions,
                "require_email_verification": settings.auth.require_email_verification,
            },
        },
        "metadata": {
            "environment": settings.environment,
            "debug": settings.debug,
            "version": getattr(settings, "version", "unknown"),
            "app_name": settings.app_name,
            "source_priority": ["environment", "default"],
        },
        "environment_variables": {
            k: v
            for k, v in os.environ.items()
            if k.startswith("COACHIQ_")
            and not any(secret in k.lower() for secret in ["password", "secret", "key", "token"])
        },
        "config_sources": {
            "env_file": ".env" if os.path.exists(".env") else None,
            "system_env": True,
            "defaults": True,
        },
    }

    return response


@router.get("/config/features")
async def get_enhanced_feature_status():
    """Get current service status and availability."""
    # In v2, feature flags are removed
    # This endpoint is kept for backward compatibility
    return {
        "features": {},
        "dependency_graph": {},
        "conflict_resolution": {},
        "validation_errors": [],
        "message": "Feature flags have been removed. All services are available through ServiceRegistry.",
    }


@router.get("/config/can/interfaces")
async def get_can_interface_mappings(
    can_service: Annotated[Any, Depends(get_can_interface_service)],
):
    """Get current CAN interface mappings."""
    return {
        "mappings": can_service.get_all_mappings(),
        "validation": can_service.validate_mapping(can_service.get_all_mappings()),
    }


@router.put("/config/can/interfaces/{logical_name}")
async def update_can_interface_mapping(
    logical_name: str,
    request: dict[str, str],  # {"physical_interface": "can1"}
    can_service: Annotated[Any, Depends(get_can_interface_service)],
):
    """Update a CAN interface mapping (runtime only)."""
    if "physical_interface" not in request:
        raise HTTPException(400, "Request must contain 'physical_interface' field")

    physical_interface = request["physical_interface"]

    # Validate the mapping
    test_mappings = can_service.get_all_mappings()
    test_mappings[logical_name] = physical_interface
    validation = can_service.validate_mapping(test_mappings)

    if not validation["valid"]:
        raise HTTPException(400, f"Invalid mapping: {', '.join(validation['issues'])}")

    can_service.update_mapping(logical_name, physical_interface)

    return {
        "logical_name": logical_name,
        "physical_interface": physical_interface,
        "message": "Interface mapping updated (runtime only)",
    }


@router.post("/config/can/interfaces/validate")
async def validate_interface_mappings(
    mappings: dict[str, str],
    can_service: Annotated[Any, Depends(get_can_interface_service)],
):
    """Validate a set of interface mappings."""
    return can_service.validate_mapping(mappings)


@router.get("/config/database")
async def get_database_configuration():
    """
    Get current database configuration.

    Returns database settings with sensitive information redacted.
    """
    settings = get_settings()

    # Check if database settings exist
    if not hasattr(settings, "database") or settings.database is None:
        # Return default SQLite configuration
        return {
            "backend": "sqlite",
            "sqlite": {
                "path": "backend/data/coachiq.db",
                "timeout": 30,
                "optimizations_enabled": True,
                "cache_size": 4000,
                "mmap_size": 134217728,
                "wal_autocheckpoint": 1000,
            },
            "postgresql": {
                "host": "localhost",
                "port": 5432,
                "user": "coachiq",
                "database": "coachiq",
                "schema": "public",
            },
            "pool": {
                "size": 5,
                "max_overflow": 10,
                "timeout": 30,
                "recycle": 3600,
            },
            "performance": {
                "echo_sql": False,
                "echo_pool": False,
            },
            "health_status": "unknown",
        }

    db_settings = settings.database

    # Handle both full DatabaseSettings and minimal database settings
    if hasattr(db_settings, "backend"):
        backend = (
            db_settings.backend.value
            if hasattr(db_settings.backend, "value")
            else str(db_settings.backend)
        )
    else:
        backend = "sqlite"

    response = {
        "backend": backend,
        "sqlite": {
            "path": getattr(
                db_settings,
                "sqlite_path",
                db_settings.get_database_path()
                if hasattr(db_settings, "get_database_path")
                else "backend/data/coachiq.db",
            ),
            "timeout": getattr(db_settings, "sqlite_timeout", 30),
            "optimizations_enabled": getattr(db_settings, "sqlite_enable_optimizations", True),
            "cache_size": getattr(db_settings, "sqlite_cache_size", 4000),
            "mmap_size": getattr(db_settings, "sqlite_mmap_size", 134217728),
            "wal_autocheckpoint": getattr(db_settings, "sqlite_wal_autocheckpoint", 1000),
        },
        "postgresql": {
            "host": getattr(db_settings, "postgres_host", "localhost"),
            "port": getattr(db_settings, "postgres_port", 5432),
            "user": getattr(db_settings, "postgres_user", "coachiq"),
            "database": getattr(db_settings, "postgres_database", "coachiq"),
            "schema": getattr(db_settings, "postgres_schema", "public"),
            # Password is intentionally omitted for security
        },
        "pool": {
            "size": getattr(db_settings, "pool_size", 5),
            "max_overflow": getattr(db_settings, "max_overflow", 10),
            "timeout": getattr(db_settings, "pool_timeout", 30),
            "recycle": getattr(db_settings, "pool_recycle", 3600),
        },
        "performance": {
            "echo_sql": getattr(db_settings, "echo_sql", False),
            "echo_pool": getattr(db_settings, "echo_pool", False),
        },
        "health_status": "healthy",  # Could be enhanced with actual health check
    }

    return response


@router.get("/config/coach/interface-requirements")
async def get_coach_interface_requirements():
    """Get coach interface requirements and compatibility validation."""
    # This endpoint is deprecated - use repository-based coach mapping service instead
    raise HTTPException(
        status_code=410,
        detail="This endpoint has been deprecated. Use /api/coach-mapping endpoints instead.",
    )


@router.get("/config/coach/metadata")
async def get_coach_mapping_metadata(
    config_service: Annotated[ConfigService, Depends(get_config_service)],
):
    """Get complete coach mapping metadata including interface analysis."""
    # This endpoint provides backwards compatibility
    # Return a default configuration until coach-mapping service is fully implemented

    # Get device mapping info from config service
    try:
        # Check if mapping is loaded
        status = await config_service.get_config_status()

        return {
            "model": "Generic RV",
            "year": 2024,
            "manufacturer": "Unknown",
            "config_file": status.get("mapping_path", "config/coach_mapping.default.yml"),
            "interface_requirements": ["can0"],  # Default single interface
            "device_mappings": {},  # Empty mappings for now
            "validation_status": "valid" if status["mapping_loaded"] else "invalid",
            "last_validated": "2024-01-01T00:00:00Z",
        }
    except Exception as e:
        logger.warning(f"Error getting coach metadata: {e}")
        return {
            "model": "Generic RV",
            "year": 2024,
            "manufacturer": "Unknown",
            "config_file": "config/coach_mapping.default.yml",
            "interface_requirements": ["can0"],
            "device_mappings": {},
            "validation_status": "warning",
            "last_validated": "2024-01-01T00:00:00Z",
        }
