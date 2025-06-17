"""
Repository Service Registration

Factory functions and registration helpers for repositories.
Part of Phase 2R.2: Register repositories with EnhancedServiceRegistry
"""

import logging
from typing import Any

from backend.repositories import (
    EntityStateRepository,
    RVCConfigRepository,
    CANTrackingRepository,
    DiagnosticsRepository,
)
from backend.core.entity_manager import EntityManager

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
    logger.info("RVCConfigRepository initialized (configuration will be loaded during AppState startup)")
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
        health_check=lambda repo: repo.get_health_status()
    )

    # Register RVCConfigRepository
    service_registry.register_service(
        name="rvc_config_repository",
        init_func=_init_rvc_config_repository,
        dependencies=[],  # No dependencies
        description="Repository for RV-C protocol configuration data",
        tags={"repository", "data", "configuration", "rvc"},
        health_check=lambda repo: repo.get_health_status()
    )

    # Register CANTrackingRepository
    service_registry.register_service(
        name="can_tracking_repository",
        init_func=_init_can_tracking_repository,
        dependencies=[],  # No dependencies
        description="Repository for real-time CAN message tracking",
        tags={"repository", "data", "can", "real-time"},
        health_check=lambda repo: repo.get_health_status()
    )

    # Register DiagnosticsRepository (Phase 2R.4)
    service_registry.register_service(
        name="diagnostics_repository",
        init_func=_init_diagnostics_repository,
        dependencies=[],  # No dependencies
        description="Repository for diagnostic data and legacy unmapped entries",
        tags={"repository", "data", "diagnostics", "legacy"},
        health_check=lambda repo: repo.get_health_status()
    )

    logger.info("All repositories registered with ServiceRegistry")
