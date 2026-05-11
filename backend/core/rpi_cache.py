"""
Lightweight Caching System for Raspberry Pi Deployment

Optimized for minimal memory usage and fast access with <5 concurrent users.
Features:
- Simple TTL-based eviction
- Memory-efficient storage
- Automatic cleanup
- Performance metrics
"""

import asyncio
import contextlib
import time
from collections import OrderedDict
from typing import Any, Generic, TypeVar

from backend.core.rpi_performance_monitor import monitor_rpi_operation
from backend.core.structured_logging import get_logger

logger = get_logger(__name__, "RPiCache")

T = TypeVar("T")

# Cache size limits for RPi deployment
MAX_CACHE_SIZE_MB = 50  # Maximum 50MB for all caches
MAX_ITEMS_PER_CACHE = 1000  # Maximum items per cache instance
DEFAULT_TTL_SECONDS = 300  # 5 minutes default TTL


class CacheMetrics:
    """Lightweight cache metrics tracking."""

    def __init__(self):
        """Initialize cache metrics."""
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.size_bytes = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate, 3),
            "evictions": self.evictions,
            "size_bytes": self.size_bytes,
            "size_mb": round(self.size_bytes / (1024 * 1024), 2),
        }


class RPiCache(Generic[T]):
    """
    Lightweight cache optimized for Raspberry Pi deployment.

    Features:
    - TTL-based expiration
    - LRU eviction when size limit reached
    - Minimal memory overhead
    - Automatic cleanup
    """

    def __init__(
        self,
        name: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_items: int = MAX_ITEMS_PER_CACHE,
    ):
        """
        Initialize cache instance.

        Args:
            name: Cache identifier
            ttl_seconds: Time-to-live for cached items
            max_items: Maximum number of items
        """
        self.name = name
        self.ttl_seconds = ttl_seconds
        self.max_items = min(max_items, MAX_ITEMS_PER_CACHE)

        # Use OrderedDict for LRU behavior
        self._cache: OrderedDict[str, tuple[T, float]] = OrderedDict()
        self._metrics = CacheMetrics()

        # Cleanup task
        self._cleanup_task: asyncio.Task[None] | None = None
        self._cleanup_interval = min(ttl_seconds / 2, 60)  # Cleanup interval

        logger.info(
            "Created cache with TTL and max_items",
            cache_name=name,
            ttl_seconds=ttl_seconds,
            max_items=self.max_items
        )

    @monitor_rpi_operation("cache.get", alert_threshold_ms=5.0)
    async def get(self, key: str) -> T | None:
        """
        Get item from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if key in self._cache:
            value, expiry = self._cache[key]

            if time.time() < expiry:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._metrics.hits += 1
                return value
            # Expired
            del self._cache[key]
            self._metrics.evictions += 1

        self._metrics.misses += 1
        return None

    @monitor_rpi_operation("cache.set", alert_threshold_ms=10.0)
    async def set(self, key: str, value: T, ttl: int | None = None) -> None:
        """
        Set item in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional custom TTL in seconds
        """
        ttl = ttl or self.ttl_seconds
        expiry = time.time() + ttl

        # Check if we need to evict
        if len(self._cache) >= self.max_items:
            # Remove least recently used
            self._cache.popitem(last=False)
            self._metrics.evictions += 1

        self._cache[key] = (value, expiry)
        self._cache.move_to_end(key)

        # Estimate size (rough)
        self._metrics.size_bytes = len(self._cache) * 1024  # Rough estimate

    async def delete(self, key: str) -> bool:
        """
        Delete item from cache.

        Args:
            key: Cache key

        Returns:
            True if item was deleted
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    async def clear(self) -> None:
        """Clear all cached items."""
        self._cache.clear()
        self._metrics.size_bytes = 0
        logger.info("Cleared cache", cache_name=self.name)

    async def cleanup_expired(self) -> int:
        """
        Remove expired items.

        Returns:
            Number of items removed
        """
        current_time = time.time()
        expired_keys = []

        for key, (_, expiry) in self._cache.items():
            if current_time >= expiry:
                expired_keys.append(key)

        for key in expired_keys:
            del self._cache[key]
            self._metrics.evictions += 1

        if expired_keys:
            logger.debug(
                "Cleaned up expired items from cache",
                cache_name=self.name,
                items_cleaned=len(expired_keys)
            )

        return len(expired_keys)

    def start_cleanup_task(self) -> None:
        """Start background cleanup task."""
        if not self._cleanup_task or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        logger.debug("Started cleanup task for cache", cache_name=self.name)

        try:
            while True:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_expired()
        except asyncio.CancelledError:
            logger.debug("Cleanup task cancelled for cache", cache_name=self.name)
            raise

    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

    def get_metrics(self) -> dict[str, Any]:
        """Get cache metrics."""
        metrics = self._metrics.to_dict()
        metrics.update({
            "name": self.name,
            "items": len(self._cache),
            "max_items": self.max_items,
            "ttl_seconds": self.ttl_seconds,
        })
        return metrics

    def get_keys_with_prefix(self, prefix: str) -> list[str]:
        """Get all keys with the given prefix."""
        return [key for key in self._cache if key.startswith(prefix)]


