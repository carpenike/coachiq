"""
Vector service for the CoachIQ backend.

This service provides a consistent async interface for vector search
functionality. Phase 0 initializes the sqlite-vec substrate; document ingestion
and non-empty search results arrive in later knowledge subsystem phases.
"""

import logging
from typing import Any

from backend.core.performance import PerformanceMonitor
from backend.repositories.vector_repository import VectorRepository

logger = logging.getLogger(__name__)


class VectorService:
    """
    Service for managing vector embeddings and semantic search.

    Service for status, initialization, and search calls against the vector
    repository.
    """

    def __init__(
        self,
        vector_repository: VectorRepository,
        performance_monitor: PerformanceMonitor,
        index_path: str | None = None,
    ) -> None:
        """
        Initialize the vector service.

        Args:
            vector_repository: Repository for vector data
            performance_monitor: Performance monitoring instance
            index_path: Path to the vector index (currently unused)
        """
        self._repository = vector_repository
        self._monitor = performance_monitor
        self.index_path = index_path
        self._set_index_path_task: object | None = None

        # Apply performance monitoring
        self._apply_monitoring()

        # Set index path in repository if provided
        if index_path:
            import asyncio

            self._set_index_path_task = asyncio.create_task(
                self._repository.set_index_path(index_path)
            )

        logger.info("VectorService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.is_available = self._monitor.monitor_service_method("VectorService", "is_available")(
            self.is_available
        )

        self.similarity_search = self._monitor.monitor_service_method(
            "VectorService", "similarity_search"
        )(self.similarity_search)

    async def is_available(self) -> bool:
        """
        Check if the vector service is available.

        Returns:
            True when the underlying vector repository is initialized.
        """
        return await self._repository.is_available()

    async def get_status(self) -> dict[str, Any]:
        """
        Get the status of the vector service.

        Returns:
            Dictionary with vector-store status information.
        """
        return await self._repository.get_status()

    async def similarity_search(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        """
        Perform a similarity search.

        Args:
            query: Search query
            k: Number of results to return

        Returns:
            Search results. Empty until document ingestion is implemented.
        """
        return await self._repository.search(query, k)

    async def initialize_index(self, index_path: str) -> bool:
        """
        Initialize the vector index.

        Args:
            index_path: Path to the index

        Returns:
            True when the repository initializes the vector store.
        """
        return await self._repository.initialize_index(index_path)

    async def get_index_stats(self) -> dict[str, Any]:
        """
        Get index statistics.

        Returns:
            Statistics dictionary
        """
        return await self._repository.get_index_stats()
