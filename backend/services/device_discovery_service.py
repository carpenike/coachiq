"""
Device Discovery Service

Provides device polling and network discovery capabilities for CAN bus systems.
Supports active device scanning, polling schedules, and network topology mapping.

This service follows the established backend patterns with proper integration
into the config, logging, persistence, and WebSocket systems.
"""

import asyncio
import contextlib
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import can

from backend.core.config import get_settings
from backend.integrations.can.manager import can_tx_queue

# CANService import removed - now using dependency injection

logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    """Information about a discovered device."""

    source_address: int
    protocol: str
    device_type: str | None = None
    manufacturer: str | None = None
    product_id: str | None = None
    version: str | None = None
    capabilities: set[str] = field(default_factory=set)
    last_seen: float = field(default_factory=time.time)
    first_seen: float = field(default_factory=time.time)
    response_count: int = 0
    response_times: list[float] = field(default_factory=list)
    status: str = "discovered"  # discovered, online, offline, error


@dataclass
class PollRequest:
    """Represents a polling request for a specific PGN."""

    target_pgn: int
    target_address: int | None = None  # None for broadcast
    instance: int | None = None
    protocol: str = "rvc"
    last_sent: float = 0
    response_timeout: float = 5.0
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class NetworkTopology:
    """Network topology information."""

    devices: dict[int, DeviceInfo] = field(default_factory=dict)
    protocol_bridges: dict[str, dict[str, Any]] = field(default_factory=dict)
    network_health: dict[str, float] = field(default_factory=dict)
    last_discovery: float = field(default_factory=time.time)


