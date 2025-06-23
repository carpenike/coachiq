"""
Protocol Configuration API

Provides endpoints for managing protocol enablement and configuration.
Allows runtime protocol management without requiring application restarts.
"""

import logging
from typing import Annotated, ClassVar

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette import status

from backend.core.dependencies import ServiceRegistry, get_service_registry
from backend.middleware.auth import require_admin_role
from backend.models.protocol_config import ProtocolRuntimeStatus

logger = logging.getLogger(__name__)


# API Models
class ProtocolListResponse(BaseModel):
    """Response for protocol list endpoint."""

    protocols: list[ProtocolRuntimeStatus] = Field(
        ..., description="List of protocols with runtime status"
    )
    total: int = Field(..., description="Total number of protocols")
    enabled_count: int = Field(..., description="Number of enabled protocols")


class ProtocolUpdateRequest(BaseModel):
    """Request to update protocol configuration."""

    enabled: bool | None = Field(None, description="Enable/disable protocol")
    config: dict | None = Field(None, description="Protocol-specific configuration")

    class Config:
        json_schema_extra: ClassVar = {
            "example": {
                "enabled": True,
                "config": {"enable_cummins_extensions": True, "baud_rate": 250000},
            }
        }


class ProtocolUpdateResponse(BaseModel):
    """Response for protocol update."""

    success: bool = Field(..., description="Whether update was successful")
    requires_restart: bool = Field(..., description="Whether restart is required")
    message: str = Field(..., description="Status message")
    protocol: ProtocolRuntimeStatus | None = Field(None, description="Updated protocol status")


# Create router
router = APIRouter(
    prefix="/api/protocols",
    tags=["protocols"],
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Admin privileges required"},
    },
)


@router.get(
    "/",
    response_model=ProtocolListResponse,
    summary="List all protocols",
    description="Get list of all protocols with their runtime status",
)
async def list_protocols(
    service_registry: Annotated[ServiceRegistry, Depends(get_service_registry)],
) -> ProtocolListResponse:
    """List all protocols with runtime status."""
    protocols = []

    # Get protocol manager from service registry
    protocol_manager = service_registry.get_service("protocol_manager")
    if not protocol_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Protocol manager service not available",
        )

    # Get status for each known protocol
    for protocol_name in ["rvc", "j1939", "firefly"]:
        protocol_status = await protocol_manager.get_protocol_status(
            protocol_name, service_registry
        )
        protocols.append(protocol_status)

    enabled_count = sum(1 for p in protocols if p.enabled)

    return ProtocolListResponse(
        protocols=protocols,
        total=len(protocols),
        enabled_count=enabled_count,
    )


@router.get(
    "/{protocol_name}",
    response_model=ProtocolRuntimeStatus,
    summary="Get protocol status",
    description="Get detailed status for a specific protocol",
)
async def get_protocol_status(
    protocol_name: str,
    service_registry: Annotated[ServiceRegistry, Depends(get_service_registry)],
) -> ProtocolRuntimeStatus:
    """Get detailed status for a specific protocol."""
    if protocol_name not in ["rvc", "j1939", "firefly"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_name}' not found",
        )

    # Get protocol manager from service registry
    protocol_manager = service_registry.get_service("protocol_manager")
    if not protocol_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Protocol manager service not available",
        )

    return await protocol_manager.get_protocol_status(protocol_name, service_registry)


@router.put(
    "/{protocol_name}",
    response_model=ProtocolUpdateResponse,
    summary="Update protocol configuration",
    description="Update protocol enablement and configuration (requires admin)",
    dependencies=[Depends(require_admin_role)],
)
async def update_protocol(
    protocol_name: str,
    update: ProtocolUpdateRequest,
    request: Request,
    service_registry: Annotated[ServiceRegistry, Depends(get_service_registry)],
) -> ProtocolUpdateResponse:
    """Update protocol configuration."""
    if protocol_name not in ["rvc", "j1939", "firefly"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_name}' not found",
        )

    # Get protocol manager from service registry
    protocol_manager = service_registry.get_service("protocol_manager")
    if not protocol_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Protocol manager service not available",
        )

    # Get user info for audit
    user = getattr(request.state, "user", {})  # type: ignore[attr-defined]
    modified_by = user.get("username", "unknown")

    # Special handling for RVC
    if protocol_name == "rvc" and update.enabled is False:
        return ProtocolUpdateResponse(
            success=False,
            requires_restart=False,
            message="RV-C protocol cannot be disabled",
            protocol=None,
        )

    # Update configuration
    success = await protocol_manager.update_protocol_config(
        protocol=protocol_name,
        enabled=update.enabled,
        config=update.config,
        modified_by=modified_by,
    )

    if not success:
        return ProtocolUpdateResponse(
            success=False,
            requires_restart=False,
            message="Failed to update protocol configuration",
            protocol=None,
        )

    # Get updated status
    updated_status = await protocol_manager.get_protocol_status(protocol_name, service_registry)

    # Check if restart required
    requires_restart = protocol_manager.requires_restart(protocol_name)

    message = f"Protocol {protocol_name} configuration updated"
    if requires_restart:
        message += " - restart required for changes to take effect"

    logger.info(
        "Protocol %s updated by %s: enabled=%s, restart_required=%s",
        protocol_name,
        modified_by,
        update.enabled,
        requires_restart,
    )

    return ProtocolUpdateResponse(
        success=True,
        requires_restart=requires_restart,
        message=message,
        protocol=updated_status,
    )


@router.post(
    "/{protocol_name}/reload",
    response_model=ProtocolUpdateResponse,
    summary="Reload protocol configuration",
    description="Reload protocol configuration from database (requires admin)",
    dependencies=[Depends(require_admin_role)],
)
async def reload_protocol(
    protocol_name: str,
    service_registry: Annotated[ServiceRegistry, Depends(get_service_registry)],
) -> ProtocolUpdateResponse:
    """Reload protocol configuration from database."""
    if protocol_name not in ["rvc", "j1939", "firefly"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_name}' not found",
        )

    # Get protocol manager from service registry
    protocol_manager = service_registry.get_service("protocol_manager")
    if not protocol_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Protocol manager service not available",
        )

    try:
        # Force reload from database
        await protocol_manager._load_configuration()  # noqa: SLF001

        # Get updated status
        updated_status = await protocol_manager.get_protocol_status(protocol_name, service_registry)

        return ProtocolUpdateResponse(
            success=True,
            requires_restart=False,
            message=f"Protocol {protocol_name} configuration reloaded",
            protocol=updated_status,
        )

    except Exception as e:
        logger.error("Failed to reload protocol configuration: %s", e)
        return ProtocolUpdateResponse(
            success=False,
            requires_restart=False,
            message=f"Failed to reload configuration: {e}",
            protocol=None,
        )
