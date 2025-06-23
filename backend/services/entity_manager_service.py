"""
Entity Manager Service - Clean Implementation

Direct service implementation without Feature inheritance.
Uses repository injection pattern for all dependencies.
"""

import logging
from typing import Any, Optional

from backend.core.entity_manager import EntityManager

logger = logging.getLogger(__name__)


class EntityManagerService:
    """
    Clean entity manager service without Feature inheritance.

    This service manages entity state and configuration using
    repository injection for all dependencies.
    """

    def __init__(
        self,
        database_manager=None,
        rvc_config_provider=None,
        config: dict[str, Any] | None = None,
    ):
        """
        Initialize EntityManagerService with injected dependencies.

        Args:
            database_manager: Database manager for entity persistence
            rvc_config_provider: Optional RVC configuration provider
            config: Optional configuration dictionary
        """
        self._database_manager = database_manager
        self._rvc_config_provider = rvc_config_provider
        self._config = config or {}

        # Create the core EntityManager
        self._entity_manager = EntityManager()
        self._persistence_service = None
        self._initialized = False

        logger.info("EntityManagerService initialized with dependency injection")

    async def start(self) -> None:
        """Start the entity manager service."""
        if self._initialized:
            return

        logger.info("Starting EntityManagerService...")

        try:
            # EntityManager doesn't need async initialization
            # It's ready to use after construction

            # Load RVC configuration if available
            if self._rvc_config_provider:
                await self._load_rvc_configuration()

            # Initialize persistence if database manager available
            if self._database_manager:
                await self._initialize_persistence()
            else:
                logger.warning("Database manager not available - entity persistence disabled")

            self._initialized = True
            logger.info("EntityManagerService started successfully")

        except Exception as e:
            logger.error(f"Failed to start EntityManagerService: {e}")
            raise

    async def stop(self) -> None:
        """Stop the entity manager service."""
        if not self._initialized:
            return

        logger.info("Stopping EntityManagerService...")

        try:
            # Stop persistence service
            if self._persistence_service:
                await self._persistence_service.stop()
                self._persistence_service = None

            # EntityManager cleanup (if needed)
            # Currently no cleanup required

            self._initialized = False
            logger.info("EntityManagerService stopped successfully")

        except Exception as e:
            logger.error(f"Error stopping EntityManagerService: {e}")

    async def _load_rvc_configuration(self) -> None:
        """Load RVC configuration into entity manager."""
        try:
            if not self._rvc_config_provider:
                return

            # Get RVC configuration
            rvc_config = await self._rvc_config_provider.get_config()
            if not rvc_config:
                logger.warning("No RVC configuration available")
                return

            # Load entities from RVC configuration
            entities_loaded = 0
            if "message_definitions" in rvc_config:
                for message_def in rvc_config["message_definitions"]:
                    # Extract entity information from message definition
                    entity_info = self._extract_entity_from_message(message_def)
                    if entity_info:
                        from backend.models.entity_model import EntityConfig

                        config = EntityConfig(entity_info)
                        self._entity_manager.register_entity(
                            entity_id=entity_info.get("entity_id", f"rvc_{entities_loaded}"),
                            config=config,
                            protocol="rvc",
                        )
                        entities_loaded += 1

            logger.info(f"Loaded {entities_loaded} entities from RVC configuration")

        except Exception as e:
            logger.error(f"Failed to load RVC configuration: {e}")

    def _extract_entity_from_message(self, message_def: dict) -> dict | None:
        """Extract entity information from RVC message definition."""
        try:
            # This would contain the logic to convert RVC message definitions
            # to entity definitions. For now, return None as this would require
            # detailed RVC specification parsing.
            return None

        except Exception as e:
            logger.debug(f"Could not extract entity from message: {e}")
            return None

    async def _initialize_persistence(self) -> None:
        """Initialize entity persistence service."""
        try:
            from backend.services.entity_persistence_service import EntityPersistenceService

            self._persistence_service = EntityPersistenceService(
                entity_manager=self._entity_manager,
                database_manager=self._database_manager,
                debounce_delay=0.5,  # 500ms debounce for SSD optimization
            )

            await self._persistence_service.start()
            logger.info("Entity persistence service started")

        except Exception as e:
            logger.error(f"Failed to initialize entity persistence: {e}")
            self._persistence_service = None

    def get_entity_manager(self) -> EntityManager:
        """Get the underlying EntityManager instance."""
        return self._entity_manager

    def get_health_status(self) -> dict[str, Any]:
        """Get health status for ServiceRegistry monitoring."""
        entity_count = len(self._entity_manager.get_entity_ids())

        return {
            "healthy": self._initialized,
            "initialized": self._initialized,
            "entity_count": entity_count,
            "persistence_enabled": self._persistence_service is not None,
            "rvc_config_loaded": self._rvc_config_provider is not None,
        }

    def health_check(self) -> dict[str, Any]:
        """Alias for get_health_status for backward compatibility."""
        return self.get_health_status()

    # Delegate common EntityManager methods for convenience
    def get_entity_ids(self) -> list[str]:
        """Get list of all entity IDs."""
        return self._entity_manager.get_entity_ids()

    def get_entity(self, entity_id: str) -> dict | None:
        """Get entity by ID."""
        entity = self._entity_manager.get_entity(entity_id)
        return entity.to_dict() if entity else None

    def update_entity(self, entity_id: str, updates: dict) -> bool:
        """Update entity state."""
        entity = self._entity_manager.get_entity(entity_id)
        if entity:
            entity.update_state(updates)
            return True
        return False

    def add_entity(self, **kwargs) -> str:
        """Add new entity."""
        from backend.models.entity_model import EntityConfig

        entity_id = kwargs.get("entity_id", f"entity_{len(self._entity_manager.entities)}")
        config = EntityConfig(kwargs)
        entity = self._entity_manager.register_entity(
            entity_id=entity_id, config=config, protocol=kwargs.get("protocol", "rvc")
        )
        return entity.entity_id

    def remove_entity(self, entity_id: str) -> bool:
        """Remove entity."""
        if entity_id in self._entity_manager.entities:
            entity = self._entity_manager.entities[entity_id]
            # Remove from physical_id_map
            physical_id = entity.config.get("physical_id")
            if physical_id and physical_id in self._entity_manager.physical_id_map:
                del self._entity_manager.physical_id_map[physical_id]
            # Remove from entities dict
            del self._entity_manager.entities[entity_id]
            # Remove from protocol entities tracking
            for protocol_entities in self._entity_manager.protocol_entities.values():
                protocol_entities.discard(entity_id)
            return True
        return False