class DeviceDiscoveryService:
    """
    Service for device polling and network discovery.

    This service provides active device scanning, polling schedules,
    and network topology mapping for CAN bus systems.
    """

    def __init__(self, can_facade: Any | None = None, config: Any | None = None):
        """
        Initialize the device discovery service.

        Args:
            can_facade: CAN facade instance for dependency injection
            config: Configuration instance
        """
        self.can_service = can_facade  # Keep same attribute name for compatibility
        self.can_facade = can_facade  # Also store as can_facade for new code
        self.config = config or get_settings()
        self.start_time = time.time()  # Track service start time

        # Discovery state
        self.topology = NetworkTopology()
        self.active_polls: dict[str, PollRequest] = {}
        self.poll_schedules: dict[str, dict[str, Any]] = {}
        self.discovery_active = False

        # Configuration from feature flags
        self.enable_device_polling = getattr(self.config, "device_discovery", {}).get(
            "enable_device_polling", True
        )

        # Determine enabled protocols from configuration
        self.enabled_protocols: list[str] = []
        # RVC is enabled by default
        if getattr(self.config, "rvc_enabled", True):
            self.enabled_protocols.append("rvc")

        # Check J1939 - prefer nested setting if available
        j1939_settings = getattr(self.config, "j1939", None)
        if (j1939_settings and getattr(j1939_settings, "enabled", False)) or getattr(
            self.config, "j1939_enabled", False
        ):
            self.enabled_protocols.append("j1939")

        # Protocol-specific PGN ranges for detection
        self.protocol_pgn_ranges = {
            "rvc": {
                # RV-C specific PGNs
                "characteristic_pgns": {0x1FEF2, 0x1FEDA, 0x1FEEB, 0x1FEE1, 0x1FF7D},
                "pgn_ranges": [(0x1FE00, 0x1FFFF), (0x1F000, 0x1F0FF)],  # Proprietary ranges
            },
            "j1939": {
                # J1939 specific PGNs
                "characteristic_pgns": {0xFECA, 0xF004, 0xFEE5, 0xFEF1, 0xFEF6},
                "pgn_ranges": [(0xF000, 0xFFFF), (0x00000, 0xEFFF)],  # Standard J1939
            },
        }

        # Track detected protocols per interface
        self.detected_protocols: dict[str, set[str]] = defaultdict(set)

        self.polling_interval = getattr(self.config, "device_discovery", {}).get(
            "polling_interval_seconds", 30.0
        )

        self.discovery_interval = getattr(self.config, "device_discovery", {}).get(
            "discovery_interval_seconds", 300.0
        )

        # Protocol-specific configurations
        self.protocol_configs = {
            "rvc": {
                "discovery_pgns": [
                    0x1FEF2,
                    0x1FEDA,
                    0x1FEEB,
                    0x1FEE1,
                ],  # Product ID, Light, Tank, Temperature
                "request_pgn": 0xEA00,
                "timeout": 5.0,
                "retry_limit": 3,
            },
            "j1939": {
                "discovery_pgns": [
                    0x1FEF2,
                    0x1FEE5,
                    0x1FEF1,
                ],  # Product ID, Engine, Component ID
                "request_pgn": 0xEA00,
                "timeout": 5.0,
                "retry_limit": 3,
            },
        }

        # Async tasks
        self._discovery_task: asyncio.Task | None = None
        self._polling_task: asyncio.Task | None = None

        logger.info(
            f"DeviceDiscoveryService initialized with polling_interval={self.polling_interval}s"
        )

    async def start_discovery(self) -> None:
        """Start the device discovery service."""
        if self.discovery_active:
            logger.warning("Device discovery already active")
            return

        self.discovery_active = True

        # Start background tasks
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        self._polling_task = asyncio.create_task(self._polling_loop())

        logger.info("Device discovery service started")

    async def stop_discovery(self) -> None:
        """Stop the device discovery service."""
        self.discovery_active = False

        # Cancel background tasks
        if self._discovery_task:
            self._discovery_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._discovery_task

        if self._polling_task:
            self._polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._polling_task

        logger.info("Device discovery service stopped")

    async def discover_devices(self, protocol: str = "rvc") -> dict[int, DeviceInfo]:
        """
        Perform active device discovery for a specific protocol.

        Args:
            protocol: Protocol to scan (rvc, j1939, etc.)

        Returns:
            Dictionary of discovered devices by source address
        """
        if protocol not in self.protocol_configs:
            logger.warning(f"Unsupported protocol for discovery: {protocol}")
            return {}

        config = self.protocol_configs[protocol]
        discovered = {}

        logger.info(f"Starting device discovery for protocol: {protocol}")

        # Send discovery requests for each PGN
        for pgn in config["discovery_pgns"]:
            try:
                await self._send_pgn_request(
                    pgn=pgn,
                    protocol=protocol,
                    destination=0xFF,  # Broadcast
                )

                # Wait for responses
                await asyncio.sleep(config["timeout"])

            except Exception as e:
                logger.error(f"Error during discovery for PGN {pgn:04X}: {e}")

        # Update topology
        self.topology.last_discovery = time.time()

        logger.info(f"Discovery completed for {protocol}, found {len(discovered)} devices")
        return discovered

    async def poll_device(
        self,
        source_address: int,
        pgn: int,
        protocol: str = "rvc",
        instance: int | None = None,
    ) -> bool:
        """
        Poll a specific device for status information.

        Args:
            source_address: Target device address
            pgn: PGN to request
            protocol: Protocol to use
            instance: Instance number if applicable

        Returns:
            True if request was sent successfully
        """
        try:
            success = await self._send_pgn_request(
                pgn=pgn,
                protocol=protocol,
                destination=source_address,
                instance=instance,
            )

            if success:
                # Track the poll request
                poll_key = f"{protocol}_{source_address:02X}_{pgn:04X}"
                if instance is not None:
                    poll_key += f"_{instance}"

                self.active_polls[poll_key] = PollRequest(
                    target_pgn=pgn,
                    target_address=source_address,
                    instance=instance,
                    protocol=protocol,
                    last_sent=time.time(),
                )

                logger.debug(f"Sent poll request to {source_address:02X} for PGN {pgn:04X}")

            return success

        except Exception as e:
            logger.error(f"Error polling device {source_address:02X}: {e}")
            return False

    async def auto_discovery_wizard(
        self,
        protocols: list[str],
        scan_duration: int = 30,
        deep_scan: bool = False,
        save_results: bool = True,
    ) -> dict[str, Any]:
        """
        Enhanced auto-discovery wizard with intelligent device profiling.

        Args:
            protocols: List of protocols to scan
            scan_duration: Duration of scan in seconds
            deep_scan: Whether to perform deep capability analysis
            save_results: Whether to save discovered devices

        Returns:
            Comprehensive discovery results with setup recommendations
        """
        logger.info(f"Starting auto-discovery wizard for protocols: {protocols}")

        discovery_results = {
            "scan_id": f"discovery_{int(time.time())}",
            "protocols_scanned": protocols,
            "scan_duration": scan_duration,
            "deep_scan": deep_scan,
            "total_devices": 0,
            "devices_by_protocol": {},
            "device_profiles": {},
            "setup_recommendations": [],
            "network_topology": {},
            "scan_summary": {},
        }

        # Phase 1: Basic discovery across all protocols
        all_discovered = {}
        for protocol in protocols:
            logger.info(f"Phase 1: Basic discovery for {protocol}")
            protocol_devices = await self.discover_devices(protocol)
            all_discovered[protocol] = protocol_devices
            discovery_results["devices_by_protocol"][protocol] = len(protocol_devices)

        total_devices = sum(len(devices) for devices in all_discovered.values())
        discovery_results["total_devices"] = total_devices

        if total_devices == 0:
            logger.info("No devices discovered during basic scan")
            discovery_results["scan_summary"]["status"] = "no_devices_found"
            return discovery_results

        # Phase 2: Deep profiling if requested
        if deep_scan:
            logger.info("Phase 2: Deep device profiling")
            for protocol, devices in all_discovered.items():
                for addr in devices:
                    try:
                        profile = await self.get_device_profile(addr, protocol)
                        if profile:
                            device_key = f"{protocol}_{addr:02X}"
                            discovery_results["device_profiles"][device_key] = profile
                    except Exception as e:
                        logger.warning(f"Failed to profile device {addr:02X}: {e}")

        # Phase 3: Generate setup recommendations
        logger.info("Phase 3: Generating setup recommendations")
        recommendations = await self._generate_discovery_recommendations(all_discovered)
        discovery_results["setup_recommendations"] = recommendations

        # Phase 4: Build network topology
        logger.info("Phase 4: Building network topology")
        topology = await self._build_network_topology(all_discovered)
        discovery_results["network_topology"] = topology

        # Phase 5: Save results if requested
        if save_results:
            await self._save_discovery_results(discovery_results)

        discovery_results["scan_summary"] = {
            "status": "completed",
            "devices_found": total_devices,
            "profiles_generated": len(discovery_results["device_profiles"]),
            "recommendations": len(recommendations),
            "scan_completed_at": time.time(),
        }

        logger.info(f"Auto-discovery wizard completed: {total_devices} devices found")
        return discovery_results

    async def get_device_profile(
        self, device_address: int, protocol: str = "rvc"
    ) -> dict[str, Any]:
        """
        Get detailed device profile with capabilities and configuration options.

        Args:
            device_address: Device address to profile
            protocol: Protocol to use for profiling

        Returns:
            Comprehensive device profile with setup guidance
        """
        # Check if device is in our topology
        device_info = self.topology.devices.get(device_address)
        if not device_info:
            logger.warning(f"Device {device_address:02X} not found in topology")
            return {}

        profile = {
            "device_address": device_address,
            "protocol": protocol,
            "basic_info": {
                "source_address": device_info.source_address,
                "device_type": device_info.device_type or "unknown",
                "manufacturer": device_info.manufacturer or "unknown",
                "product_id": device_info.product_id or "unknown",
                "version": device_info.version or "unknown",
                "status": device_info.status,
                "last_seen": device_info.last_seen,
                "first_seen": device_info.first_seen,
                "response_count": device_info.response_count,
            },
            "capabilities": {
                "detected": list(device_info.capabilities),
                "inferred": await self._infer_device_capabilities(device_info),
                "pgns_supported": await self._get_supported_pgns(device_address, protocol),
            },
            "setup_guidance": await self._generate_setup_guidance(device_info),
            "configuration_options": await self._get_configuration_options(device_info),
            "recommended_name": await self._suggest_device_name(device_info),
            "recommended_area": await self._suggest_device_area(device_info),
            "health_metrics": {
                "response_rate": len(device_info.response_times)
                / max(1, device_info.response_count),
                "average_response_time": sum(device_info.response_times)
                / max(1, len(device_info.response_times)),
                "reliability_score": await self._calculate_reliability_score(device_info),
            },
        }

        logger.debug(
            f"Generated profile for device {device_address:02X}: {profile['basic_info']['device_type']}"
        )
        return profile

    async def setup_device_wizard(
        self,
        device_address: int,
        device_name: str,
        device_type: str,
        area: str = "unknown",
        capabilities: list[str] | None = None,
        configuration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Set up a discovered device with guided configuration.

        Args:
            device_address: Device address to set up
            device_name: User-provided device name
            device_type: Device type
            area: Area/location for the device
            capabilities: List of device capabilities
            configuration: Device-specific configuration

        Returns:
            Setup results and entity configuration
        """
        logger.info(f"Setting up device {device_address:02X} as '{device_name}'")

        # Validate device exists
        device_info = self.topology.devices.get(device_address)
        if not device_info:
            msg = f"Device {device_address:02X} not found in topology"
            raise ValueError(msg)

        capabilities = capabilities or []
        configuration = configuration or {}

        setup_result = {
            "device_address": device_address,
            "device_name": device_name,
            "device_type": device_type,
            "area": area,
            "setup_status": "success",
            "entity_id": f"{device_type}_{device_address:02X}",
            "capabilities_configured": capabilities,
            "configuration_applied": configuration,
            "setup_timestamp": time.time(),
            "validation_results": {},
            "next_steps": [],
        }

        try:
            # Validate capabilities
            validation = await self._validate_device_setup(
                device_info, device_type, capabilities, configuration
            )
            setup_result["validation_results"] = validation

            if not validation.get("valid", False):
                setup_result["setup_status"] = "validation_failed"
                setup_result["errors"] = validation.get("errors", [])
                return setup_result

            # Create entity configuration
            entity_config = {
                "entity_id": setup_result["entity_id"],
                "name": device_name,
                "device_type": device_type,
                "suggested_area": area,
                "capabilities": capabilities,
                "raw": {
                    "source_address": device_address,
                    "protocol": device_info.protocol,
                    "discovery_info": {
                        "discovered_at": device_info.first_seen,
                        "device_type": device_info.device_type,
                        "manufacturer": device_info.manufacturer,
                        "product_id": device_info.product_id,
                    },
                },
                "configuration": configuration,
            }

            # TODO: Integrate with entity management system
            # This would require access to the entity service
            # await self._register_entity(entity_config)

            setup_result["entity_config"] = entity_config

            # Generate next steps
            next_steps = await self._generate_setup_next_steps(device_info, setup_result)
            setup_result["next_steps"] = next_steps

            # Update device info
            device_info.device_type = device_type
            device_info.capabilities.update(capabilities)

            logger.info(f"Successfully set up device '{device_name}' ({device_address:02X})")

        except Exception as e:
            logger.error(f"Error setting up device {device_address:02X}: {e}")
            setup_result["setup_status"] = "error"
            setup_result["error"] = str(e)

        return setup_result

    async def get_setup_recommendations(self, include_configured: bool = False) -> dict[str, Any]:
        """
        Generate intelligent setup recommendations for discovered devices.

        Args:
            include_configured: Whether to include already configured devices

        Returns:
            Setup recommendations and configuration guidance
        """
        recommendations = {
            "total_devices": len(self.topology.devices),
            "unconfigured_devices": 0,
            "recommendations": [],
            "priority_actions": [],
            "device_groupings": [],
            "area_suggestions": {},
            "generated_at": time.time(),
        }

        unconfigured_devices = []

        for device in self.topology.devices.values():
            # Determine if device is configured
            is_configured = bool(device.device_type and device.device_type != "unknown")

            if not is_configured or include_configured:
                unconfigured_devices.append(device)

        recommendations["unconfigured_devices"] = len(unconfigured_devices)

        if not unconfigured_devices:
            recommendations["message"] = "All discovered devices are configured"
            return recommendations

        # Generate individual device recommendations
        for device in unconfigured_devices:
            device_rec = await self._generate_device_recommendation(device)
            recommendations["recommendations"].append(device_rec)

        # Generate priority actions
        priority_actions = await self._generate_priority_actions(unconfigured_devices)
        recommendations["priority_actions"] = priority_actions

        # Generate device groupings
        groupings = await self._suggest_device_groupings(unconfigured_devices)
        recommendations["device_groupings"] = groupings

        # Generate area suggestions
        area_suggestions = await self._suggest_area_assignments(unconfigured_devices)
        recommendations["area_suggestions"] = area_suggestions

        logger.info(f"Generated {len(recommendations['recommendations'])} setup recommendations")
        return recommendations

    async def get_enhanced_network_map(
        self, include_offline: bool = True, group_by_protocol: bool = True
    ) -> dict[str, Any]:
        """
        Get enhanced network topology map with device relationships.

        Args:
            include_offline: Whether to include offline devices
            group_by_protocol: Whether to group devices by protocol

        Returns:
            Enhanced network topology with relationships and metrics
        """
        network_map = {
            "total_devices": len(self.topology.devices),
            "online_devices": 0,
            "offline_devices": 0,
            "device_groups": {},
            "protocol_distribution": {},
            "device_relationships": [],
            "network_health": {},
            "topology_metrics": {},
            "last_updated": time.time(),
        }

        online_count = 0
        offline_count = 0
        protocol_counts = defaultdict(int)

        # Process devices
        devices_to_include = []
        for device in self.topology.devices.values():
            is_online = (
                device.status in ["online", "discovered"] and (time.time() - device.last_seen) < 300
            )

            if is_online:
                online_count += 1
            else:
                offline_count += 1
                if not include_offline:
                    continue

            devices_to_include.append(device)
            protocol_counts[device.protocol] += 1

        network_map["online_devices"] = online_count
        network_map["offline_devices"] = offline_count
        network_map["protocol_distribution"] = dict(protocol_counts)

        # Group devices
        if group_by_protocol:
            # Group by protocol
            for device in devices_to_include:
                protocol = device.protocol
                if protocol not in network_map["device_groups"]:
                    network_map["device_groups"][protocol] = []

                device_info = {
                    "address": device.source_address,
                    "device_type": device.device_type or "unknown",
                    "status": device.status,
                    "last_seen": device.last_seen,
                    "response_count": device.response_count,
                    "capabilities": list(device.capabilities),
                }
                network_map["device_groups"][protocol].append(device_info)
        else:
            # Group by device type
            type_groups = defaultdict(list)
            for device in devices_to_include:
                device_type = device.device_type or "unknown"
                device_info = {
                    "address": device.source_address,
                    "protocol": device.protocol,
                    "status": device.status,
                    "last_seen": device.last_seen,
                    "response_count": device.response_count,
                    "capabilities": list(device.capabilities),
                }
                type_groups[device_type].append(device_info)
            network_map["device_groups"] = dict(type_groups)

        # Calculate network health
        network_health = await self._calculate_network_health(devices_to_include)
        network_map["network_health"] = network_health

        # Generate topology metrics
        topology_metrics = await self._calculate_topology_metrics(devices_to_include)
        network_map["topology_metrics"] = topology_metrics

        # Detect device relationships
        relationships = await self._detect_device_relationships(devices_to_include)
        network_map["device_relationships"] = relationships

        logger.info(f"Generated enhanced network map with {len(devices_to_include)} devices")
        return network_map

    # Helper methods for the wizard functionality

    async def _infer_device_capabilities(self, device_info: DeviceInfo) -> list[str]:
        """Infer additional capabilities based on device type and protocol."""
        inferred = []

        if device_info.device_type:
            # Common capability mappings
            capability_map = {
                "light": ["on_off", "brightness"],
                "lock": ["lock", "unlock"],
                "tank": ["level_reading"],
                "temperature": ["temperature_reading"],
                "pump": ["on_off", "pressure"],
                "generator": ["on_off", "status_reading", "load_reading"],
                "hvac": ["on_off", "temperature_control", "fan_speed"],
                "slide": ["extend", "retract", "position_reading"],
            }

            device_type = device_info.device_type.lower()
            for type_key, capabilities in capability_map.items():
                if type_key in device_type:
                    inferred.extend(capabilities)

        return inferred

    async def _get_supported_pgns(self, device_address: int, protocol: str) -> list[int]:
        """Get list of PGNs supported by the device."""
        # This would involve querying the device for supported PGNs
        # For now, return common PGNs based on protocol
        common_pgns = {
            "rvc": [0x1FEDA, 0x1FEEB, 0x1FEE1, 0x1FED9, 0x1FED8, 0x1FED6],
            "j1939": [0x1FEE5, 0x1FEF1, 0x1FEE9, 0x1FEE8],
        }
        return common_pgns.get(protocol, [])

    async def _generate_setup_guidance(self, device_info: DeviceInfo) -> list[str]:
        """Generate setup guidance for a device."""
        guidance = []

        if not device_info.device_type or device_info.device_type == "unknown":
            guidance.append("Device type needs to be identified before configuration")

        if not device_info.capabilities:
            guidance.append("Device capabilities should be detected or manually specified")

        if device_info.response_count < 3:
            guidance.append("Device has limited response history - verify connectivity")

        if time.time() - device_info.last_seen > 300:
            guidance.append("Device appears offline - check device power and connections")

        guidance.append("Choose a descriptive name that identifies the device's purpose")
        guidance.append("Assign the device to the appropriate area/location")

        return guidance

    async def _get_configuration_options(self, device_info: DeviceInfo) -> dict[str, Any]:
        """Get available configuration options for a device."""
        options = {
            "naming": {
                "required": True,
                "suggestions": await self._suggest_device_names(device_info),
                "validation": "Name must be unique and descriptive",
            },
            "area_assignment": {
                "required": True,
                "suggestions": await self._suggest_device_areas(device_info),
                "validation": "Area helps organize devices by location",
            },
            "capabilities": {
                "required": False,
                "detected": list(device_info.capabilities),
                "additional": await self._infer_device_capabilities(device_info),
            },
        }

        # Add device-type specific options
        if device_info.device_type:
            type_options = await self._get_device_type_options(device_info.device_type)
            options.update(type_options)

        return options

    async def _suggest_device_name(self, device_info: DeviceInfo) -> str:
        """Suggest a device name based on type and location."""
        if device_info.device_type and device_info.device_type != "unknown":
            base_name = device_info.device_type.replace("_", " ").title()
            return f"{base_name} {device_info.source_address:02X}"
        return f"Device {device_info.source_address:02X}"

    async def _suggest_device_area(self, device_info: DeviceInfo) -> str:
        """Suggest an area for the device based on type."""
        area_map = {
            "light": "living_room",
            "lock": "entry",
            "tank": "utility",
            "temperature": "living_room",
            "pump": "utility",
            "generator": "utility",
            "hvac": "climate",
            "slide": "living_room",
        }

        if device_info.device_type:
            for type_key, area in area_map.items():
                if type_key in device_info.device_type.lower():
                    return area

        return "unknown"

    async def _calculate_reliability_score(self, device_info: DeviceInfo) -> float:
        """Calculate device reliability score."""
        if device_info.response_count == 0:
            return 0.0

        # Factor in response rate and response times
        response_rate = len(device_info.response_times) / device_info.response_count
        avg_response_time = sum(device_info.response_times) / max(
            1, len(device_info.response_times)
        )

        # Factor in how recent the device was seen
        time_since_seen = time.time() - device_info.last_seen
        recency_factor = max(0, 1 - (time_since_seen / 3600))  # Decay over 1 hour

        # Combine factors
        reliability = (
            (response_rate * 0.4)
            + (min(1, 5 / max(0.1, avg_response_time)) * 0.3)
            + (recency_factor * 0.3)
        )
        return min(1.0, reliability)

    # Additional helper methods for the wizard functionality

    async def _suggest_device_names(self, device_info: DeviceInfo) -> list[str]:
        """Suggest multiple device name options."""
        suggestions = []
        base_name = await self._suggest_device_name(device_info)
        suggestions.append(base_name)

        if device_info.device_type:
            type_name = device_info.device_type.replace("_", " ").title()
            suggestions.extend(
                [
                    f"{type_name}",
                    f"Main {type_name}",
                    f"Primary {type_name}",
                    f"{type_name} {device_info.source_address:02X}",
                ]
            )

        return list(set(suggestions))  # Remove duplicates

    async def _suggest_device_areas(self, device_info: DeviceInfo) -> list[str]:
        """Suggest multiple area options."""
        return [
            "living_room",
            "bedroom",
            "kitchen",
            "bathroom",
            "utility",
            "entry",
            "exterior",
            "climate",
        ]

    async def _get_device_type_options(self, device_type: str) -> dict[str, Any]:
        """Get device-type specific configuration options."""
        options = {}

        if "light" in device_type.lower():
            options["brightness_control"] = {
                "enabled": True,
                "min_brightness": 0,
                "max_brightness": 100,
                "step": 10,
            }
        elif "tank" in device_type.lower():
            options["level_monitoring"] = {
                "enabled": True,
                "units": "percentage",
                "warning_threshold": 20,
                "critical_threshold": 10,
            }

        return options

    async def _validate_device_setup(
        self,
        device_info: DeviceInfo,
        device_type: str,
        capabilities: list[str],
        configuration: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate device setup configuration."""
        validation = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "recommendations": [],
        }

        # Basic validation
        if not device_type or device_type == "unknown":
            validation["errors"].append("Device type must be specified")
            validation["valid"] = False

        # Check if device is still responding
        if time.time() - device_info.last_seen > 600:
            validation["warnings"].append("Device hasn't responded recently - verify connectivity")

        # Validate capabilities
        inferred_caps = await self._infer_device_capabilities(device_info)
        for cap in capabilities:
            if cap not in inferred_caps and cap not in device_info.capabilities:
                validation["warnings"].append(f"Capability '{cap}' not detected on device")

        return validation

    async def _generate_setup_next_steps(
        self, device_info: DeviceInfo, setup_result: dict[str, Any]
    ) -> list[str]:
        """Generate next steps after device setup."""
        steps = []

        if setup_result["setup_status"] == "success":
            steps.extend(
                [
                    "Test device functionality using the entity controls",
                    "Verify device responds to commands correctly",
                    "Consider adding device to appropriate groups",
                    "Set up any automation or scheduling if needed",
                ]
            )

            # Add device-specific steps
            device_type = setup_result["device_type"]
            if "light" in device_type.lower():
                steps.append("Test brightness control and on/off functionality")
            elif "tank" in device_type.lower():
                steps.append("Monitor tank levels and verify reading accuracy")

        return steps

    async def _generate_discovery_recommendations(
        self, all_discovered: dict[str, dict]
    ) -> list[dict[str, Any]]:
        """Generate recommendations from discovery results."""
        recommendations = []

        for protocol, devices in all_discovered.items():
            for addr, device in devices.items():
                rec = {
                    "device_address": addr,
                    "protocol": protocol,
                    "priority": "medium",
                    "action": "setup_required",
                    "message": f"Configure {device.device_type or 'unknown device'} at address {addr:02X}",
                    "estimated_time": "2-5 minutes",
                }

                # Adjust priority based on device type
                if device.device_type in ["light", "lock", "hvac"]:
                    rec["priority"] = "high"
                elif device.device_type in ["tank", "temperature"]:
                    rec["priority"] = "medium"

                recommendations.append(rec)

        return recommendations

    async def _build_network_topology(self, all_discovered: dict[str, dict]) -> dict[str, Any]:
        """Build network topology from discovery results."""
        topology = {
            "protocols": list(all_discovered.keys()),
            "device_count_by_protocol": {
                protocol: len(devices) for protocol, devices in all_discovered.items()
            },
            "total_devices": sum(len(devices) for devices in all_discovered.values()),
            "network_segments": [],
            "device_density": {},
        }

        # Simple network segmentation based on address ranges
        for protocol, devices in all_discovered.items():
            if devices:
                addresses = list(devices.keys())
                topology["network_segments"].append(
                    {
                        "protocol": protocol,
                        "address_range": {"min": min(addresses), "max": max(addresses)},
                        "device_count": len(addresses),
                    }
                )

        return topology

    async def _save_discovery_results(self, discovery_results: dict[str, Any]) -> None:
        """Save discovery results for future reference."""
        # This would persist discovery results
        # For now, just log the save operation
        logger.info(f"Saving discovery results for scan {discovery_results['scan_id']}")

    async def _generate_device_recommendation(self, device: DeviceInfo) -> dict[str, Any]:
        """Generate setup recommendation for a single device."""
        return {
            "device_address": device.source_address,
            "protocol": device.protocol,
            "current_status": device.status,
            "device_type": device.device_type or "unknown",
            "recommended_name": await self._suggest_device_name(device),
            "recommended_area": await self._suggest_device_area(device),
            "priority": "high" if device.device_type in ["light", "lock"] else "medium",
            "setup_complexity": "simple",
            "estimated_time_minutes": 3,
        }

    async def _generate_priority_actions(self, devices: list[DeviceInfo]) -> list[dict[str, Any]]:
        """Generate priority actions for device setup."""
        actions = []

        # Group by device type for efficient setup
        type_groups = defaultdict(list)
        for device in devices:
            device_type = device.device_type or "unknown"
            type_groups[device_type].append(device)

        for device_type, device_list in type_groups.items():
            if len(device_list) > 1:
                actions.append(
                    {
                        "action": "bulk_setup",
                        "device_type": device_type,
                        "device_count": len(device_list),
                        "message": f"Set up {len(device_list)} {device_type} devices together",
                        "priority": "high",
                        "time_saved": "50%",
                    }
                )

        return actions

    async def _suggest_device_groupings(self, devices: list[DeviceInfo]) -> list[dict[str, Any]]:
        """Suggest device groupings for organization."""
        groupings = []

        # Group by type
        type_groups = defaultdict(list)
        for device in devices:
            device_type = device.device_type or "unknown"
            type_groups[device_type].append(device.source_address)

        for device_type, addresses in type_groups.items():
            if len(addresses) > 1:
                groupings.append(
                    {
                        "group_type": "device_type",
                        "group_name": f"All {device_type.title()} Devices",
                        "device_addresses": addresses,
                        "suggested_operations": (
                            ["all_on", "all_off"] if device_type == "light" else ["status_check"]
                        ),
                    }
                )

        return groupings

    async def _suggest_area_assignments(self, devices: list[DeviceInfo]) -> dict[str, list[int]]:
        """Suggest area assignments for devices."""
        area_assignments = defaultdict(list)

        for device in devices:
            suggested_area = await self._suggest_device_area(device)
            area_assignments[suggested_area].append(device.source_address)

        return dict(area_assignments)

    async def _calculate_network_health(self, devices: list[DeviceInfo]) -> dict[str, Any]:
        """Calculate overall network health metrics."""
        if not devices:
            return {"score": 0.0, "status": "no_devices"}

        total_devices = len(devices)
        online_devices = sum(1 for d in devices if d.status in ["online", "discovered"])
        responsive_devices = sum(1 for d in devices if d.response_count > 0)

        health_score = (online_devices / total_devices) * 0.6 + (
            responsive_devices / total_devices
        ) * 0.4

        return {
            "score": round(health_score, 2),
            "status": (
                "healthy" if health_score > 0.8 else "degraded" if health_score > 0.5 else "poor"
            ),
            "online_percentage": round((online_devices / total_devices) * 100, 1),
            "responsive_percentage": round((responsive_devices / total_devices) * 100, 1),
        }

    async def _calculate_topology_metrics(self, devices: list[DeviceInfo]) -> dict[str, Any]:
        """Calculate topology-specific metrics."""
        if not devices:
            return {}

        protocols = {d.protocol for d in devices}
        device_types = {d.device_type for d in devices if d.device_type}

        return {
            "protocol_diversity": len(protocols),
            "device_type_diversity": len(device_types),
            "average_response_count": sum(d.response_count for d in devices) / len(devices),
            "newest_device_age": min(time.time() - d.first_seen for d in devices),
            "oldest_device_age": max(time.time() - d.first_seen for d in devices),
        }

    async def _detect_device_relationships(self, devices: list[DeviceInfo]) -> list[dict[str, Any]]:
        """Detect relationships between devices."""
        relationships = []

        # Simple relationship detection based on device types and addresses
        device_by_type = defaultdict(list)
        for device in devices:
            if device.device_type:
                device_by_type[device.device_type].append(device)

        # Detect groups of similar devices
        for device_type, device_list in device_by_type.items():
            if len(device_list) > 1:
                addresses = [d.source_address for d in device_list]
                relationships.append(
                    {
                        "relationship_type": "device_group",
                        "device_type": device_type,
                        "devices": addresses,
                        "strength": "high",
                        "description": f"Group of {len(device_list)} {device_type} devices",
                    }
                )

        return relationships

    async def get_network_topology(self) -> dict[str, Any]:
        """
        Get the current network topology information.

        Returns:
            Dictionary containing network topology data
        """
        # Calculate network health metrics
        total_devices = len(self.topology.devices)
        online_devices = sum(
            1 for device in self.topology.devices.values() if device.status == "online"
        )

        health_score = (online_devices / total_devices) if total_devices > 0 else 1.0

        # Group devices by protocol
        protocol_groups = defaultdict(list)
        for device in self.topology.devices.values():
            protocol_groups[device.protocol].append(
                {
                    "source_address": device.source_address,
                    "device_type": device.device_type,
                    "status": device.status,
                    "last_seen": device.last_seen,
                    "response_count": device.response_count,
                    "avg_response_time": (
                        sum(device.response_times) / len(device.response_times)
                        if device.response_times
                        else 0
                    ),
                }
            )

        return {
            "devices": dict(protocol_groups),
            "total_devices": total_devices,
            "online_devices": online_devices,
            "health_score": health_score,
            "last_discovery": self.topology.last_discovery,
            "active_polls": len(self.active_polls),
            "discovery_active": self.discovery_active,
        }

    async def get_device_availability(self) -> dict[str, Any]:
        """
        Get device availability statistics.

        Returns:
            Dictionary containing availability metrics
        """
        now = time.time()
        availability_threshold = 300  # 5 minutes

        stats = {
            "total_devices": len(self.topology.devices),
            "online_devices": 0,
            "offline_devices": 0,
            "recent_devices": 0,
            "protocols": defaultdict(int),
            "device_types": defaultdict(int),
        }

        for device in self.topology.devices.values():
            # Update device status based on last seen time
            if now - device.last_seen < availability_threshold:
                device.status = "online"
                stats["online_devices"] += 1
            else:
                device.status = "offline"
                stats["offline_devices"] += 1

            if now - device.last_seen < 60:  # Recent activity
                stats["recent_devices"] += 1

            stats["protocols"][device.protocol] += 1
            if device.device_type:
                stats["device_types"][device.device_type] += 1

        return dict(stats)

    async def _discovery_loop(self) -> None:
        """Background task for periodic device discovery."""
        while self.discovery_active:
            try:
                # Discover devices on enabled protocols
                if hasattr(self.config, "rvc") and getattr(self.config.rvc, "enabled", False):
                    await self.discover_devices("rvc")

                if hasattr(self.config, "j1939") and getattr(self.config.j1939, "enabled", False):
                    await self.discover_devices("j1939")

                # Wait for next discovery interval
                await asyncio.sleep(self.discovery_interval)

            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(10)  # Short delay on error

    async def _polling_loop(self) -> None:
        """Background task for periodic device polling."""
        while self.discovery_active:
            try:
                await self._poll_known_devices()
                await asyncio.sleep(self.polling_interval)

            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(5)  # Short delay on error

    async def _poll_known_devices(self) -> None:
        """Poll all known devices for status updates."""
        if not self.topology.devices:
            return

        # Poll devices that haven't been seen recently
        now = time.time()
        poll_threshold = self.polling_interval * 2

        for device in self.topology.devices.values():
            if now - device.last_seen > poll_threshold:
                # Determine appropriate PGN based on device type
                pgn = self._get_status_pgn_for_device(device)
                if pgn:
                    await self.poll_device(
                        source_address=device.source_address,
                        pgn=pgn,
                        protocol=device.protocol,
                    )

    def _get_status_pgn_for_device(self, device: DeviceInfo) -> int | None:
        """
        Get the appropriate status PGN for a device type.

        Args:
            device: Device information

        Returns:
            PGN to request for status, or None if unknown
        """
        device_type_pgns = {
            "light": 0x1FEDA,
            "tank": 0x1FEEB,
            "temperature": 0x1FEE1,
            "lock": 0x1FED9,
            "pump": 0x1FED8,
            "fan": 0x1FED6,
        }

        return device_type_pgns.get(device.device_type)

    async def _send_pgn_request(
        self,
        pgn: int,
        protocol: str,
        destination: int = 0xFF,
        instance: int | None = None,
    ) -> bool:
        """
        Send a PGN Request message (0xEA00) to discover or poll devices.

        Args:
            pgn: PGN to request
            protocol: Protocol to use
            destination: Destination address (0xFF for broadcast)
            instance: Instance number if applicable

        Returns:
            True if request was sent successfully
        """
        try:
            # Get source address from configuration
            source_address = 0xE0  # Default CoachIQ source address

            # Build CAN arbitration ID for PGN Request (0xEA00)
            request_pgn = 0xEA00
            priority = 6  # Standard priority for requests

            # CAN ID format: Priority(3) + Reserved(1) + Data Page(1) + PGN(16) + Source(8)
            can_id = (priority << 26) | (request_pgn << 8) | source_address

            # Build data payload with requested PGN
            data = [
                pgn & 0xFF,  # PGN LSB
                (pgn >> 8) & 0xFF,  # PGN middle byte
                (pgn >> 16) & 0xFF,  # PGN MSB
                destination,  # Destination address
                0xFF,
                0xFF,
                0xFF,
                0xFF,  # Padding
            ]

            # If instance is specified, include it in the request
            if instance is not None:
                data[4] = instance & 0xFF

            # Create CAN message
            message = can.Message(arbitration_id=can_id, data=data, is_extended_id=True)

            # Send via CAN queue
            await can_tx_queue.put(message)

            logger.debug(
                f"Sent PGN request: PGN={pgn:04X}, Dest={destination:02X}, "
                f"Protocol={protocol}, Instance={instance}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to send PGN request: {e}")
            return False

    def process_can_message(self, message: can.Message) -> None:
        """
        Process incoming CAN messages for device discovery.

        This method should be called by the CAN message handler
        to track device responses and update topology.

        Args:
            message: Received CAN message
        """
        try:
            # Extract source address and PGN from CAN ID
            source_address = message.arbitration_id & 0xFF
            pgn = (message.arbitration_id >> 8) & 0xFFFF

            # Skip messages from our own source address
            if source_address == 0xE0:
                return

            # Check if this is a response to one of our polls
            self._process_poll_response(message, source_address, pgn)

            # Update device information
            self._update_device_info(message, source_address, pgn)

        except Exception as e:
            logger.error(f"Error processing CAN message for discovery: {e}")

    def _process_poll_response(self, message: can.Message, source_address: int, pgn: int) -> None:
        """Process response to a poll request."""
        now = time.time()

        # Find matching poll request
        for poll_key, poll_request in list(self.active_polls.items()):
            if poll_request.target_address == source_address and poll_request.target_pgn == pgn:
                # Calculate response time
                response_time = now - poll_request.last_sent

                # Update device response times
                if source_address in self.topology.devices:
                    device = self.topology.devices[source_address]
                    device.response_times.append(response_time)
                    # Keep only recent response times
                    if len(device.response_times) > 10:
                        device.response_times = device.response_times[-10:]
                    device.response_count += 1

                # Remove completed poll
                del self.active_polls[poll_key]

                logger.debug(
                    f"Poll response received from {source_address:02X} "
                    f"for PGN {pgn:04X} in {response_time:.3f}s"
                )
                break

    def _detect_protocol_from_pgn(self, pgn: int) -> str | None:
        """Detect protocol based on PGN.

        Args:
            pgn: Parameter Group Number

        Returns:
            Protocol name ('rvc', 'j1939') or None if unknown
        """
        for protocol, info in self.protocol_pgn_ranges.items():
            # Check characteristic PGNs first (faster)
            if pgn in info["characteristic_pgns"]:
                return protocol

            # Check PGN ranges
            for start, end in info["pgn_ranges"]:
                if start <= pgn <= end:
                    # Additional check to avoid false positives on shared PGNs
                    if pgn == 0xEA00:  # Address claimed - used by both
                        continue
                    return protocol

        return None

    def _update_device_info(self, message: can.Message, source_address: int, pgn: int) -> None:
        """Update device information based on received message."""
        now = time.time()

        # Detect protocol from PGN
        detected_protocol = self._detect_protocol_from_pgn(pgn)

        # Track detected protocols per interface (assuming can0 for now)
        # TODO: Get actual interface name from message metadata
        if detected_protocol:
            self.detected_protocols["can0"].add(detected_protocol)

        # Get or create device info
        if source_address not in self.topology.devices:
            # Use detected protocol or default to 'unknown'
            protocol = detected_protocol or "unknown"
            self.topology.devices[source_address] = DeviceInfo(
                source_address=source_address,
                protocol=protocol,
                first_seen=now,
            )
        else:
            # Update protocol if we have better detection
            device = self.topology.devices[source_address]
            if device.protocol == "unknown" and detected_protocol:
                device.protocol = detected_protocol

        device = self.topology.devices[source_address]
        device.last_seen = now
        device.status = "online"

        # Update device type based on PGN
        if pgn == 0x1FEDA:  # DC Load Status
            device.device_type = "light"
        elif pgn == 0x1FEEB:  # Tank Status
            device.device_type = "tank"
        elif pgn == 0x1FEE1:  # Temperature Status
            device.device_type = "temperature"
        elif pgn == 0x1FED9:  # Lock Status
            device.device_type = "lock"

        # Process Product Identification (0x1FEF2) for device details
        if pgn == 0x1FEF2 and len(message.data) >= 8:
            try:
                # This is typically a multi-packet BAM message
                # For now, just mark that we have product info
                device.capabilities.add("product_identification")
            except Exception as e:
                logger.debug(f"Error processing product identification: {e}")

    async def health_check(self) -> dict[str, Any]:
        """
        Check the health status of the device discovery service.

        Returns:
            Dictionary containing health status information
        """
        try:
            # Check CAN facade availability
            can_available = self.can_facade is not None

            # Count discovered devices
            device_count = len(self.topology.devices)

            # Calculate uptime
            uptime = time.time() - self.start_time if hasattr(self, "start_time") else 0

            # Group devices by protocol
            devices_by_protocol = defaultdict(list)
            for device in self.topology.devices.values():
                devices_by_protocol[device.protocol].append(device)

            # Build protocol details
            protocol_details = {}
            for protocol in self.enabled_protocols:
                device_list = devices_by_protocol.get(protocol, [])
                # Check if protocol has been detected on any interface
                detected_on_interfaces = [
                    iface for iface, protos in self.detected_protocols.items() if protocol in protos
                ]

                protocol_details[protocol] = {
                    "status": "active" if device_list else "configured",
                    "device_count": len(device_list),
                    "detected_on_interfaces": detected_on_interfaces,
                }

            # Include any unexpected protocols found
            for protocol in devices_by_protocol:
                if protocol not in self.enabled_protocols and protocol != "unknown":
                    protocol_details[protocol] = {
                        "status": "detected_unexpected",
                        "device_count": len(devices_by_protocol[protocol]),
                        "detected_on_interfaces": [
                            iface
                            for iface, protos in self.detected_protocols.items()
                            if protocol in protos
                        ],
                    }

            return {
                "status": "healthy",
                "can_interface_available": can_available,
                "discovered_devices": device_count,
                "enabled_protocols": self.enabled_protocols,
                "protocol_details": protocol_details,
                "uptime_seconds": int(uptime),
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e), "timestamp": time.time()}
