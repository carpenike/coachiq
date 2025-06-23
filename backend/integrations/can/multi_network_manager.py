"""
Multi-Network CAN Manager for CoachIQ

This module provides comprehensive multi-network CAN bus management with:
- Network isolation and fault containment
- Protocol-specific routing and filtering
- Health monitoring and automatic recovery
- Security policies for cross-network communication
- Performance optimization with priority scheduling

Architecture based on industry research for RV multi-network environments
supporting segmented CAN buses (house/RV-C vs chassis/J1939).
"""

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import can
import can.interface
from can.exceptions import CanInterfaceNotImplementedError

from backend.core.config import get_can_settings, get_multi_network_settings

logger = logging.getLogger(__name__)


class NetworkStatus(Enum):
    """Network operational status."""

    INITIALIZING = "initializing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAULTED = "faulted"
    ISOLATED = "isolated"
    SHUTDOWN = "shutdown"


class NetworkPriority(Enum):
    """Network priority levels for resource allocation."""

    CRITICAL = "critical"  # Safety-critical systems (chassis, brakes)
    HIGH = "high"  # Essential systems (engine, transmission)
    NORMAL = "normal"  # Coach amenities (lighting, HVAC)
    LOW = "low"  # Non-essential systems (entertainment)
    BACKGROUND = "background"  # Diagnostics, logging


class ProtocolType(Enum):
    """Supported CAN protocol types."""

    RVC = "rvc"
    J1939 = "j1939"
    CUSTOM = "custom"


@dataclass
class NetworkHealth:
    """Network health monitoring data."""

    status: NetworkStatus = NetworkStatus.INITIALIZING
    last_message_time: float = 0.0
    message_count: int = 0
    error_count: int = 0
    bus_off_count: int = 0
    last_error: str | None = None
    uptime: float = 0.0


@dataclass
class NetworkNode:
    """Individual CAN network representation."""

    network_id: str
    interface: str
    protocol: ProtocolType
    priority: NetworkPriority
    isolation_enabled: bool = True
    description: str = ""

    # Runtime state
    bus: Any = None
    health: NetworkHealth = field(default_factory=NetworkHealth)
    start_time: float = field(default_factory=time.time)
    last_health_check: float = 0.0

    # Message filtering and routing
    message_filters: list[dict] = field(default_factory=list)
    cross_network_allowed: bool = False

    def __post_init__(self):
        """Initialize computed fields."""
        if not self.description:
            self.description = f"{self.protocol.value.upper()} network on {self.interface}"

    @property
    def is_healthy(self) -> bool:
        """Check if network is in healthy state."""
        return self.health.status == NetworkStatus.HEALTHY

    @property
    def is_operational(self) -> bool:
        """Check if network can handle messages."""
        return self.health.status in [NetworkStatus.HEALTHY, NetworkStatus.DEGRADED]

    @property
    def uptime_seconds(self) -> float:
        """Get network uptime in seconds."""
        return time.time() - self.start_time

    def shutdown_bus(self) -> None:
        """Gracefully shutdown the CAN bus with multiple fallback methods."""
        if not self.bus:
            return

        # Try shutdown methods in order of preference
        shutdown_methods = ["shutdown", "close", "stop"]

        for method_name in shutdown_methods:
            with contextlib.suppress(Exception):
                if hasattr(self.bus, method_name):
                    method = getattr(self.bus, method_name)
                    if callable(method):
                        method()
                        logger.debug(
                            f"Successfully shut down bus for network '{self.network_id}' using {method_name}"
                        )
                        self.bus = None
                        return

        logger.debug(f"No shutdown method found for bus in network '{self.network_id}'")


