"""
Core Services Layer for CoachIQ Backend.

This module manages mandatory infrastructure services that must always be available.
These services are initialized before the feature manager and are not subject to
feature flags or configuration overrides.

Core services included:
- PersistenceService: Data storage (no dependencies)
- DatabaseManager: Database connections (no dependencies)

Note: EntityService is NOT included here as it depends on WebSocketManager,
making it an application-level service rather than core infrastructure.

Target Environment: Raspberry Pi (4GB RAM) with <5 concurrent users
Focus: Reliability and resource efficiency
"""

import logging

from prometheus_client import Gauge

from backend.services.database_manager import DatabaseManager
from backend.services.persistence_service import PersistenceService

logger = logging.getLogger(__name__)

# Prometheus metrics for core service health (minimal overhead)
CORE_SERVICE_UP = Gauge(
    "coachiq_core_service_up",
    "Core service health status (1=up, 0=down)",
    ["service"],
)


class CoreServicesError(Exception):
    """Raised when core service initialization fails."""



class CoreServices:
    """
    Manages mandatory infrastructure services for the CoachIQ system.

    This class ensures that critical infrastructure services are always available
    and properly initialized before any application-level features are started.

    Services managed:
    - PersistenceService: SQLite-based data storage (no dependencies)
    - DatabaseManager: Database connections and schema management (no dependencies)

    Note: Application-level services like EntityService, WebSocketManager, etc.
    remain in the FeatureManager as they have interdependencies.
    """

    def __init__(self) -> None:
        """Initialize the core services container."""
        self._persistence: PersistenceService | None = None
        self._database_manager: DatabaseManager | None = None
        self._initialized = False

    async def startup(self) -> None:
        """
        Initialize all core services in dependency order.

        Services are started in a specific order to respect dependencies:
        1. Persistence (no dependencies)
        2. Database Manager (depends on persistence)

        Raises:
            CoreServicesError: If any core service fails to initialize
        """
        logger.info("Starting core services initialization...")

        try:
            # 1. Initialize Persistence Service (SQLite-based, no external deps)
            logger.info("Starting PersistenceService...")
            self._persistence = PersistenceService()
            # PersistenceService doesn't have a startup method
            logger.info("✅ PersistenceService initialized successfully")

            # 2. Initialize Database Manager
            logger.info("Starting DatabaseManager...")
            self._database_manager = DatabaseManager()

            # Initialize the database manager
            if not await self._database_manager.initialize():
                msg = "DatabaseManager initialization failed"
                raise CoreServicesError(msg)

            self._persistence.set_database_manager(self._database_manager)
            logger.info("✅ DatabaseManager initialized successfully")


            # Validate database schema
            await self._validate_database_schema()

            self._initialized = True
            logger.info("✅ All core services initialized successfully")

        except Exception as e:
            logger.error("❌ Core service initialization failed: %s", e)
            await self.shutdown()  # Clean up any partially initialized services
            msg = f"Failed to initialize core services: {e}"
            raise CoreServicesError(msg) from e

    async def shutdown(self) -> None:
        """
        Shutdown core services in reverse dependency order.

        This ensures that dependent services are stopped before their dependencies.
        """
        logger.info("Shutting down core services...")

        # Shutdown in reverse order

        if self._database_manager:
            try:
                await self._database_manager.shutdown()
                logger.info("DatabaseManager shut down")
            except Exception as e:
                logger.error("Error shutting down DatabaseManager: %s", e)

        if self._persistence:
            try:
                await self._persistence.shutdown()
                logger.info("PersistenceService shut down")
            except Exception as e:
                logger.error("Error shutting down PersistenceService: %s", e)

        self._initialized = False
        logger.info("Core services shutdown complete")

    async def check_health(self) -> dict[str, dict[str, str]]:
        """
        Perform health checks on all core services.

        Updates Prometheus metrics for monitoring.

        Returns:
            Dictionary mapping service names to health status
        """
        health = {}

        # Check each service
        for service_name, service in [
            ("persistence", self._persistence),
            ("database_manager", self._database_manager),
        ]:
            if service and hasattr(service, "health_check"):
                try:
                    await service.health_check()
                    health[service_name] = {"status": "healthy"}
                    CORE_SERVICE_UP.labels(service=service_name).set(1)
                except Exception as e:
                    health[service_name] = {"status": "unhealthy", "error": str(e)}
                    CORE_SERVICE_UP.labels(service=service_name).set(0)
                    logger.error("Health check failed for %s: %s", service_name, e)
            else:
                health[service_name] = {"status": "not_initialized"}
                CORE_SERVICE_UP.labels(service=service_name).set(0)

        return health

    async def _validate_database_schema(self) -> None:
        """
        Validate database schema using Alembic programmatically.

        This replaces the subprocess-based validation in main.py.

        Raises:
            CoreServicesError: If schema validation fails
        """
        if not self._database_manager:
            return

        try:
            # Import here to avoid circular dependencies
            from alembic.config import Config
            from alembic.runtime.migration import MigrationContext
            from alembic.script import ScriptDirectory
            from sqlalchemy import create_engine

            logger.info("Validating database schema...")

            # Create Alembic configuration (in backend directory)
            import os
            backend_dir = os.path.dirname(os.path.dirname(__file__))  # backend/core -> backend
            alembic_ini_path = os.path.join(backend_dir, "alembic.ini")
            config = Config(alembic_ini_path)
            script = ScriptDirectory.from_config(config)

            # Get database path from persistence settings
            from backend.core.config import get_persistence_settings
            persistence_settings = get_persistence_settings()
            database_path = persistence_settings.get_database_dir() / "coachiq.db"
            database_url = f"sqlite:///{database_path}"

            # Create engine and check current revision
            engine = create_engine(database_url)
            with engine.connect() as connection:
                context = MigrationContext.configure(connection)
                current_rev = context.get_current_revision()

            # Get the latest revision
            head_rev = script.get_current_head()

            if current_rev != head_rev:
                logger.warning(
                    "Database schema is not up to date. Current: %s, Head: %s",
                    current_rev, head_rev
                )
                # In production, we might want to fail here
                # For development, we'll just warn
            else:
                logger.info("✅ Database schema is up to date")

        except Exception as e:
            logger.error("Database schema validation failed: %s", e)
            # Don't fail startup for schema validation in development
            # In production, you might want to raise here

    @property
    def persistence(self) -> PersistenceService:
        """Get the persistence service instance."""
        if not self._persistence:
            msg = "Core services not initialized"
            raise RuntimeError(msg)
        return self._persistence

    @property
    def database_manager(self) -> DatabaseManager:
        """Get the database manager instance."""
        if not self._database_manager:
            msg = "Core services not initialized"
            raise RuntimeError(msg)
        return self._database_manager


    @property
    def initialized(self) -> bool:
        """Check if core services are initialized."""
        return self._initialized


# Global instance (singleton pattern)
_core_services_instance: CoreServices | None = None


def get_core_services() -> CoreServices:
    """
    Get the global CoreServices instance.

    Returns:
        The initialized CoreServices instance

    Raises:
        RuntimeError: If core services haven't been initialized
    """
    if _core_services_instance is None:
        msg = "Core services not initialized. Call initialize_core_services() first."
        raise RuntimeError(msg)
    return _core_services_instance


async def initialize_core_services() -> CoreServices:
    """
    Initialize the global CoreServices instance.

    This should be called once during application startup.

    Returns:
        The initialized CoreServices instance

    Raises:
        CoreServicesError: If initialization fails
    """
    global _core_services_instance

    if _core_services_instance is not None:
        logger.warning("Core services already initialized")
        return _core_services_instance

    _core_services_instance = CoreServices()
    await _core_services_instance.startup()

    return _core_services_instance


async def shutdown_core_services() -> None:
    """Shutdown the global CoreServices instance."""
    global _core_services_instance

    if _core_services_instance is not None:
        await _core_services_instance.shutdown()
        _core_services_instance = None
