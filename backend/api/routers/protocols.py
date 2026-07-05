"""
Protocol Configuration API

Provides endpoints for managing protocol enablement and configuration.
Allows runtime protocol management without requiring application restarts.
"""

import logging
from typing import Any, ClassVar

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette import status

from backend.core.dependencies import CompositionRoot, ProtocolManager
from backend.middleware.auth import get_admin_user
from backend.models.protocol_config import ProtocolRuntimeStatus
from backend.services.protocols.protocol_manager import ProtocolStatus

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
    config: dict[str, Any] | None = Field(None, description="Protocol-specific configuration")

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


def _protocol_runtime_status(
    protocol_manager: ProtocolManager,
    composition_root: CompositionRoot,
    protocol_name: str,
) -> ProtocolRuntimeStatus:
    """Build API runtime status from the currently wired ProtocolManager."""
    info = protocol_manager.get_protocol_info(protocol_name)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_name}' not found",
        )

    runtime_status = protocol_manager.get_protocol_status(protocol_name, composition_root)
    service_registered = composition_root.has_service(info.service_name)
    service_healthy = runtime_status == ProtocolStatus.ENABLED

    return ProtocolRuntimeStatus(
        protocol_name=protocol_name,
        enabled=info.enabled,
        config_source="settings",
        service_registered=service_registered,
        service_healthy=service_healthy,
        last_error=None
        if runtime_status != ProtocolStatus.DEGRADED
        else f"Service '{info.service_name}' is not healthy or not registered",
    )


@router.get(
    "/",
    response_model=ProtocolListResponse,
    summary="List all protocols",
    description="Get list of all protocols with their runtime status",
)
async def list_protocols(
    protocol_manager: ProtocolManager,
    composition_root: CompositionRoot,
) -> ProtocolListResponse:
    """List all protocols with runtime status."""
    protocols = []

    # Get status for each known protocol
    for protocol_name in ["rvc", "j1939", "firefly", "victron"]:
        protocol_status = _protocol_runtime_status(
            protocol_manager, composition_root, protocol_name
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
    protocol_manager: ProtocolManager,
    composition_root: CompositionRoot,
) -> ProtocolRuntimeStatus:
    """Get detailed status for a specific protocol."""
    if protocol_name not in ["rvc", "j1939", "firefly", "victron"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_name}' not found",
        )

    return _protocol_runtime_status(protocol_manager, composition_root, protocol_name)


@router.put(
    "/{protocol_name}",
    response_model=ProtocolUpdateResponse,
    summary="Update protocol configuration",
    description="Update protocol enablement and configuration (requires admin)",
    dependencies=[Depends(get_admin_user)],
)
async def update_protocol(
    protocol_name: str,
    update: ProtocolUpdateRequest,
    protocol_manager: ProtocolManager,
) -> ProtocolUpdateResponse:
    """Update protocol configuration."""
    if protocol_manager.get_protocol_info(protocol_name) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_name}' not found",
        )

    # Special handling for RVC
    if protocol_name == "rvc" and update.enabled is False:
        return ProtocolUpdateResponse(
            success=False,
            requires_restart=False,
            message="RV-C protocol cannot be disabled",
            protocol=None,
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Runtime protocol configuration updates are not supported by the "
            "currently wired ProtocolManager"
        ),
    )


@router.post(
    "/{protocol_name}/reload",
    response_model=ProtocolUpdateResponse,
    summary="Reload protocol configuration",
    description="Reload protocol configuration from database (requires admin)",
    dependencies=[Depends(get_admin_user)],
)
async def reload_protocol(
    protocol_name: str,
    protocol_manager: ProtocolManager,
) -> ProtocolUpdateResponse:
    """Reload protocol configuration from database."""
    if protocol_manager.get_protocol_info(protocol_name) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_name}' not found",
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Runtime protocol configuration reload is not supported by the "
            "currently wired ProtocolManager"
        ),
    )
