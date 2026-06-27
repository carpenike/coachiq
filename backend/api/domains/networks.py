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
from backend.core.dependencies import CANNetworkTelemetryService, VerifiedCANFacade

logger = logging.getLogger(__name__)


# Domain-specific schemas for v2 API
class NetworkStatus(BaseModel):
    """Configured logical-to-physical network interface mapping with CAN telemetry."""

    logical_name: str = Field(..., description="Logical interface name")
    physical_interface: str = Field(..., description="Configured physical interface name")
    state: str | None = Field(default=None, description="SocketCAN controller state when available")
    bitrate: int | None = Field(default=None, description="Configured CAN bitrate when available")
    rx_packets: int | None = Field(default=None, description="Cumulative received packet count")
    tx_packets: int | None = Field(default=None, description="Cumulative transmitted packet count")
    rx_bytes: int | None = Field(default=None, description="Cumulative received byte count")
    tx_bytes: int | None = Field(default=None, description="Cumulative transmitted byte count")
    rx_errors: int | None = Field(default=None, description="Cumulative received error count")
    tx_errors: int | None = Field(default=None, description="Cumulative transmitted error count")
    rx_dropped: int | None = Field(default=None, description="Cumulative received dropped count")
    tx_dropped: int | None = Field(default=None, description="Cumulative transmitted dropped count")
    bus_errors: int | None = Field(
        default=None, description="Best-effort CAN controller bus error count"
    )
    restarts: int | None = Field(
        default=None, description="Best-effort CAN controller restart count"
    )
    arbitration_lost: int | None = Field(
        default=None, description="Best-effort CAN controller arbitration lost count"
    )
    error_warning: int | None = Field(
        default=None, description="Best-effort CAN controller error-warning count"
    )
    error_passive: int | None = Field(
        default=None, description="Best-effort CAN controller error-passive count"
    )
    bus_off: int | None = Field(
        default=None, description="Best-effort CAN controller bus-off count"
    )
    message_rate: float | None = Field(
        default=None, description="Rolling CAN frame rate in frames/second"
    )
    bus_load_percent: float | None = Field(
        default=None, description="Approximate rolling CAN bus load percentage"
    )
    last_activity: str | None = Field(
        default=None, description="ISO 8601 timestamp of last observed packet activity"
    )


class NetworkSummary(BaseModel):
    """Truthful network summary from CAN facade and SocketCAN telemetry."""

    total_interfaces: int = Field(..., description="Total configured logical interfaces")
    interfaces: list[NetworkStatus] = Field(..., description="Configured interface mappings")
    can_service_health: dict[str, Any] = Field(
        ..., description="Service-level CAN health reported by CANFacade"
    )
    queue_status: dict[str, Any] = Field(
        ..., description="Facade-reported CAN queue status, not real TX queue telemetry"
    )
    timestamp: str = Field(..., description="Summary timestamp in ISO 8601 format")


class NetworkStatistics(BaseModel):
    """CAN network statistics from facade-reported queue and bus telemetry."""

    queue_status: dict[str, Any] = Field(
        ..., description="Facade-reported CAN queue status, not real TX queue telemetry"
    )
    bus_statistics: dict[str, Any] = Field(
        ..., description="CANFacade bus statistics built from cumulative SocketCAN counters"
    )
    timestamp: str = Field(..., description="Statistics timestamp in ISO 8601 format")


def _utc_timestamp() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


NETWORK_TELEMETRY_FIELDS = (
    "state",
    "bitrate",
    "rx_packets",
    "tx_packets",
    "rx_bytes",
    "tx_bytes",
    "rx_errors",
    "tx_errors",
    "rx_dropped",
    "tx_dropped",
    "bus_errors",
    "restarts",
    "arbitration_lost",
    "error_warning",
    "error_passive",
    "bus_off",
    "message_rate",
    "bus_load_percent",
    "last_activity",
)


def _network_statuses(
    interface_mappings: dict[str, str],
    interface_details: dict[str, dict[str, Any]] | None = None,
    rolling_telemetry: dict[str, dict[str, Any]] | None = None,
) -> list[NetworkStatus]:
    """Build response models from configured interface mappings."""
    details = interface_details or {}
    rolling = rolling_telemetry or {}
    statuses = []
    for logical_name, physical_interface in sorted(interface_mappings.items()):
        merged_details = {
            **details.get(physical_interface, {}),
            **rolling.get(physical_interface, {}),
        }
        telemetry = {
            field_name: merged_details.get(field_name) for field_name in NETWORK_TELEMETRY_FIELDS
        }
        statuses.append(
            NetworkStatus(
                logical_name=logical_name,
                physical_interface=physical_interface,
                **telemetry,
            )
        )
    return statuses


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
            "real cumulative per-interface SocketCAN telemetry when available."
        ),
        response_description="Truthful network summary from CAN facade and SocketCAN telemetry",
    )
    async def get_network_status(
        can_facade: VerifiedCANFacade,
        telemetry_service: CANNetworkTelemetryService,
        _: Annotated[None, Depends(verify_can_interface_enabled)],
    ) -> NetworkSummary:
        """Get truthful network status from currently implemented CAN facade sources."""

        try:
            interface_mappings = await can_facade.get_interface_mappings()
            interface_details = await can_facade.get_interface_details()
            interfaces = _network_statuses(
                interface_mappings,
                interface_details,
                telemetry_service.get_rolling_telemetry(),
            )

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
        description="Return configured logical-to-physical CAN interface mappings with telemetry.",
        response_description="List of configured CAN interface mappings with telemetry",
    )
    async def get_network_interfaces(
        can_facade: VerifiedCANFacade,
        telemetry_service: CANNetworkTelemetryService,
        _: Annotated[None, Depends(verify_can_interface_enabled)],
    ) -> list[NetworkStatus]:
        """Get configured logical-to-physical network interface mappings."""

        try:
            interface_mappings = await can_facade.get_interface_mappings()
            interface_details = await can_facade.get_interface_details()
            return _network_statuses(
                interface_mappings,
                interface_details,
                telemetry_service.get_rolling_telemetry(),
            )

        except Exception as e:
            logger.error("Error getting network interfaces: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to get interfaces: {e!s}") from e

    @router.get(
        "/statistics",
        response_model=NetworkStatistics,
        summary="Get CAN network statistics",
        description=(
            "Return facade-reported queue status plus bus statistics derived from real cumulative "
            "SocketCAN counters. Queue status is not real TX queue telemetry."
        ),
        response_description="CAN queue status and cumulative bus statistics",
    )
    async def get_network_statistics(
        can_facade: VerifiedCANFacade,
        _: Annotated[None, Depends(verify_can_interface_enabled)],
    ) -> NetworkStatistics:
        """Get facade-reported queue status and cumulative bus statistics telemetry."""

        try:
            return NetworkStatistics(
                queue_status=await can_facade.get_queue_status(),
                bus_statistics=await can_facade.get_bus_statistics(),
                timestamp=_utc_timestamp(),
            )

        except Exception as e:
            logger.error("Error getting network statistics: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to get statistics: {e!s}") from e

    return router


@register_domain_router("networks")
def register_networks_router() -> APIRouter:
    """Register the networks domain router"""
    return create_networks_router()
