"""
RVC Configuration Repository

Manages RV-C protocol configuration data with clear separation of concerns.
Part of Phase 2R: AppState Repository Migration

This repository handles:
- RV-C specification data
- Device mapping configuration
- PGN name mappings
- Command/status DGN pairs
- Coach information
"""

import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from backend.models.common import CoachInfo

logger = logging.getLogger(__name__)


@dataclass
class RVCConfiguration:
    """Encapsulates all RV-C configuration data."""
    raw_device_mapping: Dict[Tuple[str, str], Any]
    pgn_hex_to_name_map: Dict[str, str]
    coach_info: Optional[CoachInfo]
    known_command_status_pairs: Dict[str, str]
    spec_meta: Dict[str, Any]
    decoder_map: Dict[str, Any]
    mapping_dict: Dict[str, Any]
    entity_map: Dict[str, Any]
    entity_ids: list[str]
    inst_map: Dict[str, Any]
    unique_instances: Dict[str, Any]


class RVCConfigRepository:
    """
    Repository for RV-C configuration data.

    This class encapsulates all RV-C protocol configuration,
    providing a clean read-only interface for configuration access.
    """

    def __init__(self):
        """Initialize the RVC configuration repository."""
        self._config: Optional[RVCConfiguration] = None
        logger.info("RVCConfigRepository initialized")

    def load_configuration(
        self,
        decoder_map: Dict[str, Any],
        spec_meta: Dict[str, Any],
        mapping_dict: Dict[str, Any],
        entity_map: Dict[str, Any],
        entity_ids: list[str],
        inst_map: Dict[str, Any],
        unique_instances: Dict[str, Any],
        pgn_hex_to_name_map: Dict[str, str],
        dgn_pairs: Dict[str, str],
        coach_info: Optional[CoachInfo]
    ) -> None:
        """
        Load RV-C configuration data.

        This method is typically called once during startup to populate
        the repository with configuration data.
        """
        # Process command/status pairs
        known_pairs = {}
        if dgn_pairs:
            for cmd_dgn, status_dgn in dgn_pairs.items():
                known_pairs[cmd_dgn.upper()] = status_dgn.upper()

        # Create mapping dict for raw device mapping
        raw_mapping = {}
        for key, value in mapping_dict.items():
            if isinstance(key, tuple) and len(key) == 2:
                raw_mapping[key] = value

        self._config = RVCConfiguration(
            raw_device_mapping=raw_mapping,
            pgn_hex_to_name_map=pgn_hex_to_name_map,
            coach_info=coach_info,
            known_command_status_pairs=known_pairs,
            spec_meta=spec_meta,
            decoder_map=decoder_map,
            mapping_dict=mapping_dict,
            entity_map=entity_map,
            entity_ids=entity_ids,
            inst_map=inst_map,
            unique_instances=unique_instances
        )

        logger.info(
            f"RVC configuration loaded: {len(entity_ids)} entities, "
            f"{len(pgn_hex_to_name_map)} PGNs, {len(known_pairs)} command/status pairs"
        )

    def get_pgn_name(self, pgn_hex: str) -> Optional[str]:
        """
        Get the human-readable name for a PGN.

        Args:
            pgn_hex: PGN in hex format

        Returns:
            PGN name or None if not found
        """
        if not self._config:
            return None
        return self._config.pgn_hex_to_name_map.get(pgn_hex)

    def get_command_status_pair(self, command_dgn: str) -> Optional[str]:
        """
        Get the status DGN for a command DGN.

        Args:
            command_dgn: Command DGN in hex format

        Returns:
            Status DGN or None if not found
        """
        if not self._config:
            return None
        return self._config.known_command_status_pairs.get(command_dgn.upper())

    def get_coach_info(self) -> Optional[CoachInfo]:
        """Get coach information."""
        return self._config.coach_info if self._config else None

    def get_entity_config(self, dgn_hex: str, instance: str) -> Optional[Dict[str, Any]]:
        """
        Get entity configuration by DGN and instance.

        Args:
            dgn_hex: DGN in hex format
            instance: Instance identifier

        Returns:
            Entity configuration or None if not found
        """
        if not self._config:
            return None
        key = (dgn_hex, instance)
        return self._config.entity_map.get(key)

    def get_raw_device_mapping(self) -> Dict[Tuple[str, str], Any]:
        """Get raw device mapping data."""
        if not self._config:
            return {}
        return self._config.raw_device_mapping.copy()

    def is_loaded(self) -> bool:
        """Check if configuration is loaded."""
        return self._config is not None

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get repository health status.

        Returns:
            Health status information
        """
        if not self._config:
            return {
                "healthy": False,
                "reason": "Configuration not loaded"
            }

        return {
            "healthy": True,
            "entity_count": len(self._config.entity_ids),
            "pgn_count": len(self._config.pgn_hex_to_name_map),
            "command_pairs": len(self._config.known_command_status_pairs),
            "coach_info_loaded": self._config.coach_info is not None
        }

    def get_configuration_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the loaded configuration.

        Returns:
            Configuration summary
        """
        if not self._config:
            return {"loaded": False}

        return {
            "loaded": True,
            "entities": len(self._config.entity_ids),
            "pgns": len(self._config.pgn_hex_to_name_map),
            "command_status_pairs": len(self._config.known_command_status_pairs),
            "unique_instances": len(self._config.unique_instances),
            "coach_model": self._config.coach_info.model if self._config.coach_info else "Unknown",
        }
