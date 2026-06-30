"""Tests for the sqlite-vec backed vector repository."""

from pathlib import Path

import pytest

from backend.repositories.vector_repository import VectorRepository


@pytest.fixture
def repository() -> VectorRepository:
    """Build a VectorRepository without monitoring for focused substrate tests."""
    return VectorRepository(database_manager=None, performance_monitor=None)


@pytest.mark.asyncio
async def test_uninitialized_repository_is_unavailable(repository: VectorRepository) -> None:
    """An uninitialized repository is unavailable but does not raise on search."""
    assert await repository.is_available() is False
    assert await repository.search("black tank capacity") == []


@pytest.mark.asyncio
async def test_initialize_index_creates_sqlite_vec_store(
    repository: VectorRepository, tmp_path: Path
) -> None:
    """Initializing creates a sqlite database and an empty vec0 table."""
    db_path = tmp_path / "knowledge_vectors.sqlite3"

    assert await repository.initialize_index(str(db_path)) is True

    assert await repository.is_available() is True
    assert await repository.search("black tank capacity") == []

    status = await repository.get_status()
    assert status["status"] == "available"
    assert status["backend"] == "sqlite-vec"
    assert status["document_count"] == 0
    assert status["database_path"] == str(db_path)


@pytest.mark.asyncio
async def test_initialize_index_accepts_directory_path(
    repository: VectorRepository, tmp_path: Path
) -> None:
    """A directory-style index path resolves to the default sqlite store file."""
    index_dir = tmp_path / "vectors"

    assert await repository.initialize_index(str(index_dir)) is True

    status = await repository.get_status()
    assert status["database_path"] == str(index_dir / "vector_store.db")
    assert (index_dir / "vector_store.db").exists()


@pytest.mark.asyncio
async def test_cleanup_closes_store(repository: VectorRepository, tmp_path: Path) -> None:
    """Cleanup closes the active connection and marks the repository unavailable."""
    assert await repository.initialize_index(str(tmp_path / "vectors.sqlite3")) is True

    await repository.cleanup()

    assert await repository.is_available() is False
