"""
EntityManager Feature for CoachIQ.

This module implements the EntityManager as a proper Feature that can be registered
with the FeatureManager, providing an independent entity management system that
completely removes legacy state dictionary dependencies.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.services.entity_persistence_service import EntityPersistenceService

from backend.core.entity_manager import EntityManager
from backend.services.feature_base import Feature

logger = logging.getLogger(__name__)


class EntityManagerFeature(Feature):
    """
    Feature that provides unified entity state management.

    This Feature wraps the EntityManager to integrate it properly with the
    FeatureManager system, providing an independent entity management system
    that completely replaces legacy state dictionaries.
    """

    def __init__(
        self,
        name: str = "entity_manager",
        enabled: bool = True,
        core: bool = True,
        config: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        friendly_name: str | None = None,
        safety_classification=None,
        log_state_transitions: bool = True,
        **kwargs
    ) -> None:
        """
        Initialize the EntityManager feature.

        Args:
            name: Feature name (default: "entity_manager")
            enabled: Whether the feature is enabled (default: True)
            core: Whether this is a core feature (default: True)
            config: Configuration options
            dependencies: Feature dependencies
            friendly_name: Human-readable display name for the feature
            safety_classification: Safety classification for state validation
            log_state_transitions: Whether to log state transitions
            **kwargs: Additional arguments for compatibility
        """
        super().__init__(
            name=name,
            enabled=enabled,
            core=core,
            config=config or {},
            dependencies=dependencies or [],
            friendly_name=friendly_name,
            safety_classification=safety_classification,
            log_state_transitions=log_state_transitions,
        )

        # Initialize the EntityManager
        self.entity_manager = EntityManager()

        # Initialize the persistence service (will be started in startup)
        self._persistence_service: EntityPersistenceService | None = None

    async def startup(self, rvc_config_provider=None) -> None:
        """
        Initialize the EntityManager feature on startup.

        Args:
            rvc_config_provider: Optional RVCConfigProvider instance (for ServiceRegistry integration)
        """
        logger.info("Starting EntityManager feature")

        # Load entities from coach mapping file
        try:
            logger.info("Loading entity configuration from coach mapping files...")

            # Use shared config provider if available (ServiceRegistry integration)
            if rvc_config_provider is not None:
                logger.info("Using shared RVCConfigProvider (ServiceRegistry mode)")

                # Get configuration paths from provider
                rvc_spec_path = str(rvc_config_provider._spec_path) if rvc_config_provider._spec_path else None
                device_mapping_path = str(rvc_config_provider._device_mapping_path) if rvc_config_provider._device_mapping_path else None

            else:
                logger.info("Using legacy configuration loading (fallback mode)")

                # Get configuration paths from settings (legacy mode)
                from backend.core.config import get_settings

                settings = get_settings()

                rvc_spec_path = str(settings.rvc_spec_path) if settings.rvc_spec_path else None
                device_mapping_path = (
                    str(settings.rvc_coach_mapping_path) if settings.rvc_coach_mapping_path else None
                )

            logger.info("Using RV-C spec path: %s", rvc_spec_path)
            logger.info("Using device mapping path: %s", device_mapping_path)

            # Load entity configuration using structured config
            from backend.integrations.rvc import load_config_data_v2

            rvc_config = load_config_data_v2(
                rvc_spec_path_override=rvc_spec_path,
                device_mapping_path_override=device_mapping_path,
            )

            # Extract values from structured config
            entity_map = rvc_config.entity_map
            entity_ids = rvc_config.entity_ids
            entity_id_lookup = rvc_config.inst_map

            # Register all entities with the EntityManager
            for entity_id in entity_ids:
                if entity_id in entity_id_lookup:
                    # Get DGN and instance from entity_id_lookup
                    dgn_instance_info = entity_id_lookup[entity_id]
                    dgn_hex = dgn_instance_info["dgn_hex"]
                    instance = dgn_instance_info["instance"]

                    # Get full entity configuration from entity_map
                    entity_key = (dgn_hex, instance)
                    if entity_key in entity_map:
                        config = entity_map[entity_key]
                        self.entity_manager.register_entity(entity_id, config)
                        logger.debug("Registered entity: %s from %s:%s", entity_id, dgn_hex, instance)
                    else:
                        logger.warning(
                            "Entity %s not found in entity_map for %s:%s", entity_id, dgn_hex, instance
                        )

            logger.info("Successfully loaded %d entities into EntityManager", len(entity_ids))

        except Exception as e:
            logger.error("Failed to load entity configuration during startup: %s", e)
            # Don't fail startup completely, but log the error

        # Initialize entity persistence service using CoreServices
        try:
            from backend.services.entity_persistence_service import EntityPersistenceService
            from backend.services.feature_manager import get_feature_manager

            # Get database manager from CoreServices
            feature_manager = get_feature_manager()
            core_services = feature_manager.get_core_services()
            database_manager = core_services.database_manager

            if database_manager:
                # Create and start the persistence service
                self._persistence_service = EntityPersistenceService(
                    entity_manager=self.entity_manager,
                    database_manager=database_manager,
                    debounce_delay=0.5,  # 500ms debounce for SSD optimization
                )
                await self._persistence_service.start()
                logger.info("Entity persistence service started successfully")
            else:
                logger.warning("Database manager not available - entity persistence disabled")

        except Exception as e:
            logger.error("Failed to initialize entity persistence service: %s", e)
            # Continue without persistence rather than failing startup
            self._persistence_service = None

    async def shutdown(self) -> None:
        """Clean up resources on shutdown."""
        logger.info("Shutting down EntityManager feature")

        # Stop the persistence service if it's running
        if self._persistence_service:
            try:
                await self._persistence_service.stop()
                logger.info("Entity persistence service stopped")
            except Exception as e:
                logger.error("Error stopping entity persistence service: %s", e)

        # EntityManager doesn't require explicit cleanup, but we could add it here if needed

    @property
    def health(self) -> str:
        """Return the health status of the feature."""
        if not self.enabled:
            return "healthy"  # Disabled is considered healthy

        # Return simple status - entity count details should be in health_details
        return "healthy"

    @property
    def health_details(self) -> dict[str, Any]:
        """Return detailed health information for diagnostics."""
        if not self.enabled:
            return {"status": "disabled", "reason": "Feature not enabled"}

        entity_count = len(self.entity_manager.get_entity_ids())
        return {
            "status": "healthy",
            "entity_count": entity_count,
            "description": (
                f"{entity_count} entities loaded" if entity_count > 0 else "No entities loaded"
            ),
        }

    def get_entity_manager(self) -> EntityManager:
        """Get the EntityManager instance."""
        return self.entity_manager


# Singleton instance and accessor functions
_entity_manager_feature: EntityManagerFeature | None = None


def initialize_entity_manager_feature(
    config: dict[str, Any] | None = None,
) -> EntityManagerFeature:
    """
    Initialize the EntityManager feature singleton.

    NOTE: This global singleton pattern is deprecated. New code should register
    EntityManagerFeature with FeatureManager, which will automatically register
    it with ServiceRegistry for proper lifecycle management.

    Example of preferred pattern:
        entity_manager_feature = EntityManagerFeature(config=config)
        feature_manager.register_feature(entity_manager_feature)

    Args:
        config: Optional configuration dictionary

    Returns:
        The initialized EntityManagerFeature instance
    """
    global _entity_manager_feature

    if _entity_manager_feature is None:
        _entity_manager_feature = EntityManagerFeature(config=config)
        logger.warning(
            "EntityManagerFeature initialized with global singleton pattern (deprecated). "
            "Consider registering with FeatureManager for proper lifecycle management."
        )

    return _entity_manager_feature


def get_entity_manager_feature() -> EntityManagerFeature:
    """
    Get the EntityManager feature instance.

    This function follows the enhanced singleton pattern that checks modern
    locations (app.state, ServiceRegistry) before falling back to the global
    instance for backward compatibility.

    Returns:
        The EntityManagerFeature instance

    Raises:
        RuntimeError: If the feature has not been initialized
    """
    # Try to get from app.state first (ServiceRegistry/FeatureManager integration)
    try:
        # Try to access the global app instance if available
        import backend.main
        if hasattr(backend.main, 'app'):
            app = backend.main.app
            # Check if registered as a feature
            if hasattr(app.state, 'feature_manager'):
                feature_manager = app.state.feature_manager
                entity_feature = feature_manager.get_feature('entity_manager')
                if isinstance(entity_feature, EntityManagerFeature):
                    return entity_feature

            # Check ServiceRegistry
            if hasattr(app.state, 'service_registry'):
                service_registry = app.state.service_registry
                if service_registry.has_service('entity_manager'):
                    service = service_registry.get_service('entity_manager')
                    if isinstance(service, EntityManagerFeature):
                        return service
    except Exception:
        # Continue to fallback
        pass

    # Fall back to global singleton for backward compatibility
    if _entity_manager_feature is None:
        msg = "EntityManager feature has not been initialized"
        raise RuntimeError(msg)

    return _entity_manager_feature


def get_entity_manager() -> EntityManager:
    """
    Get the EntityManager instance from the feature.

    Returns:
        The EntityManager instance

    Raises:
        RuntimeError: If the feature has not been initialized
    """
    feature = get_entity_manager_feature()
    return feature.get_entity_manager()
