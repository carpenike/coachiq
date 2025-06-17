"""
Device Discovery API Router

FastAPI router for device discovery and network topology endpoints.
Provides device polling, network mapping, and availability tracking.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.core.dependencies_v2 import get_feature_manager
from backend.services.device_discovery_service import DeviceDiscoveryService

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter(prefix="/api/discovery", tags=["device_discovery"])


class PollDeviceRequest(BaseModel):
    """Request model for device polling."""

    source_address: int
    pgn: int
    protocol: str = "rvc"
    instance: int | None = None


class DiscoverDevicesRequest(BaseModel):
    """Request model for device discovery."""

    protocol: str = "rvc"


class DeviceSetupRequest(BaseModel):
    """Request model for device setup wizard."""

    device_address: int
    device_name: str
    device_type: str
    area: str = "unknown"
    capabilities: list[str] = []
    configuration: dict[str, Any] = {}


class AutoDiscoveryRequest(BaseModel):
    """Request model for auto-discovery wizard."""

    protocols: list[str] = ["rvc"]
    scan_duration_seconds: int = 30
    deep_scan: bool = False
    save_results: bool = True


def _check_device_discovery_enabled(request: Request) -> None:
    """Check if device discovery feature is enabled, raise 404 if disabled."""
    feature_manager = get_feature_manager(request)
    if not feature_manager.is_enabled("device_discovery"):
        raise HTTPException(status_code=404, detail="device_discovery feature is disabled")


def get_device_discovery_service(request: Request) -> DeviceDiscoveryService:
    """Get the device discovery service from app state."""
    if not hasattr(request.app.state, "device_discovery_service"):
        raise HTTPException(status_code=500, detail="Device discovery service not available")
    return request.app.state.device_discovery_service


def _get_device_discovery_feature(request: Request):
    """Get the device discovery feature instance."""
    feature_manager = get_feature_manager(request)
    feature = feature_manager.get_feature("device_discovery")
    if not feature:
        raise HTTPException(status_code=503, detail="Device discovery feature not available")
    return feature


@router.get(
    "/topology",
    response_model=dict[str, Any],
    summary="Get network topology",
    description="Return the current network topology with discovered devices and their status.",
    response_description="Network topology information including devices, protocols, and health metrics",
)
async def get_network_topology(
    request: Request,
    service: Annotated[DeviceDiscoveryService, Depends(get_device_discovery_service)],
) -> dict[str, Any]:
    """
    Get the current network topology information.

    This endpoint provides a comprehensive view of the discovered network
    including devices, protocols, health metrics, and availability statistics.
    """
    logger.debug("GET /discovery/topology - Retrieving network topology")
    _check_device_discovery_enabled(request)

    try:
        topology = await service.get_network_topology()

        logger.info(f"Retrieved network topology with {topology.get('total_devices', 0)} devices")
        return topology

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving network topology: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/availability",
    response_model=dict[str, Any],
    summary="Get device availability",
    description="Return device availability statistics and status information.",
    response_description="Device availability metrics including online/offline counts and protocol distribution",
)
async def get_device_availability(
    request: Request,
    service: Annotated[DeviceDiscoveryService, Depends(get_device_discovery_service)],
) -> dict[str, Any]:
    """
    Get device availability statistics.

    This endpoint provides information about device availability,
    including online/offline status, recent activity, and protocol distribution.
    """
    logger.debug("GET /discovery/availability - Retrieving device availability")
    _check_device_discovery_enabled(request)

    try:
        availability = await service.get_device_availability()

        logger.info(f"Retrieved availability for {availability.get('total_devices', 0)} devices")
        return availability

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving device availability: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/discover",
    response_model=dict[str, Any],
    summary="Discover devices",
    description="Perform active device discovery for a specific protocol.",
    response_description="Discovery results with found devices and their information",
)
async def discover_devices(
    request: Request,
    discover_request: DiscoverDevicesRequest,
) -> dict[str, Any]:
    """
    Perform active device discovery for a specific protocol.

    This endpoint initiates an active discovery process using PGN Request
    messages to find devices on the specified protocol network.

    Args:
        discover_request: Discovery configuration including protocol

    Returns:
        Discovery results with found devices
    """
    logger.info(
        f"POST /discovery/discover - Starting discovery for protocol: {discover_request.protocol}"
    )
    _check_device_discovery_enabled(request)

    try:
        feature = _get_device_discovery_feature(request)
        discovered = await feature.discover_devices(discover_request.protocol)

        # Convert DeviceInfo objects to dictionaries for JSON response
        result = {
            "protocol": discover_request.protocol,
            "devices_found": len(discovered),
            "devices": {
                str(addr): {
                    "source_address": device.source_address,
                    "protocol": device.protocol,
                    "device_type": device.device_type,
                    "status": device.status,
                    "last_seen": device.last_seen,
                    "first_seen": device.first_seen,
                    "response_count": device.response_count,
                    "capabilities": list(device.capabilities),
                }
                for addr, device in discovered.items()
            },
        }

        logger.info(
            f"Discovery completed for {discover_request.protocol}, found {len(discovered)} devices"
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during device discovery: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/poll",
    response_model=dict[str, Any],
    summary="Poll device",
    description="Send a polling request to a specific device for status information.",
    response_description="Polling request status and information",
)
async def poll_device(
    request: Request,
    poll_request: PollDeviceRequest,
) -> dict[str, Any]:
    """
    Poll a specific device for status information.

    This endpoint sends a PGN Request message to a specific device
    to request current status information.

    Args:
        poll_request: Polling configuration including device address and PGN

    Returns:
        Polling request status
    """
    logger.info(
        f"POST /discovery/poll - Polling device {poll_request.source_address:02X} "
        f"for PGN {poll_request.pgn:04X}"
    )
    _check_device_discovery_enabled(request)

    try:
        feature = _get_device_discovery_feature(request)
        success = await feature.poll_device(
            source_address=poll_request.source_address,
            pgn=poll_request.pgn,
            protocol=poll_request.protocol,
            instance=poll_request.instance,
        )

        result = {
            "success": success,
            "message": (
                "Poll request sent successfully" if success else "Failed to send poll request"
            ),
            "request": {
                "source_address": poll_request.source_address,
                "pgn": poll_request.pgn,
                "protocol": poll_request.protocol,
                "instance": poll_request.instance,
            },
        }

        if success:
            logger.info(f"Poll request sent to device {poll_request.source_address:02X}")
        else:
            logger.warning(
                f"Failed to send poll request to device {poll_request.source_address:02X}"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error polling device: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/status",
    response_model=dict[str, Any],
    summary="Get discovery service status",
    description="Return the current status and configuration of the device discovery service.",
    response_description="Service status including configuration and runtime information",
)
async def get_discovery_status(
    request: Request,
) -> dict[str, Any]:
    """
    Get the current status of the device discovery service.

    This endpoint provides information about the discovery service
    status, configuration, and runtime metrics.
    """
    logger.debug("GET /discovery/status - Retrieving discovery service status")
    _check_device_discovery_enabled(request)

    try:
        feature_manager = get_feature_manager(request)
        feature = _get_device_discovery_feature(request)

        # Get feature info and health status
        feature_info = await feature.get_feature_info()
        health_status = await feature.health_check()

        # Combine into status response
        status = {
            "enabled": feature_manager.is_enabled("device_discovery"),
            "feature_info": feature_info,
            "health": health_status,
            "service_status": (
                "active"
                if health_status.get("status") == "healthy"
                else health_status.get("status", "unknown")
            ),
        }

        logger.info(f"Discovery service status: {status['service_status']}")
        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving discovery status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/protocols",
    response_model=dict[str, Any],
    summary="Get supported protocols",
    description="Return information about supported protocols for device discovery.",
    response_description="List of supported protocols and their configuration",
)
async def get_supported_protocols(
    request: Request,
) -> dict[str, Any]:
    """
    Get information about supported protocols for device discovery.

    This endpoint provides details about which protocols are supported
    for device discovery and their specific configuration.
    """
    logger.debug("GET /discovery/protocols - Retrieving supported protocols")
    _check_device_discovery_enabled(request)

    try:
        feature_manager = get_feature_manager(request)

        # Get feature configuration
        feature_config = feature_manager.get_feature_config("device_discovery")

        protocols = {
            "supported_protocols": feature_config.get("supported_protocols", ["rvc", "j1939"]),
            "discovery_pgns": feature_config.get("discovery_pgns", {}),
            "status_pgns": feature_config.get("status_pgns", {}),
            "configuration": {
                "polling_interval": feature_config.get("polling_interval_seconds", 30),
                "discovery_interval": feature_config.get("discovery_interval_seconds", 300),
                "poll_timeout": feature_config.get("poll_timeout_seconds", 5),
                "max_retries": feature_config.get("poll_retry_limit", 3),
            },
        }

        logger.info(
            f"Retrieved protocol information for {len(protocols['supported_protocols'])} protocols"
        )
        return protocols

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving protocol information: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/wizard/auto-discover",
    response_model=dict[str, Any],
    summary="Start auto-discovery wizard",
    description="Begin an intelligent auto-discovery process with step-by-step guidance.",
    response_description="Auto-discovery wizard results with discovered devices and setup recommendations",
)
async def start_auto_discovery_wizard(
    request: Request,
    discovery_request: AutoDiscoveryRequest,
    service: Annotated[DeviceDiscoveryService, Depends(get_device_discovery_service)],
) -> dict[str, Any]:
    """
    Start the enhanced auto-discovery wizard.

    This endpoint initiates an intelligent discovery process that:
    - Scans multiple protocols simultaneously
    - Profiles device capabilities
    - Provides setup recommendations
    - Offers configuration guidance

    Args:
        discovery_request: Auto-discovery configuration

    Returns:
        Comprehensive discovery results with setup guidance
    """
    logger.info(
        f"POST /discovery/wizard/auto-discover - Starting enhanced discovery for protocols: {discovery_request.protocols}"
    )
    _check_device_discovery_enabled(request)

    try:
        # Start enhanced auto-discovery
        results = await service.auto_discovery_wizard(
            protocols=discovery_request.protocols,
            scan_duration=discovery_request.scan_duration_seconds,
            deep_scan=discovery_request.deep_scan,
            save_results=discovery_request.save_results,
        )

        logger.info(
            f"Auto-discovery completed: found {results.get('total_devices', 0)} devices across {len(discovery_request.protocols)} protocols"
        )
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during auto-discovery wizard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/wizard/setup-device",
    response_model=dict[str, Any],
    summary="Setup discovered device",
    description="Configure a discovered device with guided setup wizard.",
    response_description="Device setup results and configuration status",
)
async def setup_discovered_device(
    request: Request,
    setup_request: DeviceSetupRequest,
    service: Annotated[DeviceDiscoveryService, Depends(get_device_discovery_service)],
) -> dict[str, Any]:
    """
    Set up a discovered device with guided configuration.

    This endpoint helps users configure a discovered device by:
    - Validating device capabilities
    - Setting up device naming and areas
    - Configuring device-specific parameters
    - Adding to entity management system

    Args:
        setup_request: Device setup configuration

    Returns:
        Setup results and entity configuration
    """
    logger.info(
        f"POST /discovery/wizard/setup-device - Setting up device {setup_request.device_address:02X}"
    )
    _check_device_discovery_enabled(request)

    try:
        # Setup device with wizard guidance
        setup_result = await service.setup_device_wizard(
            device_address=setup_request.device_address,
            device_name=setup_request.device_name,
            device_type=setup_request.device_type,
            area=setup_request.area,
            capabilities=setup_request.capabilities,
            configuration=setup_request.configuration,
        )

        logger.info(
            f"Device setup completed for {setup_request.device_name} ({setup_request.device_address:02X})"
        )
        return setup_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting up device: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/wizard/device-profile/{device_address}",
    response_model=dict[str, Any],
    summary="Get device profile",
    description="Get detailed device profile with capabilities and configuration options.",
    response_description="Comprehensive device profile with setup recommendations",
)
async def get_device_profile(
    request: Request,
    device_address: int,
    protocol: str = Query("rvc", description="Protocol to use for device profiling"),
) -> dict[str, Any]:
    """
    Get a detailed profile of a discovered device.

    This endpoint analyzes a device to provide:
    - Detailed capability detection
    - Device type identification
    - Configuration recommendations
    - Setup guidance

    Args:
        device_address: Address of the device to profile
        protocol: Protocol to use for profiling

    Returns:
        Comprehensive device profile and setup recommendations
    """
    logger.info(f"GET /discovery/wizard/device-profile/{device_address:02X} - Profiling device")
    _check_device_discovery_enabled(request)

    try:
        feature = _get_device_discovery_feature(request)

        # Get enhanced device profile
        profile = await feature.get_device_profile(device_address=device_address, protocol=protocol)

        if not profile:
            raise HTTPException(status_code=404, detail="Device not found or not responding")

        logger.info(
            f"Retrieved profile for device {device_address:02X}: {profile.get('device_type', 'unknown')}"
        )
        return profile

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error profiling device {device_address:02X}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/wizard/setup-recommendations",
    response_model=dict[str, Any],
    summary="Get setup recommendations",
    description="Get intelligent setup recommendations based on discovered devices.",
    response_description="Setup recommendations and configuration suggestions",
)
async def get_setup_recommendations(
    request: Request,
    service: Annotated[DeviceDiscoveryService, Depends(get_device_discovery_service)],
    include_configured: bool = Query(False, description="Include already configured devices"),
) -> dict[str, Any]:
    """
    Get intelligent setup recommendations for discovered devices.

    This endpoint analyzes all discovered devices and provides:
    - Priority setup recommendations
    - Device grouping suggestions
    - Area assignment recommendations
    - Configuration best practices

    Args:
        include_configured: Whether to include already configured devices

    Returns:
        Intelligent setup recommendations and guidance
    """
    logger.debug("GET /discovery/wizard/setup-recommendations - Generating setup recommendations")
    _check_device_discovery_enabled(request)

    try:
        # Generate intelligent recommendations
        recommendations = await service.get_setup_recommendations(
            include_configured=include_configured
        )

        logger.info(
            f"Generated {len(recommendations.get('recommendations', []))} setup recommendations"
        )
        return recommendations

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating setup recommendations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/network-map",
    response_model=dict[str, Any],
    summary="Get enhanced network map",
    description="Get comprehensive network topology map with device relationships.",
    response_description="Enhanced network topology with device relationships and health metrics",
)
async def get_enhanced_network_map(
    request: Request,
    service: Annotated[DeviceDiscoveryService, Depends(get_device_discovery_service)],
    include_offline: bool = Query(True, description="Include offline devices"),
    group_by_protocol: bool = Query(True, description="Group devices by protocol"),
) -> dict[str, Any]:
    """
    Get an enhanced network topology map.

    This endpoint provides a comprehensive view of the network including:
    - Device relationships and dependencies
    - Protocol bridges and connections
    - Network health and performance metrics
    - Geographic/logical device groupings

    Args:
        include_offline: Whether to include offline devices
        group_by_protocol: Whether to group devices by protocol

    Returns:
        Enhanced network topology map with relationships
    """
    logger.debug("GET /discovery/network-map - Retrieving enhanced network map")
    _check_device_discovery_enabled(request)

    try:
        # Get enhanced network topology
        network_map = await service.get_enhanced_network_map(
            include_offline=include_offline, group_by_protocol=group_by_protocol
        )

        total_devices = sum(
            len(devices) for devices in network_map.get("device_groups", {}).values()
        )
        logger.info(f"Retrieved enhanced network map with {total_devices} devices")
        return network_map

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving enhanced network map: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
