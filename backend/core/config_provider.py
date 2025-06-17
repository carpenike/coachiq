"""
RVCConfigProvider - Centralized RV-C Configuration Management

This module provides a centralized configuration provider that loads RVC specification
and device mapping files once and shares them across all services. Eliminates the
duplicate loading that was causing startup inefficiency.

Key Features:
- Single loading point for RVC spec and device mapping
- Lazy initialization with caching
- Proper error handling and validation
- Type-safe access to configuration data
- Integration with existing config_loader functions
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.integrations.rvc.config_loader import (
    get_default_paths,
    load_device_mapping,
    load_rvc_spec,
    extract_coach_info
)
from backend.models.common import CoachInfo

logger = logging.getLogger(__name__)


class RVCConfigProvider:
    """
    Centralized RVC configuration provider.

    Loads RVC specification and device mapping files once during startup
    and provides shared access across all services. Eliminates duplicate
    file loading that was causing startup inefficiency.
    """

    def __init__(self, spec_path: Optional[Path] = None, device_mapping_path: Optional[Path] = None):
        """
        Initialize the RVC config provider.

        Args:
            spec_path: Path to RVC spec JSON file (auto-detected if None)
            device_mapping_path: Path to device mapping YAML file (auto-detected if None)
        """
        self._spec_path: Optional[Path] = spec_path
        self._device_mapping_path: Optional[Path] = device_mapping_path

        # Loaded configuration data
        self._spec_data: Optional[Dict[str, Any]] = None
        self._device_mapping_data: Optional[Dict[str, Any]] = None
        self._coach_info: Optional[CoachInfo] = None

        # Initialization state
        self._initialized: bool = False

    async def initialize(self):
        """
        Load configuration files once during startup.

        This method is called by the ServiceRegistry during startup to ensure
        configuration is loaded exactly once and shared across all services.

        Raises:
            FileNotFoundError: If required configuration files don't exist
            ConfigValidationError: If configuration validation fails
        """
        if self._initialized:
            logger.debug("RVCConfigProvider already initialized")
            return

        logger.info("RVCConfigProvider: Loading configuration files...")

        try:
            # Determine paths if not provided
            if not self._spec_path or not self._device_mapping_path:
                spec_path_str, device_mapping_path_str = get_default_paths()
                self._spec_path = Path(spec_path_str)
                self._device_mapping_path = Path(device_mapping_path_str)

            # Load RVC specification
            logger.info(f"Loading RVC spec from: {self._spec_path}")
            self._spec_data = load_rvc_spec(str(self._spec_path))

            # Load device mapping
            logger.info(f"Loading device mapping from: {self._device_mapping_path}")
            self._device_mapping_data = load_device_mapping(str(self._device_mapping_path))

            # Extract coach information
            self._coach_info = extract_coach_info(
                self._device_mapping_data,
                str(self._device_mapping_path)
            )

            self._initialized = True

            # Log summary
            pgn_count = len(self._spec_data.get('pgns', {}))
            entity_count = len(self._device_mapping_data.get('entities', {}))

            logger.info(
                f"RVCConfigProvider: Configuration loaded successfully - "
                f"PGNs: {pgn_count}, Entities: {entity_count}, "
                f"Coach: {self._coach_info.year} {self._coach_info.make} {self._coach_info.model}"
            )

        except Exception as e:
            logger.error(f"RVCConfigProvider: Failed to load configuration - {e}")
            self._initialized = False
            raise

    def _ensure_initialized(self):
        """Ensure the provider is initialized before accessing data."""
        if not self._initialized:
            raise RuntimeError(
                "RVCConfigProvider not initialized. Call initialize() first."
            )

    @property
    def spec_data(self) -> Dict[str, Any]:
        """
        Get RVC specification data.

        Returns:
            Complete RVC specification dictionary

        Raises:
            RuntimeError: If provider not initialized
        """
        self._ensure_initialized()
        return self._spec_data

    @property
    def device_mapping_data(self) -> Dict[str, Any]:
        """
        Get device mapping data.

        Returns:
            Complete device mapping dictionary

        Raises:
            RuntimeError: If provider not initialized
        """
        self._ensure_initialized()
        return self._device_mapping_data

    @property
    def coach_info(self) -> CoachInfo:
        """
        Get coach information.

        Returns:
            CoachInfo object with vehicle metadata

        Raises:
            RuntimeError: If provider not initialized
        """
        self._ensure_initialized()
        return self._coach_info

    def get_entity_config(self, entity_id: str) -> Dict[str, Any]:
        """
        Get configuration for a specific entity.

        Args:
            entity_id: The entity identifier

        Returns:
            Entity configuration dictionary, empty if not found
        """
        self._ensure_initialized()
        return self.device_mapping_data.get('entities', {}).get(entity_id, {})

    def get_pgn_config(self, pgn: int) -> Dict[str, Any]:
        """
        Get PGN configuration from spec.

        Args:
            pgn: The PGN number

        Returns:
            PGN configuration dictionary, empty if not found
        """
        self._ensure_initialized()
        return self.spec_data.get('pgns', {}).get(str(pgn), {})

    def get_entity_list(self) -> List[str]:
        """
        Get list of all entity IDs.

        Returns:
            List of entity identifiers
        """
        self._ensure_initialized()
        return list(self.device_mapping_data.get('entities', {}).keys())

    def get_pgn_list(self) -> List[int]:
        """
        Get list of all PGN numbers.

        Returns:
            List of PGN numbers as integers
        """
        self._ensure_initialized()
        pgns = self.spec_data.get('pgns', {}).keys()
        return [int(pgn) for pgn in pgns if pgn.isdigit()]

    def has_entity(self, entity_id: str) -> bool:
        """
        Check if an entity exists in the configuration.

        Args:
            entity_id: The entity identifier

        Returns:
            True if entity exists, False otherwise
        """
        self._ensure_initialized()
        return entity_id in self.device_mapping_data.get('entities', {})

    def has_pgn(self, pgn: int) -> bool:
        """
        Check if a PGN exists in the specification.

        Args:
            pgn: The PGN number

        Returns:
            True if PGN exists, False otherwise
        """
        self._ensure_initialized()
        return str(pgn) in self.spec_data.get('pgns', {})

    def get_entities_by_device_type(self, device_type: str) -> List[str]:
        """
        Get all entity IDs of a specific device type.

        Args:
            device_type: The device type (e.g., 'light', 'fan', 'awning')

        Returns:
            List of entity IDs matching the device type
        """
        self._ensure_initialized()
        matching_entities = []

        for entity_id, entity_config in self.device_mapping_data.get('entities', {}).items():
            if entity_config.get('device_type') == device_type:
                matching_entities.append(entity_id)

        return matching_entities

    def get_configuration_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the loaded configuration.

        Returns:
            Dictionary with configuration statistics and metadata
        """
        self._ensure_initialized()

        entities = self.device_mapping_data.get('entities', {})
        device_types = {}

        # Count entities by device type
        for entity_config in entities.values():
            device_type = entity_config.get('device_type', 'unknown')
            device_types[device_type] = device_types.get(device_type, 0) + 1

        return {
            'coach_info': {
                'year': self._coach_info.year,
                'make': self._coach_info.make,
                'model': self._coach_info.model,
                'trim': self._coach_info.trim,
                'filename': self._coach_info.filename
            },
            'statistics': {
                'total_pgns': len(self.spec_data.get('pgns', {})),
                'total_entities': len(entities),
                'device_types': device_types,
                'spec_file': str(self._spec_path),
                'mapping_file': str(self._device_mapping_path)
            }
        }

    async def shutdown(self):
        """
        Shutdown the config provider.

        Currently a no-op but provided for consistency with service interface.
        """
        logger.debug("RVCConfigProvider: Shutdown complete")

    async def check_health(self) -> 'ServiceStatus':
        """
        Check health of the configuration provider.

        Returns:
            ServiceStatus indicating provider health
        """
        from backend.core.service_registry import ServiceStatus

        if not self._initialized:
            return ServiceStatus.FAILED

        # Verify configuration data is still accessible
        try:
            _ = self.spec_data
            _ = self.device_mapping_data
            return ServiceStatus.HEALTHY
        except Exception:
            return ServiceStatus.DEGRADED

    def __repr__(self) -> str:
        """String representation for debugging."""
        if not self._initialized:
            return "RVCConfigProvider(uninitialized)"

        entity_count = len(self.device_mapping_data.get('entities', {}))
        pgn_count = len(self.spec_data.get('pgns', {}))

        return (f"RVCConfigProvider(entities={entity_count}, pgns={pgn_count}, "
                f"coach={self._coach_info.make} {self._coach_info.model})")
