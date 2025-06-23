"""
Pydantic models for RVC configuration data structure.

This module defines structured models to replace the complex tuple returned
by load_config_data(), improving type safety, maintainability, and clarity.
"""

from typing import Any, Dict, List, Set, Tuple

from pydantic import BaseModel, Field

from backend.models.common import CoachInfo


class RVCSpecMeta(BaseModel):
    """Metadata from the RVC specification."""

    version: str = Field(default="unknown", description="RVC spec version")
    source: str = Field(default="unknown", description="RVC spec source")
    rvc_version: str = Field(default="unknown", description="RVC protocol version")


class RVCEntityMapping(BaseModel):
    """Mapping information for an RVC entity."""

    dgn_hex: str = Field(description="DGN in hex format")
    instance: int = Field(description="Instance number")


class RVCConfiguration(BaseModel):
    """
    Structured RVC configuration data.

    This replaces the complex 10-element tuple returned by load_config_data()
    with a properly typed structure that is easier to work with and maintain.
    """

    # Core RVC specification data
    dgn_dict: dict[int, dict[str, Any]] = Field(
        default_factory=dict, description="Dictionary mapping DGNs to specification entries"
    )

    spec_meta: RVCSpecMeta = Field(
        default_factory=RVCSpecMeta, description="Metadata from the RVC spec"
    )

    # Device mapping data
    mapping_dict: dict[tuple[str, str], list[dict[str, Any]]] = Field(
        default_factory=dict,
        description="Dictionary mapping (DGN, instance) pairs to device entries",
    )

    entity_map: dict[tuple[str, str], dict[str, Any]] = Field(
        default_factory=dict, description="Dictionary mapping entity IDs to device entries"
    )

    entity_ids: set[str] = Field(
        default_factory=set, description="Set of all entity IDs for validation"
    )

    inst_map: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Dictionary mapping entity IDs to (dgn_hex, instance) pairs",
    )

    unique_instances: dict[str, dict[str, dict[str, Any]]] = Field(
        default_factory=dict, description="Dictionary of DGN instances with only one device"
    )

    # Lookup tables
    pgn_hex_to_name_map: dict[str, str] = Field(
        default_factory=dict, description="Dictionary mapping DGN hex strings to PGN names"
    )

    dgn_pairs: dict[str, str] = Field(
        default_factory=dict, description="Dictionary mapping command DGNs to status DGNs"
    )

    # Coach information
    coach_info: CoachInfo = Field(
        default_factory=CoachInfo, description="Coach metadata extracted from mapping file"
    )

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True

    def get_entity_config(self, entity_id: str) -> RVCEntityMapping | None:
        """
        Get entity configuration by ID.

        Args:
            entity_id: The entity ID to look up

        Returns:
            RVCEntityMapping or None if not found
        """
        mapping_data = self.inst_map.get(entity_id)
        if mapping_data:
            return RVCEntityMapping(
                dgn_hex=mapping_data["dgn_hex"], instance=mapping_data["instance"]
            )
        return None

    def get_device_config(self, dgn_hex: str, instance: str) -> dict[str, Any] | None:
        """
        Get device configuration by DGN and instance.

        Args:
            dgn_hex: DGN in hex format
            instance: Instance ID as string

        Returns:
            Device configuration dict or None if not found
        """
        return self.entity_map.get((dgn_hex, instance))

    def get_dgn_spec(self, dgn: int) -> dict[str, Any] | None:
        """
        Get DGN specification by numeric DGN.

        Args:
            dgn: Numeric DGN value

        Returns:
            DGN specification dict or None if not found
        """
        return self.dgn_dict.get(dgn)

    def get_command_dgn(self, status_dgn_hex: str) -> str | None:
        """
        Get command DGN for a given status DGN.

        Args:
            status_dgn_hex: Status DGN in hex format

        Returns:
            Command DGN in hex format or None if not found
        """
        return self.dgn_pairs.get(status_dgn_hex)

    def is_valid_entity(self, entity_id: str) -> bool:
        """
        Check if an entity ID is valid.

        Args:
            entity_id: Entity ID to validate

        Returns:
            True if entity ID is valid
        """
        return entity_id in self.entity_ids