class SharedCache:
    """
    Shared cache instance for commonly accessed data.

    Provides typed access to different data categories while
    sharing the same underlying cache storage.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        """Initialize shared cache."""
        self._cache = RPiCache[Any]("shared", ttl_seconds=ttl_seconds)

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Get cached entity data."""
        return await self._cache.get(f"entity:{entity_id}")

    async def set_entity(self, entity_id: str, data: dict[str, Any]) -> None:
        """Cache entity data."""
        await self._cache.set(f"entity:{entity_id}", data)

    async def get_entities_by_type(self, device_type: str) -> list[dict[str, Any]] | None:
        """Get cached entities by type."""
        return await self._cache.get(f"entities:type:{device_type}")

    async def set_entities_by_type(
        self, device_type: str, entities: list[dict[str, Any]]
    ) -> None:
        """Cache entities by type."""
        await self._cache.set(f"entities:type:{device_type}", entities)

    @monitor_rpi_operation("cache.get_all_entities", alert_threshold_ms=15.0)
    async def get_all_entities(self, active_only: bool) -> list[dict[str, Any]] | None:
        """Get cached all entities list."""
        return await self._cache.get(f"entities:all:active_{active_only}")

    @monitor_rpi_operation("cache.set_all_entities", alert_threshold_ms=20.0)
    async def set_all_entities(
        self, entities: list[dict[str, Any]], active_only: bool, ttl: int = 60
    ) -> None:
        """Cache all entities list."""
        await self._cache.set(f"entities:all:active_{active_only}", entities, ttl)

    async def get_user_settings(self, user_id: str) -> dict[str, Any] | None:
        """Get cached user settings."""
        return await self._cache.get(f"user:settings:{user_id}")

    async def set_user_settings(self, user_id: str, settings: dict[str, Any]) -> None:
        """Cache user settings."""
        await self._cache.set(f"user:settings:{user_id}", settings)

    async def invalidate_entity(self, entity_id: str) -> None:
        """Invalidate entity cache."""
        await self._cache.delete(f"entity:{entity_id}")

        # Also invalidate type caches (simple approach)
        # In production, track which types to invalidate
        await self.clear_all_entities()

    async def clear_all_entities(self) -> None:
        """Clear all entity-related caches."""
        # Get all entity-related keys
        entity_keys = self._cache.get_keys_with_prefix("entity:")
        entities_keys = self._cache.get_keys_with_prefix("entities:")

        # Delete all entity-related keys
        for key in entity_keys + entities_keys:
            await self._cache.delete(key)

    def get_metrics(self) -> dict[str, Any]:
        """Get cache metrics."""
        return self._cache.get_metrics()

    async def start(self) -> None:
        """Start cache background tasks."""
        self._cache.start_cleanup_task()

    async def stop(self) -> None:
        """Stop cache background tasks."""
        await self._cache.stop_cleanup_task()


class CacheManager:
    """
    Manages all cache instances in the application.

    Provides centralized cache lifecycle management and monitoring.
    """

    def __init__(self):
        """Initialize cache manager."""
        self._caches: dict[str, RPiCache[Any]] = {}
        self._shared_cache = SharedCache()

    def create_cache(
        self,
        name: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_items: int = MAX_ITEMS_PER_CACHE,
    ) -> RPiCache[Any]:
        """
        Create or get a named cache instance.

        Args:
            name: Cache identifier
            ttl_seconds: TTL for cached items
            max_items: Maximum items in cache

        Returns:
            Cache instance
        """
        if name not in self._caches:
            cache = RPiCache[Any](name, ttl_seconds, max_items)
            self._caches[name] = cache
            cache.start_cleanup_task()

        return self._caches[name]

    @property
    def shared(self) -> SharedCache:
        """Get shared cache instance."""
        return self._shared_cache

    async def get_all_metrics(self) -> dict[str, Any]:
        """Get metrics for all caches."""
        metrics = {
            "shared": self._shared_cache.get_metrics(),
            "named_caches": {},
            "total": {
                "hits": 0,
                "misses": 0,
                "evictions": 0,
                "size_mb": 0,
                "items": 0,
            }
        }

        # Add shared cache stats to total
        shared_metrics = metrics["shared"]
        for key in ["hits", "misses", "evictions", "items"]:
            metrics["total"][key] += shared_metrics.get(key, 0)
        metrics["total"]["size_mb"] += shared_metrics.get("size_mb", 0)

        # Add named cache stats
        for name, cache in self._caches.items():
            cache_metrics = cache.get_metrics()
            metrics["named_caches"][name] = cache_metrics

            for key in ["hits", "misses", "evictions", "items"]:
                metrics["total"][key] += cache_metrics.get(key, 0)
            metrics["total"]["size_mb"] += cache_metrics.get("size_mb", 0)

        # Calculate total hit rate
        total = metrics["total"]["hits"] + metrics["total"]["misses"]
        metrics["total"]["hit_rate"] = (
            round(metrics["total"]["hits"] / total, 3) if total > 0 else 0.0
        )

        return metrics

    async def clear_all(self) -> None:
        """Clear all caches."""
        await self._shared_cache.clear_all_entities()

        for cache in self._caches.values():
            await cache.clear()

        logger.info("Cleared all caches")

    async def start(self) -> None:
        """Start all cache background tasks."""
        await self._shared_cache.start()

        for cache in self._caches.values():
            cache.start_cleanup_task()

        logger.info("Started cache manager", cache_count=len(self._caches) + 1)

    async def stop(self) -> None:
        """Stop all cache background tasks."""
        await self._shared_cache.stop()

        for cache in self._caches.values():
            await cache.stop_cleanup_task()

        logger.info("Stopped cache manager")


class _CacheManagerSingleton:
    """Singleton holder for cache manager instance."""
    instance: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """Get global cache manager instance."""
    if _CacheManagerSingleton.instance is None:
        _CacheManagerSingleton.instance = CacheManager()
    return _CacheManagerSingleton.instance


async def initialize_cache_manager() -> CacheManager:
    """Initialize and start cache manager."""
    manager = get_cache_manager()
    await manager.start()
    return manager


async def cleanup_cache_manager() -> None:
    """Stop and cleanup cache manager."""
    if _CacheManagerSingleton.instance:
        await _CacheManagerSingleton.instance.stop()
        _CacheManagerSingleton.instance = None

