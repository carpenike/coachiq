"""RV-C configuration facade (renamed from ConfigService in audit A10).

Thin wrapper over :class:`backend.repositories.RVCConfigRepository`
exposing PGN/coach metadata lookups to the rest of the application.

Renamed from ``ConfigService`` -> ``RVCConfigFacade`` in audit cycle
2026-05-13 PR A10 to disambiguate from Pydantic ``Settings`` (the
canonical app-config object) and from the spec-file loader, now called
``RVCSpecLoader`` (see ``backend/integrations/rvc/spec_loader.py``).
See ADR-0008 for the three-tier config layering rationale.
"""

import logging
from typing import Any

from backend.models.common import CoachInfo
from backend.repositories import RVCConfigRepository

logger = logging.getLogger(__name__)


class RVCConfigFacade:
    """RV-C configuration facade backed by :class:`RVCConfigRepository`.

    This is the request-time read API for RV-C metadata (PGN names,
    coach info, command/status DGN pairs). It is *not* the canonical
    app-configuration source -- that role belongs to Pydantic
    ``Settings`` (``backend.core.config.get_settings``).
    """

    def __init__(self, rvc_config_repository: RVCConfigRepository):
        """
        Initialize with repository dependency injection.

        Args:
            rvc_config_repository: The RVC configuration repository
        """
        self._rvc_config_repo = rvc_config_repository
        logger.info("RVCConfigFacade initialized with RVCConfigRepository")

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
            "service": "RVCConfigFacade",
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


# Example factory function for composition root registration
def create_rvc_config_facade() -> RVCConfigFacade:
    """Factory function for creating RVCConfigFacade with dependencies.

    This would be registered with composition root and automatically
    get the RVCConfigRepository injected.
    """
    raise NotImplementedError(
        "This factory should be registered with composition root "
        "to get automatic dependency injection of RVCConfigRepository"
    )
