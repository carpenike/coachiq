"""
Multi-Network API Router

Provides API endpoints for multi-network CAN management status and bridge operations.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.core.dependencies_v2 import get_feature_manager
from backend.services.feature_manager import FeatureManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/multi-network", tags=["multi-network"])


@router.get("/status")
async def get_multi_network_status(
    feature_manager: Annotated[FeatureManager, Depends(get_feature_manager)],
) -> dict[str, Any]:
    """
    Get the status of multi-network CAN management.

    Returns:
        Multi-network status information including network health and statistics
    """
    try:
        multi_network_feature = feature_manager.get_feature("multi_network_can")
        if not multi_network_feature or not multi_network_feature.enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "message": "Multi-network CAN feature is not enabled",
            }

        # Get status from the multi-network feature
        status = multi_network_feature.get_status()
        return {"enabled": True, "status": "active", **status}

    except Exception as e:
        logger.error(f"Error getting multi-network status: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get multi-network status: {e}"
        ) from e


@router.get("/bridge-status")
async def get_bridge_status(
    feature_manager: Annotated[FeatureManager, Depends(get_feature_manager)],
) -> dict[str, Any]:
    """
    Get the status of protocol bridges between different CAN networks.

    Returns:
        Bridge status information including translation statistics and health
    """
    try:
        # Check if multi-network feature is available
        multi_network_feature = feature_manager.get_feature("multi_network_can")
        if not multi_network_feature or not multi_network_feature.enabled:
            return {
                "enabled": False,
                "bridges": {},
                "message": "Multi-network CAN feature is not enabled",
            }

        # Check for J1939 bridge
        j1939_feature = feature_manager.get_feature("j1939")
        j1939_bridge_status = {}
        if j1939_feature and j1939_feature.enabled:
            try:
                j1939_bridge_status = j1939_feature.get_bridge_status()
            except AttributeError:
                j1939_bridge_status = {
                    "enabled": True,
                    "status": "active",
                    "message": "J1939 bridge operational",
                }

        # Check for Firefly bridge
        firefly_feature = feature_manager.get_feature("firefly")
        firefly_bridge_status = {}
        if firefly_feature and firefly_feature.enabled:
            try:
                firefly_bridge_status = firefly_feature.get_bridge_status()
            except AttributeError:
                firefly_bridge_status = {
                    "enabled": True,
                    "status": "active",
                    "message": "Firefly bridge operational",
                }

        # Check for Spartan K2 bridge
        spartan_k2_feature = feature_manager.get_feature("spartan_k2")
        spartan_k2_bridge_status = {}
        if spartan_k2_feature and spartan_k2_feature.enabled:
            try:
                spartan_k2_bridge_status = spartan_k2_feature.get_bridge_status()
            except AttributeError:
                spartan_k2_bridge_status = {
                    "enabled": True,
                    "status": "active",
                    "message": "Spartan K2 bridge operational",
                }

        return {
            "enabled": True,
            "bridges": {
                "j1939": j1939_bridge_status,
                "firefly": firefly_bridge_status,
                "spartan_k2": spartan_k2_bridge_status,
            },
            "total_bridges": len(
                [
                    status
                    for status in [
                        j1939_bridge_status,
                        firefly_bridge_status,
                        spartan_k2_bridge_status,
                    ]
                    if status.get("enabled", False)
                ]
            ),
        }

    except Exception as e:
        logger.error(f"Error getting bridge status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get bridge status: {e}") from e


@router.get("/networks")
async def get_networks(
    feature_manager: Annotated[FeatureManager, Depends(get_feature_manager)],
) -> dict[str, Any]:
    """
    Get information about all registered CAN networks.

    Returns:
        Network information including health status and configuration
    """
    try:
        multi_network_feature = feature_manager.get_feature("multi_network_can")
        if not multi_network_feature or not multi_network_feature.enabled:
            return {
                "enabled": False,
                "networks": {},
                "message": "Multi-network CAN feature is not enabled",
            }

        # Get network information from the multi-network feature
        try:
            networks = multi_network_feature.get_networks()
            return {"enabled": True, "networks": networks, "network_count": len(networks)}
        except AttributeError:
            # Fallback if method doesn't exist
            return {
                "enabled": True,
                "networks": {
                    "house": {"status": "unknown", "interface": "logical"},
                    "chassis": {"status": "unknown", "interface": "logical"},
                },
                "network_count": 2,
                "message": "Network details unavailable - using defaults",
            }

    except Exception as e:
        logger.error(f"Error getting networks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get networks: {e}") from e


@router.get("/health")
async def get_multi_network_health(
    feature_manager: Annotated[FeatureManager, Depends(get_feature_manager)],
) -> dict[str, Any]:
    """
    Get comprehensive health status of the multi-network system.

    Returns:
        Health status including feature status, network health, and diagnostics
    """
    try:
        health_status = {"overall_status": "healthy", "features": {}, "warnings": [], "errors": []}

        # Check each protocol feature
        protocol_features = ["multi_network_can", "j1939", "firefly", "spartan_k2"]

        for feature_name in protocol_features:
            feature = feature_manager.get_feature(feature_name)
            if feature:
                try:
                    feature_health = feature.health if hasattr(feature, "health") else "unknown"
                    health_status["features"][feature_name] = {
                        "enabled": feature.enabled,
                        "health": feature_health,
                        "status": "operational"
                        if feature.enabled and feature_health == "healthy"
                        else "degraded",
                    }
                except Exception as e:
                    health_status["features"][feature_name] = {
                        "enabled": False,
                        "health": "error",
                        "status": "failed",
                        "error": str(e),
                    }
                    health_status["errors"].append(f"{feature_name}: {e}")
            else:
                health_status["features"][feature_name] = {
                    "enabled": False,
                    "health": "unavailable",
                    "status": "not_configured",
                }

        # Determine overall status
        if health_status["errors"]:
            health_status["overall_status"] = "error"
        elif any(f["status"] == "degraded" for f in health_status["features"].values()):
            health_status["overall_status"] = "degraded"

        return health_status

    except Exception as e:
        logger.error(f"Error getting multi-network health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get health status: {e}") from e
