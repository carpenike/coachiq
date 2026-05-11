"""
Enhanced Database Connection Pooling

Optimized connection pooling configuration for different database backends
with performance monitoring and health checks.
"""

import asyncio
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import QueuePool, StaticPool, event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import Pool

from backend.core.structured_logging import get_logger

logger = get_logger(__name__, "DatabasePooling")


class PoolingStrategy(str, Enum):
    """Database connection pooling strategies."""

    STATIC = "static"  # Single connection, good for SQLite
    QUEUE = "queue"  # Connection pool with queue, good for PostgreSQL/MySQL
    NULL = "null"  # No pooling, creates new connections each time
    OPTIMIZED = "optimized"  # Auto-selected based on backend


class ConnectionPoolMetrics:
    """Tracks connection pool performance metrics."""

    def __init__(self):
        """Initialize metrics tracking."""
        self.connections_created = 0
        self.connections_recycled = 0
        self.connections_overflow = 0
        self.connections_failed = 0
        self.wait_times: list[float] = []
        self.connection_durations: list[float] = []
        self.active_connections = 0
        self.peak_connections = 0
        self._lock = asyncio.Lock()

    async def record_connection_created(self) -> None:
        """Record a new connection creation."""
        async with self._lock:
            self.connections_created += 1
            self.active_connections += 1
            self.peak_connections = max(self.peak_connections, self.active_connections)

    async def record_connection_closed(self) -> None:
        """Record a connection closure."""
        async with self._lock:
            self.active_connections = max(0, self.active_connections - 1)

    async def record_wait_time(self, wait_time: float) -> None:
        """Record connection acquisition wait time."""
        async with self._lock:
            self.wait_times.append(wait_time)
            # Keep only last N measurements
            max_samples = 1000
            if len(self.wait_times) > max_samples:
                self.wait_times = self.wait_times[-max_samples:]

    async def record_connection_duration(self, duration: float) -> None:
        """Record how long a connection was held."""
        async with self._lock:
            self.connection_durations.append(duration)
            # Keep only last N measurements
            max_samples = 1000
            if len(self.connection_durations) > max_samples:
                self.connection_durations = self.connection_durations[-max_samples:]

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics snapshot."""
        avg_wait = sum(self.wait_times) / len(self.wait_times) if self.wait_times else 0
        avg_duration = (
            sum(self.connection_durations) / len(self.connection_durations)
            if self.connection_durations
            else 0
        )

        return {
            "connections_created": self.connections_created,
            "connections_recycled": self.connections_recycled,
            "connections_overflow": self.connections_overflow,
            "connections_failed": self.connections_failed,
            "active_connections": self.active_connections,
            "peak_connections": self.peak_connections,
            "avg_wait_time_ms": round(avg_wait * 1000, 2),
            "avg_connection_duration_ms": round(avg_duration * 1000, 2),
            "wait_time_samples": len(self.wait_times),
            "duration_samples": len(self.connection_durations),
        }


class OptimizedConnectionPool:
    """
    Optimized connection pool configuration for different backends.

    Provides backend-specific optimizations and monitoring.
    """

    def __init__(self, backend: str, settings: dict[str, Any] | None = None):
        """
        Initialize optimized connection pool.

        Args:
            backend: Database backend type (sqlite, postgresql, mysql)
            settings: Optional pool settings override
        """
        self.backend = backend.lower()
        self.settings = settings or {}
        self.metrics = ConnectionPoolMetrics()
        self._health_check_interval = 60  # seconds
        self._last_health_check = 0.0

    def get_pool_class(self) -> type[Pool]:
        """
        Get the optimal pool class for the backend.

        Returns:
            SQLAlchemy pool class
        """
        if self.backend == "sqlite":
            # SQLite works best with StaticPool in async mode
            return StaticPool
        if self.backend in ("postgresql", "mysql"):
            # PostgreSQL and MySQL benefit from connection pooling
            return QueuePool
        # Default to QueuePool for unknown backends
        logger.warning(f"Unknown backend {self.backend}, using QueuePool")
        return QueuePool

    def get_pool_config(self) -> dict[str, Any]:
        """
        Get optimized pool configuration for the backend.

        Returns:
            Pool configuration dictionary
        """
        base_config = {}

        if self.backend == "sqlite":
            # SQLite-specific optimizations
            base_config = {
                "poolclass": StaticPool,
                "connect_args": {
                    "check_same_thread": False,
                    "timeout": self.settings.get("timeout", 30),
                },
            }
        elif self.backend == "postgresql":
            # PostgreSQL-specific optimizations
            base_config = {
                "poolclass": QueuePool,
                "pool_size": self.settings.get("pool_size", 10),  # Increased from default 5
                "max_overflow": self.settings.get("max_overflow", 20),  # Increased from default 10
                "pool_timeout": self.settings.get("pool_timeout", 30),
                "pool_recycle": self.settings.get("pool_recycle", 3600),
                "pool_pre_ping": True,  # Test connections before use
                "connect_args": {
                    "server_settings": {
                        "jit": "off",  # Disable JIT for consistent performance
                        "search_path": self.settings.get("schema", "public"),
                    },
                    "command_timeout": self.settings.get("command_timeout", 60),
                    "prepared_statement_cache_size": 0,  # Disable to prevent memory bloat
                    "prepared_statement_name_func": lambda _: None,  # Disable prepared statements
                },
            }
        elif self.backend == "mysql":
            # MySQL-specific optimizations
            base_config = {
                "poolclass": QueuePool,
                "pool_size": self.settings.get("pool_size", 10),
                "max_overflow": self.settings.get("max_overflow", 20),
                "pool_timeout": self.settings.get("pool_timeout", 30),
                "pool_recycle": self.settings.get("pool_recycle", 3600),
                "pool_pre_ping": True,
                "connect_args": {
                    "connect_timeout": self.settings.get("connect_timeout", 10),
                    "read_timeout": self.settings.get("read_timeout", 30),
                    "write_timeout": self.settings.get("write_timeout", 30),
                    "charset": "utf8mb4",
                    "use_unicode": True,
                },
            }

        # Apply user overrides
        base_config.update(self.settings.get("pool_kwargs", {}))

        return base_config

    def setup_engine_events(self, engine: AsyncEngine) -> None:
        """
        Set up engine event listeners for monitoring and optimization.

        Args:
            engine: SQLAlchemy async engine
        """

        # Track connection lifecycle
        @event.listens_for(engine.sync_engine, "connect")
        def on_connect(dbapi_conn, connection_record):
            """Handle new connection creation."""
            connection_record.info["connect_time"] = time.perf_counter()
            # Note: Can't use asyncio.create_task here - not in async context
            # Metrics will be updated via other means

            # Apply backend-specific connection settings
            if self.backend == "postgresql":
                cursor = dbapi_conn.cursor()
                try:
                    # Set statement timeout to prevent long-running queries
                    stmt_timeout = self.settings.get("statement_timeout", 30000)
                    cursor.execute(f"SET statement_timeout = {stmt_timeout}")
                    # Set lock timeout to prevent deadlocks
                    lock_timeout = self.settings.get("lock_timeout", 10000)
                    cursor.execute(f"SET lock_timeout = {lock_timeout}")
                    cursor.close()
                except Exception as e:
                    logger.warning(f"Failed to set PostgreSQL connection parameters: {e}")

        @event.listens_for(engine.sync_engine, "close")
        def on_close(_dbapi_conn, connection_record):
            """Handle connection closure."""
            if "connect_time" in connection_record.info:
                duration = time.perf_counter() - connection_record.info["connect_time"]
                # Note: Can't use asyncio.create_task here - not in async context

        @event.listens_for(engine.sync_engine, "checkout")
        def on_checkout(_dbapi_conn, connection_record, _connection_proxy):
            """Handle connection checkout from pool."""
            connection_record.info["checkout_time"] = time.perf_counter()

        @event.listens_for(engine.sync_engine, "checkin")
        def on_checkin(_dbapi_conn, connection_record):
            """Handle connection checkin to pool."""
            if "checkout_time" in connection_record.info:
                duration = time.perf_counter() - connection_record.info["checkout_time"]
                logger.debug(f"Connection held for {duration:.3f}s")

    async def create_optimized_engine(
        self,
        database_url: str,
        **engine_kwargs: Any,
    ) -> AsyncEngine:
        """
        Create an optimized async engine with monitoring.

        Args:
            database_url: Database connection URL
            **engine_kwargs: Additional engine arguments

        Returns:
            Configured AsyncEngine
        """
        # Get optimized pool configuration
        pool_config = self.get_pool_config()

        # Merge with provided kwargs
        final_kwargs = {**pool_config, **engine_kwargs}

        # Add performance monitoring settings
        final_kwargs.update(
            {
                "query_cache_size": 1200,  # Cache parsed SQL statements
                "echo_pool": logger.logger.isEnabledFor(10),  # Echo pool events in debug mode
            }
        )

        pool_size = final_kwargs.get("pool_size", "N/A")
        logger.info(
            f"Creating optimized engine for {self.backend} with pool_size={pool_size}"
        )

        # Create engine
        engine = create_async_engine(database_url, **final_kwargs)

        # Set up monitoring
        self.setup_engine_events(engine)

        return engine

    async def check_pool_health(self, engine: AsyncEngine) -> dict[str, Any]:
        """
        Check connection pool health and performance.

        Args:
            engine: Database engine to check

        Returns:
            Health status dictionary
        """
        current_time = time.time()

        # Rate limit health checks
        if current_time - self._last_health_check < self._health_check_interval:
            return {"status": "skipped", "reason": "rate_limited"}

        self._last_health_check = current_time

        health_status = {
            "timestamp": datetime.now(UTC).isoformat(),
            "backend": self.backend,
            "pool_metrics": self.metrics.get_metrics(),
            "checks": {},
        }

        # Test connection acquisition time
        start_time = time.perf_counter()
        try:
            async with engine.connect() as conn:
                acquisition_time = time.perf_counter() - start_time
                await self.metrics.record_wait_time(acquisition_time)

                health_status["checks"]["connection_acquisition_ms"] = round(
                    acquisition_time * 1000, 2
                )
                health_status["checks"]["connection_healthy"] = True

                # Backend-specific health checks
                if self.backend == "postgresql":
                    # Check PostgreSQL specific metrics
                    result = await conn.execute(
                        text(
                            "SELECT count(*) as total, "
                            "sum(CASE WHEN state = 'active' THEN 1 ELSE 0 END) as active, "
                            "sum(CASE WHEN state = 'idle' THEN 1 ELSE 0 END) as idle "
                            "FROM pg_stat_activity WHERE datname = current_database()"
                        )
                    )
                    row = result.first()
                    if row:
                        health_status["checks"]["postgres_connections"] = {
                            "total": row.total,
                            "active": row.active,
                            "idle": row.idle,
                        }

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            health_status["checks"]["connection_healthy"] = False
            health_status["checks"]["error"] = str(e)
            self.metrics.connections_failed += 1

        # Analyze metrics for warnings
        metrics = health_status["pool_metrics"]
        warnings = []

        wait_threshold = 100
        if metrics["avg_wait_time_ms"] > wait_threshold:
            warnings.append(f"High average wait time: {metrics['avg_wait_time_ms']}ms")

        failure_threshold = 10
        if metrics["connections_failed"] > failure_threshold:
            warnings.append(f"High failure count: {metrics['connections_failed']}")

        pool_size_multiplier = 1.5
        if metrics["peak_connections"] > self.settings.get("pool_size", 10) * pool_size_multiplier:
            warnings.append(
                f"Peak connections ({metrics['peak_connections']}) exceeds optimal range"
            )

        health_status["warnings"] = warnings
        health_status["healthy"] = len(warnings) == 0 and health_status["checks"].get(
            "connection_healthy", False
        )

        return health_status


def create_optimized_pool(
    backend: str, settings: dict[str, Any] | None = None
) -> OptimizedConnectionPool:
    """
    Factory function to create an optimized connection pool.

    Args:
        backend: Database backend type
        settings: Optional pool settings

    Returns:
        Configured OptimizedConnectionPool
    """
    return OptimizedConnectionPool(backend, settings)


# Pool configuration presets for common scenarios
POOL_PRESETS = {
    "development": {
        "pool_size": 5,
        "max_overflow": 5,
        "pool_timeout": 30,
        "pool_recycle": 3600,
    },
    "production": {
        "pool_size": 20,
        "max_overflow": 40,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    },
    "high_performance": {
        "pool_size": 50,
        "max_overflow": 100,
        "pool_timeout": 10,
        "pool_recycle": 900,
        "pool_pre_ping": True,
    },
    "low_resource": {
        "pool_size": 2,
        "max_overflow": 3,
        "pool_timeout": 60,
        "pool_recycle": 7200,
    },
}


def get_pool_preset(preset_name: str) -> dict[str, Any]:
    """
    Get a predefined pool configuration preset.

    Args:
        preset_name: Name of the preset (development, production, high_performance, low_resource)

    Returns:
        Pool configuration dictionary
    """
    return POOL_PRESETS.get(preset_name, POOL_PRESETS["production"]).copy()
