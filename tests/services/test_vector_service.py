"""
Tests for the vector service.

The VectorService is a thin async facade over VectorRepository, with
performance monitoring applied to its public methods. These tests verify
the delegation contract — the repository is fully mocked.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.performance import PerformanceMonitor
from backend.services.vector_service import VectorService


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Build a mock VectorRepository with sensible async stubs."""
    repo = AsyncMock()
    repo.is_available = AsyncMock(return_value=False)
    repo.get_status = AsyncMock(
        return_value={"status": "unavailable", "error": "stub", "index_path": "not configured"}
    )
    repo.search = AsyncMock(return_value=[])
    repo.initialize_index = AsyncMock(return_value=False)
    repo.get_index_stats = AsyncMock(return_value={"total_documents": 0})
    repo.set_index_path = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_monitor() -> MagicMock:
    """Build a no-op PerformanceMonitor that returns the wrapped fn unchanged."""
    monitor = MagicMock(spec=PerformanceMonitor)
    # monitor_service_method is a decorator factory; make it a passthrough.
    monitor.monitor_service_method = MagicMock(return_value=lambda fn: fn)
    return monitor


class TestVectorServiceConstruction:
    """The service stores its dependencies and forwards index_path to the repo."""

    def test_init_without_index_path(self, mock_repository, mock_monitor):
        service = VectorService(
            vector_repository=mock_repository, performance_monitor=mock_monitor
        )

        assert service.index_path is None
        # No background task should be scheduled when index_path is omitted.
        mock_repository.set_index_path.assert_not_called()

    def test_init_applies_monitoring(self, mock_repository, mock_monitor):
        VectorService(vector_repository=mock_repository, performance_monitor=mock_monitor)

        # _apply_monitoring wraps is_available and similarity_search.
        assert mock_monitor.monitor_service_method.call_count >= 2


class TestVectorServiceDelegation:
    """Each public method just awaits the matching repository method."""

    @pytest.mark.asyncio
    async def test_is_available_delegates_to_repository(self, mock_repository, mock_monitor):
        mock_repository.is_available.return_value = True
        service = VectorService(
            vector_repository=mock_repository, performance_monitor=mock_monitor
        )

        result = await service.is_available()

        assert result is True
        mock_repository.is_available.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_status_delegates_to_repository(self, mock_repository, mock_monitor):
        expected: dict[str, Any] = {
            "status": "ok",
            "error": "",
            "index_path": "/var/lib/coachiq/vectors",
        }
        mock_repository.get_status.return_value = expected
        service = VectorService(
            vector_repository=mock_repository, performance_monitor=mock_monitor
        )

        result = await service.get_status()

        assert result == expected
        mock_repository.get_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_similarity_search_delegates_with_default_k(
        self, mock_repository, mock_monitor
    ):
        mock_repository.search.return_value = [{"id": "doc-1", "score": 0.9}]
        service = VectorService(
            vector_repository=mock_repository, performance_monitor=mock_monitor
        )

        results = await service.similarity_search("hello world")

        assert results == [{"id": "doc-1", "score": 0.9}]
        mock_repository.search.assert_awaited_once_with("hello world", 3)

    @pytest.mark.asyncio
    async def test_similarity_search_passes_through_k(self, mock_repository, mock_monitor):
        service = VectorService(
            vector_repository=mock_repository, performance_monitor=mock_monitor
        )

        await service.similarity_search("query", k=10)

        mock_repository.search.assert_awaited_once_with("query", 10)

    @pytest.mark.asyncio
    async def test_initialize_index_delegates_to_repository(
        self, mock_repository, mock_monitor
    ):
        mock_repository.initialize_index.return_value = True
        service = VectorService(
            vector_repository=mock_repository, performance_monitor=mock_monitor
        )

        result = await service.initialize_index("/some/path")

        assert result is True
        mock_repository.initialize_index.assert_awaited_once_with("/some/path")

    @pytest.mark.asyncio
    async def test_get_index_stats_delegates_to_repository(
        self, mock_repository, mock_monitor
    ):
        expected = {"total_documents": 42, "size_bytes": 1024}
        mock_repository.get_index_stats.return_value = expected
        service = VectorService(
            vector_repository=mock_repository, performance_monitor=mock_monitor
        )

        result = await service.get_index_stats()

        assert result == expected
        mock_repository.get_index_stats.assert_awaited_once()
