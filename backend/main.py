#!/usr/bin/env python3
"""
Clean main application entry point for the coachiq backend.

This module provides a simplified FastAPI application setup with proper
initialization order to avoid metrics collisions and circular imports.
"""

import argparse
import json
import logging
import os
import platform
import signal
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.api.router_config import configure_routers
from backend.core.config import get_settings
from backend.core.dependencies import ServiceRegistry
from backend.core.exceptions import ServiceNotAvailableError
from backend.core.logging_config import configure_unified_logging, setup_early_logging
from backend.core.metrics import initialize_backend_metrics
from backend.core.performance import PerformanceMonitor
from backend.core.safety_registry import SafetyServiceRegistry
from backend.core.service_dependency_resolver import DependencyType, ServiceDependency
from backend.core.service_registry import ServiceStatus

# CAN Tools Services
from backend.integrations.can.message_injector import CANMessageInjector, SafetyLevel

# from backend.integrations.registration import register_custom_features  # No longer needed - all services in ServiceRegistry
from backend.middleware.auth import AuthenticationMiddleware

# CORS handling moved to Caddy edge layer - see config/Caddyfile.example
from backend.middleware.rate_limiting import limiter, rate_limit_exceeded_handler
from backend.middleware.validation import RuntimeValidationMiddleware
from backend.monitoring import get_health_monitoring_summary, record_health_probe

# Group 2 repository imports
from backend.repositories.auth_repository import (
    AuthEventRepository,
    CredentialRepository,
    MfaRepository,
    SessionRepository,
)
from backend.repositories.database_repository import (
    DatabaseConnectionRepository,
    DatabaseSessionRepository,
    MigrationRepository,
)
from backend.repositories.entity_repository import (
    CanCommandRepository,
    EntityConfigRepository,
    EntityHistoryRepository,
    EntityStateRepository,
)
from backend.repositories.security_audit_repository import SecurityAuditRepository
from backend.repositories.security_event_repository import (
    SecurityEventRepository,
    SecurityListenerRepository,
)
from backend.services.analytics_dashboard_service import AnalyticsDashboardService

# Phase 4 service imports
from backend.services.auth_manager import AccountLockedError
from backend.services.auth_service import AuthService

# Group 2 service imports
from backend.services.auth_services import (
    LockoutService,
    MfaService,
    SessionService,
    TokenService,
)
from backend.services.can_bus_service import CANBusService
from backend.services.can_interface_service import CANInterfaceService

# CANService import removed - not used in this file
from backend.services.config_service import ConfigService
from backend.services.database_services import (
    DatabaseConnectionService,
    DatabaseMigrationService,
    DatabaseSessionService,
)
from backend.services.edge_proxy_monitor_service import EdgeProxyMonitorService
from backend.services.entity_initialization_service import EntityInitializationService

# from backend.services.docs_service import DocsService  # Not used
from backend.services.entity_manager_service import EntityManagerService
from backend.services.entity_service import EntityService
from backend.services.entity_services import (
    EntityControlService,
    EntityManagementService,
    EntityQueryService,
)
from backend.services.pin_manager import PINConfig, PINManager
from backend.services.protocol_manager import ProtocolManager

# EntityService import removed - not used in this file
# from backend.services.predictive_maintenance_service import PredictiveMaintenanceService  # Not migrated yet
# RVCService import removed - not used in this file
from backend.services.safety_service import SafetyService
from backend.services.security_audit_service import RateLimitConfig, SecurityAuditService
from backend.services.security_config_service import SecurityConfigService
from backend.services.security_event_service import SecurityEventService

# from backend.services.vector_service import VectorService  # Not used
from backend.services.websocket_service import WebSocketService

# Set up early logging before anything else
setup_early_logging()

logger = logging.getLogger(__name__)

# Store startup time for health checks
SERVER_START_TIME = time.time()


async def _configure_service_startup_stages(service_registry):
    """
    Configure EnhancedServiceRegistry with rich service definitions and dependencies.

    This function uses the enhanced service registry features to provide:
    - Automatic dependency resolution and stage calculation
    - Rich metadata for each service (tags, descriptions)
    - Dependency types (REQUIRED, OPTIONAL, RUNTIME)
    - Better error messages and circular dependency detection
    """

    # Define services with rich metadata using EnhancedServiceRegistry
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

    # Register all Group 2 services and repositories (Phase 3 - moved from service_registry_update_v2.py)
    _register_group2_repositories(service_registry)
    _register_group2_services(service_registry)

    # Phase 4: Register migrated features as services
    _register_phase4_services(service_registry)

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

    # Register repositories (Phase 2R.2)
    from backend.repositories.service_registration import (
        register_repositories_with_service_registry,
    )

    register_repositories_with_service_registry(service_registry)
    logger.info("Repositories registered with ServiceRegistry (Phase 2R.2)")

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
    from backend.services.security_event_manager_v2 import EnhancedSecurityEventManager

    # Create enhanced orchestration facade
    manager = EnhancedSecurityEventManager(
        security_event_service=security_event_service,
        attempt_tracker_service=attempt_tracker_service,
        security_config_service=security_config_service,
        security_audit_service=security_audit_service,
        auth_manager=auth_manager,
        pin_manager=pin_manager,
        lockout_service=lockout_service,
        performance_monitor=performance_monitor,
    )
    logger.info("Enhanced SecurityEventManager initialized as orchestration facade")
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


