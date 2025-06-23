"""
Repository Service Registration

Factory functions and registration helpers for repositories.
Part of Phase 2R.2: Register repositories with EnhancedServiceRegistry
"""

import logging
from typing import Any

from backend.core.entity_manager import EntityManager
from backend.repositories import (
    CANTrackingRepository,
    DiagnosticsRepository,
    EntityStateRepository,
    RVCConfigRepository,
    SystemStateRepository,
)
from backend.repositories.persistence_repository import PersistenceRepository
from backend.repositories.security_config_repository import SecurityConfigRepository

logger = logging.getLogger(__name__)


def _init_entity_state_repository() -> EntityStateRepository:
    """
    Initialize EntityStateRepository.

    This repository manages entity state and history data.
    """
    logger.info("Initializing EntityStateRepository")

    # For now, create with a new EntityManager
    # In Phase 2R.3, this will be refactored to share the EntityManager
    entity_manager = EntityManager()
    repository = EntityStateRepository(entity_manager)

    logger.info("EntityStateRepository initialized successfully")
    return repository


def _init_rvc_config_repository() -> RVCConfigRepository:
    """
    Initialize RVCConfigRepository.

    This repository manages RV-C protocol configuration data.
    """
    logger.info("Initializing RVCConfigRepository")
    repository = RVCConfigRepository()
    logger.info(
        "RVCConfigRepository initialized (configuration will be loaded during AppState startup)"
    )
    return repository


def _init_can_tracking_repository() -> CANTrackingRepository:
    """
    Initialize CANTrackingRepository.

    This repository manages real-time CAN message tracking.
    """
    logger.info("Initializing CANTrackingRepository")
    repository = CANTrackingRepository()
    logger.info("CANTrackingRepository initialized with bounded collections")
    return repository


def _init_diagnostics_repository() -> DiagnosticsRepository:
    """
    Initialize DiagnosticsRepository.

    This repository manages diagnostic data including unmapped entries
    and unknown PGNs that were previously in AppState.
    Part of Phase 2R.4: Legacy Data Cleanup.
    """
    logger.info("Initializing DiagnosticsRepository")
    repository = DiagnosticsRepository()
    logger.info("DiagnosticsRepository initialized for legacy data management")
    return repository


def _init_system_state_repository() -> SystemStateRepository:
    """
    Initialize SystemStateRepository.

    This repository manages system-wide state and configuration
    that doesn't belong to specific domains.
    Part of Phase 4A: App State Cleanup.
    """
    logger.info("Initializing SystemStateRepository")
    repository = SystemStateRepository()
    logger.info("SystemStateRepository initialized for global system state")
    return repository


def _init_security_config_repository(
    database_manager, performance_monitor
) -> SecurityConfigRepository:
    """
    Initialize SecurityConfigRepository.

    This repository manages security configuration including policies,
    rate limiting, and PIN authentication settings.
    """
    logger.info("Initializing SecurityConfigRepository")
    repository = SecurityConfigRepository(database_manager, performance_monitor)
    logger.info("SecurityConfigRepository initialized for security configuration management")
    return repository


def _init_persistence_repository(database_manager, performance_monitor) -> PersistenceRepository:
    """
    Initialize PersistenceRepository.

    This repository provides the data access layer for the persistence service.
    """
    from backend.core.config import get_settings

    logger.info("Initializing PersistenceRepository")

    # Get data directory from settings
    settings = get_settings()
    data_dir = settings.data_dir

    repository = PersistenceRepository(
        database_manager=database_manager,
        performance_monitor=performance_monitor,
        data_dir=data_dir,
    )
    logger.info("PersistenceRepository initialized for persistence data access")
    return repository


def _init_analytics_repository(database_manager, performance_monitor) -> Any:
    """
    Initialize AnalyticsRepository.

    This repository manages analytics data persistence.
    """
    from backend.repositories.analytics_repository import AnalyticsRepository

    logger.info("Initializing AnalyticsRepository")
    repository = AnalyticsRepository(
        database_manager=database_manager,
        performance_monitor=performance_monitor,
    )
    logger.info("AnalyticsRepository initialized for analytics data management")
    return repository


def register_repositories_with_service_registry(service_registry: Any) -> None:
    """
    Register all repositories with the ServiceRegistry.

    This enables repositories to be accessed independently of AppState,
    supporting the gradual migration away from the monolithic design.

    Args:
        service_registry: The EnhancedServiceRegistry instance
    """

    # Register EntityStateRepository
    service_registry.register_service(
        name="entity_state_repository",
        init_func=_init_entity_state_repository,
        dependencies=[],  # No dependencies for now
        description="Repository for entity state and history management",
        tags={"repository", "data", "entities"},
        health_check=lambda repo: repo.get_health_status(),
    )

    # Register RVCConfigRepository
    service_registry.register_service(
        name="rvc_config_repository",
        init_func=_init_rvc_config_repository,
        dependencies=[],  # No dependencies
        description="Repository for RV-C protocol configuration data",
        tags={"repository", "data", "configuration", "rvc"},
        health_check=lambda repo: repo.get_health_status(),
    )

    # Register CANTrackingRepository
    service_registry.register_service(
        name="can_tracking_repository",
        init_func=_init_can_tracking_repository,
        dependencies=[],  # No dependencies
        description="Repository for real-time CAN message tracking",
        tags={"repository", "data", "can", "real-time"},
        health_check=lambda repo: repo.get_health_status(),
    )

    # Register DiagnosticsRepository (Phase 2R.4)
    service_registry.register_service(
        name="diagnostics_repository",
        init_func=_init_diagnostics_repository,
        dependencies=[],  # No dependencies
        description="Repository for diagnostic data and legacy unmapped entries",
        tags={"repository", "data", "diagnostics", "legacy"},
        health_check=lambda repo: repo.get_health_status(),
    )

    # Register SystemStateRepository (Phase 4A)
    service_registry.register_service(
        name="system_state_repository",
        init_func=_init_system_state_repository,
        dependencies=[],  # No dependencies
        description="Repository for system-wide state and configuration",
        tags={"repository", "data", "system", "configuration"},
        health_check=lambda repo: repo.get_health_status(),
    )

    # Register SecurityConfigRepository
    from backend.core.service_dependency_resolver import DependencyType, ServiceDependency

    service_registry.register_service(
        name="security_config_repository",
        init_func=_init_security_config_repository,
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for security configuration and policy management",
        tags={"repository", "data", "security", "configuration"},
        health_check=lambda repo: repo.get_health_status()
        if hasattr(repo, "get_health_status")
        else {"healthy": repo is not None},
    )

    # Register PersistenceRepository
    service_registry.register_service(
        name="persistence_repository",
        init_func=_init_persistence_repository,
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for persistence service data access",
        tags={"repository", "data", "persistence", "storage"},
        health_check=lambda repo: repo.get_health_status()
        if hasattr(repo, "get_health_status")
        else {"healthy": repo is not None},
    )

    # Register AnalyticsRepository
    service_registry.register_service(
        name="analytics_repository",
        init_func=_init_analytics_repository,
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for analytics data persistence and insights",
        tags={"repository", "data", "analytics", "metrics"},
        health_check=lambda repo: repo.get_health_status()
        if hasattr(repo, "get_health_status")
        else {"healthy": repo is not None},
    )

    logger.info("All repositories registered with ServiceRegistry")
