"""
Entity data models for the CoachIQ backend.

This module defines the core entity models that combine configuration and runtime state
for all entities in the system. It provides a unified approach to entity management
with proper typing and validation.
"""

import time
from collections import deque
from typing import Any, TypedDict

from pydantic import BaseModel, Field


class EntityConfig(TypedDict, total=False):
    """Configuration for an entity derived from the device mapping file."""

    device_type: str
    suggested_area: str
    friendly_name: str
    capabilities: list[str]
    groups: list[str]
    # Protocol ownership and identification
    protocol: str  # Primary protocol (e.g., "rvc", "j1939", "firefly", "spartan_k2")
    secondary_protocols: list[str]  # Other protocols that can access this entity
    physical_id: str  # Unique physical device identifier across protocols
    # Protocol-specific metadata
    protocol_metadata: dict[str, Any]  # Protocol-specific configuration data
    # Additional configuration fields that may be present
    instance: int
    command_dgn: str
    status_dgn: str
    status_source_addr: int
    status_instance: int
    parameter_group_number: str


class EntityState(BaseModel):
    """
    Current runtime state of an entity.

    This model represents the dynamic properties of an entity that change over time,
    such as its current value, state, and last update timestamp.
    """

    entity_id: str = Field(..., description="Unique identifier for the entity")
    value: dict[str, Any] = Field(default_factory=dict, description="Decoded entity value")
    raw: dict[str, Any] = Field(default_factory=dict, description="Raw entity data")
    state: str = Field("unknown", description="Human-readable state (e.g., 'on', 'off')")
    timestamp: float = Field(default_factory=time.time, description="Last update timestamp")

    # These fields are copied from config for convenience in API responses
    suggested_area: str = Field("Unknown", description="Suggested area for the entity")
    device_type: str = Field("unknown", description="Type of device (e.g., 'light', 'lock')")
    capabilities: list[str] = Field(default_factory=list, description="Entity capabilities")
    friendly_name: str | None = Field(None, description="Human-readable name")
    groups: list[str] = Field(default_factory=list, description="Entity groups")
    # Protocol ownership information
    protocol: str = Field("rvc", description="Primary owning protocol")
    secondary_protocols: list[str] = Field(default_factory=list, description="Secondary protocols")
    physical_id: str | None = Field(None, description="Physical device identifier")
    protocol_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Protocol-specific data"
    )
    # Required by the control path to build CAN messages; sourced from the
    # coach mapping's DGN section (inst_map) at initialization.
    instance: int | None = Field(None, description="RV-C DGN instance for command emission")


class Entity:
    """
    Unified entity model that combines configuration and runtime state.

    This class provides a single source of truth for entity data, combining
    the static configuration (from device mapping) with dynamic runtime state.
    It also maintains a history of state changes for analysis and debugging.
    """

    def __init__(
        self,
        entity_id: str,
        config: EntityConfig,
        max_history_length: int = 1000,
        history_duration: int = 24 * 3600,  # 24 hours in seconds
    ):
        """
        Initialize a new entity with the given ID and configuration.

        Args:
            entity_id: Unique identifier for the entity
            config: Entity configuration from device mapping
            max_history_length: Maximum number of history entries to keep
            history_duration: Maximum age of history entries in seconds
        """
        self.entity_id = entity_id
        self.config = config
        self.max_history_length = max_history_length
        self.history_duration = history_duration
        self.history: deque[EntityState] = deque(maxlen=max_history_length)

        # Initialize with default state
        self.current_state = EntityState(
            entity_id=entity_id,
            state="unknown",
            suggested_area=config.get("suggested_area", "Unknown"),
            device_type=config.get("device_type", "unknown"),
            capabilities=config.get("capabilities", []),
            friendly_name=config.get("friendly_name"),
            groups=config.get("groups", []),
            protocol=config.get("protocol", "rvc"),
            secondary_protocols=config.get("secondary_protocols", []),
            physical_id=config.get("physical_id"),
            protocol_metadata=config.get("protocol_metadata", {}),
            instance=config.get("instance"),
        )

        # Add initial state to history
        self.history.append(self.current_state)

        # Additional properties specific to entity types
        self.last_known_brightness: int | None = None

    def update_state(self, new_state: dict[str, Any]) -> None:
        """
        Update the entity's current state and add to history.

        Args:
            new_state: New state data to apply
        """
        # Create a copy of the current state and update it
        updated_state = self.current_state.model_copy(update=new_state)
        updated_state.timestamp = new_state.get("timestamp", time.time())

        # Update current state
        self.current_state = updated_state

        # Add to history
        self.history.append(updated_state)

        # Prune old history entries
        self._prune_history()

        # Update type-specific properties
        if self.config.get("device_type") == "light" and "brightness" in new_state:
            self.last_known_brightness = new_state["brightness"]

    def _prune_history(self) -> None:
        """Remove history entries older than history_duration."""
        current_time = time.time()
        cutoff = current_time - self.history_duration

        while self.history and self.history[0].timestamp < cutoff:
            self.history.popleft()

    def get_state(self) -> EntityState:
        """Get the current state of the entity."""
        return self.current_state

    def get_history(
        self, count: int | None = None, since: float | None = None
    ) -> list[EntityState]:
        """
        Get historical state data for the entity.

        Args:
            count: Maximum number of history entries to return
            since: Return only entries newer than this timestamp

        Returns:
            List of historical entity states
        """
        history_data = list(self.history)

        if since is not None:
            history_data = [state for state in history_data if state.timestamp >= since]

        if count is not None:
            history_data = history_data[-count:]

        return history_data

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the entity to a dictionary for API responses.

        Returns:
            Dictionary representation of the entity's current state
        """
        return self.current_state.model_dump()
