"""
Entity Models

Pydantic models for entity management and control operations.
These models handle entity state, control commands, and response validation.
"""

from typing import Any

from pydantic import BaseModel, Field


class Entity(BaseModel):
    """Represents the state and metadata of a monitored RV-C entity."""

    entity_id: str
    value: dict[str, str]
    raw: dict[str, int]
    state: str
    timestamp: float
    suggested_area: str | None = "Unknown"
    device_type: str | None = "unknown"
    capabilities: list[str] | None = []
    friendly_name: str | None = None
    groups: list[str] | None = Field(default_factory=list)


class ControlCommand(BaseModel):
    """Defines the structure for sending control commands to an entity, typically a light."""

    command: str
    state: str | None = Field(
        None,
        description="Target state: 'on' or 'off'. Required only for 'set' command.",
    )
    brightness: int | None = Field(
        None,
        ge=0,
        le=100,
        description=(
            "Brightness percent (0-100). Only used when command is 'set' and state is 'on'."
        ),
    )
    parameters: dict[str, Any] | None = Field(
        None,
        description=(
            "Device-type-specific parameters. Climate zones use setpoint_f / "
            "setpoint_heat_f / setpoint_cool_f, mode, fan_mode, fan_speed_pct."
        ),
    )


class ControlEntityResponse(BaseModel):
    """Response model for individual entity control commands, confirming the action taken."""

    status: str
    entity_id: str
    command: str
    state: str
    brightness: int
    action: str


class SuggestedMapping(BaseModel):
    """
    Provides a suggested mapping for an unmapped device instance
    based on existing configurations.
    """

    instance: str
    name: str
    suggested_area: str | None = None


class CreateEntityMappingRequest(BaseModel):
    """Request model for creating a new entity mapping from an unmapped entry."""

    # Source unmapped entry information
    pgn_hex: str = Field(..., description="PGN hex identifier from the unmapped entry")
    instance: str = Field(..., description="Instance identifier from the unmapped entry")

    # Entity configuration
    entity_id: str = Field(..., description="Unique identifier for the new entity")
    friendly_name: str = Field(..., description="Human-readable name for the entity")
    device_type: str = Field(..., description="Device type (e.g., 'light', 'lock', 'tank')")
    suggested_area: str | None = Field(None, description="Suggested area/location for the entity")
    capabilities: list[str] | None = Field(default_factory=list, description="Entity capabilities")
    notes: str | None = Field(None, description="Optional notes about the entity mapping")


class CreateEntityMappingResponse(BaseModel):
    """Response model for entity mapping creation."""

    status: str
    entity_id: str
    message: str
    entity_data: dict | None = None
