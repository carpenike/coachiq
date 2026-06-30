"""Vector repository backed by sqlite-vec.

Phase 0 of the knowledge subsystem proves and initializes the local vector
substrate without adding ingestion or search-ranking behavior yet. The repository
therefore creates a real sqlite-vec store, reports whether it is loadable, and
returns an empty result set until Phase 1 adds document ingestion.
"""

# ruff: noqa: SLF001

import importlib
import logging
import sqlite3
from pathlib import Path
from typing import Any, override

from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)

VECTOR_TABLE_NAME = "vec_documents"
METADATA_TABLE_NAME = "vector_documents"
DEFAULT_VECTOR_DIMENSION = 384
DEFAULT_DATABASE_FILENAME = "vector_store.db"


class VectorRepository(MonitoredRepository):
    """Repository for vector search data management."""

    def __init__(self, database_manager: Any, performance_monitor: Any):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # Status tracking
        self._index_path: str | None = None
        self._database_path: Path | None = None
        self._connection: sqlite3.Connection | None = None
        self._is_initialized = False
        self._initialization_error: str | None = "Vector store has not been initialized"

    def _resolve_database_path(self, index_path: str) -> Path:
        """Resolve an index path to a concrete sqlite database file path."""
        path = Path(index_path).expanduser()
        if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            return path
        return path / DEFAULT_DATABASE_FILENAME

    def _load_sqlite_vec(self, connection: sqlite3.Connection) -> str:
        """Load sqlite-vec into a sqlite connection and return its version."""
        sqlite_vec = importlib.import_module("sqlite_vec")
        connection.enable_load_extension(True)
        try:
            sqlite_vec.load(connection)
        finally:
            connection.enable_load_extension(False)

        version_row = connection.execute("select vec_version()").fetchone()
        return str(version_row[0]) if version_row else "unknown"

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        """Create the Phase-0 sqlite-vec schema if it does not exist."""
        connection.execute(
            """
            create virtual table if not exists vec_documents
            using vec0(embedding float[384])
            """
        )
        connection.execute(
            """
            create table if not exists vector_documents (
                rowid integer primary key,
                document_id text,
                content text,
                metadata_json text,
                created_at text not null default current_timestamp
            )
            """
        )
        connection.commit()

    @MonitoredRepository._monitored_operation("set_index_path")
    async def set_index_path(self, index_path: str | None) -> bool:
        """Set the vector index path.

        Args:
            index_path: Path to the vector index

        Returns:
            True if set successfully
        """
        self._index_path = index_path
        logger.info("Vector index path set to: %s", index_path or "not configured")
        return True

    @MonitoredRepository._monitored_operation("get_index_path")
    async def get_index_path(self) -> str | None:
        """Get the current index path.

        Returns:
            Index path or None
        """
        return self._index_path

    @MonitoredRepository._monitored_operation("is_available")
    async def is_available(self) -> bool:
        """Check if the sqlite-vec store is initialized and queryable.

        Returns:
            True when sqlite-vec is loaded and the vector table exists.
        """
        if not self._is_initialized or self._connection is None:
            return False

        try:
            self._connection.execute("select vec_version()").fetchone()
            table_row = self._connection.execute(
                "select name from sqlite_master where type = 'table' and name = ?",
                (VECTOR_TABLE_NAME,),
            ).fetchone()
            return table_row is not None
        except sqlite3.Error as exc:
            self._initialization_error = f"Vector store availability check failed: {exc}"
            self._is_initialized = False
            return False

    @MonitoredRepository._monitored_operation("get_status")
    async def get_status(self) -> dict[str, Any]:
        """Get vector service status.

        Returns:
            Status dictionary
        """
        stats = await self.get_index_stats()
        return {
            "status": "available" if self._is_initialized else "unavailable",
            "error": None if self._is_initialized else self._initialization_error,
            "index_path": self._index_path or "not configured",
            "database_path": str(self._database_path) if self._database_path else None,
            "initialized": self._is_initialized,
            "backend": "sqlite-vec",
            **stats,
        }

    @MonitoredRepository._monitored_operation("search")
    async def search(self, _query: str, _k: int = 3) -> list[dict[str, Any]]:
        """Perform similarity search.

        Args:
            _query: Search query
            _k: Number of results

        Returns:
            Search results. Empty until Phase 1 adds ingestion/query embeddings.
        """
        if not self._is_initialized:
            return []

        # Phase 0 proves substrate availability only. Ingestion and actual vector
        # similarity queries are introduced in the deterministic/retrieval phases.
        return []

    @MonitoredRepository._monitored_operation("initialize_index")
    async def initialize_index(self, index_path: str) -> bool:
        """Initialize vector index.

        Args:
            index_path: Path to index

        Returns:
            True when sqlite-vec loads and the vector table is created.
        """
        self._index_path = index_path
        self._database_path = self._resolve_database_path(index_path)
        logger.info("Initializing sqlite-vec store at: %s", self._database_path)

        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            if self._connection is not None:
                self._connection.close()

            connection = sqlite3.connect(str(self._database_path))
            vec_version = self._load_sqlite_vec(connection)
            self._ensure_schema(connection)

            self._connection = connection
            self._is_initialized = True
            self._initialization_error = None
            logger.info(
                "sqlite-vec store initialized at %s (version %s)",
                self._database_path,
                vec_version,
            )
            return True
        except Exception as exc:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            self._is_initialized = False
            self._initialization_error = f"sqlite-vec initialization failed: {exc}"
            logger.exception("Failed to initialize sqlite-vec store at %s", self._database_path)
            return False

    @MonitoredRepository._monitored_operation("add_documents")
    async def add_documents(self, _documents: list[dict[str, Any]]) -> int:
        """Add documents to index.

        Args:
            _documents: Documents to add

        Returns:
            Number of documents added (0 for stub)
        """
        if not self._is_initialized:
            logger.warning("Cannot add documents - vector index not initialized")
            return 0

        # Phase 0 does not implement ingestion. The real substrate exists, but
        # document chunk storage belongs to the deterministic tier phase.
        return 0

    @MonitoredRepository._monitored_operation("clear_index")
    async def clear_index(self) -> bool:
        """Clear the vector index.

        Returns:
            True if cleared
        """
        if self._connection is None:
            return True

        self._connection.execute("delete from vec_documents")
        self._connection.execute("delete from vector_documents")
        self._connection.commit()
        logger.info("Vector index cleared")
        return True

    @MonitoredRepository._monitored_operation("get_index_stats")
    async def get_index_stats(self) -> dict[str, Any]:
        """Get index statistics.

        Returns:
            Statistics dictionary
        """
        document_count = 0
        if self._connection is not None and self._is_initialized:
            try:
                row = self._connection.execute("select count(*) from vec_documents").fetchone()
                document_count = int(row[0]) if row else 0
            except sqlite3.Error as exc:
                logger.warning("Unable to read vector index stats: %s", exc)

        return {
            "document_count": document_count,
            "index_size_bytes": (
                self._database_path.stat().st_size
                if self._database_path and self._database_path.exists()
                else 0
            ),
            "last_updated": None,
            "is_initialized": self._is_initialized,
            "vector_dimension": DEFAULT_VECTOR_DIMENSION,
            "vector_table": VECTOR_TABLE_NAME,
        }

    @override
    async def cleanup(self) -> None:
        """Close the sqlite connection held by the repository."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._is_initialized = False
