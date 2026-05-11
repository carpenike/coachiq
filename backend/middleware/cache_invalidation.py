"""
Cache Invalidation Middleware

Lightweight middleware to invalidate cache entries when entities are modified.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.rpi_cache import get_cache_manager
from backend.core.structured_logging import get_logger

logger = get_logger(__name__, "CacheInvalidation")

# Paths that modify entities and require cache invalidation
INVALIDATION_PATHS = {
    "/api/entities": ["POST", "PUT", "PATCH", "DELETE"],
    "/api/v2/entities": ["POST", "PUT", "PATCH", "DELETE"],
    "/api/control": ["POST"],
    "/api/v2/control": ["POST"],
}

# HTTP status code threshold for success
HTTP_SUCCESS_THRESHOLD = 300

# Minimum path parts for entity ID extraction
MIN_PATH_PARTS_FOR_ENTITY_ID = 2


class CacheInvalidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to invalidate cache entries on entity modifications.

    This is a simple implementation that invalidates related cache entries
    when entities are modified through the API.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and invalidate cache if needed."""
        # Process the request
        response = await call_next(request)

        # Check if this request should trigger cache invalidation
        if response.status_code < HTTP_SUCCESS_THRESHOLD:  # Successful request
            path = str(request.url.path)
            method = request.method

            # Check if this is an invalidating operation
            for pattern, methods in INVALIDATION_PATHS.items():
                if pattern in path and method in methods:
                    await self._invalidate_cache(request, path)
                    break

        return response

    async def _invalidate_cache(self, _request: Request, path: str) -> None:
        """Invalidate cache based on the request."""
        try:
            cache_manager = get_cache_manager()

            # Extract entity ID from path if available
            path_parts = path.strip("/").split("/")

            # Handle different path patterns
            if "entities" in path and len(path_parts) > MIN_PATH_PARTS_FOR_ENTITY_ID:
                # Path like /api/entities/{entity_id}
                entity_id = path_parts[-1]
                if not entity_id.startswith("v"):  # Skip version indicators
                    await cache_manager.shared.invalidate_entity(entity_id)
                    logger.debug("Invalidated cache for entity: %s", entity_id)
            else:
                # Bulk operation or unknown pattern - clear entity caches
                # This is a simple approach - in production, parse request body
                # Clear all entity-related caches
                await self._clear_entity_caches(cache_manager)
                logger.debug("Cleared entity cache after bulk operation")

        except Exception as e:
            # Don't let cache errors break the request
            logger.warning("Cache invalidation failed: %s", e)

    async def _clear_entity_caches(self, cache_manager) -> None:
        """Clear all entity-related caches."""
        # Get the shared cache instance
        shared_cache = cache_manager.shared

        # Clear the underlying cache
        # This is done through the SharedCache's methods rather than accessing _cache directly
        await shared_cache.clear_all_entities()