def _register_group2_repositories(service_registry: SafetyServiceRegistry) -> None:
    """
    Register all Group 2 repositories with the ServiceRegistry (Phase 3).

    These repositories provide the data access layer for the refactored services.
    They all extend MonitoredRepository for consistent performance monitoring.
    Updated to use constructor injection pattern.
    """

    # Security Event Repositories
    service_registry.register_service(
        name="security_event_repository",
        init_func=lambda database_manager, performance_monitor: SecurityEventRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for security event storage and retrieval",
        tags={"repository", "security", "events", "monitoring"},
    )

    service_registry.register_service(
        name="security_listener_repository",
        init_func=lambda database_manager, performance_monitor: SecurityListenerRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for security event listener management",
        tags={"repository", "security", "events", "listeners"},
    )

    # Database Repositories
    service_registry.register_service(
        name="database_connection_repository",
        init_func=lambda database_manager, performance_monitor: DatabaseConnectionRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for database connection tracking and pooling",
        tags={"repository", "database", "connections", "monitoring"},
    )

    service_registry.register_service(
        name="database_session_repository",
        init_func=lambda database_manager, performance_monitor: DatabaseSessionRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for database session lifecycle management",
        tags={"repository", "database", "sessions", "monitoring"},
    )

    service_registry.register_service(
        name="migration_repository",
        init_func=lambda database_manager, performance_monitor: MigrationRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for database migration history tracking",
        tags={"repository", "database", "migrations", "monitoring"},
    )

    # Auth Repositories
    service_registry.register_service(
        name="credential_repository",
        init_func=lambda database_manager, performance_monitor: CredentialRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for user credential storage and validation",
        tags={"repository", "auth", "credentials", "monitoring"},
    )

    service_registry.register_service(
        name="session_repository",
        init_func=lambda database_manager, performance_monitor: SessionRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for session and refresh token management",
        tags={"repository", "auth", "sessions", "monitoring"},
    )

    service_registry.register_service(
        name="mfa_repository",
        init_func=lambda database_manager, performance_monitor: MfaRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for multi-factor authentication data",
        tags={"repository", "auth", "mfa", "monitoring"},
    )

    service_registry.register_service(
        name="auth_event_repository",
        init_func=lambda database_manager, performance_monitor: AuthEventRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for authentication event tracking",
        tags={"repository", "auth", "events", "monitoring"},
    )

    # Entity Repositories
    service_registry.register_service(
        name="entity_config_repository",
        init_func=lambda database_manager, performance_monitor: EntityConfigRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for entity configuration (YAML) management",
        tags={"repository", "entity", "config", "monitoring"},
    )

    service_registry.register_service(
        name="entity_state_repository",
        init_func=lambda database_manager, performance_monitor: EntityStateRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for runtime entity state persistence",
        tags={"repository", "entity", "state", "monitoring"},
    )

    service_registry.register_service(
        name="entity_history_repository",
        init_func=lambda database_manager, performance_monitor: EntityHistoryRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for time-series entity state tracking",
        tags={"repository", "entity", "history", "monitoring"},
    )

    service_registry.register_service(
        name="can_command_repository",
        init_func=lambda database_manager, performance_monitor: CanCommandRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for CAN command auditing and tracking",
        tags={"repository", "entity", "can", "monitoring"},
    )

    # Security Audit Repository
    service_registry.register_service(
        name="security_audit_repository",
        init_func=lambda database_manager, performance_monitor: SecurityAuditRepository(
            database_manager, performance_monitor
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Repository for security audit logging and tracking",
        tags={"repository", "security", "audit", "monitoring"},
    )

    # Entity Initialization Service
    service_registry.register_service(
        name="entity_initialization_service",
        init_func=lambda entity_state_repository,
        rvc_config_repository,
        entity_manager_service: EntityInitializationService(
            entity_state_repository=entity_state_repository,
            rvc_config_repository=rvc_config_repository,
            entity_manager=entity_manager_service.get_entity_manager()
            if entity_manager_service
            else None,
        ),
        dependencies=[
            ServiceDependency("entity_state_repository", DependencyType.REQUIRED),
            ServiceDependency("rvc_config_repository", DependencyType.REQUIRED),
            ServiceDependency("entity_manager_service", DependencyType.REQUIRED),
        ],
        description="Service for loading and preseeding entities from coach mapping",
        tags={"service", "entity", "initialization", "coach-mapping"},
        health_check=lambda s: {
            "healthy": s is not None,
            "initialized": s._initialized if hasattr(s, "_initialized") else False,
            "entity_count": len(s._entity_manager.get_entity_ids())
            if hasattr(s, "_entity_manager")
            else 0,
        },
    )


def _register_group2_services(service_registry: SafetyServiceRegistry) -> None:
    """
    Register all Group 2 services with the ServiceRegistry (Phase 3).

    These services contain the business logic extracted from the monolithic managers.
    They depend on their respective repositories for data operations.
    Updated to use constructor injection pattern.
    """

    # Security Event Service
    service_registry.register_service(
        name="security_event_service",
        init_func=lambda security_event_repository,
        security_listener_repository,
        performance_monitor: SecurityEventService(
            event_repository=security_event_repository,
            listener_repository=security_listener_repository,
            performance_monitor=performance_monitor,
        ),
        dependencies=[
            ServiceDependency("security_event_repository", DependencyType.REQUIRED),
            ServiceDependency("security_listener_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Core service for security event publishing and subscription",
        tags={"service", "security", "events", "core"},
        health_check=lambda s: {"healthy": s is not None, "listeners": len(s._listeners)},
    )

    # Attempt Tracker Service
    from backend.services.attempt_tracker_service import AttemptTrackerService

    service_registry.register_service(
        name="attempt_tracker_service",
        init_func=lambda auth_event_repository,
        security_audit_repository,
        performance_monitor,
        security_event_service: AttemptTrackerService(
            auth_event_repository=auth_event_repository,
            security_audit_repository=security_audit_repository,
            performance_monitor=performance_monitor,
            security_event_service=security_event_service,
        ),
        dependencies=[
            ServiceDependency("auth_event_repository", DependencyType.REQUIRED),
            ServiceDependency("security_audit_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
            ServiceDependency("security_event_service", DependencyType.OPTIONAL),
        ],
        description="Centralized service for tracking all security-related attempts",
        tags={"service", "security", "monitoring", "attempts"},
        health_check=lambda s: {"healthy": s is not None, "thresholds": s._thresholds},
    )

    # Database Services
    service_registry.register_service(
        name="database_connection_service",
        init_func=lambda database_connection_repository,
        performance_monitor: DatabaseConnectionService(
            database_engine=_create_database_engine(),
            connection_repository=database_connection_repository,
            performance_monitor=performance_monitor,
        ),
        dependencies=[
            ServiceDependency("database_connection_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Service for database connection lifecycle management",
        tags={"service", "database", "connections", "core"},
        health_check=lambda s: {"healthy": s is not None, "pool_size": s.get_pool_size()},
    )

    service_registry.register_service(
        name="database_session_service",
        init_func=lambda database_session_repository, performance_monitor: DatabaseSessionService(
            database_engine=_create_database_engine(),
            session_repository=database_session_repository,
            performance_monitor=performance_monitor,
        ),
        dependencies=[
            ServiceDependency("database_session_repository", DependencyType.REQUIRED),
            ServiceDependency("database_connection_service", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Service for database session handling and transactions",
        tags={"service", "database", "sessions", "core"},
        health_check=lambda s: {"healthy": s is not None, "active_sessions": s.get_active_count()},
    )

    service_registry.register_service(
        name="database_migration_service",
        init_func=lambda migration_repository, performance_monitor: DatabaseMigrationService(
            database_engine=_create_database_engine(),
            migration_repository=migration_repository,
            performance_monitor=performance_monitor,
        ),
        dependencies=[
            ServiceDependency("migration_repository", DependencyType.REQUIRED),
            ServiceDependency("database_connection_service", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Service for database migration execution and tracking",
        tags={"service", "database", "migrations", "core"},
        health_check=lambda s: {
            "healthy": s is not None,
            "pending_migrations": s.get_pending_count(),
        },
    )

    # Auth Services
    async def _init_token_service(security_config_service):
        """Initialize token service with config from SecurityConfigService."""
        auth_config = await security_config_service.get_auth_config()
        return TokenService(
            jwt_secret=auth_config.get("jwt_secret"),
            jwt_algorithm=auth_config.get("jwt_algorithm", "HS256"),
            access_token_expire_minutes=auth_config.get("access_token_expire_minutes", 60),
            magic_link_expire_minutes=auth_config.get("magic_link_expire_minutes", 15),
        )

    service_registry.register_service(
        name="token_service",
        init_func=_init_token_service,
        dependencies=[ServiceDependency("security_config_service", DependencyType.REQUIRED)],
        description="Stateless JWT token generation and validation",
        tags={"service", "auth", "tokens", "stateless"},
        health_check=lambda s: {"healthy": s is not None, "algorithm": s._jwt_algorithm},
    )

    service_registry.register_service(
        name="session_service",
        init_func=lambda session_repository, token_service, performance_monitor: SessionService(
            session_repository=session_repository,
            token_service=token_service,
            performance_monitor=performance_monitor,
        ),
        dependencies=[
            ServiceDependency("session_repository", DependencyType.REQUIRED),
            ServiceDependency("token_service", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Service for session and refresh token management",
        tags={"service", "auth", "sessions", "core"},
        health_check=lambda s: {"healthy": s is not None, "active_sessions": s.get_active_count()},
    )

    service_registry.register_service(
        name="mfa_service",
        init_func=lambda mfa_repository, performance_monitor: MfaService(
            mfa_repository=mfa_repository,
            performance_monitor=performance_monitor,
        ),
        dependencies=[
            ServiceDependency("mfa_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Service for TOTP and backup code operations",
        tags={"service", "auth", "mfa", "security"},
        health_check=lambda s: {"healthy": s is not None, "totp_enabled": True},
    )

    async def _init_lockout_service(
        auth_event_repository, performance_monitor, security_config_service, attempt_tracker_service
    ):
        """Initialize lockout service with config from SecurityConfigService."""
        auth_config = await security_config_service.get_auth_config()
        return LockoutService(
            auth_event_repository=auth_event_repository,
            performance_monitor=performance_monitor,
            max_failed_attempts=auth_config.get("max_login_attempts", 5),
            lockout_window_minutes=auth_config.get("login_attempt_window_minutes", 15),
            lockout_duration_minutes=auth_config.get("login_lockout_minutes", 30),
            attempt_tracker_service=attempt_tracker_service,
        )

    service_registry.register_service(
        name="lockout_service",
        init_func=_init_lockout_service,
        dependencies=[
            ServiceDependency("auth_event_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
            ServiceDependency("security_config_service", DependencyType.REQUIRED),
            ServiceDependency("attempt_tracker_service", DependencyType.OPTIONAL),
        ],
        description="Service for account lockout protection",
        tags={"service", "auth", "security", "lockout"},
        health_check=lambda s: {
            "healthy": s is not None,
            "max_attempts": s._max_attempts if hasattr(s, "_max_attempts") else 0,
        },
    )

    # Entity Services
    # Note: These services have complex dependencies on entity_manager and websocket_manager
    # which are now retrieved from ServiceRegistry dynamically during initialization.

    def _init_entity_query_service(
        entity_state_repository,
        entity_history_repository,
        performance_monitor,
        entity_manager_service,
    ):
        # Get entity manager from injected service
        entity_manager = (
            entity_manager_service.get_entity_manager() if entity_manager_service else None
        )

        return EntityQueryService(
            entity_manager=entity_manager,
            state_repository=entity_state_repository,
            history_repository=entity_history_repository,
            performance_monitor=performance_monitor,
        )

    service_registry.register_service(
        name="entity_query_service",
        init_func=_init_entity_query_service,
        dependencies=[
            ServiceDependency("entity_state_repository", DependencyType.REQUIRED),
            ServiceDependency("entity_history_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
            ServiceDependency("entity_manager_service", DependencyType.REQUIRED),
        ],
        description="Service for entity read operations and queries",
        tags={"service", "entity", "query", "readonly"},
        health_check=lambda s: {"healthy": s is not None, "repositories_connected": True},
    )

    def _init_entity_control_service(
        entity_state_repository,
        can_command_repository,
        entity_query_service,
        performance_monitor,
        entity_manager_service,
        websocket_manager,
    ):
        # Get entity manager from injected service
        entity_manager = (
            entity_manager_service.get_entity_manager() if entity_manager_service else None
        )

        # Get CAN TX queue
        from backend.integrations.can.manager import can_tx_queue

        return EntityControlService(
            entity_manager=entity_manager,
            websocket_manager=websocket_manager,
            can_tx_queue=can_tx_queue,
            command_repository=can_command_repository,
            performance_monitor=performance_monitor,
        )

    service_registry.register_service(
        name="entity_control_service",
        init_func=_init_entity_control_service,
        dependencies=[
            ServiceDependency("entity_state_repository", DependencyType.REQUIRED),
            ServiceDependency("can_command_repository", DependencyType.REQUIRED),
            ServiceDependency("entity_query_service", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
            ServiceDependency("entity_manager_service", DependencyType.REQUIRED),
            ServiceDependency("websocket_manager", DependencyType.REQUIRED),
        ],
        description="Service for hardware control with security validation",
        tags={"service", "entity", "control", "hardware", "security"},
        health_check=lambda s: {"healthy": s is not None, "can_enabled": s._can_enabled},
    )

    def _init_entity_management_service(
        entity_config_repository,
        entity_state_repository,
        entity_query_service,
        performance_monitor,
        entity_manager_service,
        websocket_manager,
    ):
        # Get entity manager from injected service
        entity_manager = (
            entity_manager_service.get_entity_manager() if entity_manager_service else None
        )

        return EntityManagementService(
            entity_manager=entity_manager,
            websocket_manager=websocket_manager,
            config_repository=entity_config_repository,
            performance_monitor=performance_monitor,
        )

    service_registry.register_service(
        name="entity_management_service",
        init_func=_init_entity_management_service,
        dependencies=[
            ServiceDependency("entity_config_repository", DependencyType.REQUIRED),
            ServiceDependency("entity_state_repository", DependencyType.REQUIRED),
            ServiceDependency("entity_query_service", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
            ServiceDependency("entity_manager_service", DependencyType.REQUIRED),
            ServiceDependency("websocket_manager", DependencyType.REQUIRED),
        ],
        description="Service for entity lifecycle management",
        tags={"service", "entity", "management", "lifecycle"},
        health_check=lambda s: {"healthy": s is not None, "management_enabled": True},
    )

    # EntityService - unified entity facade service
    service_registry.register_service(
        name="entity_service",
        init_func=lambda websocket_manager,
        entity_state_repository,
        rvc_config_repository,
        diagnostics_repository: EntityService(
            websocket_manager=websocket_manager,
            entity_state_repository=entity_state_repository,
            rvc_config_repository=rvc_config_repository,
            diagnostics_repository=diagnostics_repository,
        ),
        dependencies=[
            ServiceDependency("websocket_manager", DependencyType.REQUIRED),
            ServiceDependency("entity_state_repository", DependencyType.REQUIRED),
            ServiceDependency("rvc_config_repository", DependencyType.REQUIRED),
            ServiceDependency("diagnostics_repository", DependencyType.REQUIRED),
        ],
        description="Unified entity service facade providing comprehensive entity operations",
        tags={"service", "entity", "facade", "api"},
        health_check=lambda s: {"healthy": s is not None, "repositories_available": True},
    )

    # EntityDomainService - safety-critical entity domain operations
    from backend.services.entity_domain_service import EntityDomainService

    service_registry.register_service(
        name="entity_domain_service",
        init_func=lambda config_service,
        auth_manager,
        entity_service,
        websocket_manager,
        entity_manager_service: EntityDomainService(
            config_service=config_service,
            auth_manager=auth_manager,
            entity_service=entity_service,
            websocket_manager=websocket_manager,
            entity_manager=entity_manager_service,
        ),
        dependencies=[
            ServiceDependency("config_service", DependencyType.REQUIRED),
            ServiceDependency("auth_manager", DependencyType.REQUIRED),
            ServiceDependency("entity_service", DependencyType.REQUIRED),
            ServiceDependency("websocket_manager", DependencyType.REQUIRED),
            ServiceDependency("entity_manager_service", DependencyType.REQUIRED),
        ],
        description="Safety-critical entity domain service with comprehensive safety interlocks",
        tags={"service", "entity", "domain", "safety-critical"},
        health_check=lambda s: {"healthy": s is not None, "safety_interlocks_enabled": True},
    )


def _create_database_engine():
    """Create a database engine instance."""
    from backend.core.config import get_settings
    from backend.services.database_engine import DatabaseEngine

    settings = get_settings()
    return DatabaseEngine(settings)


def _register_phase4_services(service_registry: SafetyServiceRegistry) -> None:
    """
    Register Phase 4 migrated features as services (Phase 4).

    These are services that are now managed by ServiceRegistry with constructor injection.
    """
    logger.info("Registering Phase 4 services (migrated features)")

    # ProtocolManager - manages protocol enablement and status
    async def _init_protocol_manager():
        manager = ProtocolManager()
        await manager.start()
        return manager

    service_registry.register_service(
        name="protocol_manager",
        init_func=_init_protocol_manager,
        dependencies=[],  # No dependencies, reads from configuration
        description="Protocol enablement and status management",
        tags={"service", "protocol", "configuration"},
        health_check=lambda m: m.get_health_status()
        if hasattr(m, "get_health_status")
        else {"healthy": m is not None},
    )

    # SafetyService - ISO 26262-compliant safety monitoring (CRITICAL)
    async def _init_safety_service(pin_manager, security_audit_service):
        """Initialize SafetyService - service_registry will be injected after registration."""
        service = SafetyService(
            service_registry=None,  # Will be set after registration to avoid circular dependency
            health_check_interval=5.0,  # Check health every 5 seconds
            watchdog_timeout=15.0,  # Watchdog timeout at 15 seconds
            pin_manager=pin_manager,
            security_audit_service=security_audit_service,
        )
        await service.start_monitoring()
        logger.info("SafetyService started - will set service_registry after registration")
        return service

    # Import safety classification for proper registration
    from backend.core.safety_interfaces import SafetyClassification

    service_registry.register_safety_service(
        name="safety_service",
        init_func=_init_safety_service,
        safety_classification=SafetyClassification.CRITICAL,
        dependencies=[
            ServiceDependency("pin_manager", DependencyType.REQUIRED),
            ServiceDependency("security_audit_service", DependencyType.REQUIRED),
            # Note: service_registry removed to avoid circular dependency
        ],
        description="ISO 26262-compliant safety monitoring and emergency stop system",
        tags={"service", "safety", "critical", "iso26262"},
        health_check=lambda s: s.get_health_status(),
    )

    # AppStateService removed - services now use repositories directly

    # WebSocketService - Direct service registration without Feature inheritance
    async def _init_websocket_service(can_tracking_repository=None, system_state_repository=None):
        service = WebSocketService(
            can_tracking_repository=can_tracking_repository,
            system_state_repository=system_state_repository,
        )
        await service.start()
        return service

    service_registry.register_safety_service(
        name="websocket_manager",
        init_func=_init_websocket_service,
        safety_classification=SafetyClassification.OPERATIONAL,  # Real-time communication is important for operation
        dependencies=[
            ServiceDependency("can_tracking_repository", DependencyType.OPTIONAL),
            ServiceDependency("system_state_repository", DependencyType.OPTIONAL),
        ],
        description="WebSocket connection management service",
        tags={"service", "websocket", "realtime"},
        health_check=lambda s: s.get_health_status()
        if hasattr(s, "get_health_status")
        else {"healthy": s is not None},
    )

    # EntityManagerService - central entity management
    service_registry.register_service(
        name="entity_manager_service",
        init_func=lambda database_manager, rvc_config: EntityManagerService(
            database_manager=database_manager,
            rvc_config_provider=rvc_config,
            config={},  # TODO: Load from YAML config
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("rvc_config", DependencyType.OPTIONAL),  # Can work without it
        ],
        description="Entity management service with persistence (migrated from feature)",
        tags={"service", "entity", "management", "phase4"},
        health_check=lambda s: s.health_check()
        if hasattr(s, "health_check")
        else {"healthy": s is not None},
    )

    # AuthService - Direct service registration without Feature inheritance
    async def _init_auth_service(
        credential_repository,
        session_repository,
        auth_event_repository,
        mfa_repository,
        performance_monitor,
        database_manager,
        token_service,
        session_service,
        mfa_service,
        lockout_service,
        security_config_service,
        notification_service=None,
    ):
        # Create legacy AuthRepository for backward compatibility
        from backend.services.auth_repository import AuthRepository

        auth_repository = AuthRepository(database_manager) if database_manager else None

        # Get authentication configuration from SecurityConfigService
        auth_config = await security_config_service.get_auth_config()

        service = AuthService(
            credential_repository=credential_repository,
            session_repository=session_repository,
            auth_event_repository=auth_event_repository,
            mfa_repository=mfa_repository,
            notification_service=notification_service,
            performance_monitor=performance_monitor,
            auth_repository=auth_repository,  # Inject legacy repository
            token_service=token_service,
            session_service=session_service,
            mfa_service=mfa_service,
            lockout_service=lockout_service,
            auth_config=auth_config,
        )
        await service.start()
        return service

    service_registry.register_safety_service(
        name="auth_manager",
        init_func=_init_auth_service,
        safety_classification=SafetyClassification.CRITICAL,  # Access control is safety-critical
        dependencies=[
            ServiceDependency("credential_repository", DependencyType.REQUIRED),
            ServiceDependency("session_repository", DependencyType.REQUIRED),
            ServiceDependency("auth_event_repository", DependencyType.REQUIRED),
            ServiceDependency("mfa_repository", DependencyType.OPTIONAL),
            ServiceDependency("notification_service", DependencyType.OPTIONAL),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
            ServiceDependency(
                "database_manager", DependencyType.REQUIRED
            ),  # For legacy AuthRepository
            ServiceDependency("token_service", DependencyType.REQUIRED),
            ServiceDependency("session_service", DependencyType.REQUIRED),
            ServiceDependency("mfa_service", DependencyType.OPTIONAL),
            ServiceDependency("lockout_service", DependencyType.REQUIRED),
            ServiceDependency("security_config_service", DependencyType.REQUIRED),
        ],
        description="Authentication service with JWT, magic links, and MFA",
        tags={"service", "auth", "security"},
        health_check=lambda s: s.get_health_status()
        if hasattr(s, "get_health_status")
        else {"healthy": s is not None},
    )

    # CANAnomalyDetector - Security monitoring for CAN bus
    def _init_can_anomaly_detector():
        from backend.integrations.can.anomaly_detector import CANAnomalyDetector

        detector = CANAnomalyDetector()
        logger.info("CAN Anomaly Detector initialized via ServiceRegistry")
        return detector

    service_registry.register_service(
        name="can_anomaly_detector",
        init_func=_init_can_anomaly_detector,
        dependencies=[
            ServiceDependency(
                "security_event_manager", DependencyType.OPTIONAL
            ),  # Will connect if available
        ],
        description="CAN bus anomaly detection and security monitoring",
        tags={"service", "can", "security", "monitoring"},
        health_check=lambda d: {"healthy": d is not None, "monitoring_active": True},
    )

    # CANBusService - Direct service registration without Feature inheritance
    async def _init_can_bus_service(
        can_tracking_repository, system_state_repository, can_anomaly_detector=None
    ):
        service = CANBusService(
            can_tracking_repository=can_tracking_repository,
            system_state_repository=system_state_repository,
            can_anomaly_detector=can_anomaly_detector,
        )
        await service.start()
        return service

    service_registry.register_safety_service(
        name="can_bus_service",
        init_func=_init_can_bus_service,
        safety_classification=SafetyClassification.CRITICAL,  # CAN bus control is safety-critical for vehicle control
        dependencies=[
            ServiceDependency("can_tracking_repository", DependencyType.REQUIRED),
            ServiceDependency("system_state_repository", DependencyType.REQUIRED),
            ServiceDependency(
                "can_anomaly_detector", DependencyType.OPTIONAL
            ),  # Security monitoring
        ],
        description="CAN bus integration service for message processing",
        tags={"service", "can", "hardware", "realtime"},
        health_check=lambda s: s.get_health_status()
        if hasattr(s, "get_health_status")
        else {"healthy": s is not None},
    )

    # CANService registration removed - use can_facade instead

    # CAN Tools Services Registration
    def _init_can_message_injector():
        """Initialize CAN message injector service with audit callback."""

        # Create audit callback that uses ServiceRegistry
        async def audit_injection(request, result):
            try:
                # Get security audit service if available
                if service_registry.has_service("security_audit_service"):
                    security_audit = service_registry.get_service("security_audit_service")
                    if hasattr(security_audit, "log_injection"):
                        await security_audit.log_injection(request, result)
                else:
                    # Fallback to standard logging
                    logger.info(
                        "CAN message injection: user=%s, interface=%s, can_id=0x%X, "
                        "mode=%s, success=%s, sent=%d, duration=%.3fs",
                        request.user,
                        request.interface,
                        request.can_id,
                        request.mode.value,
                        result.success,
                        result.messages_sent,
                        result.duration,
                    )
            except Exception as e:
                logger.error("CAN injection audit error: %s", e)

        # Use default safety level - feature flags have been removed per CLAUDE.md
        safety_level = SafetyLevel.MODERATE  # Default safety level for CAN injection

        service = CANMessageInjector(safety_level=safety_level, audit_callback=audit_injection)
        return service

    service_registry.register_safety_service(
        name="can_message_injector",
        init_func=_init_can_message_injector,
        safety_classification=SafetyClassification.CRITICAL,  # CAN message injection is safety-critical
        dependencies=[
            ServiceDependency("security_audit_service", DependencyType.OPTIONAL),
        ],
        description="Safe CAN message injection service for testing and diagnostics",
        tags={"service", "can", "testing", "diagnostics", "safety-critical"},
        health_check=lambda s: {"healthy": s is not None and not s._emergency_stop_active}
        if hasattr(s, "_emergency_stop_active")
        else {"healthy": s is not None},
    )

    # Register CAN Message Filter Service
    def _init_can_message_filter():
        """Initialize CAN message filter service with alert callback."""
        from backend.integrations.can.message_filter import MessageFilter

        # Create alert callback that uses ServiceRegistry
        async def alert_callback(alert_data):
            try:
                # Get WebSocket service for real-time alerts
                websocket_manager = None
                if service_registry.has_service("websocket_manager"):
                    websocket_manager = service_registry.get_service("websocket_manager")

                if websocket_manager:
                    # Send filter alert via WebSocket to can_filter clients
                    await websocket_manager.broadcast_can_filter_update("filter_alert", alert_data)
                else:
                    logger.warning("Filter alert - no WebSocket manager available: %s", alert_data)
            except Exception as e:
                logger.error("Error in filter alert callback: %s", e)

        # Use default configuration - feature flags have been removed per CLAUDE.md
        max_rules = 100
        capture_buffer_size = 10000

        return MessageFilter(
            max_rules=max_rules,
            alert_callback=alert_callback,
            capture_buffer_size=capture_buffer_size,
        )

    service_registry.register_safety_service(
        name="can_message_filter",
        init_func=_init_can_message_filter,
        safety_classification=SafetyClassification.CRITICAL,
        dependencies=[
            ServiceDependency("websocket_manager", DependencyType.OPTIONAL),
        ],
        description="CAN message filtering system with real-time monitoring and alerting",
        tags={"service", "can", "filtering", "monitoring", "safety"},
        health_check=lambda s: {"healthy": s is not None and not s._emergency_stop_active}
        if hasattr(s, "_emergency_stop_active")
        else {"healthy": s is not None},
    )

    # Register CAN Bus Recorder Service
    def _init_can_bus_recorder(websocket_manager=None):
        """Initialize CAN bus recorder service."""
        from pathlib import Path

        from backend.integrations.can.can_bus_recorder import CANBusRecorder

        # Use default configuration - feature flags have been removed per CLAUDE.md
        buffer_size = 100000
        storage_path = Path("./recordings")
        auto_save_interval = 60.0
        max_file_size_mb = 100.0

        recorder = CANBusRecorder(
            buffer_size=buffer_size,
            storage_path=storage_path,
            auto_save_interval=auto_save_interval,
            max_file_size_mb=max_file_size_mb,
        )

        # Store WebSocket manager for broadcasting
        if websocket_manager:
            recorder._websocket_manager = websocket_manager

        return recorder

    service_registry.register_safety_service(
        name="can_bus_recorder",
        init_func=_init_can_bus_recorder,
        safety_classification=SafetyClassification.OPERATIONAL,
        dependencies=[
            ServiceDependency("websocket_manager", DependencyType.OPTIONAL),
        ],
        description="CAN bus traffic recorder with replay capabilities",
        tags={"service", "can", "recording", "replay", "diagnostics"},
        health_check=lambda s: {"healthy": s is not None and not s._emergency_stop_active}
        if hasattr(s, "_emergency_stop_active")
        else {"healthy": s is not None},
    )

    # Register CAN Protocol Analyzer Service
    def _init_can_protocol_analyzer(websocket_manager=None):
        """Initialize CAN protocol analyzer service."""
        from backend.integrations.can.protocol_analyzer import ProtocolAnalyzer

        # Use default configuration - feature flags have been removed per CLAUDE.md
        buffer_size = 10000
        pattern_window_ms = 5000.0

        analyzer = ProtocolAnalyzer(buffer_size=buffer_size, pattern_window_ms=pattern_window_ms)

        # Store WebSocket manager for broadcasting
        if websocket_manager:
            analyzer._websocket_manager = websocket_manager

        return analyzer

    service_registry.register_safety_service(
        name="can_protocol_analyzer",
        init_func=_init_can_protocol_analyzer,
        safety_classification=SafetyClassification.OPERATIONAL,
        dependencies=[
            ServiceDependency("websocket_manager", DependencyType.OPTIONAL),
        ],
        description="CAN protocol analyzer for deep packet inspection and protocol detection",
        tags={"service", "can", "analysis", "protocol", "diagnostics"},
        health_check=lambda s: {"healthy": s is not None and not s._emergency_stop_active}
        if hasattr(s, "_emergency_stop_active")
        else {"healthy": s is not None},
    )

    # Register CAN Interface Service
    service_registry.register_service(
        name="can_interface_service",
        init_func=lambda: CANInterfaceService(),
        dependencies=[],
        description="CAN interface mapping and resolution service",
        tags={"service", "can", "interface", "mapping"},
        health_check=lambda s: {"healthy": s is not None},
    )

    # CANFacade - Unified facade for all CAN operations
    async def _init_can_facade(
        can_bus_service,
        can_message_injector,
        can_message_filter,
        can_bus_recorder,
        can_protocol_analyzer,
        can_anomaly_detector,
        can_interface_service,
        performance_monitor,
    ):
        """Initialize CANFacade with all CAN-related services."""
        from backend.services.can_facade import CANFacade

        return CANFacade(
            bus_service=can_bus_service,
            injector=can_message_injector,
            message_filter=can_message_filter,
            recorder=can_bus_recorder,
            analyzer=can_protocol_analyzer,
            anomaly_detector=can_anomaly_detector,
            interface_service=can_interface_service,
            performance_monitor=performance_monitor,
        )

    service_registry.register_safety_service(
        name="can_facade",
        init_func=_init_can_facade,
        safety_classification=SafetyClassification.CRITICAL,
        dependencies=[
            ServiceDependency("can_bus_service", DependencyType.REQUIRED),
            ServiceDependency("can_message_injector", DependencyType.REQUIRED),
            ServiceDependency("can_message_filter", DependencyType.REQUIRED),
            ServiceDependency("can_bus_recorder", DependencyType.REQUIRED),
            ServiceDependency("can_protocol_analyzer", DependencyType.REQUIRED),
            ServiceDependency("can_anomaly_detector", DependencyType.REQUIRED),
            ServiceDependency("can_interface_service", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Unified facade for all CAN operations with safety coordination",
        tags={"facade", "can", "safety-critical", "coordination"},
        health_check=lambda s: s.get_health_status()
        if hasattr(s, "get_health_status")
        else {"healthy": s is not None},
    )

    # AnalyticsDashboardService - Analytics and business intelligence service
    def _init_analytics_dashboard_service(
        performance_monitor=None, database_manager=None, analytics_repository=None
    ):
        """Initialize AnalyticsDashboardService with direct dependencies."""
        return AnalyticsDashboardService(
            performance_monitor=performance_monitor,
            database_manager=database_manager,
            analytics_repository=analytics_repository,
        )

    service_registry.register_service(
        name="analytics_dashboard_service",
        init_func=_init_analytics_dashboard_service,
        dependencies=[
            ServiceDependency("performance_monitor", DependencyType.OPTIONAL),
            ServiceDependency(
                "database_manager", DependencyType.REQUIRED
            ),  # Now required for persistence
            ServiceDependency("analytics_repository", DependencyType.OPTIONAL),
        ],
        description="Advanced analytics dashboard for business intelligence and operational insights (requires persistence)",
        tags={
            "service",
            "analytics",
            "dashboard",
            "insights",
            "business-intelligence",
            "persistence",
        },
        health_check=lambda s: {
            "healthy": s is not None,
            "running": s._running if hasattr(s, "_running") else False,
        },
    )

    # DashboardService - Frontend dashboard aggregation service
    from backend.services.dashboard_service import DashboardService

    def _init_dashboard_service(
        entity_state_repository=None,
        dashboard_config_repository=None,
        performance_monitor=None,
        websocket_manager=None,
    ):
        """Initialize DashboardService with direct dependencies."""
        return DashboardService(
            dashboard_repository=dashboard_config_repository,
            entity_repository=entity_state_repository,
            performance_monitor=performance_monitor,
            websocket_manager=websocket_manager,
        )

    service_registry.register_service(
        name="dashboard_service",
        init_func=_init_dashboard_service,
        dependencies=[
            ServiceDependency("entity_state_repository", DependencyType.OPTIONAL),
            ServiceDependency("dashboard_config_repository", DependencyType.OPTIONAL),
            ServiceDependency("performance_monitor", DependencyType.OPTIONAL),
            ServiceDependency("websocket_manager", DependencyType.OPTIONAL),
        ],
        description="Frontend dashboard data aggregation service with activity feeds",
        tags={"service", "dashboard", "frontend", "aggregation"},
        health_check=lambda s: {
            "healthy": s is not None,
            "activity_tracker_enabled": hasattr(s, "_activity_tracker"),
        },
    )

    logger.info("Phase 4 service registration complete")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager with ServiceRegistry integration.

    Handles startup and shutdown logic using the new ServiceRegistry for
    improved dependency management and orchestrated service lifecycle.
    """
    logger.info("Starting coachiq backend application")

    # Initialize EnhancedServiceRegistry for advanced dependency management
    # Use SafetyServiceRegistry for ISO 26262-compliant safety monitoring
    service_registry = SafetyServiceRegistry()

    # Initialize the module-level service registry for dependency injection
    from backend.core.dependencies import initialize_service_registry

    initialize_service_registry(service_registry)

    # Initialize backend metrics FIRST to avoid collisions
    initialize_backend_metrics()

    try:
        # Configure service startup stages with explicit dependencies
        await _configure_service_startup_stages(service_registry)

        # Execute orchestrated startup via EnhancedServiceRegistry
        await service_registry.startup_all()

        # CRITICAL: Inject service_registry into safety_service after startup to avoid circular dependency
        safety_service = service_registry.get_service("safety_service")
        if safety_service and hasattr(safety_service, "set_service_registry"):
            safety_service.set_service_registry(service_registry)
            logger.info(
                "ServiceRegistry injected into SafetyService for emergency stop coordination"
            )
        elif safety_service:
            # If SafetyService doesn't have set_service_registry method, set directly
            safety_service._service_registry = service_registry
            logger.info("ServiceRegistry directly assigned to SafetyService._service_registry")
        else:
            logger.error(
                "SafetyService not found in ServiceRegistry - emergency stop coordination unavailable"
            )

        # Get services from registry
        settings = service_registry.get_service("app_settings")
        rvc_config_provider = service_registry.get_service("rvc_config")
        security_event_manager = service_registry.get_service("security_event_manager")
        device_discovery_service = service_registry.get_service("device_discovery_service")
        persistence_service = service_registry.get_service("persistence_service")
        database_manager = service_registry.get_service("database_manager")

        logger.info("ServiceRegistry startup completed successfully")
        logger.info(f"RVC Config Summary: {rvc_config_provider.get_configuration_summary()}")

        # Phase 0: Add dependency visualization
        try:
            # Get dependency diagram
            diagram = service_registry.export_dependency_diagram()
            logger.info("ServiceRegistry Dependency Diagram:\n%s", diagram)

            # Get startup metrics
            metrics = service_registry.get_enhanced_metrics()
            logger.info("ServiceRegistry Startup Metrics:")
            logger.info(f"  Total startup time: {metrics.get('total_startup_time_ms', 0):.2f}ms")
            logger.info(f"  Service count: {metrics.get('service_count', 0)}")
            logger.info(f"  Total stages: {metrics.get('total_stages', 0)}")
            logger.info(f"  Startup errors: {metrics.get('startup_errors', 0)}")

            # Show slowest services
            slowest = metrics.get("slowest_services", [])
            if slowest:
                logger.info("  Slowest services:")
                for service_name, timing in slowest[:5]:
                    logger.info(f"    - {service_name}: {timing:.2f}ms")

        except Exception as e:
            logger.warning(f"Could not generate dependency visualization: {e}")

        # Get services from ServiceRegistry
        websocket_manager = service_registry.get_service("websocket_manager")
        entity_manager_service = service_registry.get_service("entity_manager_service")

        if not websocket_manager or not entity_manager_service:
            msg = "Required services (websocket, entity_manager) failed to initialize"
            raise RuntimeError(msg)

        # Update logging configuration to include WebSocket handler now that manager is available
        from backend.core.logging_config import update_websocket_logging

        update_websocket_logging(websocket_manager)
        logger.info("WebSocket logging integration completed")

        # Services are now managed by ServiceRegistry - no need for manual initialization
        # TODO(Phase 3): These services need to be updated for constructor injection
        # For now, they're getting dependencies via service locator pattern internally
        docs_service = None  # DocsService() - needs docs_repository, performance_monitor
        vector_service = None  # VectorService() - needs vector_repository, performance_monitor
        can_interface_service = None  # CANInterfaceService() - needs performance_monitor
        # Get database_manager from ServiceRegistry
        database_manager = service_registry.get_service("database_manager")
        # TODO: Migrate these services to ServiceRegistry
        # For now, create with None until properly migrated
        predictive_maintenance_service = (
            None  # PredictiveMaintenanceService - needs maintenance_repository, performance_monitor
        )
        # analytics_dashboard_service now registered in ServiceRegistry

        # Get security services from ServiceRegistry (already initialized)
        security_config_service = service_registry.get_service("security_config_service")
        pin_manager = service_registry.get_service("pin_manager")
        security_audit_service = service_registry.get_service("security_audit_service")

        logger.info("Security services retrieved from ServiceRegistry")

        # Get services from ServiceRegistry
        pin_manager = service_registry.get_service("pin_manager")
        security_audit_service = service_registry.get_service("security_audit_service")

        # SafetyService is now registered in ServiceRegistry
        safety_service = service_registry.get_service("safety_service")
        logger.info("Backend services initialized")

        # Authentication middleware will be configured dynamically via the middleware itself

        # Services are now accessed via ServiceRegistry and dependency injection

        # Initialize Security WebSocket Handler with dependency injection
        # ARCHITECTURE NOTE: The SecurityWebSocketHandler is created as a singleton
        # instance for the entire application lifespan. This ensures it can register
        # its listeners with the SecurityEventManager at startup and not miss any
        # events that occur before the first client connects.
        #
        # CRITICAL LIMITATION: This approach is only safe in a SINGLE-PROCESS
        # environment. In a multi-process setup, each worker would have its own
        # handler instance, and events would not be broadcast to clients connected
        # to other workers.
        #
        # MIGRATION PATH: To support multiple workers, replace with a message broker
        # backend (e.g., Redis Pub/Sub) using a library like encode/broadcaster.
        from backend.websocket.security_handler import SecurityWebSocketHandler

        security_websocket_handler = SecurityWebSocketHandler(event_manager=security_event_manager)
        await security_websocket_handler.startup()
        # Security websocket handler is available via ServiceRegistry
        logger.info("Security WebSocket handler initialized with dependency injection")

        # Analytics dashboard service now started via ServiceRegistry lifecycle

        # Safety monitoring already started during service initialization
        logger.info("Safety monitoring active via ServiceRegistry")

        logger.info("Backend services initialized successfully")

        yield

    except Exception as e:
        logger.error("Error during application startup: %s", e)
        raise
    finally:
        # Cleanup with ServiceRegistry orchestration
        logger.info("Shutting down coachiq backend application")

        # Services shutdown is now handled by ServiceRegistry
        # Individual service shutdown calls removed - ServiceRegistry handles proper shutdown order

        # Shutdown Security WebSocket handler
        # Use ServiceRegistry for orchestrated shutdown
        try:
            from backend.core.dependencies import get_service_registry

            service_registry = get_service_registry()
            logger.info("Using ServiceRegistry for orchestrated shutdown")
            await service_registry.shutdown()
        except Exception as e:
            logger.error(f"Error during ServiceRegistry shutdown: {e}")
            logger.info("Using legacy shutdown (ServiceRegistry not available)")

            # Feature manager removed - all services managed by ServiceRegistry

            # CoreServices removed - individual services shutdown by ServiceRegistry

        logger.info("Backend services stopped")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="CoachIQ Backend",
        description="Modernized backend API for RV-C CANbus monitoring and control",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS handling moved to Caddy edge layer for better performance
    # See config/Caddyfile.example for CORS configuration

    # Add network security middleware for RV-C protection (FIRST for security)
    # Configuration will be loaded from security config service during runtime
    settings = get_settings()

    # Determine HTTPS configuration based on environment and explicit settings
    is_dev_mode = settings.is_development()
    is_behind_trusted_proxy = settings.security.tls_termination_is_external

    # The proxy will handle the redirect, or we're in dev mode
    disable_https_redirect = is_dev_mode or is_behind_trusted_proxy

    # Require HTTPS validation for defense-in-depth, except in development mode
    # In production with external TLS, this protects against requests that bypass the proxy
    # In development mode, allow HTTP for convenience
    require_https_validation = not is_dev_mode

    # Log security configuration for audit trail
    if is_behind_trusted_proxy:
        logger.warning(
            "Security Configuration: External TLS termination enabled. "
            "Operator is responsible for HTTPS redirection and HSTS. "
            "Application MUST be run with proxy headers support enabled.",
            extra={
                "event": "security_configuration",
                "tls_termination": "external",
                "https_redirect": "disabled",
                "proxy_headers_required": True,
            },
        )
    else:
        mode = "development" if is_dev_mode else "production"
        logger.info(
            f"Security Configuration: Application is self-enforcing HTTPS in {mode} mode.",
            extra={
                "event": "security_configuration",
                "tls_termination": "internal",
                "https_redirect": "enabled" if not disable_https_redirect else "disabled",
                "mode": mode,
            },
        )

    # Configure authentication middleware
    # The middleware will obtain the auth manager from app state at runtime
    app.add_middleware(AuthenticationMiddleware)

    # Add runtime validation middleware for safety-critical operations
    app.add_middleware(
        RuntimeValidationMiddleware, validate_requests=True, validate_responses=False
    )

    # Add rate limiting middleware
    # Rate limiter is now accessed via dependency injection
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[attr-defined]

    # Add custom exception handler for account lockout
    @app.exception_handler(AccountLockedError)
    async def account_locked_exception_handler(request: Request, exc: AccountLockedError):
        logger = logging.getLogger(__name__)
        logger.warning("Account locked: %s", exc)

        return JSONResponse(
            status_code=423,  # HTTP_423_LOCKED
            content={
                "error": "account_locked",
                "message": str(exc),
                "lockout_until": (exc.lockout_until.isoformat() if exc.lockout_until else None),
                "failed_attempts": exc.attempts,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Add exception handler for ServiceNotAvailableError
    @app.exception_handler(ServiceNotAvailableError)
    async def service_not_available_handler(request: Request, exc: ServiceNotAvailableError):
        logger = logging.getLogger(__name__)
        logger.warning("Service not available: %s", exc.service_name)

        return JSONResponse(
            status_code=503,  # Service Unavailable
            content={
                "detail": str(exc),
                "service": exc.service_name,
                "message": "This service is not configured in the current deployment",
            },
        )

    # Configure and include routers
    configure_routers(app)

    return app


# Create the FastAPI application
app = create_app()


@app.get("/")
async def root():
    """Root endpoint for health checking."""
    return {"message": "CoachIQ Backend is running", "version": "2.0.0"}


@app.get("/health")
async def health_check(request: Request):
    """
    Human-readable diagnostic endpoint for technicians and simple connectivity tests.

    Always returns 200 OK with system information. For automated health monitoring,
    use /readyz (external monitors) or /healthz (internal orchestration).
    """
    settings = get_settings()

    # Calculate uptime
    uptime_seconds = round(time.time() - SERVER_START_TIME)

    # Get version info
    version = "unknown"
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            version = version_file.read_text().strip()
        else:
            version = os.getenv("VERSION", "development")
    except Exception:
        version = "unknown"

    # Get enabled protocols from the protocol manager
    from backend.core.dependencies import get_service_registry

    service_registry = get_service_registry()
    protocol_manager = service_registry.get_service("protocol_manager")

    if protocol_manager:
        # Get enabled protocols with runtime health checks
        enabled_protocols = protocol_manager.get_enabled_protocols(service_registry)
    else:
        # Fallback if protocol manager not available
        enabled_protocols = ["rvc"]  # RVC is always enabled

    return {
        "status": "online",
        "service_name": settings.app_name,
        "version": version,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "uptime_seconds": uptime_seconds,
        "uptime_human": f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m {uptime_seconds % 60}s",
        "timestamp": datetime.now(UTC).isoformat(),
        "entity_count": 0,  # Entity count removed - use /api/v2/entities endpoint for entity info
        "can_interfaces": settings.can.interfaces,
        "protocols_enabled": enabled_protocols,
        "hostname": platform.node(),
        "platform": platform.system(),
        "python_version": platform.python_version(),
    }


@app.get(
    "/healthz",
    summary="Liveness probe",
    description="Minimal IETF-compliant liveness probe. Checks only process health, not dependencies. Optimized for <5ms response time.",
)
async def healthz(request: Request) -> Response:
    """
    Minimal liveness probe following Kubernetes patterns.

    Only checks if the process is alive and responsive - no dependency checking.
    Optimized for ultra-fast response time (<5ms target).

    Use /readyz for comprehensive dependency checking.
    Use /startupz for hardware initialization status.
    """
    start_time = time.time()

    try:
        # Minimal liveness checks - only process health
        # 1. Check if we can access basic application state (proves process is alive)
        try:
            _ = request.app.state
            process_alive = True
        except Exception:
            process_alive = False

        # 2. Check if event loop is responsive (basic async health)
        import asyncio

        try:
            # Simple async operation to verify event loop isn't blocked
            await asyncio.sleep(0)
            event_loop_responsive = True
        except Exception:
            event_loop_responsive = False

        # Overall liveness is just: process alive + event loop responsive
        is_alive = process_alive and event_loop_responsive
        ietf_status = "pass" if is_alive else "fail"

        response_time_ms = round((time.time() - start_time) * 1000, 2)

        # Minimal IETF health+json response optimized for speed
        response_data = {
            "status": ietf_status,
            "version": "1",
            "serviceId": "coachiq-liveness",
            "description": "Process alive and responsive" if is_alive else "Process unresponsive",
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {
                "process": {"status": "pass" if process_alive else "fail"},
                "event_loop": {"status": "pass" if event_loop_responsive else "fail"},
            },
            "response_time_ms": response_time_ms,
        }

        # Only add minimal metadata to keep response small and fast
        response_data["service"] = {
            "name": "coachiq",
            "environment": os.getenv("ENVIRONMENT", "development"),
        }

        # Use appropriate HTTP status code
        status_code = 200 if is_alive else 503

        # Record metrics for monitoring
        record_health_probe(
            endpoint="healthz",
            response_time_ms=response_time_ms,
            status_code=status_code,
            status=ietf_status,
        )

        # Log only on failure or if response is slow (>5ms)
        if not is_alive:
            logger.warning(
                f"Liveness check failed - process_alive: {process_alive}, event_loop: {event_loop_responsive}"
            )
        elif response_time_ms > 5.0:
            logger.warning(f"Liveness check slow - {response_time_ms}ms (target: <5ms)")
        else:
            logger.debug(f"Liveness check passed - {response_time_ms}ms")

        return Response(
            content=json.dumps(response_data),
            status_code=status_code,
            media_type="application/health+json",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    except Exception as e:
        # Even exception handling is minimal for speed
        logger.error(f"Liveness probe error: {e}")
        error_response_time = round((time.time() - start_time) * 1000, 2)

        # Record error metrics
        record_health_probe(
            endpoint="healthz",
            response_time_ms=error_response_time,
            status_code=503,
            status="fail",
            error=str(e),
        )

        error_response = {
            "status": "fail",
            "version": "1",
            "serviceId": "coachiq-liveness",
            "description": "Liveness probe exception",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return Response(
            content=json.dumps(error_response),
            status_code=503,
            media_type="application/health+json",
        )


@app.get(
    "/startupz",
    summary="Startup probe",
    description="Returns IETF-compliant health status for hardware initialization. Succeeds when CAN transceivers are initialized.",
)
async def startupz(request: Request, service_registry: ServiceRegistry) -> Response:
    """
    Startup probe for hardware initialization following Kubernetes patterns.

    Focuses specifically on hardware readiness (CAN transceivers) to protect
    against slow initialization in RV-C environments.
    """
    logger.debug("GET /startupz - Startup probe requested")
    start_time = time.time()

    try:
        # Check CAN bus service status from ServiceRegistry
        can_interface_ready = (
            service_registry.has_service("can_interface_service")
            and service_registry.get_service_status("can_interface_service")
            == ServiceStatus.HEALTHY
        )
        can_bus_ready = (
            service_registry.has_service("can_bus_service")
            and service_registry.get_service_status("can_bus_service") == ServiceStatus.HEALTHY
        )

        # Hardware is considered ready when CAN services are initialized
        # This is the minimum requirement for the application to start receiving traffic
        startup_ready = can_interface_ready and can_bus_ready

        # IETF-compliant status
        ietf_status = "pass" if startup_ready else "fail"

        # Get service version
        version = "unknown"
        try:
            version_file = Path(__file__).parent.parent / "VERSION"
            if version_file.exists():
                version = version_file.read_text().strip()
            else:
                version = os.getenv("VERSION", "development")
        except Exception:
            version = "unknown"

        response_time_ms = round((time.time() - start_time) * 1000, 2)

        # IETF health+json response for startup probe
        response_data = {
            "status": ietf_status,
            "version": "1",
            "releaseId": version,
            "serviceId": "coachiq-startup",
            "description": "Hardware initialization complete"
            if startup_ready
            else "Waiting for CAN transceiver initialization",
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {
                "can_interface": {"status": "pass" if can_interface_ready else "fail"},
                "can_bus": {"status": "pass" if can_bus_ready else "fail"},
            },
            "response_time_ms": response_time_ms,
        }

        # Add service metadata
        response_data["service"] = {
            "name": "coachiq",
            "version": version,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "hostname": platform.node(),
            "platform": platform.system(),
        }

        # Use appropriate HTTP status code
        status_code = 200 if startup_ready else 503

        # Record metrics for monitoring
        record_health_probe(
            endpoint="startupz",
            response_time_ms=response_time_ms,
            status_code=status_code,
            status=ietf_status,
            details={
                "can_interface_ready": can_interface_ready,
                "can_bus_ready": can_bus_ready,
            },
        )

        logger.info(
            f"Startup probe completed - status: {ietf_status}, "
            f"can_ready: {startup_ready}, "
            f"response_time: {response_time_ms}ms, "
            f"status_code: {status_code}"
        )

        return Response(
            content=json.dumps(response_data),
            status_code=status_code,
            media_type="application/health+json",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    except Exception as e:
        logger.error(f"Error in startup probe: {e}")
        error_response_time = round((time.time() - start_time) * 1000, 2)

        # Record error metrics
        record_health_probe(
            endpoint="startupz",
            response_time_ms=error_response_time,
            status_code=503,
            status="fail",
            error=str(e),
        )

        # Return a minimal failure response even if feature manager fails
        error_response = {
            "status": "fail",
            "version": "1",
            "serviceId": "coachiq-startup",
            "description": f"Startup probe error: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return Response(
            content=json.dumps(error_response),
            status_code=503,
            media_type="application/health+json",
        )


@app.get(
    "/readyz",
    summary="Readiness probe",
    description="Returns IETF-compliant comprehensive readiness status with dependency checking. Includes safety-critical monitoring.",
)
async def readyz(request: Request, details: bool = False) -> Response:
    """
    Comprehensive readiness probe following Kubernetes patterns.

    Checks all critical system dependencies and safety requirements.
    Returns 200 only when the service can safely handle traffic.
    """
    logger.debug(f"GET /readyz - Readiness probe requested with details={details}")
    start_time = time.time()

    try:
        # Comprehensive readiness checks
        readiness_checks = {}
        critical_failures = []
        warning_failures = []

        # Get ServiceRegistry for health checks
        service_registry = None
        try:
            from backend.core.dependencies import get_service_registry

            service_registry = get_service_registry()
        except Exception:
            pass

        # ServiceRegistry health aggregation
        if service_registry:
            try:
                service_counts = service_registry.get_service_count_by_status()
                healthy_services = service_counts.get(ServiceStatus.HEALTHY, 0)
                total_services = sum(service_counts.values())

                readiness_checks["service_registry"] = {
                    "status": "pass" if healthy_services >= 3 else "fail",
                    "details": {
                        "healthy_services": healthy_services,
                        "total_services": total_services,
                        "service_breakdown": {
                            status.value: count for status, count in service_counts.items()
                        },
                    },
                }
                if healthy_services < 3:
                    critical_failures.append("service_registry")
            except Exception:
                readiness_checks["service_registry"] = {
                    "status": "fail",
                    "details": {"error": "ServiceRegistry error"},
                }
                critical_failures.append("service_registry")
        else:
            readiness_checks["service_registry"] = {
                "status": "fail",
                "details": {"error": "ServiceRegistry not available"},
            }
            critical_failures.append("service_registry")

        # 1. Hardware initialization (from startup probe)
        can_interface_ready = False
        can_bus_ready = False
        if service_registry:
            can_interface_ready = (
                service_registry.has_service("can_interface_service")
                and service_registry.get_service_status("can_interface_service")
                == ServiceStatus.HEALTHY
            )
            can_bus_ready = (
                service_registry.has_service("can_bus_service")
                and service_registry.get_service_status("can_bus_service") == ServiceStatus.HEALTHY
            )
        hardware_ready = can_interface_ready and can_bus_ready
        readiness_checks["hardware_initialization"] = {
            "status": "pass" if hardware_ready else "fail",
            "details": {"can_interface": can_interface_ready, "can_bus": can_bus_ready},
        }
        if not hardware_ready:
            critical_failures.append("hardware_initialization")

        # 2. Core services operational (now using ServiceRegistry)
        entity_manager_ready = (
            service_registry.has_service("entity_manager_service")
            and service_registry.get_service_status("entity_manager_service")
            == ServiceStatus.HEALTHY
        )
        # app_state_service removed - check repositories instead
        app_state_ready = True  # Now using repositories directly
        websocket_ready = (
            service_registry.has_service("websocket_service")
            and service_registry.get_service_status("websocket_service") == ServiceStatus.HEALTHY
        )
        persistence_ready = service_registry.has_service("persistence_service")
        database_ready = service_registry.has_service("database_manager")

        core_services_ready = (
            entity_manager_ready and websocket_ready and persistence_ready and database_ready
        )
        readiness_checks["core_services"] = {
            "status": "pass" if core_services_ready else "fail",
            "details": {
                "entity_manager": entity_manager_ready,
                "websocket": websocket_ready,
                "persistence": persistence_ready,
                "database": database_ready,
            },
        }
        if not core_services_ready:
            critical_failures.append("core_services")

        # 3. Entity discovery (traffic readiness indicator)
        entity_manager = (
            service_registry.get_service("entity_manager_service") if service_registry else None
        )
        entity_count = (
            len(entity_manager.get_entity_ids())
            if entity_manager and hasattr(entity_manager, "get_entity_ids")
            else 0
        )
        entities_discovered = entity_count > 0
        readiness_checks["entity_discovery"] = {
            "status": "pass" if entities_discovered else "fail",
            "details": {"entity_count": entity_count, "discovery_complete": entities_discovered},
        }
        if not entities_discovered:
            warning_failures.append("entity_discovery")

        # 4. Protocol readiness
        # RVC is always enabled in modern architecture
        rvc_ready = True
        protocol_health = {"rvc": True}

        # J1939 is optional and not yet migrated
        j1939_ready = False

        protocols_healthy = all(protocol_health.values())
        readiness_checks["protocol_systems"] = {
            "status": "pass" if protocols_healthy else "fail",
            "details": {
                "rvc_enabled": rvc_ready,
                "j1939_enabled": j1939_ready,
                "protocol_health": protocol_health,
            },
        }
        if not protocols_healthy:
            critical_failures.append("protocol_systems")

        # 5. Safety-critical systems
        # Check safety service and auth service from ServiceRegistry
        safety_service_ready = (
            service_registry.has_service("safety_service")
            and service_registry.get_service_status("safety_service") == ServiceStatus.HEALTHY
        )
        auth_ready = (
            service_registry.has_service("auth_manager")
            and service_registry.get_service_status("auth_manager") == ServiceStatus.HEALTHY
        )

        safety_systems_ready = safety_service_ready and auth_ready
        readiness_checks["safety_systems"] = {
            "status": "pass" if safety_systems_ready else "fail",
            "details": {
                "safety_service": safety_service_ready,
                "authentication": auth_ready,
            },
        }
        if not safety_systems_ready:
            critical_failures.append("safety_systems")

        # 6. API readiness
        # Domain API v2 is always enabled in modern architecture
        domain_api_ready = True
        entities_api_ready = True
        api_systems_ready = domain_api_ready and entities_api_ready
        readiness_checks["api_systems"] = {
            "status": "pass" if api_systems_ready else "fail",
            "details": {"domain_api_v2": domain_api_ready, "entities_api_v2": entities_api_ready},
        }
        if not api_systems_ready:
            warning_failures.append("api_systems")

        # Overall readiness determination
        # Critical failures prevent readiness, warning failures are noted but don't block
        overall_ready = len(critical_failures) == 0
        ietf_status = "pass" if overall_ready else "fail"

        # Get service version
        version = "unknown"
        try:
            version_file = Path(__file__).parent.parent / "VERSION"
            if version_file.exists():
                version = version_file.read_text().strip()
            else:
                version = os.getenv("VERSION", "development")
        except Exception:
            version = "unknown"

        response_time_ms = round((time.time() - start_time) * 1000, 2)

        # Generate description
        if critical_failures:
            description = f"Service not ready: {len(critical_failures)} critical system(s) failed"
        elif warning_failures:
            description = f"Service ready with warnings: {len(warning_failures)} non-critical system(s) degraded"
        else:
            description = "All systems ready to handle traffic"

        # IETF health+json response for readiness probe
        response_data = {
            "status": ietf_status,
            "version": "1",
            "releaseId": version,
            "serviceId": "coachiq-readiness",
            "description": description,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {
                name: {"status": check["status"]} for name, check in readiness_checks.items()
            },
            "response_time_ms": response_time_ms,
        }

        # Add service metadata
        response_data["service"] = {
            "name": "coachiq",
            "version": version,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "hostname": platform.node(),
            "platform": platform.system(),
        }

        # Add failure categorization for safety-aware orchestration
        if critical_failures or warning_failures:
            response_data["issues"] = {"critical": critical_failures, "warning": warning_failures}

        # Add detailed check information if requested
        if details:
            response_data["detailed_checks"] = readiness_checks

            # Add system metrics
            response_data["metrics"] = {
                "entity_count": entity_count,
                "enabled_services": healthy_services,
                "total_services": total_services,
                "critical_systems_healthy": len(critical_failures) == 0,
                "warning_systems_healthy": len(warning_failures) == 0,
            }

        # Use appropriate HTTP status code
        status_code = 200 if overall_ready else 503

        # Record metrics for monitoring
        record_health_probe(
            endpoint="readyz",
            response_time_ms=response_time_ms,
            status_code=status_code,
            status=ietf_status,
            details={
                "entity_count": entity_count,
                "critical_failures": critical_failures,
                "warning_failures": warning_failures,
                "hardware_ready": hardware_ready,
                "core_services_ready": core_services_ready,
                "safety_systems_ready": safety_systems_ready,
            },
        )

        logger.info(
            f"Readiness probe completed - status: {ietf_status}, "
            f"critical_failures: {len(critical_failures)}, "
            f"warning_failures: {len(warning_failures)}, "
            f"entities: {entity_count}, "
            f"response_time: {response_time_ms}ms, "
            f"status_code: {status_code}"
        )

        if critical_failures:
            logger.warning(f"Readiness check failed - critical systems: {critical_failures}")
        elif warning_failures:
            logger.info(f"Readiness check passed with warnings: {warning_failures}")

        return Response(
            content=json.dumps(response_data),
            status_code=status_code,
            media_type="application/health+json",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    except Exception as e:
        logger.error(f"Error in readiness probe: {e}")
        error_response_time = round((time.time() - start_time) * 1000, 2)

        # Record error metrics
        record_health_probe(
            endpoint="readyz",
            response_time_ms=error_response_time,
            status_code=503,
            status="fail",
            error=str(e),
        )

        # Return a minimal failure response
        error_response = {
            "status": "fail",
            "version": "1",
            "serviceId": "coachiq-readiness",
            "description": f"Readiness probe error: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return Response(
            content=json.dumps(error_response),
            status_code=503,
            media_type="application/health+json",
        )


@app.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Returns Prometheus-format metrics for monitoring.",
)
def metrics() -> Response:
    """Prometheus metrics endpoint."""
    logger.debug("GET /metrics - Prometheus metrics requested")
    data = generate_latest()
    logger.debug(f"Prometheus metrics generated - {len(data)} bytes")
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get(
    "/health/monitoring",
    summary="Health probe monitoring",
    description="Returns comprehensive monitoring data for health probe performance and reliability.",
)
async def health_monitoring(request: Request) -> JSONResponse:
    """
    Health probe monitoring endpoint.

    Provides detailed metrics about health endpoint performance, success rates,
    and alerting information for production monitoring.
    """
    logger.debug("GET /health/monitoring - Health monitoring requested")

    try:
        monitoring_summary = get_health_monitoring_summary()

        return JSONResponse(
            status_code=200,
            content={
                "monitoring_summary": monitoring_summary,
                "timestamp": datetime.now(UTC).isoformat(),
                "description": "Health probe monitoring data",
            },
        )

    except Exception as e:
        logger.error(f"Error in health monitoring endpoint: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "monitoring_error",
                "message": f"Failed to retrieve monitoring data: {e}",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )


def main():
    """
    Main entry point for running the backend as a script.

    This function is used when the backend is run via the project scripts
    defined in pyproject.toml.
    """
    import os

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Get settings to use as CLI defaults
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Start the coachiq backend server.")
    parser.add_argument(
        "--host",
        type=str,
        default=settings.server.host,
        help=f"Host to bind the server (default: {settings.server.host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.server.port,
        help=f"Port to bind the server (default: {settings.server.port})",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=os.getenv("COACHIQ_RELOAD", "false").lower() == "true",
        help="Enable auto-reload (development only, or COACHIQ_RELOAD=true)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=settings.logging.level.lower(),
        help=f"Uvicorn log level (default: {settings.logging.level.lower()})",
    )
    args = parser.parse_args()

    # Set up early logging before anything else
    setup_early_logging()

    # Get settings to potentially configure more comprehensive logging
    settings = get_settings()

    # Configure unified logging for standalone script execution
    log_config, root_logger = configure_unified_logging(settings.logging)

    logger.info("Starting coachiq backend server in standalone mode")

    # Get SSL configuration if available
    ssl_config = settings.get_uvicorn_ssl_config()

    # Build uvicorn run arguments
    uvicorn_args = {
        "app": "backend.main:app",
        "host": args.host,
        "port": args.port,
        "reload": args.reload,
        "log_level": args.log_level,
        "log_config": log_config,
    }

    # Add reload directories to prevent PermissionError on protected directories
    if args.reload:
        # Use absolute path to backend directory to handle cases where working directory is /
        import os

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        uvicorn_args["reload_dirs"] = [os.path.join(backend_dir, "backend")]

    # Add SSL configuration if available
    uvicorn_args.update(ssl_config)

    # Log SSL status
    if ssl_config:
        logger.info("SSL/TLS enabled - server will run on HTTPS")
    else:
        logger.info("SSL/TLS not configured - server will run on HTTP")

    # Run the application using the top-level uvicorn import with unified log config
    uvicorn.run(**uvicorn_args)


if __name__ == "__main__":
    main()
