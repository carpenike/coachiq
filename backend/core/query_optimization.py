"""
Query Optimization for Raspberry Pi Deployment

Lightweight query optimization specifically designed for SQLite on Raspberry Pi 4
with minimal resource usage and fast response times for <5 concurrent users.
"""

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.structured_logging import get_logger

logger = get_logger(__name__, "QueryOptimization")

F = TypeVar("F", bound=Callable[..., Any])

# Query timing threshold for slow query logging (ms)
SLOW_QUERY_THRESHOLD_MS = 100  # 100ms is slow for local SQLite

# Query truncation length for display
QUERY_TRUNCATE_LENGTH = 100

# Bulk insert threshold
BULK_INSERT_THRESHOLD = 10


class QueryOptimizer:
    """
    Lightweight query optimizer for SQLite on Raspberry Pi.

    Focuses on:
    - Minimal memory usage
    - Fast response times
    - Simple but effective optimizations
    """

    def __init__(self):
        """Initialize query optimizer."""
        self.slow_queries: list[dict[str, Any]] = []
        self._max_slow_queries = 50  # Keep only recent slow queries

    def analyze_slow_query(
        self, query: str, duration_ms: float, params: dict[str, Any] | None = None
    ) -> None:
        """
        Analyze and log slow queries for optimization.

        Args:
            query: SQL query string
            duration_ms: Query execution time in milliseconds
            params: Query parameters
        """
        slow_query_info = {
            "query": query[:500],  # Truncate long queries
            "duration_ms": round(duration_ms, 2),
            "timestamp": time.time(),
            "params_count": len(params) if params else 0,
        }

        # Identify query type
        query_upper = query.upper().strip()
        if query_upper.startswith("SELECT"):
            slow_query_info["type"] = "SELECT"
            # Check for common issues
            if "JOIN" in query_upper:
                slow_query_info["has_joins"] = True
            if "ORDER BY" in query_upper:
                slow_query_info["has_order_by"] = True
            if "LIKE" in query_upper:
                slow_query_info["has_like"] = True
        elif query_upper.startswith("INSERT"):
            slow_query_info["type"] = "INSERT"
        elif query_upper.startswith("UPDATE"):
            slow_query_info["type"] = "UPDATE"
        elif query_upper.startswith("DELETE"):
            slow_query_info["type"] = "DELETE"

        self.slow_queries.append(slow_query_info)

        # Keep only recent queries to minimize memory usage
        if len(self.slow_queries) > self._max_slow_queries:
            self.slow_queries = self.slow_queries[-self._max_slow_queries:]

        logger.warning(
            f"Slow query detected: {duration_ms}ms - {query[:QUERY_TRUNCATE_LENGTH] + '...' if len(query) > QUERY_TRUNCATE_LENGTH else query}"
        )

    def get_optimization_suggestions(self) -> list[str]:
        """
        Get optimization suggestions based on slow query analysis.

        Returns:
            List of optimization suggestions
        """
        if not self.slow_queries:
            return ["No slow queries detected"]

        suggestions = []

        # Analyze patterns
        select_queries = [q for q in self.slow_queries if q.get("type") == "SELECT"]
        if select_queries:
            # Check for missing indexes on JOINs
            join_queries = [q for q in select_queries if q.get("has_joins")]
            if len(join_queries) > len(select_queries) * 0.3:
                suggestions.append("Consider adding indexes on foreign key columns used in JOINs")

            # Check for ORDER BY without indexes
            order_queries = [q for q in select_queries if q.get("has_order_by")]
            if len(order_queries) > len(select_queries) * 0.5:
                suggestions.append("Consider adding indexes on columns used in ORDER BY clauses")

            # Check for LIKE queries
            like_queries = [q for q in select_queries if q.get("has_like")]
            if like_queries:
                suggestions.append("LIKE queries detected - consider using FTS5 for text search")

        # Check for bulk operations
        insert_queries = [q for q in self.slow_queries if q.get("type") == "INSERT"]
        if len(insert_queries) > BULK_INSERT_THRESHOLD:
            suggestions.append("Multiple INSERT queries detected - consider using bulk inserts")

        return suggestions if suggestions else ["No specific optimization patterns detected"]


# Global query optimizer instance
_query_optimizer = QueryOptimizer()


def track_query_performance(func: F) -> F:
    """
    Decorator to track query performance for async functions.

    Args:
        func: Async function that executes queries

    Returns:
        Wrapped function with performance tracking
    """
    @wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            if duration_ms > SLOW_QUERY_THRESHOLD_MS:
                # Try to extract query info from args
                query_info = "Unknown query"
                if args and hasattr(args[0], "__class__"):
                    query_info = f"{args[0].__class__.__name__}.{func.__name__}"

                _query_optimizer.analyze_slow_query(query_info, duration_ms)

    return async_wrapper  # type: ignore[return-value]


