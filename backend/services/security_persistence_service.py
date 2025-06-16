"""
Security Persistence Service

High-performance database persistence for security events with batch processing
and SQLite optimization. Designed to handle high-volume attack scenarios (570+ msg/sec).
"""

import asyncio
import contextlib
import logging
import time
from collections import deque
from typing import Any

from backend.models.security_events import SecurityEvent
from backend.models.security_events_db import SecurityEventDB
from backend.services.database_manager import DatabaseManager
from backend.services.feature_base import Feature
from backend.services.security_event_manager import get_security_event_manager

logger = logging.getLogger(__name__)

# Performance monitoring constants
MIN_EVENTS_FOR_ERROR_RATE_CHECK = 100
DEGRADED_ERROR_RATE_THRESHOLD = 0.05  # 5%
FAILED_ERROR_RATE_THRESHOLD = 0.1     # 10%


class SecurityEventBatch:
    """
    Batch container for security events with performance tracking.

    Manages a collection of events for efficient batch insertion
    with timing and size constraints.
    """

    def __init__(self, max_size: int = 100, max_age_seconds: float = 5.0):
        """
        Initialize event batch.

        Args:
            max_size: Maximum number of events in batch
            max_age_seconds: Maximum age before forcing flush
        """
        self.events: deque[SecurityEvent] = deque()
        self.max_size = max_size
        self.max_age_seconds = max_age_seconds
        self.created_at = time.time()

    def add_event(self, event: SecurityEvent) -> bool:
        """
        Add event to batch.

        Args:
            event: SecurityEvent to add

        Returns:
            True if batch should be flushed (full or expired)
        """
        self.events.append(event)

        # Check if batch should be flushed
        return (
            len(self.events) >= self.max_size
            or (time.time() - self.created_at) >= self.max_age_seconds
        )

    def is_empty(self) -> bool:
        """Check if batch is empty."""
        return len(self.events) == 0

    def is_expired(self) -> bool:
        """Check if batch has exceeded max age."""
        return (time.time() - self.created_at) >= self.max_age_seconds

    def clear(self) -> list[SecurityEvent]:
        """
        Clear batch and return events.

        Returns:
            List of events that were in the batch
        """
        events = list(self.events)
        self.events.clear()
        self.created_at = time.time()
        return events


