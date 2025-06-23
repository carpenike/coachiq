"""
Multi-Network API Router

Provides API endpoints for multi-network CAN management status and bridge operations.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.core.dependencies import create_optional_service_dependency

# Create service dependencies - these services are optional based on configuration
get_multi_network_service = create_optional_service_dependency("multi_network_can_service")
get_j1939_service = create_optional_service_dependency("j1939_service")
get_firefly_service = create_optional_service_dependency("firefly_service")
get_spartan_k2_service = create_optional_service_dependency("spartan_k2_service")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/multi-network", tags=["multi-network"])


@router.get("/status")
async def get_multi_network_status(
    multi_network_service: Annotated[Any | None, Depends(get_multi_network_service)],
) -> dict[str, Any]:
    """
    Get the status of multi-network CAN management.

    Returns:
        Multi-network status information including network health and statistics
    """
    try:
        if not multi_network_service:
            return {
                "enabled": False,
                "status": "disabled",
                "message": "Multi-network CAN service is not available",
            }

        # Get status from the multi-network service
        status = await multi_network_service.get_status()
        return {"enabled": True, "status": "active", **status}

    except Exception as e:
        logger.error(f"Error getting multi-network status: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get multi-network status: {e}"
        ) from e


@router.get("/bridge-status")
async def get_bridge_status(
    multi_network_service: Annotated[Any | None, Depends(get_multi_network_service)],
    j1939_service: Annotated[Any | None, Depends(get_j1939_service)],
    firefly_service: Annotated[Any | None, Depends(get_firefly_service)],
    spartan_k2_service: Annotated[Any | None, Depends(get_spartan_k2_service)],
) -> dict[str, Any]:
    """
    Get the status of protocol bridges between different CAN networks.

    Returns:
        Bridge status information including translation statistics and health
    """
    try:
        bridges = {}

        # Check for J1939 bridge
        if j1939_service:
            bridges["j1939"] = await j1939_service.get_bridge_status()
        else:
            bridges["j1939"] = {"enabled": False, "status": "unavailable"}

        # Check for Firefly bridge
        if firefly_service:
            bridges["firefly"] = await firefly_service.get_bridge_status()
        else:
            bridges["firefly"] = {"enabled": False, "status": "unavailable"}

        # Check for Spartan K2 bridge
        if spartan_k2_service:
            bridges["spartan_k2"] = await spartan_k2_service.get_bridge_status()
        else:
            bridges["spartan_k2"] = {"enabled": False, "status": "unavailable"}

        total_bridges = len([status for status in bridges.values() if status.get("enabled", False)])

        return {
            "enabled": bool(multi_network_service),
            "bridges": bridges,
            "total_bridges": total_bridges,
        }

    except Exception as e:
        logger.error(f"Error getting bridge status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get bridge status: {e}") from e


@router.get("/networks")
async def get_networks(
    multi_network_service: Annotated[Any | None, Depends(get_multi_network_service)],
) -> dict[str, Any]:
    """
    Get information about all registered CAN networks.

    Returns:
        Network information including health status and configuration
    """
    try:
        if not multi_network_service:
            return {
                "enabled": False,
                "networks": {},
                "message": "Multi-network CAN service is not available",
            }

        # Get network information from the multi-network service
        networks = await multi_network_service.get_networks()
        return {"enabled": True, "networks": networks, "network_count": len(networks)}

    except Exception as e:
        logger.error(f"Error getting networks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get networks: {e}") from e


@router.get("/health")
async def get_multi_network_health(
    multi_network_service: Annotated[Any | None, Depends(get_multi_network_service)],
    j1939_service: Annotated[Any | None, Depends(get_j1939_service)],
    firefly_service: Annotated[Any | None, Depends(get_firefly_service)],
    spartan_k2_service: Annotated[Any | None, Depends(get_spartan_k2_service)],
) -> dict[str, Any]:
    """
    Get comprehensive health status of the multi-network system.

    Returns:
        Health status including service status, network health, and diagnostics
    """
    try:
        health_status = {"overall_status": "healthy", "services": {}, "warnings": [], "errors": []}

        # Check each protocol service
        services = {
            "multi_network_can": multi_network_service,
            "j1939": j1939_service,
            "firefly": firefly_service,
            "spartan_k2": spartan_k2_service,
        }

        for service_name, service in services.items():
            if service:
                try:
                    service_health = (
                        await service.health_check()
                        if hasattr(service, "health_check")
                        else {"status": "unknown"}
                    )
                    health_status["services"][service_name] = {
                        "enabled": True,
                        "health": service_health.get("status", "unknown"),
                        "status": "operational"
                        if service_health.get("status") == "healthy"
                        else "degraded",
                    }
                except Exception as e:
                    health_status["services"][service_name] = {
                        "enabled": False,
                        "health": "error",
                        "status": "failed",
                        "error": str(e),
                    }
                    health_status["errors"].append(f"{service_name}: {e}")
            else:
                health_status["services"][service_name] = {
                    "enabled": False,
                    "health": "unavailable",
                    "status": "not_configured",
                }

        # Determine overall status
        if health_status["errors"]:
            health_status["overall_status"] = "error"
        elif any(f["status"] == "degraded" for f in health_status["services"].values()):
            health_status["overall_status"] = "degraded"

        return health_status

    except Exception as e:
        logger.error(f"Error getting multi-network health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get health status: {e}") from e
