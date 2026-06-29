"""
Protocol Manager Service

Manages protocol enablement and status across the application.
Provides a clean abstraction over protocol configuration and runtime status.
"""

import logging
from enum import Enum
from typing import Dict, List, Optional

from backend.core.config import get_settings
from backend.core.service_registry import ServiceStatus

logger = logging.getLogger(__name__)


class ProtocolStatus(str, Enum):
    """Status of a protocol in the system."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class ProtocolInfo:
    """Information about a protocol."""

    def __init__(
        self,
        name: str,
        enabled: bool,
        service_name: str | None = None,
        always_enabled: bool = False,
        description: str = "",
    ):
        """
        Initialize protocol information.

        Args:
            name: Protocol name (e.g., "rvc", "j1939", "firefly")
            enabled: Whether the protocol is enabled in configuration
            service_name: Name of the service in ServiceRegistry
            always_enabled: Whether this protocol is always enabled
            description: Human-readable description
        """
        self.name = name
        self.enabled = enabled
        self.service_name = service_name or f"{name}_service"
        self.always_enabled = always_enabled
        self.description = description
        self.status = ProtocolStatus.UNKNOWN


class ProtocolManager:
    """
    Manages protocol enablement and status.

    This service bridges between static configuration (environment variables,
    YAML files) and runtime service status from ServiceRegistry.
    """

    def __init__(self):
        """Initialize the protocol manager."""
        self.protocols: dict[str, ProtocolInfo] = {}
        self._initialized = False
        self._initialize_protocols()

    def _initialize_protocols(self) -> None:
        """Initialize protocol configuration from settings."""
        settings = get_settings()

        # RVC is always enabled in the modern architecture
        self.protocols["rvc"] = ProtocolInfo(
            name="rvc",
            enabled=True,
            always_enabled=True,
            description="RV-C protocol for RV systems communication",
        )

        # J1939 protocol (engine/transmission systems)
        # Check environment variable first, then default to False
        j1939_enabled = getattr(settings, "j1939_enabled", False)
        self.protocols["j1939"] = ProtocolInfo(
            name="j1939",
            enabled=j1939_enabled,
            description="J1939 protocol for engine and transmission systems",
        )

        # Firefly protocol (proprietary RV systems)
        # Check environment variable first, then default to False
        firefly_enabled = getattr(settings, "firefly_enabled", False)
        self.protocols["firefly"] = ProtocolInfo(
            name="firefly", enabled=firefly_enabled, description="Firefly RV systems integration"
        )

        logger.info(
            f"Protocol manager initialized with protocols: "
            f"{', '.join(p for p, info in self.protocols.items() if info.enabled)}"
        )

    def get_enabled_protocols(self, service_registry=None) -> list[str]:
        """
        Get list of enabled protocols based on configuration and service health.

        Args:
            service_registry: Optional ServiceRegistry instance. If not provided,
                            only configuration-based status is returned.

        Returns:
            List of enabled protocol names
        """
        enabled = []

        for name, protocol in self.protocols.items():
            # Always-enabled protocols
            if protocol.always_enabled:
                enabled.append(name)
                continue

            # Check if protocol is enabled in configuration
            if not protocol.enabled:
                continue

            # If we have a service registry, check runtime health
            if service_registry:
                if service_registry.has_service(protocol.service_name):
                    status = service_registry.get_service_status(protocol.service_name)
                    if status == ServiceStatus.HEALTHY:
                        enabled.append(name)
                    else:
                        logger.debug(f"Protocol {name} enabled but service unhealthy: {status}")
                else:
                    # Protocol is enabled but service not registered yet
                    # This is expected during migration
                    logger.debug(
                        f"Protocol {name} enabled but service {protocol.service_name} "
                        "not registered"
                    )
            else:
                # No service registry, just return configuration-based status
                enabled.append(name)

        return enabled

    def get_protocol_status(self, protocol: str, service_registry=None) -> ProtocolStatus:
        """
        Get detailed status of a specific protocol.

        Args:
            protocol: Protocol name
            service_registry: Optional ServiceRegistry instance

        Returns:
            ProtocolStatus enum value
        """
        if protocol not in self.protocols:
            return ProtocolStatus.UNKNOWN

        info = self.protocols[protocol]

        # Check if disabled in configuration
        if not info.enabled:
            return ProtocolStatus.DISABLED

        # Always-enabled protocols
        if info.always_enabled:
            return ProtocolStatus.ENABLED

        # Need service registry to check runtime status
        if not service_registry:
            # Can only report configuration status
            return ProtocolStatus.ENABLED if info.enabled else ProtocolStatus.DISABLED

        # Check service status
        if not service_registry.has_service(info.service_name):
            # Enabled but service not available
            return ProtocolStatus.DEGRADED

        service_status = service_registry.get_service_status(info.service_name)
        if service_status == ServiceStatus.HEALTHY:
            return ProtocolStatus.ENABLED
        if service_status in (ServiceStatus.DEGRADED, ServiceStatus.FAILED):
            return ProtocolStatus.DEGRADED
        return ProtocolStatus.UNKNOWN

    def get_protocol_info(self, protocol: str) -> ProtocolInfo | None:
        """Get information about a specific protocol."""
        return self.protocols.get(protocol)

    def list_protocols(self) -> list[str]:
        """List all known protocols."""
        return list(self.protocols.keys())

    def is_protocol_enabled(self, protocol: str, service_registry=None) -> bool:
        """
        Check if a specific protocol is enabled and healthy.

        Args:
            protocol: Protocol name to check
            service_registry: Optional ServiceRegistry for runtime checks

        Returns:
            True if protocol is enabled and healthy
        """
        return protocol in self.get_enabled_protocols(service_registry)

    async def start(self) -> None:
        """Start the protocol manager service."""
        self._initialized = True
        logger.info("Protocol manager service started")

    async def stop(self) -> None:
        """Stop the protocol manager service."""
        self._initialized = False
        logger.info("Protocol manager service stopped")

    def get_health_status(self) -> dict:
        """Get health status for the protocol manager."""
        return {
            "healthy": self._initialized,
            "initialized": self._initialized,
            "protocol_count": len(self.protocols),
            "enabled_protocols": [name for name, info in self.protocols.items() if info.enabled],
        }