class NetworkRegistry:
    """Dynamic network registration and management."""

    def __init__(self):
        self.networks: dict[str, NetworkNode] = {}
        self.interface_mapping: dict[str, str] = {}  # logical -> network_id
        self._lock = asyncio.Lock()

    async def register_network(
        self,
        network_id: str,
        interface: str,
        protocol: ProtocolType,
        priority: NetworkPriority = NetworkPriority.NORMAL,
        isolation_enabled: bool = True,
        description: str = "",
    ) -> NetworkNode:
        """Register a new CAN network."""
        async with self._lock:
            if network_id in self.networks:
                msg = f"Network '{network_id}' already registered"
                raise ValueError(msg)

            # Check for interface conflicts
            for existing_network in self.networks.values():
                if existing_network.interface == interface:
                    logger.warning(
                        f"Interface '{interface}' already used by network "
                        f"'{existing_network.network_id}'"
                    )

            network = NetworkNode(
                network_id=network_id,
                interface=interface,
                protocol=protocol,
                priority=priority,
                isolation_enabled=isolation_enabled,
                description=description,
            )

            self.networks[network_id] = network
            self.interface_mapping[interface] = network_id

            logger.info(
                f"Registered network '{network_id}': {protocol.value} on {interface} "
                f"(priority: {priority.value}, isolation: {isolation_enabled})"
            )

            return network

    async def unregister_network(self, network_id: str) -> bool:
        """Unregister a CAN network."""
        async with self._lock:
            if network_id not in self.networks:
                return False

            network = self.networks[network_id]

            # Clean up bus connection
            network.shutdown_bus()

            # Remove from mappings
            if network.interface in self.interface_mapping:
                del self.interface_mapping[network.interface]

            del self.networks[network_id]

            logger.info(f"Unregistered network '{network_id}'")
            return True

    def get_network(self, network_id: str) -> NetworkNode | None:
        """Get network by ID."""
        return self.networks.get(network_id)

    def get_network_by_interface(self, interface: str) -> NetworkNode | None:
        """Get network by interface name."""
        network_id = self.interface_mapping.get(interface)
        if network_id:
            return self.networks.get(network_id)
        return None

    def get_networks_by_protocol(self, protocol: ProtocolType) -> list[NetworkNode]:
        """Get all networks using a specific protocol."""
        return [net for net in self.networks.values() if net.protocol == protocol]

    def get_healthy_networks(self) -> list[NetworkNode]:
        """Get all healthy networks."""
        return [net for net in self.networks.values() if net.is_healthy]

    def get_operational_networks(self) -> list[NetworkNode]:
        """Get all operational networks."""
        return [net for net in self.networks.values() if net.is_operational]

    def get_status_summary(self) -> dict[str, Any]:
        """Get comprehensive status summary."""
        total = len(self.networks)
        healthy = len(self.get_healthy_networks())
        operational = len(self.get_operational_networks())

        status_counts = {}
        for network in self.networks.values():
            status = network.health.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_networks": total,
            "healthy_networks": healthy,
            "operational_networks": operational,
            "status_distribution": status_counts,
            "interfaces": list(self.interface_mapping.keys()),
            "protocols": list({net.protocol.value for net in self.networks.values()}),
        }


