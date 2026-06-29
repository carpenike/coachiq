"""
Coach Mapping Service (Refactored with Repository Pattern)

Service for managing coach mapping configurations with interface resolution.
Integrates logical CAN interfaces with coach mapping definitions.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from backend.core.performance import PerformanceMonitor
from backend.repositories.coach_mapping_repository import CoachMappingRepository

logger = logging.getLogger(__name__)


class CoachMappingService:
    """Service for managing coach mapping configurations with performance monitoring."""

    def __init__(
        self,
        coach_mapping_repository: CoachMappingRepository,
        performance_monitor: PerformanceMonitor,
        can_interface_service: Any | None = None,
    ):
        """Initialize coach mapping service with repository.

        Args:
            coach_mapping_repository: Repository for coach mapping data
            performance_monitor: Performance monitoring instance
            can_interface_service: Optional CAN interface service for resolution
        """
        self._repository = coach_mapping_repository
        self._monitor = performance_monitor
        self.can_interface_service = can_interface_service
        self._resolved_cache: dict[str, Any] | None = None
        self._cache_lock = asyncio.Lock()

        # Apply performance monitoring
        self._apply_monitoring()

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        # Wrap methods with performance monitoring
        self.get_current_mapping = self._monitor.monitor_service_method(
            "CoachMappingService", "get_current_mapping"
        )(self.get_current_mapping)

        self.reload_mapping = self._monitor.monitor_service_method(
            "CoachMappingService", "reload_mapping"
        )(self.reload_mapping)

        self.get_interface_requirements = self._monitor.monitor_service_method(
            "CoachMappingService", "get_interface_requirements"
        )(self.get_interface_requirements)

        self.validate_interface_compatibility = self._monitor.monitor_service_method(
            "CoachMappingService", "validate_interface_compatibility"
        )(self.validate_interface_compatibility)

        self.get_mapping_metadata = self._monitor.monitor_service_method(
            "CoachMappingService", "get_mapping_metadata"
        )(self.get_mapping_metadata)

    async def get_current_mapping(self) -> dict[str, Any]:
        """Get current coach mapping with resolved interfaces."""
        async with self._cache_lock:
            if self._resolved_cache is None:
                await self._load_mapping()
            return self._resolved_cache or {}

    async def _load_mapping(self) -> None:
        """Load coach mapping from repository with interface resolution."""
        raw_mapping = await self._repository.load_mapping()

        # Resolve logical interfaces to physical interfaces
        self._resolved_cache = self._resolve_interfaces(raw_mapping)

    def _resolve_interfaces(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Resolve logical interfaces to physical interfaces throughout mapping."""
        if not self.can_interface_service:
            return mapping

        def resolve_recursive(obj):
            if isinstance(obj, dict):
                if "interface" in obj:
                    logical_interface = obj["interface"]
                    try:
                        obj["interface"] = self.can_interface_service.resolve_interface(
                            logical_interface
                        )
                        obj["_logical_interface"] = logical_interface  # Keep for reference
                    except (ValueError, AttributeError):
                        # Keep original if can't resolve
                        pass

                for value in obj.values():
                    resolve_recursive(value)

            elif isinstance(obj, list):
                for item in obj:
                    resolve_recursive(item)

        resolved = mapping.copy()
        resolve_recursive(resolved)
        return resolved

    async def reload_mapping(self) -> None:
        """Reload coach mapping from repository."""
        async with self._cache_lock:
            self._resolved_cache = None
            await self._load_mapping()

    async def get_interface_requirements(self) -> dict[str, Any]:
        """Get interface requirements from coach config."""
        return await self._repository.get_interface_requirements()

    def get_runtime_interface_mappings(self) -> dict[str, str]:
        """Get actual runtime interface mappings from CAN service."""
        if self.can_interface_service:
            return self.can_interface_service.get_all_mappings()
        return {}

    async def validate_interface_compatibility(self) -> dict[str, Any]:
        """Validate that runtime mappings are compatible with coach requirements."""
        requirements = await self.get_interface_requirements()
        runtime_mappings = self.get_runtime_interface_mappings()

        issues = []
        recommendations = []

        # Check if all required logical interfaces are mapped
        for logical_name, req_info in requirements.items():
            if logical_name not in runtime_mappings:
                issues.append(
                    f"Required logical interface '{logical_name}' not mapped to physical interface"
                )
            else:
                # Check for speed recommendations (informational)
                recommended_speed = req_info.get("recommended_speed")
                if recommended_speed:
                    recommendations.append(
                        f"Interface '{logical_name}' -> '{runtime_mappings[logical_name]}': "
                        f"recommended speed {recommended_speed} bps"
                    )

        # Check for unmapped runtime interfaces
        for logical_name in runtime_mappings:
            if logical_name not in requirements:
                recommendations.append(
                    f"Runtime interface '{logical_name}' has no coach requirements defined"
                )

        return {
            "compatible": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations,
            "requirements": requirements,
            "runtime_mappings": runtime_mappings,
        }

    async def get_mapping_metadata(self) -> dict[str, Any]:
        """Get metadata about current coach mapping."""
        # Get data from repository
        coach_info = await self._repository.get_coach_info()
        file_metadata = await self._repository.get_file_metadata()
        interface_requirements = await self._repository.get_interface_requirements()
        device_count = await self._repository.count_devices()
        interfaces_used = await self._repository.get_interfaces_used()

        # Get resolved mapping for logical/physical tracking
        mapping = await self.get_current_mapping()

        logical_interfaces_used = set()
        physical_interfaces_used = set()

        # Extract logical and physical interfaces from resolved mapping
        def extract_interfaces(obj):
            if isinstance(obj, dict):
                if "interface" in obj:
                    physical_interfaces_used.add(obj["interface"])
                if "_logical_interface" in obj:
                    logical_interfaces_used.add(obj["_logical_interface"])
                for value in obj.values():
                    extract_interfaces(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_interfaces(item)

        extract_interfaces(mapping)

        # Validate compatibility
        compatibility = await self.validate_interface_compatibility()

        return {
            "coach_info": coach_info,
            "file_metadata": file_metadata,
            "device_count": device_count,
            "logical_interfaces_used": list(logical_interfaces_used),
            "physical_interfaces_used": list(physical_interfaces_used),
            "interface_requirements": interface_requirements,
            "interface_compatibility": compatibility,
            "mapping_path": str(self._repository.get_mapping_path()),
        }
