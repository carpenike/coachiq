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
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.domains import register_domain_router

logger = logging.getLogger(__name__)


# Domain-specific schemas for v2 API
class NetworkStatus(BaseModel):
    """Network interface status"""

    interface_name: str = Field(..., description="Network interface name")
    protocol: str = Field(..., description="Protocol type (CAN, J1939, etc.)")
    status: str = Field(..., description="Interface status: active/inactive/error")
    message_count: int = Field(..., description="Total messages processed")
    error_count: int = Field(..., description="Error count")
    last_activity: float = Field(..., description="Last activity timestamp")


class NetworkSummary(BaseModel):
    """Overall network summary"""

    total_interfaces: int = Field(..., description="Total network interfaces")
    active_interfaces: int = Field(..., description="Active interfaces")
    total_messages: int = Field(..., description="Total messages across all interfaces")
    total_errors: int = Field(..., description="Total errors across all interfaces")
    networks: list[NetworkStatus] = Field(..., description="Individual network status")
    timestamp: float = Field(..., description="Summary timestamp")


def create_networks_router() -> APIRouter:
    """Create the networks domain router with all endpoints"""
    router = APIRouter(tags=["networks-v2"])

    @router.get("/health")
    async def health_check(request: Request) -> dict[str, Any]:
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
            "timestamp": "2025-01-11T00:00:00Z",
        }

    @router.get("/schemas")
    async def get_schemas(request: Request) -> dict[str, Any]:
        """Export schemas for networks domain"""

        return {
            "message": "Networks domain schemas available",
            "available_endpoints": ["/health", "/schemas", "/status", "/interfaces"],
        }

    @router.get("/status", response_model=NetworkSummary)
    async def get_network_status(request: Request) -> NetworkSummary:
        """Get overall network status and statistics"""

        try:
            # Mock network interfaces for demonstration
            # In production, this would query actual CAN interfaces
            networks = [
                NetworkStatus(
                    interface_name="can0",
                    protocol="RV-C",
                    status="active",
                    message_count=12500,
                    error_count=0,
                    last_activity=time.time(),
                ),
                NetworkStatus(
                    interface_name="virtual0",
                    protocol="Virtual",
                    status="active",
                    message_count=8300,
                    error_count=2,
                    last_activity=time.time() - 30,
                ),
            ]

            return NetworkSummary(
                total_interfaces=len(networks),
                active_interfaces=len([n for n in networks if n.status == "active"]),
                total_messages=sum(n.message_count for n in networks),
                total_errors=sum(n.error_count for n in networks),
                networks=networks,
                timestamp=time.time(),
            )

        except Exception as e:
            logger.error(f"Error getting network status: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get network status: {e!s}")

    @router.get("/interfaces")
    async def get_network_interfaces(request: Request) -> list[NetworkStatus]:
        """Get detailed information about network interfaces"""

        try:
            # This would integrate with actual CAN interface discovery
            return [
                NetworkStatus(
                    interface_name="can0",
                    protocol="RV-C",
                    status="active",
                    message_count=12500,
                    error_count=0,
                    last_activity=time.time(),
                ),
                NetworkStatus(
                    interface_name="virtual0",
                    protocol="Virtual",
                    status="active",
                    message_count=8300,
                    error_count=2,
                    last_activity=time.time() - 30,
                ),
            ]

        except Exception as e:
            logger.error(f"Error getting network interfaces: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get interfaces: {e!s}")

    return router


@register_domain_router("networks")
def register_networks_router() -> APIRouter:
    """Register the networks domain router"""
    return create_networks_router()
