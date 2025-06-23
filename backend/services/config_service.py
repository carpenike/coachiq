"""
Config Service - Repository Pattern Implementation

Service for configuration management using clean repository pattern
with no legacy AppState dependencies.
"""

import logging
from typing import Any, Dict, Optional

from backend.models.common import CoachInfo
from backend.repositories import RVCConfigRepository

logger = logging.getLogger(__name__)


class ConfigService:
    """
    Configuration service that uses RVCConfigRepository directly.

    This is an example of the target architecture where services
    depend on specific repositories rather than the monolithic AppState.
    """

    def __init__(self, rvc_config_repository: RVCConfigRepository):
        """
        Initialize with repository dependency injection.

        Args:
            rvc_config_repository: The RVC configuration repository
        """
        self._rvc_config_repo = rvc_config_repository
        logger.info("ConfigService initialized with RVCConfigRepository")

    def get_coach_info(self) -> CoachInfo | None:
        """Get coach information."""
        return self._rvc_config_repo.get_coach_info()

    def get_pgn_name(self, pgn_hex: str) -> str | None:
        """Get human-readable name for a PGN."""
        return self._rvc_config_repo.get_pgn_name(pgn_hex)

    def get_command_status_pair(self, command_dgn: str) -> str | None:
        """Get the status DGN for a command DGN."""
        return self._rvc_config_repo.get_command_status_pair(command_dgn)

    def get_configuration_summary(self) -> dict[str, Any]:
        """Get configuration summary."""
        return self._rvc_config_repo.get_configuration_summary()

    def is_configuration_loaded(self) -> bool:
        """Check if configuration is loaded."""
        return self._rvc_config_repo.is_loaded()

    def get_health_status(self) -> dict[str, Any]:
        """Get service health status."""
        repo_health = self._rvc_config_repo.get_health_status()

        return {
            "service": "ConfigService",
            "healthy": repo_health.get("healthy", False),
            "repository_health": repo_health,
            "configuration_loaded": self.is_configuration_loaded(),
        }

    async def get_device_mapping_content(self) -> str:
        """Get device mapping content."""
        # This would return the device mapping YAML content
        # For now, return a placeholder
        return "# Device mapping configuration\n"

    async def get_spec_content(self) -> str:
        """Get RV-C specification content."""
        # This would return the RV-C spec JSON content
        # For now, return a placeholder
        return '{"rvc": "specification"}'

    async def get_config_status(self) -> dict[str, Any]:
        """Get configuration status."""
        return {
            "loaded": self.is_configuration_loaded(),
            "summary": self.get_configuration_summary(),
            "health": self.get_health_status(),
        }


# Example factory function for ServiceRegistry registration
def create_config_service() -> ConfigService:
    """
    Factory function for creating ConfigService with dependencies.

    This would be registered with ServiceRegistry and automatically
    get the RVCConfigRepository injected.
    """
    # In real usage, this would get the repository from ServiceRegistry
    # For now, we'll document the pattern
    raise NotImplementedError(
        "This factory should be registered with ServiceRegistry "
        "to get automatic dependency injection of RVCConfigRepository"
    )
