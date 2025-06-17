"""
Config Service V2 - Repository Pattern Implementation

Example of Phase 2R.3: Service using repositories directly instead of AppState.
This demonstrates the migration path for services to use the repository pattern.
"""

import logging
from typing import Any, Dict, Optional

from backend.repositories import RVCConfigRepository
from backend.models.common import CoachInfo

logger = logging.getLogger(__name__)


class ConfigServiceV2:
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
        logger.info("ConfigServiceV2 initialized with RVCConfigRepository")

    def get_coach_info(self) -> Optional[CoachInfo]:
        """Get coach information."""
        return self._rvc_config_repo.get_coach_info()

    def get_pgn_name(self, pgn_hex: str) -> Optional[str]:
        """Get human-readable name for a PGN."""
        return self._rvc_config_repo.get_pgn_name(pgn_hex)

    def get_command_status_pair(self, command_dgn: str) -> Optional[str]:
        """Get the status DGN for a command DGN."""
        return self._rvc_config_repo.get_command_status_pair(command_dgn)

    def get_configuration_summary(self) -> Dict[str, Any]:
        """Get configuration summary."""
        return self._rvc_config_repo.get_configuration_summary()

    def is_configuration_loaded(self) -> bool:
        """Check if configuration is loaded."""
        return self._rvc_config_repo.is_loaded()

    def get_health_status(self) -> Dict[str, Any]:
        """Get service health status."""
        repo_health = self._rvc_config_repo.get_health_status()

        return {
            "service": "ConfigServiceV2",
            "healthy": repo_health.get("healthy", False),
            "repository_health": repo_health,
            "configuration_loaded": self.is_configuration_loaded(),
        }


# Example factory function for ServiceRegistry registration
def create_config_service_v2() -> ConfigServiceV2:
    """
    Factory function for creating ConfigServiceV2 with dependencies.

    This would be registered with ServiceRegistry and automatically
    get the RVCConfigRepository injected.
    """
    # In real usage, this would get the repository from ServiceRegistry
    # For now, we'll document the pattern
    raise NotImplementedError(
        "This factory should be registered with ServiceRegistry "
        "to get automatic dependency injection of RVCConfigRepository"
    )


# Migration helper for gradual transition
class ConfigServiceMigrationAdapter:
    """
    Adapter to help migrate from AppState-based ConfigService to repository-based.

    This allows gradual migration by providing the same interface while
    using repositories underneath.
    """

    def __init__(self, app_state):
        """Initialize with AppState for backward compatibility."""
        # Extract repository from AppState
        self._rvc_config_repo = app_state._rvc_config_repo
        self._app_state = app_state  # Keep reference for any legacy needs

    def get_coach_info(self) -> Optional[CoachInfo]:
        """Get coach information - delegates to repository."""
        return self._rvc_config_repo.get_coach_info()

    def get_pgn_hex_to_name_map(self) -> Dict[str, str]:
        """Legacy method - delegates to repository."""
        if self._rvc_config_repo.is_loaded() and self._rvc_config_repo._config:
            return self._rvc_config_repo._config.pgn_hex_to_name_map
        return {}

    # ... other legacy methods that delegate to repository ...
