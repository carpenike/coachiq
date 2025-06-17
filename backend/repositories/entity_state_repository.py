"""
Entity State Repository

Manages entity state and history data with clear separation of concerns.
Part of Phase 2R: AppState Repository Migration

This repository handles:
- Entity state storage and retrieval
- Entity history management
- Last known brightness tracking for light entities
"""

import logging
from typing import Dict, Any, Optional

from backend.core.entity_manager import EntityManager
from backend.models.entity_model import EntityConfig

logger = logging.getLogger(__name__)


class EntityStateRepository:
    """
    Repository for entity state management.

    This class encapsulates all entity-related state operations,
    providing a clean interface for entity data access and manipulation.
    """

    def __init__(self, entity_manager: Optional[EntityManager] = None):
        """
        Initialize the entity state repository.

        Args:
            entity_manager: Optional EntityManager instance. If not provided,
                          a new one will be created.
        """
        self.entity_manager = entity_manager or EntityManager()
        logger.info("EntityStateRepository initialized")

    def get_entity_count(self) -> int:
        """Get the total number of entities."""
        return len(self.entity_manager.get_entity_ids())

    def get_light_entity_count(self) -> int:
        """Get the number of light entities."""
        return len(self.entity_manager.get_light_entity_ids())

    def update_entity_state_and_history(self, entity_id: str, payload: Dict[str, Any]) -> None:
        """
        Update the state and history for a given entity.

        Args:
            entity_id: The entity identifier
            payload: The state payload to store
        """
        entity = self.entity_manager.get_entity(entity_id)
        if entity:
            entity.update_state(payload)
        else:
            # If entity doesn't exist, try to register it
            config = EntityConfig(
                device_type=payload.get("device_type", "unknown"),
                suggested_area=payload.get("suggested_area", "Unknown"),
                friendly_name=payload.get("friendly_name"),
                capabilities=payload.get("capabilities", []),
                groups=payload.get("groups", []),
            )
            entity = self.entity_manager.register_entity(entity_id, config)
            entity.update_state(payload)

    def get_last_known_brightness(self, entity_id: str) -> int:
        """
        Get the last known brightness for a light entity.

        Args:
            entity_id: The entity identifier

        Returns:
            Last known brightness (0-100), defaults to 100
        """
        entity = self.entity_manager.get_entity(entity_id)
        if entity and entity.last_known_brightness is not None:
            return entity.last_known_brightness
        return 100  # Default brightness

    def set_last_known_brightness(self, entity_id: str, brightness: int) -> None:
        """
        Set the last known brightness for a light entity.

        Args:
            entity_id: The entity identifier
            brightness: Brightness value (0-100)
        """
        entity = self.entity_manager.get_entity(entity_id)
        if entity:
            entity.last_known_brightness = brightness

    def get_entity_states(self) -> Dict[str, Any]:
        """Get all entity states."""
        return self.entity_manager.to_api_response()

    def get_entity_history(self, entity_id: str, count: Optional[int] = None) -> list:
        """
        Get historical data for an entity.

        Args:
            entity_id: The entity identifier
            count: Maximum number of history entries to return

        Returns:
            List of historical state entries
        """
        entity = self.entity_manager.get_entity(entity_id)
        if entity:
            return [state.model_dump() for state in entity.get_history(count=count)]
        return []

    def bulk_load_entities(self, entity_configs: Dict[str, EntityConfig]) -> None:
        """
        Bulk load entities from configuration.

        Args:
            entity_configs: Dictionary mapping entity IDs to configs
        """
        self.entity_manager.bulk_load_entities(entity_configs)

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get repository health status.

        Returns:
            Health status information
        """
        return {
            "healthy": True,
            "entity_count": self.get_entity_count(),
            "light_count": self.get_light_entity_count(),
            "entity_manager_healthy": True,  # Could add actual health check
        }
