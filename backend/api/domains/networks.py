"""
Networks Domain API Router (v2)

Provides domain-specific network monitoring endpoints:
- CAN bus health and statistics
- Network interface monitoring
- Protocol-specific metrics
- Connection diagnostics

This router integrates with existing network services.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.domains import register_domain_router
from backend.api.routers.can import verify_can_interface_enabled
from backend.core.dependencies import VerifiedCANFacade

logger = logging.getLogger(__name__)


# Domain-specific schemas for v2 API
class NetworkStatus(BaseModel):
    """Configured logical-to-physical network interface mapping."""

    logical_name: str = Field(..., description="Logical interface name")
    physical_interface: str = Field(..., description="Configured physical interface name")


class NetworkSummary(BaseModel):
    """Truthful network summary from currently available CAN facade data."""

    total_interfaces: int = Field(..., description="Total configured logical interfaces")
    interfaces: list[NetworkStatus] = Field(..., description="Configured interface mappings")
    can_service_health: dict[str, Any] = Field(
        ..., description="Service-level CAN health reported by CANFacade"
    )
    queue_status: dict[str, Any] = Field(
        ..., description="Facade-reported CAN queue status, not real TX queue telemetry"
    )
    timestamp: str = Field(..., description="Summary timestamp in ISO 8601 format")


def _utc_timestamp() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


def _network_statuses(interface_mappings: dict[str, str]) -> list[NetworkStatus]:
    """Build response models from configured interface mappings."""
    return [
        NetworkStatus(logical_name=logical_name, physical_interface=physical_interface)
        for logical_name, physical_interface in sorted(interface_mappings.items())
    ]


def create_networks_router() -> APIRouter:
    """Create the networks domain router with all endpoints"""
    router = APIRouter(tags=["networks-v2"])

    @router.get("/health")
    async def health_check() -> dict[str, Any]:
        """Health check endpoint for networks domain API"""

        return {
            "status": "healthy",
            "domain": "networks",
            "version": "v2",
            "features": {
                "can_monitoring": True,
                "multi_protocol": True,
                "real_time_stats": True,
            },
            "timestamp": _utc_timestamp(),
        }

    @router.get("/schemas")
    async def get_schemas() -> dict[str, Any]:
        """Export schemas for networks domain"""

        return {
            "message": "Networks domain schemas available",
            "available_endpoints": ["/health", "/schemas", "/status", "/interfaces", "/statistics"],
        }

    @router.get(
        "/status",
        response_model=NetworkSummary,
        summary="Get network status",
        description=(
            "Return configured CAN interface mappings, service-level CAN health, and "
            "facade-reported queue status without fabricated per-interface telemetry."
        ),
        response_description="Truthful network summary from currently available CAN facade data",
    )
    async def get_network_status(
        can_facade: VerifiedCANFacade,
        _: Annotated[None, Depends(verify_can_interface_enabled)],
    ) -> NetworkSummary:
        """Get truthful network status from currently implemented CAN facade sources."""

        try:
            interface_mappings = await can_facade.get_interface_mappings()
            interfaces = _network_statuses(interface_mappings)

            return NetworkSummary(
                total_interfaces=len(interfaces),
                interfaces=interfaces,
                can_service_health=await can_facade.get_interface_status(),
                queue_status=await can_facade.get_queue_status(),
                timestamp=_utc_timestamp(),
            )

        except Exception as e:
            logger.error("Error getting network status: %s", e)
            raise HTTPException(
                status_code=500, detail=f"Failed to get network status: {e!s}"
            ) from e

    @router.get(
        "/interfaces",
        response_model=list[NetworkStatus],
        summary="Get configured network interfaces",
        description="Return configured logical-to-physical CAN interface mappings.",
        response_description="List of configured CAN interface mappings",
    )
    async def get_network_interfaces(
        can_facade: VerifiedCANFacade,
        _: Annotated[None, Depends(verify_can_interface_enabled)],
    ) -> list[NetworkStatus]:
        """Get configured logical-to-physical network interface mappings."""

        try:
            return _network_statuses(await can_facade.get_interface_mappings())

        except Exception as e:
            logger.error("Error getting network interfaces: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to get interfaces: {e!s}") from e

    @router.get(
        "/statistics",
        response_model=dict[str, Any],
        summary="Get facade-reported queue status",
        description=(
            "Return CANFacade.get_queue_status() only. This is facade-reported queue status "
            "and not real TX queue telemetry."
        ),
        response_description="Facade-reported CAN queue status",
    )
    async def get_network_statistics(
        can_facade: VerifiedCANFacade,
        _: Annotated[None, Depends(verify_can_interface_enabled)],
    ) -> dict[str, Any]:
        """Get facade-reported CAN queue status without bus statistics telemetry."""

        try:
            return await can_facade.get_queue_status()

        except Exception as e:
            logger.error("Error getting network statistics: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to get statistics: {e!s}") from e

    return router


@register_domain_router("networks")
def register_networks_router() -> APIRouter:
    """Register the networks domain router"""
    return create_networks_router()
