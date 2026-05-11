"""
Entity Service

Lightweight entity service optimized for Raspberry Pi 4 deployment
with minimal memory usage and fast response times.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.query_optimization import track_query_performance
from backend.core.rpi_cache import get_cache_manager
from backend.core.rpi_performance_monitor import monitor_rpi_operation
from backend.core.structured_logging import get_logger
from backend.models.database import EntityState

logger = get_logger(__name__, "EntityService")


class EntityService:
    """
    Lightweight entity service for Raspberry Pi deployment.

    Optimizations:
    - Minimal memory footprint
    - Efficient queries with covering indexes
    - Batch operations where possible
    - Simple caching for frequently accessed entities
    """

    def __init__(self, db_session_factory):
        """Initialize the service with database session factory."""
        self._session_factory = db_session_factory
        self._cache = get_cache_manager().shared

    async def _get_session(self) -> AsyncSession:
        """Get database session."""
        async with self._session_factory() as session:
            yield session

    @track_query_performance
    @monitor_rpi_operation("entity_service.get_all_entities", alert_threshold_ms=100.0)
    async def get_all_entities(self, active_only: bool = True) -> list[dict[str, Any]]:
        """
        Get all entities with minimal overhead.

        Args:
            active_only: Whether to return only active entities

        Returns:
            List of entity dictionaries
        """
        # Try to get from cache first
        cached = await self._cache.get_all_entities(active_only)
        if cached:
            return cached

        async with self._session_factory() as session:
            # Use optimized query that leverages covering index
            if active_only:
                # This query uses the covering index we created
                result = await session.execute(
                    select(EntityState).where(EntityState.device_type.isnot(None))
                )
            else:
                result = await session.execute(select(EntityState))

            entities = []
            for row in result.scalars():
                entity_dict = row.to_entity_dict()
                # Cache individual entity
                await self._cache.set_entity(row.entity_id, entity_dict)
                entities.append(entity_dict)

            # Cache the full list
            await self._cache.set_all_entities(entities, active_only, ttl=60)  # 1 minute TTL

            return entities

    @track_query_performance
    @monitor_rpi_operation("entity_service.get_entity", alert_threshold_ms=50.0)
    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """
        Get a single entity by ID.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity dictionary or None if not found
        """
        # Check cache first
        cached = await self._cache.get_entity(entity_id)
        if cached:
            return cached

        async with self._session_factory() as session:
            result = await session.get(EntityState, entity_id)
            if result:
                entity_dict = result.to_entity_dict()
                await self._cache.set_entity(entity_id, entity_dict)
                return entity_dict
            return None

    @track_query_performance
    @monitor_rpi_operation("entity_service.update_entity_state", alert_threshold_ms=75.0)
    async def update_entity_state(
        self,
        entity_id: str,
        state_update: dict[str, Any]
    ) -> bool:
        """
        Update entity state efficiently.

        Args:
            entity_id: Entity identifier
            state_update: State updates to apply

        Returns:
            True if updated successfully
        """
        async with self._session_factory() as session:
            # Get current state
            entity = await session.get(EntityState, entity_id)
            if not entity:
                # Create new entity state
                entity = EntityState(
                    entity_id=entity_id,
                    state=state_update,
                    device_type=state_update.get("device_type"),
                    suggested_area=state_update.get("suggested_area"),
                )
                session.add(entity)
            else:
                # Update existing state
                entity.state.update(state_update)
                entity.device_type = state_update.get("device_type", entity.device_type)
                entity.suggested_area = state_update.get("suggested_area", entity.suggested_area)

            await session.commit()

            # Invalidate cache
            await self._cache.invalidate_entity(entity_id)

            return True

    @track_query_performance
    async def bulk_update_states(
        self,
        updates: list[tuple[str, dict[str, Any]]]
    ) -> int:
        """
        Bulk update entity states for efficiency.

        Args:
            updates: List of (entity_id, state_update) tuples

        Returns:
            Number of entities updated
        """
        if not updates:
            return 0

        async with self._session_factory() as session:
            updated_count = 0

            # Process in batches to limit memory usage
            batch_size = 50  # Small batches for RPi
            for i in range(0, len(updates), batch_size):
                batch = updates[i:i + batch_size]

                for entity_id, state_update in batch:
                    entity = await session.get(EntityState, entity_id)
                    if not entity:
                        entity = EntityState(
                            entity_id=entity_id,
                            state=state_update,
                            device_type=state_update.get("device_type"),
                            suggested_area=state_update.get("suggested_area"),
                        )
                        session.add(entity)
                    else:
                        entity.state.update(state_update)
                        entity.device_type = state_update.get("device_type", entity.device_type)
                        entity.suggested_area = state_update.get(
                            "suggested_area", entity.suggested_area
                        )

                    updated_count += 1

                    # Invalidate cache
                    await self._cache.invalidate_entity(entity_id)

                # Commit each batch
                await session.commit()

            logger.info("Bulk updated %d entities", updated_count)
            return updated_count

    @track_query_performance
    async def get_entities_by_type(
        self,
        device_type: str
    ) -> list[dict[str, Any]]:
        """
        Get all entities of a specific type.

        Args:
            device_type: Device type to filter by

        Returns:
            List of entity dictionaries
        """
        # Check cache first
        cached = await self._cache.get_entities_by_type(device_type)
        if cached:
            return cached

        async with self._session_factory() as session:
            # This query uses the device_type index
            result = await session.execute(
                select(EntityState).where(EntityState.device_type == device_type)
            )

            entities = []
            for row in result.scalars():
                entity_dict = row.to_entity_dict()
                # Cache individual entity
                await self._cache.set_entity(row.entity_id, entity_dict)
                entities.append(entity_dict)

            # Cache the list by type
            await self._cache.set_entities_by_type(device_type, entities)

            return entities

    @track_query_performance
    async def get_recent_changes(
        self,
        minutes: int = 60
    ) -> list[dict[str, Any]]:
        """
        Get entities that changed recently.

        Args:
            minutes: Number of minutes to look back

        Returns:
            List of recently changed entities
        """
        from datetime import UTC, datetime, timedelta

        cutoff_time = datetime.now(UTC) - timedelta(minutes=minutes)

        async with self._session_factory() as session:
            # This query uses the updated_at index
            result = await session.execute(
                select(EntityState)
                .where(EntityState.updated_at > cutoff_time)
                .order_by(EntityState.updated_at.desc())
                .limit(100)  # Limit for RPi memory
            )

            return [row.to_entity_dict() for row in result.scalars()]

    async def get_health_status(self) -> dict[str, Any]:
        """Get service health status."""
        try:
            async with self._session_factory() as session:
                # Quick count query
                result = await session.execute(
                    select(EntityState.entity_id).limit(1)
                )
                can_query = result.first() is not None

            # Get cache metrics
            cache_metrics = self._cache.get_metrics()

            return {
                "healthy": True,
                "can_query_db": can_query,
                "cache_metrics": cache_metrics,
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
            }
