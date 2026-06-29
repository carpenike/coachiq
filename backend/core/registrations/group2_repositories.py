"""
Group-2 repository registrations for the CoachIQ ServiceRegistry.

Extracted from `backend/main.py` in audit cycle 2026-05-13 PR A8.

These are the repositories that own the data-access surface for the
Group-2 services (auth, database, security, entity). They all extend
``MonitoredRepository`` for consistent performance monitoring.

Behavior is bit-identical to the original.
"""

# ruff: noqa: SLF001, PLR0913, PLR0915, E501, RET504, BLE001, G201, G202, RUF015, ARG002, ARG005, C901, EM101, F811, FIX002, PERF401
# Pre-existing patterns from the moved code (lifted from main.py in audit
# cycle 2026-05-13 PR A8). Cleanup is out of scope for the mechanical extraction.

import logging

from backend.core.safety_registry import SafetyServiceRegistry
from backend.core.service_dependency_resolver import DependencyType, ServiceDependency
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
from backend.services.entities.entity_initialization_service import EntityInitializationService

logger = logging.getLogger(__name__)


def register(service_registry: SafetyServiceRegistry) -> None:
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
