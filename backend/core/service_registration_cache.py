"""Service registration for caching services."""

from typing import Any

# No dependencies needed for cache services
from backend.core.service_registry import EnhancedServiceRegistry
from backend.core.structured_logging import get_logger

logger = get_logger(__name__, "CacheServiceRegistration")


def register_cache_services(service_registry: EnhancedServiceRegistry) -> None:
    """
    Register caching services.

    Lightweight caching optimized for minimal memory usage.
    """

    # Cache Manager Service
    async def _init_cache_manager() -> Any:
        """Initialize the global cache manager."""
        from backend.core.rpi_cache import initialize_cache_manager

        logger.info("Initializing cache manager for RPi deployment")
        cache_manager = await initialize_cache_manager()
        logger.info("Cache manager initialized successfully")

        return cache_manager

    service_registry.register_service(
        name="cache_manager",
        init_func=_init_cache_manager,
        dependencies=[],  # No dependencies
        description="Lightweight cache manager for embedded deployment",
        tags={"cache", "performance", "optimized"},
    )

    logger.info("Registered cache services")