class MultiNetworkManager:
    """
    Multi-Network CAN Manager

    Provides comprehensive management of multiple CAN network segments with:
    - Network isolation and fault containment
    - Protocol-specific message routing
    - Health monitoring and automatic recovery
    - Security policies for cross-network communication
    - Performance optimization with priority scheduling
    """

    def __init__(self):
        self.registry = NetworkRegistry()
        self.settings = get_multi_network_settings()
        self.can_settings = get_can_settings()

        # Health monitoring
        self._health_monitor_task: asyncio.Task | None = None
        self._monitoring_enabled = False

        # Message routing
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._router_task: asyncio.Task | None = None
        self._routing_enabled = False

        # Performance metrics
        self.metrics = {
            "messages_routed": 0,
            "messages_dropped": 0,
            "cross_network_messages": 0,
            "health_checks": 0,
            "fault_recoveries": 0,
        }

    async def startup(self) -> None:
        """Initialize the multi-network manager."""
        if not self.settings.enabled:
            logger.info("Multi-network manager disabled")
            return

        logger.info("Starting multi-network CAN manager...")

        # Register default networks from configuration
        await self._register_default_networks()

        # Start health monitoring
        if self.settings.enable_health_monitoring:
            await self._start_health_monitoring()

        # Start message routing
        if self.settings.enable_cross_network_routing:
            await self._start_message_routing()

        logger.info(f"Multi-network manager started with {len(self.registry.networks)} networks")

    async def shutdown(self) -> None:
        """Shutdown the multi-network manager."""
        logger.info("Shutting down multi-network CAN manager...")

        # Stop background tasks
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_monitor_task

        if self._router_task:
            self._router_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._router_task

        # Shutdown all networks
        for network_id in list(self.registry.networks.keys()):
            await self.registry.unregister_network(network_id)

        logger.info("Multi-network manager shutdown complete")

    async def _register_default_networks(self) -> None:
        """Register networks from configuration."""
        for network_id, config in self.settings.default_networks.items():
            try:
                protocol = ProtocolType(config.get("protocol", "rvc"))
                priority = NetworkPriority(config.get("priority", "normal"))

                await self.registry.register_network(
                    network_id=network_id,
                    interface=config["interface"],
                    protocol=protocol,
                    priority=priority,
                    isolation_enabled=config.get("isolation", True),
                    description=config.get("description", ""),
                )

                # Initialize CAN bus connection
                await self._initialize_network_bus(network_id)

            except Exception as e:
                logger.error(f"Failed to register network '{network_id}': {e}")

    async def _initialize_network_bus(self, network_id: str) -> bool:
        """Initialize CAN bus connection for a network."""
        network = self.registry.get_network(network_id)
        if not network:
            return False

        try:
            # Use existing CAN settings for bus configuration
            bus = can.interface.Bus(
                channel=network.interface,
                bustype=self.can_settings.bustype,
                bitrate=self.can_settings.bitrate,
            )

            network.bus = bus
            network.health.status = NetworkStatus.HEALTHY
            network.health.last_message_time = time.time()

            logger.info(f"Initialized CAN bus for network '{network_id}' on {network.interface}")
            return True

        except CanInterfaceNotImplementedError as e:
            logger.error(f"CAN interface '{network.interface}' not implemented: {e}")
            network.health.status = NetworkStatus.FAULTED
            network.health.last_error = str(e)
            return False

        except Exception as e:
            logger.error(f"Failed to initialize bus for network '{network_id}': {e}")
            network.health.status = NetworkStatus.FAULTED
            network.health.last_error = str(e)
            return False

    async def _start_health_monitoring(self) -> None:
        """Start background health monitoring."""
        if self._monitoring_enabled:
            return

        self._monitoring_enabled = True
        self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Health monitoring started")

    async def _health_monitor_loop(self) -> None:
        """Background health monitoring loop."""
        while self._monitoring_enabled:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.settings.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(1)

    async def _perform_health_checks(self) -> None:
        """Perform health checks on all networks."""
        current_time = time.time()

        for network in self.registry.networks.values():
            try:
                await self._check_network_health(network, current_time)
            except Exception as e:
                logger.error(f"Health check failed for network '{network.network_id}': {e}")

        self.metrics["health_checks"] += 1

    async def _check_network_health(self, network: NetworkNode, current_time: float) -> None:
        """Check health of a specific network."""
        network.last_health_check = current_time
        network.health.uptime = current_time - network.start_time

        # Check bus connection
        if not network.bus:
            if network.health.status != NetworkStatus.FAULTED:
                logger.warning(f"Network '{network.network_id}' has no bus connection")
                network.health.status = NetworkStatus.FAULTED

                # Attempt recovery if fault isolation is enabled
                if self.settings.enable_fault_isolation:
                    await self._attempt_network_recovery(network)
            return

        # Check for message timeouts (basic liveness check)
        time_since_last_message = current_time - network.health.last_message_time
        if (
            time_since_last_message > 30 and network.health.status == NetworkStatus.HEALTHY
        ):  # 30 seconds timeout
            logger.warning(
                f"Network '{network.network_id}' has not received messages for "
                f"{time_since_last_message:.1f}s"
            )
            network.health.status = NetworkStatus.DEGRADED

        # Check error rates
        if (
            network.health.error_count > 100 and network.health.status == NetworkStatus.HEALTHY
        ):  # Threshold for degraded status
            logger.warning(
                f"Network '{network.network_id}' has high error count: {network.health.error_count}"
            )
            network.health.status = NetworkStatus.DEGRADED

    async def _attempt_network_recovery(self, network: NetworkNode) -> bool:
        """Attempt to recover a faulted network."""
        logger.info(f"Attempting recovery for network '{network.network_id}'")

        # Close existing bus if any
        network.shutdown_bus()

        # Wait before retry
        await asyncio.sleep(1)

        # Attempt to reinitialize
        if await self._initialize_network_bus(network.network_id):
            logger.info(f"Successfully recovered network '{network.network_id}'")
            self.metrics["fault_recoveries"] += 1
            return True

        logger.warning(f"Failed to recover network '{network.network_id}'")
        return False

    async def _start_message_routing(self) -> None:
        """Start background message routing."""
        if self._routing_enabled:
            return

        self._routing_enabled = True
        self._router_task = asyncio.create_task(self._message_router_loop())
        logger.info("Message routing started")

    async def _message_router_loop(self) -> None:
        """Background message routing loop."""
        while self._routing_enabled:
            try:
                # Get message from queue with timeout
                try:
                    message_data = await asyncio.wait_for(
                        self._message_queue.get(),
                        timeout=self.settings.message_routing_timeout,
                    )
                    await self._route_message(message_data)
                except TimeoutError:
                    continue

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Message routing error: {e}")

    async def _route_message(self, message_data: dict) -> None:
        """Route a message between networks."""
        # Message routing implementation would go here
        # This is a placeholder for cross-network message routing logic
        self.metrics["messages_routed"] += 1

    # Public API methods

    async def register_network(
        self,
        network_id: str,
        interface: str,
        protocol: str,
        priority: str = "normal",
        isolation_enabled: bool = True,
        description: str = "",
    ) -> bool:
        """Register a new CAN network."""
        try:
            protocol_enum = ProtocolType(protocol.lower())
            priority_enum = NetworkPriority(priority.lower())

            await self.registry.register_network(
                network_id=network_id,
                interface=interface,
                protocol=protocol_enum,
                priority=priority_enum,
                isolation_enabled=isolation_enabled,
                description=description,
            )

            # Initialize bus connection
            return await self._initialize_network_bus(network_id)

        except ValueError as e:
            logger.error(f"Invalid protocol or priority value: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to register network '{network_id}': {e}")
            return False

    async def unregister_network(self, network_id: str) -> bool:
        """Unregister a CAN network."""
        return await self.registry.unregister_network(network_id)

    def get_network_status(self, network_id: str) -> dict[str, Any] | None:
        """Get status of a specific network."""
        network = self.registry.get_network(network_id)
        if not network:
            return None

        return {
            "network_id": network.network_id,
            "interface": network.interface,
            "protocol": network.protocol.value,
            "priority": network.priority.value,
            "status": network.health.status.value,
            "uptime": network.uptime_seconds,
            "message_count": network.health.message_count,
            "error_count": network.health.error_count,
            "last_message_time": network.health.last_message_time,
            "last_error": network.health.last_error,
            "isolation_enabled": network.isolation_enabled,
            "description": network.description,
        }

    def get_all_networks_status(self) -> dict[str, Any]:
        """Get status of all networks."""
        networks = {}
        for network_id in self.registry.networks:
            networks[network_id] = self.get_network_status(network_id)

        return {
            "networks": networks,
            "summary": self.registry.get_status_summary(),
            "metrics": self.metrics.copy(),
            "settings": {
                "enabled": self.settings.enabled,
                "health_monitoring": self.settings.enable_health_monitoring,
                "fault_isolation": self.settings.enable_fault_isolation,
                "cross_network_routing": self.settings.enable_cross_network_routing,
                "max_networks": self.settings.max_networks,
            },
        }

    def get_network_by_interface(self, interface: str) -> str | None:
        """Get network ID by interface name."""
        network = self.registry.get_network_by_interface(interface)
        return network.network_id if network else None

    async def isolate_network(self, network_id: str, reason: str = "") -> bool:
        """Manually isolate a network."""
        network = self.registry.get_network(network_id)
        if not network:
            return False

        logger.warning(f"Isolating network '{network_id}': {reason}")
        network.health.status = NetworkStatus.ISOLATED
        network.health.last_error = f"Manual isolation: {reason}"

        # Close bus connection
        network.shutdown_bus()

        return True

    async def recover_network(self, network_id: str) -> bool:
        """Manually attempt network recovery."""
        network = self.registry.get_network(network_id)
        if not network:
            return False

        return await self._attempt_network_recovery(network)


# Global instance for application use
_multi_network_manager: MultiNetworkManager | None = None


def get_multi_network_manager() -> MultiNetworkManager:
    """
    Get the multi-network manager instance.

    This function follows the enhanced singleton pattern that checks modern
    locations (app.state, ServiceRegistry) before falling back to the global
    instance for backward compatibility.

    NOTE: This global singleton pattern is deprecated. New code should register
    MultiNetworkManager with ServiceRegistry for proper lifecycle management.

    Returns:
        MultiNetworkManager: The multi-network manager instance
    """
    # Try to get from ServiceRegistry first (modern pattern)
    try:
        from backend.core.dependencies import get_service_registry

        service_registry = get_service_registry()
        if service_registry.has_service("multi_network_manager"):
            service = service_registry.get_service("multi_network_manager")
            if isinstance(service, MultiNetworkManager):
                return service
    except Exception:
        # ServiceRegistry not available yet
        pass

    # Fall back to global singleton for backward compatibility
    global _multi_network_manager
    if _multi_network_manager is None:
        logger.warning(
            "MultiNetworkManager accessed via global singleton (deprecated). "
            "Consider registering with ServiceRegistry for proper lifecycle management."
        )
        _multi_network_manager = MultiNetworkManager()
    return _multi_network_manager
