"""
Entity Service Migration Adapter

This adapter allows gradual migration from EntityService (using AppState)
to EntityServiceV2 (using repositories directly). It provides the same
interface as EntityService but delegates to EntityServiceV2 when available.

Part of Phase 2R.3: Progressive migration pattern.
"""

import logging
from typing import Any, Optional

from backend.services.entity_service import EntityService
from backend.services.entity_service_v2 import EntityServiceV2
from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class EntityServiceMigrationAdapter(EntityService):
    """
    Migration adapter that allows gradual transition to repository-based EntityServiceV2.

    This adapter checks a feature flag and either uses the new repository-based
    implementation or falls back to the legacy AppState-based implementation.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the adapter with either V2 or legacy service."""
        super().__init__(*args, **kwargs)

        # Check if we should use V2
        settings = get_settings()
        self._use_v2 = getattr(settings, "USE_ENTITY_SERVICE_V2", False)
        self._v2_service: Optional[EntityServiceV2] = None

        if self._use_v2:
            logger.info("EntityServiceMigrationAdapter: Using EntityServiceV2 (repository pattern)")
        else:
            logger.info("EntityServiceMigrationAdapter: Using legacy EntityService (AppState pattern)")

    def set_v2_service(self, v2_service: EntityServiceV2) -> None:
        """
        Set the V2 service instance for delegation.

        Args:
            v2_service: The EntityServiceV2 instance to use
        """
        self._v2_service = v2_service
        logger.info("EntityServiceV2 instance set for migration adapter")

    async def list_entities(
        self,
        device_type: str | None = None,
        area: str | None = None,
        protocol: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """List all entities with optional filtering."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.list_entities(device_type, area, protocol)
        return await super().list_entities(device_type, area, protocol)

    async def list_entity_ids(self) -> list[str]:
        """Return all known entity IDs."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.list_entity_ids()
        return await super().list_entity_ids()

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Get a specific entity by ID."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_entity(entity_id)
        return await super().get_entity(entity_id)

    async def get_entity_history(
        self,
        entity_id: str,
        since: float | None = None,
        limit: int | None = 1000,
    ) -> list[dict[str, Any]] | None:
        """Get entity history with optional filtering."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_entity_history(entity_id, since, limit)
        return await super().get_entity_history(entity_id, since, limit)

    async def get_unmapped_entries(self) -> dict[str, Any]:
        """Get unmapped entries."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_unmapped_entries()
        return await super().get_unmapped_entries()

    async def get_unknown_pgns(self) -> dict[str, Any]:
        """Get unknown PGN entries."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_unknown_pgns()
        return await super().get_unknown_pgns()

    async def get_metadata(self) -> dict:
        """Get metadata about available entity attributes."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_metadata()
        return await super().get_metadata()

    async def get_protocol_summary(self) -> dict[str, Any]:
        """Get summary of entity distribution across protocols."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.get_protocol_summary()
        return await super().get_protocol_summary()

    async def create_entity_mapping(self, request: Any) -> Any:
        """Create a new entity mapping from an unmapped entry."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.create_entity_mapping(request)
        return await super().create_entity_mapping(request)

    async def control_entity(self, entity_id: str, command: Any) -> Any:
        """Control an entity."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.control_entity(entity_id, command)
        return await super().control_entity(entity_id, command)

    async def control_light(self, entity_id: str, cmd: Any) -> Any:
        """Control a light entity."""
        if self._use_v2 and self._v2_service:
            return await self._v2_service.control_light(entity_id, cmd)
        return await super().control_light(entity_id, cmd)


def create_entity_service_with_migration(
    websocket_manager: Any,
    entity_manager: Any = None,
    service_registry: Any = None,
) -> EntityService:
    """
    Factory function that creates EntityService with migration adapter.

    This allows progressive migration to repository pattern based on
    configuration settings.

    Args:
        websocket_manager: WebSocket manager instance
        entity_manager: Optional entity manager (for legacy)
        service_registry: Optional service registry (for V2)

    Returns:
        EntityService instance (may be migration adapter)
    """
    # Create the migration adapter
    adapter = EntityServiceMigrationAdapter(
        websocket_manager=websocket_manager,
        entity_manager=entity_manager,
    )

    # If V2 is enabled and we have service registry, set up V2
    settings = get_settings()
    if getattr(settings, "USE_ENTITY_SERVICE_V2", False) and service_registry:
        try:
            # Get repositories from service registry
            entity_state_repo = service_registry.get_service("entity_state_repository")
            rvc_config_repo = service_registry.get_service("rvc_config_repository")

            if entity_state_repo and rvc_config_repo:
                from backend.services.entity_service_v2 import EntityServiceV2

                v2_service = EntityServiceV2(
                    websocket_manager=websocket_manager,
                    entity_state_repository=entity_state_repo,
                    rvc_config_repository=rvc_config_repo,
                )

                adapter.set_v2_service(v2_service)
                logger.info("EntityServiceV2 configured successfully in migration adapter")
            else:
                logger.warning("Repositories not available, falling back to legacy EntityService")

        except Exception as e:
            logger.error(f"Failed to set up EntityServiceV2: {e}")
            logger.info("Falling back to legacy EntityService")

    return adapter
