"""
RVC Service Migration Adapter

This adapter allows gradual migration from RVCService (using AppState)
to RVCServiceV2 (using repositories directly). It provides the same
interface as RVCService but delegates to RVCServiceV2 when available.

Part of Phase 2R.3: Progressive migration pattern.
"""

import logging
from typing import Any, Optional

from backend.services.rvc_service import RVCService
from backend.services.rvc_service_v2 import RVCServiceV2
from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class RVCServiceMigrationAdapter(RVCService):
    """
    Migration adapter that allows gradual transition to repository-based RVCServiceV2.

    This adapter checks a feature flag and either uses the new repository-based
    implementation or falls back to the legacy AppState-based implementation.
    """

    def __init__(self, app_state):
        """Initialize the adapter with either V2 or legacy service."""
        super().__init__(app_state)

        # Check if we should use V2
        settings = get_settings()
        self._use_v2 = getattr(settings, "USE_RVC_SERVICE_V2", False)
        self._v2_service: Optional[RVCServiceV2] = None

        if self._use_v2:
            logger.info("RVCServiceMigrationAdapter: Using RVCServiceV2 (repository pattern)")
        else:
            logger.info("RVCServiceMigrationAdapter: Using legacy RVCService (AppState pattern)")

    def set_v2_service(self, v2_service: RVCServiceV2) -> None:
        """
        Set the V2 service instance for delegation.

        Args:
            v2_service: The RVCServiceV2 instance to use
        """
        self._v2_service = v2_service
        logger.info("RVCServiceV2 instance set for migration adapter")

    async def start(self) -> None:
        """Start the RVC service and its background tasks."""
        if self._use_v2 and self._v2_service:
            await self._v2_service.start()
        else:
            await super().start()

    async def stop(self) -> None:
        """Stop the RVC service and clean up resources."""
        if self._use_v2 and self._v2_service:
            await self._v2_service.stop()
        else:
            await super().stop()

    def decode_message(self, dgn: int, data: bytes, source: int) -> dict[str, Any] | None:
        """Decode an RV-C message into a structured format."""
        if self._use_v2 and self._v2_service:
            return self._v2_service.decode_message(dgn, data, source)
        return super().decode_message(dgn, data, source)

    def get_instance_name(self, dgn: int, instance: int) -> str:
        """Get a human-readable name for a specific instance."""
        if self._use_v2 and self._v2_service:
            return self._v2_service.get_instance_name(dgn, instance)
        return super().get_instance_name(dgn, instance)

    def register_instance_name(self, dgn: int, instance: int, name: str) -> None:
        """Register a human-readable name for a specific instance."""
        if self._use_v2 and self._v2_service:
            self._v2_service.register_instance_name(dgn, instance, name)
        else:
            super().register_instance_name(dgn, instance, name)

    def get_health_status(self) -> dict[str, Any]:
        """Get service health status."""
        if self._use_v2 and self._v2_service:
            return self._v2_service.get_health_status()
        # Legacy doesn't have health status, create a basic one
        return {
            "service": "RVCService",
            "healthy": self._running,
            "running": self._running,
        }

    def get_rvc_configuration_summary(self) -> dict[str, Any]:
        """Get summary of RVC configuration."""
        if self._use_v2 and self._v2_service:
            return self._v2_service.get_rvc_configuration_summary()
        # Legacy doesn't have this method, return empty summary
        return {
            "configuration_loaded": bool(self.app_state),
        }

    def get_command_status_pair(self, command_dgn: str) -> Optional[str]:
        """Get the status DGN for a command DGN."""
        if self._use_v2 and self._v2_service:
            return self._v2_service.get_command_status_pair(command_dgn)
        # Use app_state for legacy
        if self.app_state:
            pairs = self.app_state.known_command_status_pairs
            return pairs.get(command_dgn)
        return None


def create_rvc_service_with_migration(
    app_state: Any,
    service_registry: Any = None,
) -> RVCService:
    """
    Factory function that creates RVCService with migration adapter.

    This allows progressive migration to repository pattern based on
    configuration settings.

    Args:
        app_state: Application state (for legacy)
        service_registry: Optional service registry (for V2)

    Returns:
        RVCService instance (may be migration adapter)
    """
    # Create the migration adapter
    adapter = RVCServiceMigrationAdapter(app_state)

    # If V2 is enabled and we have service registry, set up V2
    settings = get_settings()
    if getattr(settings, "USE_RVC_SERVICE_V2", False) and service_registry:
        try:
            # Get repositories from service registry or app state
            rvc_config_repo = None
            can_tracking_repo = None

            # Try service registry first
            if service_registry.has_service("rvc_config_repository"):
                rvc_config_repo = service_registry.get_service("rvc_config_repository")
            elif app_state and hasattr(app_state, "_rvc_config_repo"):
                rvc_config_repo = app_state._rvc_config_repo

            if service_registry.has_service("can_tracking_repository"):
                can_tracking_repo = service_registry.get_service("can_tracking_repository")
            elif app_state and hasattr(app_state, "_can_tracking_repo"):
                can_tracking_repo = app_state._can_tracking_repo

            if rvc_config_repo:
                from backend.services.rvc_service_v2 import RVCServiceV2

                v2_service = RVCServiceV2(
                    rvc_config_repository=rvc_config_repo,
                    can_tracking_repository=can_tracking_repo,  # Optional
                )

                adapter.set_v2_service(v2_service)
                logger.info("RVCServiceV2 configured successfully in migration adapter")
            else:
                logger.warning("RVC config repository not available, falling back to legacy RVCService")

        except Exception as e:
            logger.error(f"Failed to set up RVCServiceV2: {e}")
            logger.info("Falling back to legacy RVCService")

    return adapter
