"""
Persistence Interface Definitions

Abstract interfaces for persistence services that can be implemented
with different backends (SQLite, in-memory, etc.).
"""

from abc import ABC, abstractmethod

from backend.models.persistence import DashboardConfiguration
from backend.models.unmapped import UnmappedEntryModel


class PersistenceServiceInterface(ABC):
    """Abstract interface for persistence services."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the persistence service."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the persistence service is healthy."""

    @abstractmethod
    async def close(self) -> None:
        """Close the persistence service."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the persistence service."""

    @property
    @abstractmethod
    def config_repo(self) -> "ConfigRepositoryInterface":
        """Get the configuration repository."""

    @property
    @abstractmethod
    def dashboard_repo(self) -> "DashboardRepositoryInterface":
        """Get the dashboard repository."""

    @property
    @abstractmethod
    def unmapped_repo(self) -> "UnmappedRepositoryInterface":
        """Get the unmapped repository."""


class ConfigRepositoryInterface(ABC):
    """Abstract interface for configuration persistence."""

    @abstractmethod
    async def get_user_config(self, key: str) -> str | None:
        """Get a user configuration value."""

    @abstractmethod
    async def set_user_config(self, key: str, value: str) -> None:
        """Set a user configuration value."""

    @abstractmethod
    async def get_all_user_configs(self) -> dict[str, str]:
        """Get all user configuration values."""

    @abstractmethod
    async def delete_user_config(self, key: str) -> bool:
        """Delete a user configuration value."""


class DashboardRepositoryInterface(ABC):
    """Abstract interface for dashboard persistence."""

    @abstractmethod
    async def get_dashboard(self, dashboard_id: str) -> DashboardConfiguration | None:
        """Get a dashboard by ID."""

    @abstractmethod
    async def save_dashboard(self, dashboard: DashboardConfiguration) -> None:
        """Save a dashboard configuration."""

    @abstractmethod
    async def list_dashboards(self) -> list[DashboardConfiguration]:
        """List all dashboards."""

    @abstractmethod
    async def delete_dashboard(self, dashboard_id: str) -> bool:
        """Delete a dashboard by ID."""


class UnmappedRepositoryInterface(ABC):
    """Abstract interface for unmapped PGN persistence."""

    @abstractmethod
    async def get_unmapped_pgns(self) -> list[UnmappedEntryModel]:
        """Get all unmapped PGNs."""

    @abstractmethod
    async def save_unmapped_pgn(self, pgn: UnmappedEntryModel) -> None:
        """Save an unmapped PGN."""

    @abstractmethod
    async def delete_unmapped_pgn(self, pgn: int) -> bool:
        """Delete an unmapped PGN."""