async def create_essential_indexes(session: AsyncSession) -> None:
    """
    Create essential indexes for Raspberry Pi deployment.

    Only creates indexes that provide significant performance benefits
    for the most common queries in an RV control system.

    Args:
        session: Database session
    """
    logger.debug("Creating essential indexes for Raspberry Pi deployment")

    # Essential indexes for RV control system
    indexes = [
        # Entity queries - most common operation
        "CREATE INDEX IF NOT EXISTS idx_entities_instance_id ON entities(entity_instance_id)",
        "CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)",
        "CREATE INDEX IF NOT EXISTS idx_entities_active ON entities(is_active)",

        # Entity state tracking
        "CREATE INDEX IF NOT EXISTS idx_entity_states_entity_id ON entity_states(entity_id)",
        "CREATE INDEX IF NOT EXISTS idx_entity_states_timestamp ON entity_states(timestamp)",

        # Auth queries - minimal but necessary
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
        "CREATE INDEX IF NOT EXISTS idx_sessions_token ON auth_sessions(session_token)",
        "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON auth_sessions(expires_at)",

        # Audit log - only recent queries matter
        "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON security_audit_logs(timestamp)",

        # Composite indexes for common query patterns
        "CREATE INDEX IF NOT EXISTS idx_entities_type_active ON entities(entity_type, is_active)",
    ]

    for index_sql in indexes:
        try:
            # Extract table name from the SQL to check if it exists
            table_name = index_sql.split(" ON ")[1].split("(")[0].strip()
            
            # Check if table exists first
            table_check = await session.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
            ), {"table_name": table_name})
            
            if table_check.fetchone():
                await session.execute(text(index_sql))
                logger.debug(f"Index created/verified: {index_sql.split('idx_')[1].split(' ')[0]}")
            else:
                logger.debug(f"Skipping index creation for non-existent table: {table_name}")
        except Exception as e:
            logger.debug(f"Failed to create index (table may not exist): {index_sql.split('idx_')[1].split(' ')[0]} - {e}")

    # SQLite-specific optimizations
    sqlite_optimizations = [
        "PRAGMA optimize",  # Let SQLite optimize query planner
        "PRAGMA analysis_limit=400",  # Limit ANALYZE time for RPi
        "ANALYZE",  # Update query planner statistics
    ]

    for pragma in sqlite_optimizations:
        try:
            await session.execute(text(pragma))
            logger.debug(f"SQLite optimization applied: {pragma}")
        except Exception as e:
            logger.warning(f"SQLite optimization failed: {pragma} - {e}")

    await session.commit()
    logger.debug("Essential indexes created successfully")


async def optimize_entity_queries(session: AsyncSession) -> None:
    """
    Optimize entity-related queries specifically.

    Since entity queries are the most common in an RV control system,
    we optimize these specifically for fast access.

    Args:
        session: Database session
    """
    # Create covering index for entity listing queries
    covering_index = """
    CREATE INDEX IF NOT EXISTS idx_entities_covering
    ON entities(entity_type, is_active, entity_instance_id, name, current_value)
    """

    try:
        await session.execute(text(covering_index))
        logger.info("Created covering index for entity queries")
    except Exception as e:
        logger.error(f"Failed to create covering index: {e}")


def setup_query_monitoring(engine: Any) -> None:
    """
    Set up query monitoring for the database engine.

    Args:
        engine: SQLAlchemy engine
    """
    @event.listens_for(engine.sync_engine, "before_execute")
    def receive_before_execute(conn, _clauseelement, _multiparams, _params):
        conn.info.setdefault("query_start_time", []).append(time.perf_counter())

    @event.listens_for(engine.sync_engine, "after_execute")
    def receive_after_execute(conn, clauseelement, _multiparams, params, _result):
        total_time = time.perf_counter() - conn.info["query_start_time"].pop(-1)
        duration_ms = total_time * 1000

        if duration_ms > SLOW_QUERY_THRESHOLD_MS:
            query_str = str(clauseelement)
            _query_optimizer.analyze_slow_query(query_str, duration_ms, params)


# Raspberry Pi specific query patterns
class RPiQueryPatterns:
    """Query patterns optimized for Raspberry Pi deployment."""

    @staticmethod
    def entity_list_query() -> str:
        """Optimized query for listing entities."""
        return """
        SELECT entity_instance_id, name, entity_type, current_value, is_active
        FROM entities
        WHERE is_active = 1
        ORDER BY entity_type, name
        """

    @staticmethod
    def entity_state_query() -> str:
        """Optimized query for getting entity states."""
        return """
        SELECT e.entity_instance_id, e.name, e.current_value,
               es.timestamp, es.value, es.raw_value
        FROM entities e
        LEFT JOIN entity_states es ON e.id = es.entity_id
        WHERE e.is_active = 1
        AND (es.id IS NULL OR es.id = (
            SELECT id FROM entity_states
            WHERE entity_id = e.id
            ORDER BY timestamp DESC
            LIMIT 1
        ))
        """

    @staticmethod
    def recent_changes_query(_hours: int = 1) -> str:
        """Optimized query for recent entity changes.

        Note: The hours parameter would be used in actual query execution
        as a bound parameter, not string interpolation.
        """
        # Using parameterized query pattern (hours would be a parameter in actual usage)
        return """
        SELECT e.entity_instance_id, e.name, es.timestamp, es.value
        FROM entity_states es
        INNER JOIN entities e ON es.entity_id = e.id
        WHERE es.timestamp > datetime('now', '-' || ? || ' hours')
        ORDER BY es.timestamp DESC
        LIMIT 100
        """


def get_query_optimizer() -> QueryOptimizer:
    """Get the global query optimizer instance."""
    return _query_optimizer
