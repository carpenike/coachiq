"""Service registration for entity services."""

from typing import Any

from backend.core.service_dependency_resolver import DependencyType, ServiceDependency
from backend.core.service_registry import EnhancedServiceRegistry
from backend.core.structured_logging import get_logger

logger = get_logger(__name__, "EntityServiceRegistration")


def register_entity_services(service_registry: EnhancedServiceRegistry) -> None:
    """
    Register entity services.

    Lightweight implementation optimized for embedded deployment.
    """

    # Entity Service
    async def _init_entity_service(
        database_manager: Any,
        cache_manager: Any,
        app_settings: Any,
    ) -> Any:
        """Initialize entity service."""
        from backend.services.entity_service import EntityService

        # Using optimized entity service for embedded deployment
        logger.info("Using optimized entity service for embedded deployment")
        return EntityService(database_manager.get_session)

    # Register as THE entity_service
    service_registry.register_service(
        name="entity_service",
        init_func=_init_entity_service,
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("cache_manager", DependencyType.REQUIRED),
            ServiceDependency("app_settings", DependencyType.REQUIRED),
        ],
        description="Lightweight entity service optimized for embedded deployment",
        tags={"entity", "optimized"},
    )

    logger.info("Registered entity services")
