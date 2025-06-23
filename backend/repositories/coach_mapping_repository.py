"""Coach mapping configuration repository.

This repository manages coach mapping configurations and interface resolutions
using the repository pattern.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from backend.core.performance import PerformanceMonitor
from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class CoachMappingRepository(MonitoredRepository):
    """Repository for coach mapping configurations."""

    def __init__(
        self, database_manager, performance_monitor: PerformanceMonitor, mapping_path: Path
    ):
        """Initialize coach mapping repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
            mapping_path: Path to coach mapping file
        """
        super().__init__(database_manager, performance_monitor)
        self._mapping_path = mapping_path
        self._mapping_cache: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    @MonitoredRepository._monitored_operation("load_mapping")
    async def load_mapping(self) -> dict[str, Any]:
        """Load coach mapping from file.

        Returns:
            Dictionary containing coach mapping configuration
        """
        async with self._lock:
            if self._mapping_cache is not None:
                return self._mapping_cache

            try:
                with open(self._mapping_path) as f:
                    self._mapping_cache = yaml.safe_load(f)

                logger.info(f"Loaded coach mapping from {self._mapping_path}")
                return self._mapping_cache

            except Exception as e:
                logger.error(f"Failed to load coach mapping: {e}")
                self._mapping_cache = {}
                return {}

    @MonitoredRepository._monitored_operation("reload_mapping")
    async def reload_mapping(self) -> dict[str, Any]:
        """Reload coach mapping from file.

        Returns:
            Updated coach mapping configuration
        """
        async with self._lock:
            self._mapping_cache = None

        return await self.load_mapping()

    @MonitoredRepository._monitored_operation("get_coach_info")
    async def get_coach_info(self) -> dict[str, Any]:
        """Get coach information from mapping.

        Returns:
            Coach info dictionary
        """
        mapping = await self.load_mapping()
        return mapping.get("coach_info", {})

    @MonitoredRepository._monitored_operation("get_interface_requirements")
    async def get_interface_requirements(self) -> dict[str, Any]:
        """Get interface requirements from mapping.

        Returns:
            Interface requirements dictionary
        """
        mapping = await self.load_mapping()
        return mapping.get("interface_requirements", {})

    @MonitoredRepository._monitored_operation("get_device_mappings")
    async def get_device_mappings(self) -> dict[str, Any]:
        """Get all device mappings.

        Returns:
            Device mappings organized by DGN
        """
        mapping = await self.load_mapping()

        # Extract only device mappings (hex DGN keys)
        device_mappings = {}
        for key, value in mapping.items():
            if key.startswith(tuple("0123456789ABCDEF")):
                device_mappings[key] = value

        return device_mappings

    @MonitoredRepository._monitored_operation("count_devices")
    async def count_devices(self) -> int:
        """Count total number of devices in mapping.

        Returns:
            Total device count
        """
        mapping = await self.load_mapping()
        device_count = 0

        for dgn_hex, instances in mapping.items():
            if dgn_hex.startswith(tuple("0123456789ABCDEF")):
                for devices in instances.values():
                    if isinstance(devices, list):
                        device_count += len(devices)

        return device_count

    @MonitoredRepository._monitored_operation("get_interfaces_used")
    async def get_interfaces_used(self) -> set[str]:
        """Get set of interfaces used in mapping.

        Returns:
            Set of interface names
        """
        mapping = await self.load_mapping()
        interfaces = set()

        def extract_interfaces(obj):
            if isinstance(obj, dict):
                if "interface" in obj:
                    interfaces.add(obj["interface"])
                for value in obj.values():
                    extract_interfaces(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_interfaces(item)

        extract_interfaces(mapping)
        return interfaces

    @MonitoredRepository._monitored_operation("find_devices_by_interface")
    async def find_devices_by_interface(self, interface: str) -> list[dict[str, Any]]:
        """Find all devices using a specific interface.

        Args:
            interface: Interface name to search for

        Returns:
            List of device configurations using the interface
        """
        mapping = await self.load_mapping()
        devices = []

        for dgn_hex, instances in mapping.items():
            if dgn_hex.startswith(tuple("0123456789ABCDEF")):
                for instance_id, device_list in instances.items():
                    if isinstance(device_list, list):
                        for device in device_list:
                            if isinstance(device, dict) and device.get("interface") == interface:
                                devices.append({"dgn": dgn_hex, "instance": instance_id, **device})

        return devices

    @MonitoredRepository._monitored_operation("get_file_metadata")
    async def get_file_metadata(self) -> dict[str, Any]:
        """Get file metadata from mapping.

        Returns:
            File metadata dictionary
        """
        mapping = await self.load_mapping()
        return mapping.get("file_metadata", {})

    def get_mapping_path(self) -> Path:
        """Get the path to the mapping file.

        Returns:
            Path to mapping file
        """
        return self._mapping_path
