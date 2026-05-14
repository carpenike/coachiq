"""
Core service-startup-stage configuration for the CoachIQ ServiceRegistry.

Extracted from `backend/main.py` in audit cycle 2026-05-13 PR A8.

This module owns the FIRST stage of registration -- the small set of
services that everything else depends on:

- ``app_settings`` (Pydantic-Settings)
- ``rvc_config`` (RV-C spec / device-mapping provider)
- ``performance_monitor``
- ``edge_proxy_monitor``
- ``persistence_service`` + ``database_manager``
- ``security_event_manager``
- ``device_discovery_service``
- ``pin_manager``
- ``security_audit_service``

Plus the ``_init_*`` helper coroutines they reference.

Behavior is bit-identical to the original.
"""

# ruff: noqa: SLF001, PLR0913, PLR0915, E501, RET504, BLE001, G201, G202, RUF015, ARG002, ARG005, C901, EM101, F811, FIX002, PERF401
# Pre-existing patterns from the moved code (lifted from main.py in audit
# cycle 2026-05-13 PR A8). Cleanup is out of scope for the mechanical extraction.

import logging

from backend.core.config import get_settings
from backend.core.performance import PerformanceMonitor
from backend.core.safety_registry import SafetyServiceRegistry
from backend.core.service_dependency_resolver import DependencyType, ServiceDependency
from backend.services.config_service import ConfigService
from backend.services.edge_proxy_monitor_service import EdgeProxyMonitorService
from backend.services.pin_manager import PINConfig, PINManager
from backend.services.security_audit_service import RateLimitConfig, SecurityAuditService
from backend.services.security_config_service import SecurityConfigService

logger = logging.getLogger(__name__)


