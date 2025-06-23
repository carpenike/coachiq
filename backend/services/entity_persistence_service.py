"""
Entity Persistence Service

Manages the persistence of entity states to the database using an event-driven
architecture with debounced writes and background processing.
"""

import asyncio
import logging
import random
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from backend.core.entity_manager import EntityManager
    from backend.services.database_manager import DatabaseManager

import contextlib

from backend.models.database import EntityState as EntityStateModel

logger = logging.getLogger(__name__)


class EntityPersistenceService:
    """
    Service responsible for persisting entity states to the database.

    Uses an event-driven architecture to decouple entity state management
    from persistence concerns. Implements debounced writes and batch
    processing for optimal performance.
    """

    def __init__(
        self,
        entity_manager: "EntityManager",
        database_manager: "DatabaseManager",
        debounce_delay: float = 0.5,
        max_batch_size: int = 100,
        max_retries: int = 3,
    ):
        """
        Initialize the Entity Persistence Service.

        Args:
            entity_manager: The entity manager to observe for state changes
            database_manager: Database manager for persistence operations
            debounce_delay: Delay in seconds before writing batched changes
            max_batch_size: Maximum number of entities to persist in one batch
            max_retries: Maximum number of retry attempts for failed writes
        """
        self._entity_manager = entity_manager
        self._db_manager = database_manager
        self._debounce_delay = debounce_delay
        self._max_batch_size = max_batch_size
        self._max_retries = max_retries

        # Queue for dirty entity IDs
        self._dirty_entity_ids: asyncio.Queue[str | None] = asyncio.Queue()

        # Background worker task
        self._worker_task: asyncio.Task | None = None
        self._is_stopping = False

        # Statistics
        self._stats = {
            "total_writes": 0,
            "failed_writes": 0,
            "total_entities_persisted": 0,
            "last_write_time": None,
        }

    async def start(self) -> None:
        """Start the persistence service and background worker."""
        if self._worker_task and not self._worker_task.done():
            logger.warning("EntityPersistenceService already running")
            return

        logger.info("Starting EntityPersistenceService")
        self._is_stopping = False

        # Load initial state from database
        await self._load_entity_states()

        # Register as listener for entity state changes
        self._entity_manager.register_state_change_listener(self._on_entity_state_changed)

        # Start the background persistence worker
        self._worker_task = asyncio.create_task(self._persistence_worker())
        logger.info("EntityPersistenceService started successfully")

    async def stop(self) -> None:
        """Stop the persistence service gracefully."""
        logger.info("Stopping EntityPersistenceService...")
        self._is_stopping = True

        # Unregister listener to prevent new items
        self._entity_manager.unregister_state_change_listener(self._on_entity_state_changed)

        # Signal the worker to finish
        await self._dirty_entity_ids.put(None)  # Sentinel value

        # Wait for worker to complete
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=10.0)
            except TimeoutError:
                logger.warning("Persistence worker did not shut down in time, cancelling")
                self._worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._worker_task

        logger.info("EntityPersistenceService stopped")

    def _on_entity_state_changed(self, entity_id: str) -> None:
        """
        Handle entity state change notifications.

        This method is called synchronously by the EntityManager when
        an entity's state changes.

        Args:
            entity_id: ID of the entity whose state changed
        """
        if not self._is_stopping:
            try:
                self._dirty_entity_ids.put_nowait(entity_id)
            except asyncio.QueueFull:
                logger.warning(f"Persistence queue full, dropping update for entity {entity_id}")

    async def _load_entity_states(self) -> None:
        """Load entity states from the database on startup."""
        logger.info("Loading entity states from database...")

        try:
            async with self._db_manager.get_session() as session:
                # Load all entity states
                result = await session.execute(select(EntityStateModel))
                entity_states = result.scalars().all()

                loaded_count = 0
                for db_state in entity_states:
                    # Restore entity state in the entity manager
                    entity = self._entity_manager.get_entity(db_state.entity_id)
                    if entity:
                        # Convert database model to state dict
                        state_dict = {
                            "entity_id": db_state.entity_id,
                            "state": db_state.state,
                            "timestamp": db_state.updated_at.timestamp(),
                        }
                        # Update entity with persisted state
                        entity.update_state(state_dict)
                        loaded_count += 1
                    else:
                        logger.warning(
                            f"Entity {db_state.entity_id} found in database but not in entity manager"
                        )

                logger.info(f"Loaded {loaded_count} entity states from database")

        except Exception as e:
            logger.error(f"Failed to load entity states from database: {e}")
            # Don't fail startup - entities will start with default states

    async def _persistence_worker(self) -> None:
        """
        Background worker that processes the queue of dirty entities.

        Implements debouncing and batching for efficient database writes.
        """
        logger.debug("Persistence worker started")

        while not self._is_stopping:
            try:
                # Wait for the first dirty entity
                first_id = await self._dirty_entity_ids.get()
                if first_id is None:  # Sentinel for shutdown
                    break

                # Start collecting a batch
                batch = {first_id}

                # Debounce: collect more items that arrive within the delay window
                deadline = time.perf_counter() + self._debounce_delay

                while len(batch) < self._max_batch_size:
                    remaining_time = deadline - time.perf_counter()
                    if remaining_time <= 0:
                        break  # Debounce window expired

                    try:
                        # Try to get another item within the remaining time
                        item = await asyncio.wait_for(
                            self._dirty_entity_ids.get(), timeout=remaining_time
                        )
                        if item is None:  # Shutdown sentinel
                            self._is_stopping = True
                            break
                        batch.add(item)
                    except TimeoutError:
                        # No more items arrived within the window
                        break

                # Persist the batch
                if batch:
                    await self._persist_batch(list(batch))

            except Exception as e:
                logger.error(f"Unhandled exception in persistence worker: {e}", exc_info=True)
                # Prevent fast-spinning crash loop
                await asyncio.sleep(5)

        # Graceful shutdown: drain any remaining items
        logger.info("Draining persistence queue before shutdown...")
        final_batch = set()

        while not self._dirty_entity_ids.empty():
            try:
                entity_id = self._dirty_entity_ids.get_nowait()
                if entity_id is not None:
                    final_batch.add(entity_id)
            except asyncio.QueueEmpty:
                break

        if final_batch:
            logger.info(f"Persisting final batch of {len(final_batch)} entities")
            await self._persist_batch(list(final_batch))

        logger.debug("Persistence worker stopped")

    async def _persist_batch(self, entity_ids: list[str]) -> None:
        """
        Persist a batch of entities to the database with retry logic.

        Args:
            entity_ids: List of entity IDs to persist
        """
        logger.debug(f"Persisting batch of {len(entity_ids)} entities")

        # Collect entity states
        states_to_persist = []
        for entity_id in entity_ids:
            entity = self._entity_manager.get_entity(entity_id)
            if entity:
                state_dict = entity.to_dict()
                states_to_persist.append(
                    {
                        "entity_id": entity_id,
                        "state": state_dict,
                        "updated_at": datetime.now(UTC),
                    }
                )
            else:
                logger.warning(f"Entity {entity_id} not found in entity manager")

        if not states_to_persist:
            return

        # Retry logic with exponential backoff
        base_delay = 1.0  # seconds

        for attempt in range(self._max_retries):
            try:
                async with self._db_manager.get_session() as session:
                    await self._bulk_upsert_states(session, states_to_persist)
                    await session.commit()

                # Success!
                self._stats["total_writes"] += 1
                self._stats["total_entities_persisted"] += len(states_to_persist)
                self._stats["last_write_time"] = datetime.now(UTC)

                logger.debug(f"Successfully persisted {len(states_to_persist)} entities")
                return

            except Exception as e:
                logger.warning(
                    f"Database write failed (attempt {attempt + 1}/{self._max_retries}): {e}"
                )

                if attempt + 1 == self._max_retries:
                    # All retries exhausted
                    self._stats["failed_writes"] += 1
                    logger.error(
                        f"Failed to persist batch of {len(entity_ids)} entities after "
                        f"{self._max_retries} retries. Entity IDs: {entity_ids}"
                    )

                    # Re-queue the entities to try again later
                    # This prevents data loss but could lead to queue buildup
                    for entity_id in entity_ids:
                        try:
                            self._dirty_entity_ids.put_nowait(entity_id)
                        except asyncio.QueueFull:
                            logger.error(f"Cannot re-queue entity {entity_id} - queue full")
                    break

                # Exponential backoff with jitter
                delay = (base_delay * 2**attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)

    async def _bulk_upsert_states(
        self, session: AsyncSession, states: list[dict[str, Any]]
    ) -> None:
        """
        Perform bulk upsert of entity states using SQLite's ON CONFLICT.

        Args:
            session: Database session
            states: List of state dictionaries to upsert
        """
        # Use SQLite's INSERT ... ON CONFLICT for efficient upsert
        stmt = sqlite_insert(EntityStateModel).values(states)
        stmt = stmt.on_conflict_do_update(
            index_elements=["entity_id"],
            set_={
                "state": stmt.excluded.state,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)

    def get_statistics(self) -> dict[str, Any]:
        """Get persistence service statistics."""
        return {
            **self._stats,
            "queue_size": self._dirty_entity_ids.qsize(),
            "is_running": self._worker_task is not None and not self._worker_task.done(),
        }
