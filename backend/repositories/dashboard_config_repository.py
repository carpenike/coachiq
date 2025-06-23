"""Dashboard configuration repository.

This repository manages dashboard configurations, widget layouts,
and user preferences using the repository pattern.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.performance import PerformanceMonitor
from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class DashboardConfig:
    """Dashboard configuration model."""

    def __init__(
        self,
        user_id: str,
        layout: dict[str, Any],
        widgets: list[dict[str, Any]],
        preferences: dict[str, Any],
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.user_id = user_id
        self.layout = layout
        self.widgets = widgets
        self.preferences = preferences
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "layout": self.layout,
            "widgets": self.widgets,
            "preferences": self.preferences,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DashboardConfig":
        """Create from dictionary."""
        return cls(
            user_id=data["user_id"],
            layout=data["layout"],
            widgets=data["widgets"],
            preferences=data["preferences"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


class DashboardConfigRepository(MonitoredRepository):
    """Repository for dashboard configurations."""

    def __init__(self, database_manager, performance_monitor: PerformanceMonitor, data_dir: Path):
        """Initialize dashboard config repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
            data_dir: Directory for storing dashboard configurations
        """
        super().__init__(database_manager, performance_monitor)
        self.data_dir = data_dir / "dashboards"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._configs: dict[str, DashboardConfig] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        """Ensure configurations are loaded from disk."""
        if not self._loaded:
            await self._load_from_disk()
            self._loaded = True

    @MonitoredRepository._monitored_operation("load_from_disk")
    async def _load_from_disk(self) -> None:
        """Load all dashboard configurations from disk."""
        async with self._lock:
            self._configs.clear()

            for config_file in self.data_dir.glob("*.json"):
                try:
                    with open(config_file) as f:
                        data = json.load(f)

                    config = DashboardConfig.from_dict(data)
                    self._configs[config.user_id] = config

                except Exception as e:
                    logger.error(f"Failed to load dashboard config {config_file}: {e}")

    @MonitoredRepository._monitored_operation("save_to_disk")
    async def _save_to_disk(self, config: DashboardConfig) -> None:
        """Save a dashboard configuration to disk."""
        config_file = self.data_dir / f"{config.user_id}.json"

        try:
            with open(config_file, "w") as f:
                json.dump(config.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save dashboard config for {config.user_id}: {e}")
            raise

    @MonitoredRepository._monitored_operation("get_by_user_id")
    async def get_by_user_id(self, user_id: str) -> DashboardConfig | None:
        """Get dashboard configuration by user ID.

        Args:
            user_id: The user ID

        Returns:
            Dashboard configuration if found, None otherwise
        """
        await self._ensure_loaded()

        async with self._lock:
            return self._configs.get(user_id)

    @MonitoredRepository._monitored_operation("create_default")
    async def create_default(self, user_id: str) -> DashboardConfig:
        """Create a default dashboard configuration.

        Args:
            user_id: The user ID

        Returns:
            New default dashboard configuration
        """
        default_layout = {"type": "grid", "columns": 3, "rows": 3, "gap": 16}

        default_widgets = [
            {
                "id": "entity-summary",
                "type": "entity-summary",
                "position": {"x": 0, "y": 0, "w": 1, "h": 1},
                "title": "Entity Summary",
            },
            {
                "id": "system-metrics",
                "type": "system-metrics",
                "position": {"x": 1, "y": 0, "w": 1, "h": 1},
                "title": "System Metrics",
            },
            {
                "id": "can-status",
                "type": "can-status",
                "position": {"x": 2, "y": 0, "w": 1, "h": 1},
                "title": "CAN Bus Status",
            },
            {
                "id": "activity-feed",
                "type": "activity-feed",
                "position": {"x": 0, "y": 1, "w": 3, "h": 2},
                "title": "Activity Feed",
            },
        ]

        default_preferences = {
            "theme": "auto",
            "refresh_interval": 5000,
            "show_notifications": True,
        }

        config = DashboardConfig(
            user_id=user_id,
            layout=default_layout,
            widgets=default_widgets,
            preferences=default_preferences,
        )

        async with self._lock:
            self._configs[user_id] = config
            await self._save_to_disk(config)

        return config

    @MonitoredRepository._monitored_operation("update_layout")
    async def update_layout(self, user_id: str, layout: dict[str, Any]) -> DashboardConfig:
        """Update dashboard layout for a user.

        Args:
            user_id: The user ID
            layout: New layout configuration

        Returns:
            Updated dashboard configuration
        """
        await self._ensure_loaded()

        async with self._lock:
            config = self._configs.get(user_id)
            if not config:
                config = await self.create_default(user_id)

            config.layout = layout
            config.updated_at = datetime.now()

            await self._save_to_disk(config)

        return config

    @MonitoredRepository._monitored_operation("update_widgets")
    async def update_widgets(self, user_id: str, widgets: list[dict[str, Any]]) -> DashboardConfig:
        """Update dashboard widgets for a user.

        Args:
            user_id: The user ID
            widgets: New widgets configuration

        Returns:
            Updated dashboard configuration
        """
        await self._ensure_loaded()

        async with self._lock:
            config = self._configs.get(user_id)
            if not config:
                config = await self.create_default(user_id)

            config.widgets = widgets
            config.updated_at = datetime.now()

            await self._save_to_disk(config)

        return config

    @MonitoredRepository._monitored_operation("update_preferences")
    async def update_preferences(
        self, user_id: str, preferences: dict[str, Any]
    ) -> DashboardConfig:
        """Update dashboard preferences for a user.

        Args:
            user_id: The user ID
            preferences: New preferences

        Returns:
            Updated dashboard configuration
        """
        await self._ensure_loaded()

        async with self._lock:
            config = self._configs.get(user_id)
            if not config:
                config = await self.create_default(user_id)

            config.preferences.update(preferences)
            config.updated_at = datetime.now()

            await self._save_to_disk(config)

        return config

    @MonitoredRepository._monitored_operation("delete")
    async def delete(self, user_id: str) -> bool:
        """Delete a dashboard configuration.

        Args:
            user_id: The user ID

        Returns:
            True if deleted, False if not found
        """
        await self._ensure_loaded()

        async with self._lock:
            if user_id not in self._configs:
                return False

            del self._configs[user_id]

            config_file = self.data_dir / f"{user_id}.json"
            if config_file.exists():
                config_file.unlink()

        return True

    @MonitoredRepository._monitored_operation("list_all")
    async def list_all(self) -> list[DashboardConfig]:
        """List all dashboard configurations.

        Returns:
            List of all dashboard configurations
        """
        await self._ensure_loaded()

        async with self._lock:
            return list(self._configs.values())