class SecurityPersistenceService(Feature):
    """
    High-performance security event persistence service.

    Features:
    - Batch processing for SQLite optimization (handles 570+ msg/sec)
    - Automatic table creation and schema management
    - Performance monitoring and statistics
    - Graceful degradation on database errors
    - Observer pattern integration with SecurityEventManager
    """

    def __init__(
        self,
        name: str = "security_persistence",
        enabled: bool = True,
        core: bool = True,
        database_manager: DatabaseManager | None = None,
        batch_size: int = 100,
        batch_timeout: float = 5.0,
        flush_interval: float = 1.0,
        **kwargs,
    ):
        """
        Initialize security persistence service.

        Args:
            name: Feature name
            enabled: Whether feature is enabled
            core: Whether this is a core feature
            database_manager: Database manager instance
            batch_size: Number of events per batch
            batch_timeout: Maximum age of batch before flush (seconds)
            flush_interval: Interval between flush checks (seconds)
            **kwargs: Additional feature configuration
        """
        super().__init__(name=name, enabled=enabled, core=core, **kwargs)

        self.database_manager = database_manager
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.flush_interval = flush_interval

        # Batch management
        self.current_batch = SecurityEventBatch(batch_size, batch_timeout)
        self.pending_batches: asyncio.Queue[SecurityEventBatch] = asyncio.Queue()

        # Background tasks
        self._flush_task: asyncio.Task | None = None
        self._processor_task: asyncio.Task | None = None

        # Performance tracking
        self._stats = {
            "events_received": 0,
            "events_persisted": 0,
            "batches_processed": 0,
            "database_errors": 0,
            "avg_batch_size": 0.0,
            "avg_flush_time_ms": 0.0,
            "start_time": time.time(),
        }

        # Performance timing
        self._flush_times: deque[float] = deque(maxlen=100)
        self._batch_sizes: deque[int] = deque(maxlen=100)


        logger.info(
            "SecurityPersistenceService initialized: batch_size=%d, batch_timeout=%.1fs",
            batch_size, batch_timeout
        )

    async def startup(self) -> None:
        """Start the persistence service."""
        logger.info("Starting security persistence service")

        if not self.database_manager:
            logger.warning("No database manager provided - creating default")
            self.database_manager = DatabaseManager()

        # Initialize database if needed
        if not await self.database_manager.initialize():
            logger.error("Failed to initialize database manager")
            return

        # Security events table will be created by Alembic migrations
        # No need to create manually since we're using SQLAlchemy models

        # Register with SecurityEventManager
        try:
            event_manager = get_security_event_manager()
            event_manager.register_listener(
                self._handle_security_event, name="security_persistence"
            )
            logger.info("Registered as security event listener")
        except Exception as e:
            logger.error("Failed to register with SecurityEventManager: %s", e)

        # Start background tasks
        self._flush_task = asyncio.create_task(
            self._flush_monitor_loop(), name="security_persistence_flush"
        )

        self._processor_task = asyncio.create_task(
            self._batch_processor_loop(), name="security_persistence_processor"
        )

        logger.info("Security persistence service started")

    async def shutdown(self) -> None:
        """Shutdown the persistence service."""
        logger.info("Shutting down security persistence service")

        # Cancel background tasks
        if self._flush_task:
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task

        if self._processor_task:
            self._processor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._processor_task

        # Flush any remaining events
        await self._flush_current_batch()
        await self._process_pending_batches()

        # Log final statistics
        uptime = time.time() - self._stats["start_time"]
        logger.info(
            "SecurityPersistenceService final stats: "
            "uptime=%.1fs, events_received=%d, events_persisted=%d, "
            "batches_processed=%d, database_errors=%d",
            uptime, self._stats["events_received"], self._stats["events_persisted"],
            self._stats["batches_processed"], self._stats["database_errors"]
        )

        logger.info("Security persistence service stopped")

    async def _handle_security_event(self, event: SecurityEvent) -> None:
        """
        Handle incoming security event from SecurityEventManager.

        Args:
            event: SecurityEvent to persist
        """
        try:
            self._stats["events_received"] += 1

            # Add to current batch
            should_flush = self.current_batch.add_event(event)

            if should_flush:
                await self._flush_current_batch()

        except Exception as e:
            logger.error("Error handling security event: %s", e)

    async def _flush_current_batch(self) -> None:
        """Flush current batch to processing queue."""
        if self.current_batch.is_empty():
            return

        # Move current batch to processing queue
        await self.pending_batches.put(self.current_batch)

        # Create new batch
        self.current_batch = SecurityEventBatch(self.batch_size, self.batch_timeout)

    async def _flush_monitor_loop(self) -> None:
        """Monitor batch age and flush expired batches."""
        logger.debug("Starting flush monitor loop")

        try:
            while True:
                await asyncio.sleep(self.flush_interval)

                if self.current_batch.is_expired() and not self.current_batch.is_empty():
                    logger.debug("Flushing expired batch")
                    await self._flush_current_batch()

        except asyncio.CancelledError:
            logger.debug("Flush monitor loop cancelled")
            raise
        except Exception as e:
            logger.error("Flush monitor loop error: %s", e)

    async def _batch_processor_loop(self) -> None:
        """Process batches from the queue."""
        logger.debug("Starting batch processor loop")

        try:
            while True:
                # Wait for batch to process
                batch = await self.pending_batches.get()

                if batch.is_empty():
                    continue

                await self._process_batch(batch)

        except asyncio.CancelledError:
            logger.debug("Batch processor loop cancelled")
            raise
        except Exception as e:
            logger.error("Batch processor loop error: %s", e)

    async def _process_batch(self, batch: SecurityEventBatch) -> None:
        """
        Process a batch of security events.

        Args:
            batch: SecurityEventBatch to process
        """
        start_time = time.time()
        events = batch.clear()

        if not events:
            return

        try:
            # Use database manager session
            if not self.database_manager:
                logger.error("No database manager available for batch processing")
                return
            async with self.database_manager.get_session() as session:
                # Create SecurityEventDB instances from SecurityEvent models
                db_events = []
                for event in events:
                    db_event = SecurityEventDB(
                        event_id=event.event_id,
                        event_uuid=event.event_uuid,
                        timestamp=event.timestamp,
                        timestamp_ms=event.timestamp_ms,
                        source_component=event.source_component,
                        event_type=event.event_type,
                        severity=event.severity,
                        title=event.title,
                        description=event.description,
                        payload=event.payload,
                        event_metadata=event.event_metadata,
                        incident_id=event.incident_id,
                        correlation_id=event.correlation_id,
                        acknowledged=event.acknowledged,
                        acknowledged_by=event.acknowledged_by,
                        acknowledged_at=event.acknowledged_at,
                        evidence_data=event.evidence_data,
                        remediation_action=event.remediation_action,
                    )
                    db_events.append(db_event)

                # Use SQLAlchemy bulk insert for performance
                session.add_all(db_events)

                await session.commit()

                # Update statistics
                batch_size = len(events)
                flush_time = (time.time() - start_time) * 1000  # Convert to ms

                self._stats["events_persisted"] += batch_size
                self._stats["batches_processed"] += 1

                # Track performance metrics
                self._batch_sizes.append(batch_size)
                self._flush_times.append(flush_time)

                # Update averages
                if self._batch_sizes:
                    self._stats["avg_batch_size"] = sum(self._batch_sizes) / len(self._batch_sizes)
                if self._flush_times:
                    self._stats["avg_flush_time_ms"] = sum(self._flush_times) / len(
                        self._flush_times
                    )

                logger.debug(
                    "Persisted batch: %d events in %.1fms (%.1f events/sec)",
                    batch_size, flush_time, batch_size / (flush_time / 1000)
                )

        except Exception as e:
            self._stats["database_errors"] += 1
            logger.error("Error persisting security event batch: %s", e)

            # For debugging: log event details on persistence failure
            logger.debug("Failed batch contained %d events", len(events))

    async def _process_pending_batches(self) -> None:
        """Process all pending batches (used during shutdown)."""
        while not self.pending_batches.empty():
            try:
                batch = self.pending_batches.get_nowait()
                await self._process_batch(batch)
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error("Error processing pending batch: %s", e)

    def get_statistics(self) -> dict[str, Any]:
        """
        Get persistence service statistics.

        Returns:
            Dictionary of performance and operational statistics
        """
        uptime = time.time() - self._stats["start_time"]

        # Calculate throughput metrics
        events_per_second = 0.0
        if uptime > 0:
            events_per_second = self._stats["events_persisted"] / uptime

        # Calculate success rate
        success_rate = 0.0
        if self._stats["events_received"] > 0:
            success_rate = self._stats["events_persisted"] / self._stats["events_received"]

        return {
            "uptime_seconds": uptime,
            "events_received": self._stats["events_received"],
            "events_persisted": self._stats["events_persisted"],
            "batches_processed": self._stats["batches_processed"],
            "database_errors": self._stats["database_errors"],
            "success_rate": success_rate,
            "events_per_second": events_per_second,
            "performance": {
                "avg_batch_size": self._stats["avg_batch_size"],
                "avg_flush_time_ms": self._stats["avg_flush_time_ms"],
                "current_batch_size": len(self.current_batch.events),
                "pending_batches": self.pending_batches.qsize(),
            },
            "configuration": {
                "batch_size": self.batch_size,
                "batch_timeout": self.batch_timeout,
                "flush_interval": self.flush_interval,
            },
        }

    @property
    def health(self) -> str:
        """Return the health status of the feature."""
        if not self.enabled:
            return "healthy"  # Disabled is considered healthy

        if not self.database_manager:
            return "failed"

        # Check error rate
        if self._stats["events_received"] > MIN_EVENTS_FOR_ERROR_RATE_CHECK:
            error_rate = self._stats["database_errors"] / self._stats["events_received"]
            if error_rate > FAILED_ERROR_RATE_THRESHOLD:
                return "failed"
            if error_rate > DEGRADED_ERROR_RATE_THRESHOLD:
                return "degraded"

        return "healthy"

    @property
    def health_details(self) -> dict[str, Any]:
        """Return detailed health information for diagnostics."""
        if not self.enabled:
            return {"status": "disabled", "reason": "Feature not enabled"}

        stats = self.get_statistics()

        return {
            "status": self.health,
            "uptime_seconds": stats["uptime_seconds"],
            "events_persisted": stats["events_persisted"],
            "success_rate": stats["success_rate"],
            "events_per_second": stats["events_per_second"],
            "database_connected": self.database_manager is not None,
            "database_schema_ready": True,  # Managed by Alembic
            "background_tasks_running": {
                "flush_monitor": self._flush_task is not None and not self._flush_task.done(),
                "batch_processor": self._processor_task is not None
                and not self._processor_task.done(),
            },
        }


# Global instance management
_security_persistence_service: SecurityPersistenceService | None = None


def get_security_persistence_service() -> SecurityPersistenceService:
    """
    Get the global security persistence service instance.

    Returns:
        The SecurityPersistenceService instance

    Raises:
        RuntimeError: If service has not been initialized
    """
    global _security_persistence_service
    if _security_persistence_service is None:
        msg = (
            "SecurityPersistenceService has not been initialized. "
            "Ensure it's registered with the FeatureManager."
        )
        raise RuntimeError(msg)
    return _security_persistence_service


def initialize_security_persistence_service(**kwargs) -> SecurityPersistenceService:
    """
    Initialize the global security persistence service.

    Args:
        **kwargs: Configuration options for the service

    Returns:
        The initialized SecurityPersistenceService instance
    """
    global _security_persistence_service
    if _security_persistence_service is None:
        _security_persistence_service = SecurityPersistenceService(**kwargs)
    return _security_persistence_service
