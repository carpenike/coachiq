"""
Repository Pattern for Persistence

Base repository classes and implementations for data access layer
using the repository pattern with SQLAlchemy 2.0 and dependency injection.
"""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from sqlalchemy import delete as delete_stmt
from sqlalchemy import select
from sqlalchemy import update as update_stmt
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import ConfigurationModel, DashboardModel
from backend.services.database.database_manager import DatabaseManager

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base repository providing common data access patterns.

    Uses dependency injection for database management and provides
    a clean interface for CRUD operations with SQLAlchemy 2.0.
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the repository with a database manager.

        Args:
            db_manager: Database manager instance for connection handling
        """
        self._db_manager = db_manager

    async def get_session(self) -> AsyncSession | None:
        """Get an async database session."""
        # Check if we're in null backend mode (no persistence)
        database_url = self._db_manager.engine.settings.get_database_url()
        if database_url == "null://memory":
            return None

        async with self._db_manager.get_session() as session:
            return session

    def _is_null_backend(self) -> bool:
        """Check if we're in null backend mode (no persistence)."""
        database_url = self._db_manager.engine.settings.get_database_url()
        return database_url == "null://memory"

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create a new entity."""

    @abstractmethod
    async def get_by_id(self, entity_id: Any) -> T | None:
        """Get an entity by its ID."""

    @abstractmethod
    async def update(self, entity: T) -> T:
        """Update an existing entity."""

    @abstractmethod
    async def delete(self, entity_id: Any) -> bool:
        """Delete an entity by its ID."""


class ConfigRepository(BaseRepository[dict[str, Any]]):
    """
    Repository for managing user configuration data.

    Provides namespace-based configuration storage with type-safe
    operations using SQLAlchemy models.
    """

    async def create(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """
        Create or update configuration entries.

        Args:
            config_data: Dictionary with namespace, key, and value

        Returns:
            The created configuration data
        """
        # In null backend mode, return the input data with mock timestamps
        if self._is_null_backend():
            from datetime import datetime

            now = datetime.utcnow()
            return {
                "namespace": config_data["namespace"],
                "key": config_data["key"],
                "value": str(config_data["value"]),
                "created_at": now,
                "updated_at": now,
            }

        namespace = config_data["namespace"]
        key = config_data["key"]
        value = str(config_data["value"])

        async with self._db_manager.get_session() as session:
            # Check if config already exists
            stmt = select(ConfigurationModel).where(
                ConfigurationModel.namespace == namespace, ConfigurationModel.key == key
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                # Update existing
                config.value = value
            else:
                # Create new
                config = ConfigurationModel(namespace=namespace, key=key, value=value)
                session.add(config)

            await session.commit()
            await session.refresh(config)

        return {
            "namespace": config.namespace,
            "key": config.key,
            "value": config.value,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }

    async def get_by_id(self, config_id: tuple[str, str]) -> dict[str, Any] | None:
        """
        Get configuration by namespace and key.

        Args:
            config_id: Tuple of (namespace, key)

        Returns:
            Configuration data or None if not found
        """
        # In null backend mode, no configuration exists
        if self._is_null_backend():
            return None

        namespace, key = config_id

        async with self._db_manager.get_session() as session:
            stmt = select(ConfigurationModel).where(
                ConfigurationModel.namespace == namespace, ConfigurationModel.key == key
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                return {
                    "namespace": config.namespace,
                    "key": config.key,
                    "value": config.value,
                    "created_at": config.created_at,
                    "updated_at": config.updated_at,
                }

        return None

    async def get_namespace(self, namespace: str) -> dict[str, Any]:
        """
        Get all configuration for a namespace.

        Args:
            namespace: Configuration namespace

        Returns:
            Dictionary of key-value pairs for the namespace
        """
        # In null backend mode, return empty configuration
        if self._is_null_backend():
            return {}

        async with self._db_manager.get_session() as session:
            stmt = select(ConfigurationModel).where(ConfigurationModel.namespace == namespace)
            result = await session.execute(stmt)
            configs = result.scalars().all()

            return {config.key: config.value for config in configs}

    async def update(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """Update configuration (same as create for this use case)."""
        return await self.create(config_data)

    async def delete(self, config_id: tuple[str, str]) -> bool:
        """
        Delete configuration by namespace and key.

        Args:
            config_id: Tuple of (namespace, key)

        Returns:
            True if deleted, False if not found
        """
        # In null backend mode, nothing to delete
        if self._is_null_backend():
            return False

        namespace, key = config_id

        async with self._db_manager.get_session() as session:
            stmt = delete_stmt(ConfigurationModel).where(
                ConfigurationModel.namespace == namespace, ConfigurationModel.key == key
            )
            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount > 0

    async def delete_namespace(self, namespace: str) -> int:
        """
        Delete all configuration for a namespace.

        Args:
            namespace: Configuration namespace

        Returns:
            Number of deleted entries
        """
        # In null backend mode, nothing to delete
        if self._is_null_backend():
            return 0
        async with self._db_manager.get_session() as session:
            stmt = delete_stmt(ConfigurationModel).where(ConfigurationModel.namespace == namespace)
            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount

    async def get(self, namespace: str, key: str) -> str | None:
        """
        Get configuration value by namespace and key.

        Args:
            namespace: Configuration namespace
            key: Configuration key

        Returns:
            Configuration value or None if not found
        """
        # In null backend mode, no configuration exists
        if self._is_null_backend():
            return None

        config = await self.get_by_id((namespace, key))
        return config.get("value") if config else None

    async def set(self, namespace: str, key: str, value: str) -> bool:
        """
        Set configuration value.

        Args:
            namespace: Configuration namespace
            key: Configuration key
            value: Configuration value

        Returns:
            True if successful
        """
        # In null backend mode, simulate successful operation
        if self._is_null_backend():
            return True

        try:
            await self.create({"namespace": namespace, "key": key, "value": value})
            return True
        except Exception:
            return False


class DashboardRepository(BaseRepository[dict[str, Any]]):
    """
    Repository for managing dashboard configurations.

    Provides CRUD operations for dashboard layouts, configurations,
    and default dashboard management using SQLAlchemy models.
    """

    async def create(self, dashboard: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new dashboard configuration.

        Args:
            dashboard: Dashboard data with name, config, and optional is_default

        Returns:
            The created dashboard with ID
        """
        # In null backend mode, return mock dashboard data
        if self._is_null_backend():
            from datetime import datetime

            now = datetime.utcnow()
            return {
                "id": 1,  # Mock ID
                "name": dashboard["name"],
                "config": str(dashboard["config"]),
                "is_default": dashboard.get("is_default", False),
                "description": dashboard.get("description"),
                "created_at": now,
                "updated_at": now,
            }

        name = dashboard["name"]
        config = str(dashboard["config"])
        is_default = dashboard.get("is_default", False)

        async with self._db_manager.get_session() as session:
            # If setting as default, unset other defaults
            if is_default:
                stmt = update_stmt(DashboardModel).values(is_default=False)
                await session.execute(stmt)

            new_dashboard = DashboardModel(
                name=name,
                config=config,
                is_default=is_default,
                description=dashboard.get("description"),
            )
            session.add(new_dashboard)
            await session.commit()
            await session.refresh(new_dashboard)

            return {
                "id": new_dashboard.id,
                "name": new_dashboard.name,
                "config": new_dashboard.config,
                "is_default": new_dashboard.is_default,
                "description": new_dashboard.description,
                "created_at": new_dashboard.created_at,
                "updated_at": new_dashboard.updated_at,
            }

    async def get_by_id(self, dashboard_id: int) -> dict[str, Any] | None:
        """
        Get dashboard by ID.

        Args:
            dashboard_id: Dashboard ID

        Returns:
            Dashboard data or None if not found
        """
        # In null backend mode, no dashboards exist
        if self._is_null_backend():
            return None

        async with self._db_manager.get_session() as session:
            stmt = select(DashboardModel).where(DashboardModel.id == dashboard_id)
            result = await session.execute(stmt)
            dashboard = result.scalar_one_or_none()

            if dashboard:
                return {
                    "id": dashboard.id,
                    "name": dashboard.name,
                    "config": dashboard.config,
                    "is_default": dashboard.is_default,
                    "description": dashboard.description,
                    "created_at": dashboard.created_at,
                    "updated_at": dashboard.updated_at,
                }

        return None

    async def get_by_name(self, name: str) -> dict[str, Any] | None:
        """
        Get dashboard by name.

        Args:
            name: Dashboard name

        Returns:
            Dashboard data or None if not found
        """
        # In null backend mode, no dashboards exist
        if self._is_null_backend():
            return None

        async with self._db_manager.get_session() as session:
            stmt = select(DashboardModel).where(DashboardModel.name == name)
            result = await session.execute(stmt)
            dashboard = result.scalar_one_or_none()

            if dashboard:
                return {
                    "id": dashboard.id,
                    "name": dashboard.name,
                    "config": dashboard.config,
                    "is_default": dashboard.is_default,
                    "description": dashboard.description,
                    "created_at": dashboard.created_at,
                    "updated_at": dashboard.updated_at,
                }

        return None

    async def get_default(self) -> dict[str, Any] | None:
        """
        Get the default dashboard.

        Returns:
            Default dashboard data or None if no default set
        """
        # In null backend mode, return a default in-memory dashboard
        if self._is_null_backend():
            from datetime import datetime

            now = datetime.utcnow()
            return {
                "id": 1,
                "name": "Default Dashboard",
                "config": '{"layout": "grid", "widgets": [], "theme": "light"}',
                "is_default": True,
                "description": "Default in-memory dashboard",
                "created_at": now,
                "updated_at": now,
            }

        async with self._db_manager.get_session() as session:
            stmt = select(DashboardModel).where(DashboardModel.is_default)
            result = await session.execute(stmt)
            dashboard = result.scalar_one_or_none()

            if dashboard:
                return {
                    "id": dashboard.id,
                    "name": dashboard.name,
                    "config": dashboard.config,
                    "is_default": dashboard.is_default,
                    "description": dashboard.description,
                    "created_at": dashboard.created_at,
                    "updated_at": dashboard.updated_at,
                }

        return None

    async def list_all(self) -> list[dict[str, Any]]:
        """
        Get all dashboards.

        Returns:
            List of all dashboard configurations
        """
        # In null backend mode, return default dashboard only
        if self._is_null_backend():
            default_dashboard = await self.get_default()
            return [default_dashboard] if default_dashboard else []

        async with self._db_manager.get_session() as session:
            stmt = select(DashboardModel).order_by(DashboardModel.name)
            result = await session.execute(stmt)
            dashboards = result.scalars().all()

            return [
                {
                    "id": dashboard.id,
                    "name": dashboard.name,
                    "config": dashboard.config,
                    "is_default": dashboard.is_default,
                    "description": dashboard.description,
                    "created_at": dashboard.created_at,
                    "updated_at": dashboard.updated_at,
                }
                for dashboard in dashboards
            ]

    async def update(self, dashboard: dict[str, Any]) -> dict[str, Any]:
        """
        Update an existing dashboard.

        Args:
            dashboard: Dashboard data with id and updated fields

        Returns:
            Updated dashboard data
        """
        # In null backend mode, return updated mock data
        if self._is_null_backend():
            from datetime import datetime

            now = datetime.utcnow()
            return {
                "id": dashboard.get("id", 1),
                "name": dashboard.get("name", "Default Dashboard"),
                "config": str(dashboard.get("config", "{}")),
                "is_default": dashboard.get("is_default", True),
                "description": dashboard.get("description", "Default in-memory dashboard"),
                "created_at": now,
                "updated_at": now,
            }

        dashboard_id = dashboard["id"]
        name = dashboard.get("name")
        config = dashboard.get("config")
        is_default = dashboard.get("is_default")
        description = dashboard.get("description")

        async with self._db_manager.get_session() as session:
            # Get the existing dashboard
            stmt = select(DashboardModel).where(DashboardModel.id == dashboard_id)
            result = await session.execute(stmt)
            existing_dashboard = result.scalar_one_or_none()

            if not existing_dashboard:
                msg = f"Dashboard with id {dashboard_id} not found"
                raise ValueError(msg)

            # If setting as default, unset other defaults
            if is_default:
                stmt = update_stmt(DashboardModel).values(is_default=False)
                await session.execute(stmt)

            # Update fields
            if name is not None:
                existing_dashboard.name = name
            if config is not None:
                existing_dashboard.config = str(config)
            if is_default is not None:
                existing_dashboard.is_default = is_default
            if description is not None:
                existing_dashboard.description = description

            await session.commit()
            await session.refresh(existing_dashboard)

            return {
                "id": existing_dashboard.id,
                "name": existing_dashboard.name,
                "config": existing_dashboard.config,
                "is_default": existing_dashboard.is_default,
                "description": existing_dashboard.description,
                "created_at": existing_dashboard.created_at,
                "updated_at": existing_dashboard.updated_at,
            }

    async def delete(self, dashboard_id: int) -> bool:
        """
        Delete a dashboard by ID.

        Args:
            dashboard_id: Dashboard ID

        Returns:
            True if deleted, False if not found
        """
        # In null backend mode, nothing to delete
        if self._is_null_backend():
            return False

        async with self._db_manager.get_session() as session:
            stmt = delete_stmt(DashboardModel).where(DashboardModel.id == dashboard_id)
            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount > 0

    async def create_default_dashboard(self) -> dict[str, Any]:
        """
        Create a default dashboard configuration.

        Returns:
            Created default dashboard data
        """
        # For null backend mode, return the in-memory default
        if self._is_null_backend():
            return await self.get_default()  # type: ignore

        default_config = {
            "name": "Default Dashboard",
            "config": {"layout": "grid", "widgets": [], "theme": "light"},
            "is_default": True,
            "description": "Default dashboard configuration",
        }
        return await self.create(default_config)

    async def save_config(self, dashboard_id: str, config: dict[str, Any]) -> bool:
        """
        Save dashboard configuration.

        Args:
            dashboard_id: Dashboard ID
            config: Configuration data

        Returns:
            True if successful
        """
        # In null backend mode, simulate successful save
        if self._is_null_backend():
            return True

        try:
            # Try to get existing dashboard
            existing = (
                await self.get_by_name(dashboard_id)
                if isinstance(dashboard_id, str)
                else await self.get_by_id(int(dashboard_id))
            )

            if existing:
                # Update existing
                await self.update({"id": existing["id"], "config": config})
            else:
                # Create new
                await self.create({"name": dashboard_id, "config": config, "is_default": False})
            return True
        except Exception:
            return False
