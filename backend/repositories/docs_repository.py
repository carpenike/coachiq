"""Documentation repository.

This repository manages documentation data, schema caching, and metadata
using the repository pattern.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.performance import PerformanceMonitor
from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class DocsRepository(MonitoredRepository):
    """Repository for documentation data and schema management."""

    def __init__(
        self,
        database_manager,
        performance_monitor: PerformanceMonitor,
        cache_dir: Path | None = None,
        cache_ttl_seconds: int = 3600,
    ):
        """Initialize documentation repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
            cache_dir: Directory for caching schemas
            cache_ttl_seconds: Cache time-to-live in seconds
        """
        super().__init__(database_manager, performance_monitor)
        self._cache_dir = cache_dir
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._schema_cache: dict[str, Any] | None = None
        self._cache_timestamp: datetime | None = None
        self._lock = asyncio.Lock()

    @MonitoredRepository._monitored_operation("cache_schema")
    async def cache_schema(self, schema: dict[str, Any]) -> bool:
        """Cache OpenAPI schema.

        Args:
            schema: OpenAPI schema to cache

        Returns:
            True if caching successful
        """
        async with self._lock:
            try:
                self._schema_cache = schema
                self._cache_timestamp = datetime.now()

                # Also persist to disk if cache_dir provided
                if self._cache_dir:
                    await self._persist_schema_to_disk(schema)

                return True

            except Exception as e:
                logger.error(f"Failed to cache schema: {e}")
                return False

    @MonitoredRepository._monitored_operation("get_cached_schema")
    async def get_cached_schema(self) -> dict[str, Any] | None:
        """Get cached OpenAPI schema if still valid.

        Returns:
            Cached schema or None if expired/not available
        """
        async with self._lock:
            # Check memory cache first
            if self._schema_cache and self._cache_timestamp:
                if datetime.now() - self._cache_timestamp < self._cache_ttl:
                    return self._schema_cache

            # Try to load from disk if available
            if self._cache_dir:
                schema = await self._load_schema_from_disk()
                if schema:
                    self._schema_cache = schema
                    return schema

            return None

    async def _persist_schema_to_disk(self, schema: dict[str, Any]) -> None:
        """Persist schema to disk cache.

        Args:
            schema: Schema to persist
        """
        if not self._cache_dir:
            return

        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self._cache_dir / "openapi_schema.json"

            # Add timestamp to schema
            schema_with_meta = {
                "schema": schema,
                "cached_at": datetime.now().isoformat(),
            }

            with open(cache_file, "w") as f:
                json.dump(schema_with_meta, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to persist schema to disk: {e}")

    async def _load_schema_from_disk(self) -> dict[str, Any] | None:
        """Load schema from disk cache.

        Returns:
            Schema if valid cache exists, None otherwise
        """
        if not self._cache_dir:
            return None

        try:
            cache_file = self._cache_dir / "openapi_schema.json"

            if not cache_file.exists():
                return None

            with open(cache_file) as f:
                data = json.load(f)

            # Check cache validity
            cached_at = datetime.fromisoformat(data["cached_at"])
            if datetime.now() - cached_at > self._cache_ttl:
                logger.debug("Disk cache expired")
                return None

            self._cache_timestamp = cached_at
            return data["schema"]

        except Exception as e:
            logger.warning(f"Failed to load schema from disk: {e}")
            return None

    @MonitoredRepository._monitored_operation("store_endpoint_metadata")
    async def store_endpoint_metadata(
        self, endpoint_path: str, method: str, metadata: dict[str, Any]
    ) -> bool:
        """Store additional metadata for an endpoint.

        Args:
            endpoint_path: API endpoint path
            method: HTTP method
            metadata: Additional metadata to store

        Returns:
            True if storage successful
        """
        if not self._cache_dir:
            return False

        try:
            metadata_dir = self._cache_dir / "endpoint_metadata"
            metadata_dir.mkdir(parents=True, exist_ok=True)

            # Create safe filename from endpoint
            safe_path = endpoint_path.replace("/", "_").strip("_")
            filename = f"{method.lower()}_{safe_path}.json"

            metadata_file = metadata_dir / filename

            # Add timestamp
            metadata["updated_at"] = datetime.now().isoformat()

            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)

            return True

        except Exception as e:
            logger.error(f"Failed to store endpoint metadata: {e}")
            return False

    @MonitoredRepository._monitored_operation("get_endpoint_metadata")
    async def get_endpoint_metadata(self, endpoint_path: str, method: str) -> dict[str, Any] | None:
        """Get stored metadata for an endpoint.

        Args:
            endpoint_path: API endpoint path
            method: HTTP method

        Returns:
            Metadata if available, None otherwise
        """
        if not self._cache_dir:
            return None

        try:
            metadata_dir = self._cache_dir / "endpoint_metadata"

            if not metadata_dir.exists():
                return None

            # Create safe filename from endpoint
            safe_path = endpoint_path.replace("/", "_").strip("_")
            filename = f"{method.lower()}_{safe_path}.json"

            metadata_file = metadata_dir / filename

            if not metadata_file.exists():
                return None

            with open(metadata_file) as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"Failed to get endpoint metadata: {e}")
            return None

    @MonitoredRepository._monitored_operation("list_cached_endpoints")
    async def list_cached_endpoints(self) -> list[dict[str, str]]:
        """List all endpoints with cached metadata.

        Returns:
            List of endpoint information
        """
        if not self._cache_dir:
            return []

        try:
            metadata_dir = self._cache_dir / "endpoint_metadata"

            if not metadata_dir.exists():
                return []

            endpoints = []

            for metadata_file in metadata_dir.glob("*.json"):
                # Parse filename back to endpoint info
                parts = metadata_file.stem.split("_", 1)
                if len(parts) == 2:
                    method = parts[0].upper()
                    path = "/" + parts[1].replace("_", "/")

                    endpoints.append(
                        {"method": method, "path": path, "file": str(metadata_file.name)}
                    )

            return endpoints

        except Exception as e:
            logger.error(f"Failed to list cached endpoints: {e}")
            return []

    @MonitoredRepository._monitored_operation("clear_cache")
    async def clear_cache(self) -> bool:
        """Clear all cached data.

        Returns:
            True if cache cleared successfully
        """
        async with self._lock:
            try:
                # Clear memory cache
                self._schema_cache = None
                self._cache_timestamp = None

                # Clear disk cache
                if self._cache_dir and self._cache_dir.exists():
                    import shutil

                    shutil.rmtree(self._cache_dir)
                    logger.info("Cleared documentation cache")

                return True

            except Exception as e:
                logger.error(f"Failed to clear cache: {e}")
                return False

    def get_cache_info(self) -> dict[str, Any]:
        """Get information about current cache state.

        Returns:
            Cache information
        """
        info = {
            "has_memory_cache": self._schema_cache is not None,
            "cache_timestamp": self._cache_timestamp.isoformat() if self._cache_timestamp else None,
            "cache_dir": str(self._cache_dir) if self._cache_dir else None,
            "cache_ttl_seconds": int(self._cache_ttl.total_seconds()),
        }

        if self._cache_timestamp:
            age = datetime.now() - self._cache_timestamp
            info["cache_age_seconds"] = int(age.total_seconds())
            info["cache_valid"] = age < self._cache_ttl

        return info
