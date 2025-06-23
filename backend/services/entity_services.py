"""Entity Services

Core services for entity management including:
- Query operations for entity data
- Hardware control with security validation
- Entity lifecycle and configuration management
"""

import logging
import time
from asyncio import Queue
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from backend.core.performance import PerformanceMonitor
from backend.repositories.entity_repository import (
    CanCommandRepository,
    EntityConfigRepository,
    EntityHistoryRepository,
    EntityStateRepository,
)

logger = logging.getLogger(__name__)


class EntityQueryService:
    """Service for entity read operations."""

    def __init__(
        self,
        entity_manager,
        state_repository: EntityStateRepository,
        history_repository: EntityHistoryRepository,
        performance_monitor: PerformanceMonitor,
    ):
        """Initialize the query service.

        Args:
            entity_manager: EntityManager instance
            state_repository: Repository for entity state
            history_repository: Repository for entity history
            performance_monitor: Performance monitoring instance
        """
        self._entity_manager = entity_manager
        self._state_repo = state_repository
        self._history_repo = history_repository
        self._monitor = performance_monitor

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("EntityQueryService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.list_entities = self._monitor.monitor_service_method(
            "EntityQueryService", "list_entities"
        )(self.list_entities)

        self.get_entity = self._monitor.monitor_service_method("EntityQueryService", "get_entity")(
            self.get_entity
        )

        self.get_entity_history = self._monitor.monitor_service_method(
            "EntityQueryService", "get_entity_history"
        )(self.get_entity_history)

    async def list_entities(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """List entities with optional filtering.

        Args:
            filters: Optional filters (device_type, name_prefix, etc.)

        Returns:
            List of entity data
        """
        # Get entities from EntityManager
        entities = self._entity_manager.get_entities()

        # Apply filters
        if filters:
            filtered = []
            for entity in entities.values():
                if filters.get("device_type"):
                    if entity.device_type != filters["device_type"]:
                        continue

                if filters.get("name_prefix"):
                    if not entity.name.startswith(filters["name_prefix"]):
                        continue

                if filters.get("has_control", False):
                    if not hasattr(entity, "control"):
                        continue

                filtered.append(entity)
            entities = {e.entity_id: e for e in filtered}

        # Convert to response format
        result = []
        for entity in entities.values():
            entity_data = {
                "entity_id": entity.entity_id,
                "name": entity.name,
                "device_type": entity.device_type,
                "state": entity.state,
                "last_update": entity.last_update,
            }

            # Add optional fields
            if hasattr(entity, "icon"):
                entity_data["icon"] = entity.icon

            if hasattr(entity, "unit"):
                entity_data["unit"] = entity.unit

            if hasattr(entity, "category"):
                entity_data["category"] = entity.category

            result.append(entity_data)

        return result

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Get a specific entity by ID.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity data or None
        """
        entity = self._entity_manager.get_entity(entity_id)
        if not entity:
            return None

        # Build response
        entity_data = {
            "entity_id": entity.entity_id,
            "name": entity.name,
            "device_type": entity.device_type,
            "state": entity.state,
            "last_update": entity.last_update,
            "attributes": {},
        }

        # Add all attributes
        for attr in dir(entity):
            if not attr.startswith("_") and attr not in entity_data:
                value = getattr(entity, attr)
                if not callable(value):
                    entity_data["attributes"][attr] = value

        # Add persisted state if available
        saved_state = await self._state_repo.get_entity_state(entity_id)
        if saved_state:
            entity_data["persisted_state"] = saved_state

        return entity_data

    async def get_entity_history(self, entity_id: str, hours: int = 24) -> list[dict[str, Any]]:
        """Get entity state history.

        Args:
            entity_id: Entity identifier
            hours: Hours of history to retrieve

        Returns:
            List of state changes
        """
        end_time = time.time()
        start_time = end_time - (hours * 3600)

        history = await self._history_repo.get_entity_history(entity_id, start_time, end_time)

        return history

    async def get_unmapped_entries(self) -> dict[str, list[Any]]:
        """Get unmapped RV-C entries.

        Returns:
            Dictionary of unmapped entries by type
        """
        # This would typically query the RV-C decoder for unmapped messages
        # For now, return empty structure
        return {"dgns": [], "spns": [], "instances": []}

    async def get_metadata(self) -> dict[str, Any]:
        """Get entity system metadata.

        Returns:
            System metadata
        """
        entities = self._entity_manager.get_entities()

        # Count by type
        by_type = {}
        for entity in entities.values():
            device_type = entity.device_type
            by_type[device_type] = by_type.get(device_type, 0) + 1

        return {
            "total_entities": len(entities),
            "entities_by_type": by_type,
            "last_update": datetime.now(UTC).isoformat(),
            "version": "2.0",
        }

    async def get_protocol_summary(self) -> dict[str, Any]:
        """Get RV-C protocol summary.

        Returns:
            Protocol statistics
        """
        # This would typically query the CAN interface for statistics
        return {"messages_received": 0, "messages_sent": 0, "errors": 0, "uptime_seconds": 0}


class EntityControlService:
    """Service for hardware control operations."""

    def __init__(
        self,
        entity_manager,
        websocket_manager,
        can_tx_queue: Queue,
        command_repository: CanCommandRepository,
        performance_monitor: PerformanceMonitor,
    ):
        """Initialize the control service.

        Args:
            entity_manager: EntityManager instance
            websocket_manager: WebSocket manager for broadcasts
            can_tx_queue: CAN transmit queue
            command_repository: Repository for command auditing
            performance_monitor: Performance monitoring instance
        """
        self._entity_manager = entity_manager
        self._websocket_manager = websocket_manager
        self._can_tx_queue = can_tx_queue
        self._command_repo = command_repository
        self._monitor = performance_monitor

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("EntityControlService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.control_entity = self._monitor.monitor_service_method(
            "EntityControlService", "control_entity"
        )(self.control_entity)

        self.control_light = self._monitor.monitor_service_method(
            "EntityControlService", "control_light"
        )(self.control_light)

    async def control_entity(
        self, entity_id: str, command: dict[str, Any], user_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Control an entity with security validation.

        Args:
            entity_id: Entity to control
            command: Control command
            user_context: User authentication context

        Returns:
            Control result
        """
        timestamp = time.time()
        user_id = user_context.get("user_id") if user_context else None

        try:
            # Validate entity exists
            entity = self._entity_manager.get_entity(entity_id)
            if not entity:
                error = f"Entity {entity_id} not found"
                await self._command_repo.record_command(
                    entity_id, command, timestamp, user_id, False, error
                )
                return {"success": False, "error": error}

            # Validate entity is controllable
            if not hasattr(entity, "control"):
                error = f"Entity {entity_id} is not controllable"
                await self._command_repo.record_command(
                    entity_id, command, timestamp, user_id, False, error
                )
                return {"success": False, "error": error}

            # TODO: Add security validation here
            # if not await self._validate_command_access(user_context, entity_id, command):
            #     error = "Access denied"
            #     await self._command_repo.record_command(
            #         entity_id, command, timestamp, user_id, False, error
            #     )
            #     return {"success": False, "error": error}

            # Execute control
            result = await entity.control(command)

            # Record command
            await self._command_repo.record_command(
                entity_id,
                command,
                timestamp,
                user_id,
                result.get("success", False),
                result.get("error"),
            )

            # Update state and broadcast
            if result.get("success"):
                # Optimistic update
                if "state" in command:
                    entity.state = command["state"]
                    entity.last_update = timestamp

                # Broadcast update
                await self._websocket_manager.broadcast_entity_update(entity_id, entity.to_dict())

            return result

        except Exception as e:
            error = f"Control failed: {e!s}"
            logger.error(f"Entity control error: {e}", exc_info=True)

            await self._command_repo.record_command(
                entity_id, command, timestamp, user_id, False, error
            )

            return {"success": False, "error": error}

    async def control_light(
        self, entity_id: str, command: dict[str, Any], user_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Control a light entity with brightness support.

        Args:
            entity_id: Light entity to control
            command: Light control command
            user_context: User authentication context

        Returns:
            Control result
        """
        # Validate light-specific parameters
        if "brightness" in command:
            brightness = command.get("brightness")
            if not isinstance(brightness, int) or brightness < 0 or brightness > 100:
                return {"success": False, "error": "Brightness must be integer 0-100"}

        # Use standard control
        return await self.control_entity(entity_id, command, user_context)

    async def emergency_stop_all(
        self, user_context: dict[str, Any] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Emergency stop all controllable entities.

        Args:
            user_context: User authentication context

        Returns:
            Results by entity ID
        """
        results = {}
        entities = self._entity_manager.get_entities()

        # TODO: Add emergency access validation

        for entity_id, entity in entities.items():
            if hasattr(entity, "control"):
                # Send OFF command
                command = {"command": "set", "state": False}
                result = await self.control_entity(entity_id, command, user_context)
                results[entity_id] = result

        logger.warning(
            f"Emergency stop executed by user {user_context.get('user_id') if user_context else 'unknown'}"
        )

        return results


class EntityManagementService:
    """Service for entity lifecycle and configuration management."""

    def __init__(
        self,
        entity_manager,
        config_repository: EntityConfigRepository,
        websocket_manager,
        performance_monitor: PerformanceMonitor,
    ):
        """Initialize the management service.

        Args:
            entity_manager: EntityManager instance
            config_repository: Repository for entity configuration
            websocket_manager: WebSocket manager for broadcasts
            performance_monitor: Performance monitoring instance
        """
        self._entity_manager = entity_manager
        self._config_repo = config_repository
        self._websocket_manager = websocket_manager
        self._monitor = performance_monitor

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("EntityManagementService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.create_entity_mapping = self._monitor.monitor_service_method(
            "EntityManagementService", "create_entity_mapping"
        )(self.create_entity_mapping)

        self.update_entity_config = self._monitor.monitor_service_method(
            "EntityManagementService", "update_entity_config"
        )(self.update_entity_config)

    async def create_entity_mapping(
        self, mapping: dict[str, Any], user_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a new entity mapping.

        Args:
            mapping: Entity mapping configuration
            user_context: User authentication context

        Returns:
            Created entity data
        """
        # TODO: Add permission check

        # Validate mapping
        required_fields = ["entity_id", "name", "device_type"]
        for field in required_fields:
            if field not in mapping:
                return {"success": False, "error": f"Missing required field: {field}"}

        entity_id = mapping["entity_id"]

        # Check if already exists
        if self._entity_manager.get_entity(entity_id):
            return {"success": False, "error": f"Entity {entity_id} already exists"}

        # Save configuration
        await self._config_repo.save_entity_mapping(entity_id, mapping)

        # Create entity in EntityManager
        self._entity_manager.create_entity(mapping)

        # Get created entity
        entity = self._entity_manager.get_entity(entity_id)

        # Broadcast creation
        await self._websocket_manager.broadcast_entity_update(entity_id, entity.to_dict())

        logger.info(f"Created entity mapping for {entity_id}")

        return {"success": True, "entity": entity.to_dict()}

    async def update_entity_config(
        self, entity_id: str, updates: dict[str, Any], user_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Update entity configuration.

        Args:
            entity_id: Entity to update
            updates: Configuration updates
            user_context: User authentication context

        Returns:
            Updated entity data
        """
        # TODO: Add permission check

        # Validate entity exists
        entity = self._entity_manager.get_entity(entity_id)
        if not entity:
            return {"success": False, "error": f"Entity {entity_id} not found"}

        # Build updated config
        current_config = {
            "entity_id": entity.entity_id,
            "name": entity.name,
            "device_type": entity.device_type,
        }

        # Add current attributes
        for attr in ["icon", "unit", "category"]:
            if hasattr(entity, attr):
                current_config[attr] = getattr(entity, attr)

        # Apply updates
        current_config.update(updates)

        # Save configuration
        await self._config_repo.save_entity_mapping(entity_id, current_config)

        # Update entity in EntityManager
        for key, value in updates.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        # Broadcast update
        await self._websocket_manager.broadcast_entity_update(entity_id, entity.to_dict())

        logger.info(f"Updated entity config for {entity_id}")

        return {"success": True, "entity": entity.to_dict()}

    async def delete_entity(
        self, entity_id: str, user_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Delete an entity.

        Args:
            entity_id: Entity to delete
            user_context: User authentication context

        Returns:
            Deletion result
        """
        # TODO: Add permission check

        # Validate entity exists
        if not self._entity_manager.get_entity(entity_id):
            return {"success": False, "error": f"Entity {entity_id} not found"}

        # Delete from config
        await self._config_repo.delete_entity_config(entity_id)

        # Remove from EntityManager
        self._entity_manager.remove_entity(entity_id)

        # Broadcast deletion
        await self._websocket_manager.broadcast_entity_deletion(entity_id)

        logger.info(f"Deleted entity {entity_id}")

        return {"success": True}

    async def reload_coach_mapping(self, coach_model: str) -> dict[str, Any]:
        """Reload coach mapping from configuration.

        Args:
            coach_model: Coach model to load

        Returns:
            Load result with entity count
        """
        # Load mapping from repository
        mapping = await self._config_repo.load_coach_mapping(coach_model)

        # Clear existing entities
        self._entity_manager.clear_entities()

        # Load entities from mapping
        entity_count = 0
        for entity_config in mapping.get("entities", {}).values():
            self._entity_manager.create_entity(entity_config)
            entity_count += 1

        logger.info(f"Reloaded {entity_count} entities for coach {coach_model}")

        return {"success": True, "coach_model": coach_model, "entity_count": entity_count}
