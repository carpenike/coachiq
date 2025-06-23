"""Service registration for database update services."""

import logging
from typing import Any

from backend.core.service_dependency_resolver import DependencyType, ServiceDependency
from backend.core.service_registry import EnhancedServiceRegistry

logger = logging.getLogger(__name__)


def register_database_update_services(service_registry: EnhancedServiceRegistry) -> None:
    """
    Register database update services - TARGET PATTERN ONLY.

    No adapters, no backward compatibility, repository injection only.
    """

    # ========== Repositories (Stage 2) ==========

    # Database Backup Repository
    async def _init_backup_repository(database_manager: Any) -> Any:
        from backend.repositories.database_update_repository import (
            DatabaseBackupRepository,
        )

        # Direct repository creation - no adapters
        return DatabaseBackupRepository(database_manager.get_session)

    service_registry.register_service(
        name="database_backup_repository",
        init_func=_init_backup_repository,
        dependencies=[ServiceDependency("database_manager", DependencyType.REQUIRED)],
        description="Repository for database backup metadata",
        tags={"repository", "database", "backup"},
    )

    # Migration History Repository
    async def _init_history_repository(database_manager: Any) -> Any:
        from backend.repositories.database_update_repository import (
            MigrationHistoryRepository,
        )

        # Direct repository creation - no adapters
        return MigrationHistoryRepository(database_manager.get_session)

    service_registry.register_service(
        name="migration_history_repository",
        init_func=_init_history_repository,
        dependencies=[ServiceDependency("database_manager", DependencyType.REQUIRED)],
        description="Repository for migration execution history",
        tags={"repository", "database", "migration"},
    )

    # Database Connection Repository
    async def _init_connection_repository(database_manager: Any, app_settings: Any) -> Any:
        from backend.repositories.database_update_repository import (
            DatabaseConnectionRepository,
        )

        # Get database URL and path from settings
        database_url = app_settings.database.get_database_url()
        database_path = app_settings.database.get_database_path()

        return DatabaseConnectionRepository(
            database_manager.get_session, database_url, database_path
        )

    service_registry.register_service(
        name="database_connection_repository",
        init_func=_init_connection_repository,
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("app_settings", DependencyType.REQUIRED),
        ],
        description="Repository for database connection management",
        tags={"repository", "database", "connection"},
    )

    # Database Migration Repository
    async def _init_migration_repository(database_manager: Any) -> Any:
        from backend.repositories.database_update_repository import (
            DatabaseMigrationRepository,
        )

        # Alembic config would be loaded here
        alembic_config = None  # Placeholder
        return DatabaseMigrationRepository(database_manager.get_session, alembic_config)

    service_registry.register_service(
        name="database_migration_repository",
        init_func=_init_migration_repository,
        dependencies=[ServiceDependency("database_manager", DependencyType.REQUIRED)],
        description="Repository for Alembic migration information",
        tags={"repository", "database", "alembic"},
    )

    # Safety Repository
    async def _init_safety_repository(database_manager: Any) -> Any:
        from backend.repositories.database_update_repository import SafetyRepository

        return SafetyRepository(database_manager.get_session)

    service_registry.register_service(
        name="safety_repository",
        init_func=_init_safety_repository,
        dependencies=[ServiceDependency("database_manager", DependencyType.REQUIRED)],
        description="Repository for safety system state",
        tags={"repository", "safety"},
    )

    # ========== Services (Stage 5) ==========

    # Migration Safety Validator
    async def _init_migration_safety_validator(
        safety_repository: Any,
        database_connection_repository: Any,
        performance_monitor: Any = None,
    ) -> Any:
        from backend.services.migration_safety_validator import MigrationSafetyValidator

        # Direct service creation with repository injection only
        validator = MigrationSafetyValidator(
            safety_repository=safety_repository,
            connection_repository=database_connection_repository,
            performance_monitor=performance_monitor,
        )
        await validator.initialize()
        return validator

    service_registry.register_service(
        name="migration_safety_validator",
        init_func=_init_migration_safety_validator,
        dependencies=[
            ServiceDependency("safety_repository", DependencyType.REQUIRED),
            ServiceDependency("database_connection_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.OPTIONAL),
        ],
        description="Validates system safety before database migrations",
        tags={"database", "safety", "migration"},
        health_check=lambda _: {"healthy": True},
    )

    # Database Update Service
    async def _init_database_update_service(
        database_connection_repository: Any,
        database_migration_repository: Any,
        migration_safety_validator: Any,
        database_backup_repository: Any,
        migration_history_repository: Any,
        app_settings: Any,
        websocket_repository: Any = None,
        performance_monitor: Any = None,
    ) -> Any:
        from backend.services.database_update_service import DatabaseUpdateService

        # Get backup directory from settings
        backup_dir = app_settings.persistence.get_backup_dir()

        # Direct service creation with repository injection only
        service = DatabaseUpdateService(
            connection_repository=database_connection_repository,
            migration_repository=database_migration_repository,
            safety_validator=migration_safety_validator,
            backup_repository=database_backup_repository,
            history_repository=migration_history_repository,
            websocket_repository=websocket_repository,
            performance_monitor=performance_monitor,
            backup_dir=backup_dir,
        )
        await service.initialize()
        return service

    service_registry.register_service(
        name="database_update_service",
        init_func=_init_database_update_service,
        dependencies=[
            ServiceDependency("database_connection_repository", DependencyType.REQUIRED),
            ServiceDependency("database_migration_repository", DependencyType.REQUIRED),
            ServiceDependency("migration_safety_validator", DependencyType.REQUIRED),
            ServiceDependency("database_backup_repository", DependencyType.REQUIRED),
            ServiceDependency("migration_history_repository", DependencyType.REQUIRED),
            ServiceDependency("app_settings", DependencyType.REQUIRED),
            ServiceDependency("websocket_repository", DependencyType.OPTIONAL),
            ServiceDependency("performance_monitor", DependencyType.OPTIONAL),
        ],
        description="Orchestrates safe database schema updates",
        tags={"database", "migration", "safety"},
        health_check=lambda svc: svc.get_health(),
    )

    logger.info("Database update services registered successfully")
