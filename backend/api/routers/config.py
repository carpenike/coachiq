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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from backend.core.config import get_settings
from backend.core.dependencies_v2 import (
    get_app_state,
    get_can_interface_service,
    get_config_service,
    get_feature_manager,
    get_github_update_checker,
)
from backend.models.github_update import GitHubUpdateStatus

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
async def get_device_mapping_config(request: Request) -> PlainTextResponse:
    """Get device mapping configuration content."""
    logger.info("GET /config/device_mapping - Retrieving device mapping configuration")
    config_service = get_config_service(request)
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
async def get_spec_config(request: Request) -> PlainTextResponse:
    """Get RV-C specification configuration content."""
    logger.info("GET /config/spec - Retrieving RV-C specification configuration")
    config_service = get_config_service(request)
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
async def get_application_status(request: Request) -> dict[str, Any]:
    """Returns application-specific status information."""
    logger.debug("GET /status/application - Application status requested")
    config_service = get_config_service(request)
    app_state = get_app_state(request)

    # Get configuration status
    config_status = await config_service.get_config_status()

    # Basic check for CAN listeners (simple proxy: if entities exist, listeners likely ran)
    entity_count = len(app_state.entity_manager.get_entity_ids())
    can_listeners_active = entity_count > 0

    status_data = {
        "status": "ok",
        "rvc_spec_file_loaded": config_status["spec_loaded"],
        "rvc_spec_file_path": config_status.get("spec_path"),
        "device_mapping_file_loaded": config_status["mapping_loaded"],
        "device_mapping_file_path": config_status.get("mapping_path"),
        "known_entity_count": entity_count,
        "active_entity_state_count": entity_count,
        "unmapped_entry_count": len(app_state.unmapped_entries),
        "unknown_pgn_count": len(app_state.unknown_pgns),
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
        f"unmapped: {len(app_state.unmapped_entries)}, "
        f"unknown_pgns: {len(app_state.unknown_pgns)}, "
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
async def get_latest_github_release(request: Request) -> GitHubUpdateStatus:
    """Returns the latest GitHub release version and metadata."""
    logger.debug("GET /status/latest_release - GitHub release status requested")
    update_checker = get_github_update_checker(request)
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
    request: Request, background_tasks: BackgroundTasks
) -> GitHubUpdateStatus:
    """Forces an immediate GitHub update check and returns the new status."""
    logger.info("POST /status/force_update_check - Forcing GitHub update check")
    update_checker = get_github_update_checker(request)

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
    description="Returns the current status of all features in the system.",
    response_description="Dictionary containing feature states and metadata",
)
async def get_feature_status(request: Request) -> dict[str, Any]:
    """
    Returns the current status of all features in the system.

    This endpoint provides information about enabled/disabled features,
    their health status, and configuration details.
    """
    logger.debug("GET /status/features - Feature status requested")
    feature_manager = get_feature_manager(request)

    all_features = feature_manager.get_all_features()
    enabled_features = feature_manager.get_enabled_features()
    core_features = feature_manager.get_core_features()
    optional_features = feature_manager.get_optional_features()

    # Build health report
    health_report = {}
    for name, feature in all_features.items():
        try:
            health_status = getattr(feature, "health", "unknown")
        except AttributeError:
            health_status = "unknown"
        health_report[name] = health_status

    feature_status = {
        "total_features": len(all_features),
        "enabled_count": len(enabled_features),
        "core_count": len(core_features),
        "optional_count": len(optional_features),
        "features": {
            name: {
                "enabled": name in enabled_features,
                "core": name in core_features,
                "health": health_report.get(name, "unknown"),
                "type": type(feature).__name__ if feature else "Unknown",
            }
            for name, feature in all_features.items()
        },
    }

    logger.info(
        f"Feature status retrieved - total: {len(all_features)}, "
        f"enabled: {len(enabled_features)}, "
        f"core: {len(core_features)}, "
        f"optional: {len(optional_features)}"
    )

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

    # Build response with source tracking
    config_dict = settings.get_config_dict(hide_secrets=True)

    # Add source information for each setting
    # Environment variables are marked as immutable
    response = {
        "sections": {},
        "metadata": {
            "environment": settings.environment,
            "debug": settings.debug,
            "source_priority": ["environment", "default"],
        },
    }

    for section_name, section_data in config_dict.items():
        if isinstance(section_data, dict):
            response["sections"][section_name] = {
                "values": section_data,
                "editable": section_name not in ["security", "server"],  # Example logic
                "source": (
                    "environment" if f"COACHIQ_{section_name.upper()}" in os.environ else "default"
                ),
            }

    return response


@router.get("/config/features")
async def get_enhanced_feature_status(
    feature_manager: Annotated[Any, Depends(get_feature_manager)],
):
    """Get current feature status and availability (enhanced version)."""
    all_features = feature_manager.get_all_features()

    # Build dependency graph for dependent_features calculation
    dependency_graph = {}
    for name, feature in all_features.items():
        dependencies = getattr(feature, "dependencies", [])
        for dep in dependencies:
            if dep not in dependency_graph:
                dependency_graph[dep] = []
            dependency_graph[dep].append(name)

    # Extract rich feature data from configuration
    features_data = {}
    for name, feature in all_features.items():
        config = getattr(feature, "config", {})

        # Determine category based on core status and protocol detection
        category = "core" if getattr(feature, "core", False) else "advanced"
        if name in ["rvc", "j1939", "firefly", "spartan_k2", "multi_network_can"]:
            category = "protocol"
        elif name in [
            "log_history",
            "log_streaming",
            "github_update_checker",
            "uptimerobot",
            "pushover",
        ]:
            category = "experimental"

        # Determine stability based on feature maturity
        stability = "stable"
        if name in [
            "firefly",
            "spartan_k2",
            "multi_network_can",
            "advanced_diagnostics",
        ]:
            stability = "beta"
        elif name in ["github_update_checker", "uptimerobot", "pushover"]:
            stability = "alpha"

        features_data[name] = {
            "name": getattr(feature, "friendly_name", name),
            "enabled": getattr(feature, "enabled", False),
            "description": config.get("description", "No description available"),
            "dependencies": getattr(feature, "dependencies", []),
            "dependent_features": dependency_graph.get(name, []),
            "category": category,
            "stability": stability,
            "environment_restrictions": [],  # Could be enhanced later based on config
        }

    return {
        "features": features_data,
        "dependency_graph": {
            name: getattr(feature, "dependencies", []) for name, feature in all_features.items()
        },
        "conflict_resolution": {},  # Placeholder for future conflict detection
        "validation_errors": [],  # Placeholder for validation errors
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


@router.get("/config/coach/interface-requirements")
async def get_coach_interface_requirements(
    can_service: Annotated[Any, Depends(get_can_interface_service)],
):
    """Get coach interface requirements and compatibility validation."""
    from backend.services.coach_mapping_service import CoachMappingService

    coach_service = CoachMappingService(can_service)

    return {
        "interface_requirements": coach_service.get_interface_requirements(),
        "runtime_mappings": coach_service.get_runtime_interface_mappings(),
        "compatibility": coach_service.validate_interface_compatibility(),
    }


@router.get("/config/coach/metadata")
async def get_coach_mapping_metadata(
    can_service: Annotated[Any, Depends(get_can_interface_service)],
):
    """Get complete coach mapping metadata including interface analysis."""
    from backend.services.coach_mapping_service import CoachMappingService

    coach_service = CoachMappingService(can_service)
    return coach_service.get_mapping_metadata()
