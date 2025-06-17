"""
CAN Service Migration Adapter

This adapter allows gradual migration from CANService (using AppState)
to CANServiceV2 (using repositories directly). It provides the same
interface as CANService but delegates to CANServiceV2 when available.

Part of Phase 2R.3: Progressive migration pattern.
"""

import logging
from typing import Any, Optional

from backend.services.can_service import CANService
from backend.services.can_service_v2 import CANServiceV2
from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class CANServiceMigrationAdapter(CANService):
    """
    Migration adapter that allows gradual transition to repository-based CANServiceV2.

    This adapter checks a feature flag and either uses the new repository-based
    implementation or falls back to the legacy AppState-based implementation.
    """

    def __init__(self, app_state=None):
        """Initialize the adapter with either V2 or legacy service."""
        super().__init__(app_state)

        # Check if we should use V2
        settings = get_settings()
        self._use_v2 = getattr(settings, "USE_CAN_SERVICE_V2", False)
        self._v2_service: Optional[CANServiceV2] = None

        if self._use_v2:
            logger.info("CANServiceMigrationAdapter: Using CANServiceV2 (repository pattern)")
        else:
            logger.info("CANServiceMigrationAdapter: Using legacy CANService (AppState pattern)")

    def set_v2_service(self, v2_service: CANServiceV2) -> None:
        """
        Set the V2 service instance for delegation.

        Args:
            v2_service: The CANServiceV2 instance to use
        """
        self._v2_service = v2_service
        logger.info("CANServiceV2 instance set for migration adapter")

    async def get_queue_status(self) -> dict[str, Any]:
        """Get the current status of the CAN transmission queue."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_queue_status()
        return await super().get_queue_status()

    async def get_interfaces(self) -> list[str]:
        """Get a list of active CAN interfaces."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_interfaces()
        return await super().get_interfaces()

    async def get_interface_details(self) -> dict[str, dict[str, Any]]:
        """Get detailed information about all CAN interfaces."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_interface_details()
        return await super().get_interface_details()

    async def send_raw_message(
        self, arbitration_id: int, data: bytes, interface: str
    ) -> dict[str, Any]:
        """Send a raw CAN message to the specified interface."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.send_raw_message(arbitration_id, data, interface)
        return await super().send_raw_message(arbitration_id, data, interface)

    async def get_bus_statistics(self) -> dict[str, Any]:
        """Get comprehensive statistics about CAN bus operations."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_bus_statistics()
        return await super().get_bus_statistics()

    async def send_message(
        self, arbitration_id: int, data: bytes, interface: str
    ) -> dict[str, Any]:
        """Send a CAN message (alias for send_raw_message for compatibility)."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.send_message(arbitration_id, data, interface)
        return await super().send_message(arbitration_id, data, interface)

    async def get_recent_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent CAN messages captured on the bus."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_recent_messages(limit)
        return await super().get_recent_messages(limit)

    async def initialize_can_interfaces(
        self, interfaces: list[str] | None = None
    ) -> dict[str, Any]:
        """Initialize CAN interfaces."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.initialize_can_interfaces(interfaces)
        return await super().initialize_can_interfaces(interfaces)

    async def startup(self) -> dict[str, Any]:
        """Initialize CAN service during application startup."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.startup()
        return await super().startup()

    async def shutdown(self) -> None:
        """Shutdown the CAN service and clean up background tasks."""
        if self._use_v2 and self._v2_service:
            await self._v2_service.shutdown()
        else:
            await super().shutdown()

    async def start_can_writer(self) -> None:
        """Start the CAN writer task."""
        if self._use_v2 and self._v2_service:
            await self._v2_service.start_can_writer()
        else:
            await super().start_can_writer()


def create_can_service_with_migration(
    app_state: Any = None,
    service_registry: Any = None,
) -> CANService:
    """
    Factory function that creates CANService with migration adapter.

    This allows progressive migration to repository pattern based on
    configuration settings.

    Args:
        app_state: Optional app state (for legacy)
        service_registry: Optional service registry (for V2)

    Returns:
        CANService instance (may be migration adapter)
    """
    # Create the migration adapter
    adapter = CANServiceMigrationAdapter(app_state=app_state)

    # If V2 is enabled and we have service registry, set up V2
    settings = get_settings()
    if getattr(settings, "USE_CAN_SERVICE_V2", False) and service_registry:
        try:
            # Get repositories from service registry or app state
            can_tracking_repo = None
            rvc_config_repo = None

            # Try service registry first
            if service_registry.has_service("can_tracking_repository"):
                can_tracking_repo = service_registry.get_service("can_tracking_repository")
            elif app_state and hasattr(app_state, "_can_tracking_repo"):
                can_tracking_repo = app_state._can_tracking_repo

            if service_registry.has_service("rvc_config_repository"):
                rvc_config_repo = service_registry.get_service("rvc_config_repository")
            elif app_state and hasattr(app_state, "_rvc_config_repo"):
                rvc_config_repo = app_state._rvc_config_repo

            if can_tracking_repo and rvc_config_repo:
                from backend.services.can_service_v2 import CANServiceV2

                # Get controller source address
                controller_addr = 0xF9  # Default
                if app_state:
                    controller_addr = app_state.get_controller_source_addr()

                v2_service = CANServiceV2(
                    can_tracking_repository=can_tracking_repo,
                    rvc_config_repository=rvc_config_repo,
                    controller_source_addr=controller_addr,
                )

                adapter.set_v2_service(v2_service)
                logger.info("CANServiceV2 configured successfully in migration adapter")
            else:
                logger.warning("Repositories not available, falling back to legacy CANService")

        except Exception as e:
            logger.error(f"Failed to set up CANServiceV2: {e}")
            logger.info("Falling back to legacy CANService")

    return adapter