async def configure(service_registry: SafetyServiceRegistry) -> None:
    """
    Configure ServiceRegistry with rich service definitions and dependencies.

    This function uses the enhanced service registry features to provide:
    - Automatic dependency resolution and stage calculation
    - Rich metadata for each service (tags, descriptions)
    - Dependency types (REQUIRED, OPTIONAL, RUNTIME)
    - Better error messages and circular dependency detection
    """

    # Define services with rich metadata using ServiceRegistry
    # The registry will automatically calculate stages based on dependencies

    # Core Configuration Services
    service_registry.register_service(
        name="app_settings",
        init_func=_init_app_settings,
        dependencies=[],  # No dependencies
        description="Application configuration and settings",
        tags={"core", "configuration"},
        health_check=lambda s: {"healthy": True, "settings_loaded": s is not None},
    )

    service_registry.register_service(
        name="rvc_config",
        init_func=_init_rvc_config_provider,
        dependencies=[],  # No dependencies
        description="RV-C specification and device mapping configuration",
        tags={"core", "configuration", "rvc"},
        health_check=lambda p: {"healthy": p.initialized, "spec_loaded": p._spec_data is not None},
    )

    # CoreServices removed in Phase 2 - persistence and database services registered separately

    # Security and Event Services
    service_registry.register_service(
        name="performance_monitor",
        init_func=lambda: PerformanceMonitor(),
        dependencies=[],
        description="Global performance monitoring instance",
        tags={"core", "monitoring", "performance"},
        health_check=lambda pm: {"healthy": pm is not None},
    )

    # Edge proxy monitor (Caddy health monitoring)
    service_registry.register_service(
        name="edge_proxy_monitor",
        init_func=lambda: EdgeProxyMonitorService(),
        dependencies=[],  # No dependencies - monitors external infrastructure
        description="Edge proxy (Caddy) health monitoring for ServiceRegistry integration",
        tags={"monitoring", "infrastructure", "edge"},
        health_check=lambda epm: {"healthy": epm.is_healthy(), "last_error": epm.get_last_error()}
        if epm
        else {"healthy": False, "error": "service_not_initialized"},
    )

    # Register individual core services (Phase 2)
    service_registry.register_service(
        name="persistence_service",
        init_func=_init_persistence_service,
        dependencies=[
            ServiceDependency("persistence_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="SQLite-based data storage",
        tags={"core", "persistence", "storage"},
        health_check=lambda ps: {
            "healthy": ps is not None,
            "initialized": ps._initialized if ps else False,
        },
    )

    service_registry.register_service(
        name="database_manager",
        init_func=_init_database_manager,
        dependencies=[
            ServiceDependency("database_connection_service", DependencyType.OPTIONAL),
            ServiceDependency("database_session_service", DependencyType.OPTIONAL),
            ServiceDependency("database_migration_service", DependencyType.OPTIONAL),
            ServiceDependency("performance_monitor", DependencyType.OPTIONAL),
        ],
        description="Database operations facade",
        tags={"core", "database", "persistence"},
        health_check=lambda dm: {
            "healthy": dm is not None,
            "initialized": dm.initialized if dm else False,
        },
    )

    service_registry.register_service(
        name="security_event_manager",
        init_func=_init_security_event_manager,
        dependencies=[
            ServiceDependency("security_event_service", DependencyType.REQUIRED),
            ServiceDependency("attempt_tracker_service", DependencyType.REQUIRED),
            ServiceDependency("security_config_service", DependencyType.REQUIRED),
            ServiceDependency("security_audit_service", DependencyType.REQUIRED),
            ServiceDependency("auth_manager", DependencyType.OPTIONAL),
            ServiceDependency("pin_manager", DependencyType.OPTIONAL),
            ServiceDependency("lockout_service", DependencyType.OPTIONAL),
            ServiceDependency("performance_monitor", DependencyType.OPTIONAL),
        ],
        description="Enhanced security event manager providing orchestration across all security services",
        tags={"security", "events", "audit", "facade", "orchestration"},
        health_check=lambda sem: {
            "healthy": sem is not None and sem.health == "healthy",
            "service_active": True,
        },
    )

    service_registry.register_service(
        name="device_discovery_service",
        init_func=_init_device_discovery_service,
        dependencies=[
            ServiceDependency("rvc_config", DependencyType.REQUIRED),
            ServiceDependency("can_facade", DependencyType.OPTIONAL),  # Can start without CAN
        ],
        description="RV-C device discovery and network scanning",
        tags={"discovery", "rvc", "network"},
        health_check=lambda dds: {"healthy": dds is not None, "discovery_active": True},
    )

    # Register all Group 2 services and repositories. These were extracted
    # to their own modules in audit cycle 2026-05-13 PR A8 (commits 1-3).
    from backend.core.registrations import group2_repositories, group2_services, phase4

    group2_repositories.register(service_registry)
    group2_services.register(service_registry)

    # Phase 4: Register migrated features as services
    phase4.register(service_registry)

    # Add more service definitions that should be managed by ServiceRegistry
    # All services are now managed by ServiceRegistry

    # Temporary: SecurityConfigService needs dependencies but hasn't been updated for DI yet
    def _init_security_config_service():
        # Get dependencies from registry (temporary until Phase 3)
        security_config_repo = service_registry.get_service("security_config_repository")
        perf_monitor = service_registry.get_service("performance_monitor")
        return SecurityConfigService(security_config_repo, perf_monitor)

    service_registry.register_service(
        name="security_config_service",
        init_func=_init_security_config_service,
        dependencies=[
            ServiceDependency("security_config_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Centralized security configuration management",
        tags={"security", "configuration"},
        health_check=lambda scs: {"healthy": scs is not None, "config_loaded": True},
    )

    async def init_pin_manager(security_config_service):
        return await _init_pin_manager(security_config_service)

    service_registry.register_service(
        name="pin_manager",
        init_func=init_pin_manager,
        dependencies=[ServiceDependency("security_config_service", DependencyType.REQUIRED)],
        description="PIN-based authorization for safety operations",
        tags={"security", "safety", "authentication"},
        health_check=lambda pm: {"healthy": pm is not None, "pin_enabled": True},
    )

    async def init_security_audit_service(
        security_config_service, security_audit_repository, performance_monitor
    ):
        return await _init_security_audit_service(
            security_config_service, security_audit_repository, performance_monitor
        )

    service_registry.register_service(
        name="security_audit_service",
        init_func=init_security_audit_service,
        dependencies=[
            ServiceDependency("security_config_service", DependencyType.REQUIRED),
            ServiceDependency("security_audit_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Security audit logging and rate limiting",
        tags={"security", "audit", "monitoring"},
        health_check=lambda sas: {"healthy": sas is not None, "audit_active": True},
    )

    # Register repositories (replaced the removed AppState monolith)
    from backend.repositories.service_registration import (
        register_repositories_with_service_registry,
    )

    register_repositories_with_service_registry(service_registry)
    logger.info("Repositories registered with ServiceRegistry")

    # Register ConfigService after repositories are available
    def _init_config_service(rvc_config_repository):
        """Initialize ConfigService with RVCConfigRepository dependency."""
        return ConfigService(rvc_config_repository)

    service_registry.register_service(
        name="config_service",
        init_func=_init_config_service,
        dependencies=[
            ServiceDependency("rvc_config_repository", DependencyType.REQUIRED),
        ],
        description="Configuration service for RV-C and coach info management",
        tags={"service", "configuration", "rvc"},
        health_check=lambda cs: cs.get_health_status()
        if hasattr(cs, "get_health_status")
        else {"healthy": cs is not None},
    )

    # Register database update services
    from backend.core.service_registration_database_update import (
        register_database_update_services,
    )

    register_database_update_services(service_registry)
    logger.info("Database update services registered with ServiceRegistry")


async def _init_app_settings():
    """Initialize application settings."""
    settings = get_settings()
    logger.info("Application settings loaded successfully")
    return settings


async def _init_rvc_config_provider():
    """Initialize RVC configuration provider."""
    from backend.core.config_provider import RVCConfigProvider

    provider = RVCConfigProvider()
    await provider.initialize()
    return provider


async def _init_database_manager(
    database_connection_service=None,
    database_session_service=None,
    database_migration_service=None,
    performance_monitor=None,
):
    """Initialize database manager with optional dependencies."""
    from backend.services.database_manager import DatabaseManager

    db_manager = DatabaseManager(
        connection_service=database_connection_service,
        session_service=database_session_service,
        migration_service=database_migration_service,
        performance_monitor=performance_monitor,
    )

    if not await db_manager.initialize():
        raise RuntimeError("Failed to initialize database manager")

    logger.info("DatabaseManager initialized via ServiceRegistry")
    return db_manager


async def _init_persistence_service(persistence_repository=None, performance_monitor=None):
    """Initialize persistence service."""
    from backend.services.persistence_service import PersistenceService

    # Always use the new pattern
    if not persistence_repository or not performance_monitor:
        msg = "PersistenceService requires persistence_repository and performance_monitor"
        raise RuntimeError(msg)

    service = PersistenceService(
        persistence_repository=persistence_repository, performance_monitor=performance_monitor
    )

    await service.initialize()
    logger.info("PersistenceService initialized via ServiceRegistry")
    return service


def _init_security_event_manager(
    security_event_service,
    attempt_tracker_service,
    security_config_service,
    security_audit_service,
    auth_manager=None,
    pin_manager=None,
    lockout_service=None,
    performance_monitor=None,
):
    """Initialize enhanced security event manager as orchestration facade."""
    from backend.services.security_event_manager import SecurityEventManager

    # Create enhanced orchestration facade
    manager = SecurityEventManager(
        security_event_service=security_event_service,
        attempt_tracker_service=attempt_tracker_service,
        security_config_service=security_config_service,
        security_audit_service=security_audit_service,
        auth_manager=auth_manager,
        pin_manager=pin_manager,
        lockout_service=lockout_service,
        performance_monitor=performance_monitor,
    )
    logger.info("SecurityEventManager initialized as orchestration facade")
    return manager


async def _init_device_discovery_service(rvc_config, can_facade=None):
    """Initialize device discovery service with RVC config and optional CANFacade dependencies."""
    from backend.services.device_discovery_service import DeviceDiscoveryService

    service = DeviceDiscoveryService(can_facade=can_facade, config=rvc_config)
    logger.info(
        "DeviceDiscoveryService initialized via ServiceRegistry with RVC config and CANFacade (available: %s)",
        can_facade is not None,
    )
    return service


async def _init_pin_manager(security_config_service):
    """Initialize PIN manager with centralized security config."""
    pin_config_dict = await security_config_service.get_pin_config()
    pin_config = PINConfig(**pin_config_dict)
    pin_manager = PINManager(pin_config)
    logger.info("PIN Manager initialized via ServiceRegistry")
    return pin_manager


async def _init_security_audit_service(
    security_config_service, security_audit_repository, performance_monitor
):
    """Initialize security audit service with centralized config."""
    rate_limit_config_dict = await security_config_service.get_rate_limit_config()
    rate_limit_config = RateLimitConfig(**rate_limit_config_dict)
    security_audit_service = SecurityAuditService(
        security_audit_repository=security_audit_repository,
        performance_monitor=performance_monitor,
        config=rate_limit_config,
    )
    logger.info("Security Audit Service initialized via ServiceRegistry")
    return security_audit_service


# Feature manager will be initialized through the legacy path for now
# This allows us to test the core ServiceRegistry functionality first
