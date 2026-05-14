"""
Group-2 service registrations for the CoachIQ ServiceRegistry.

Extracted from `backend/main.py` in audit cycle 2026-05-13 PR A8.
These are the services that were extracted from the monolithic legacy
managers in the Phase 2/3 ServiceRegistry refactor and use constructor
injection for their repository dependencies.

Behavior is bit-identical to the original.
"""

# ruff: noqa: SLF001, PLR0913, PLR0915, E501, RET504, BLE001, G201, G202, RUF015, ARG002, ARG005, C901, EM101, F811, FIX002, PERF401
# Pre-existing patterns from the moved code (lifted from main.py in audit
# cycle 2026-05-13 PR A8). Cleanup is out of scope for the mechanical extraction.

import logging

from backend.core.config import get_settings
from backend.core.safety_registry import SafetyServiceRegistry
from backend.core.service_dependency_resolver import DependencyType, ServiceDependency

# Auth services (token, session, MFA, lockout) -- split into per-file modules
# under backend/services/auth/ in audit cycle 2026-05-13 PR A9.
from backend.services.auth.lockout import LockoutService
from backend.services.auth.mfa import MfaService
from backend.services.auth.sessions import SessionService
from backend.services.auth.tokens import TokenService
from backend.services.database_engine import DatabaseEngine
from backend.services.database_services import (
    DatabaseConnectionService,
    DatabaseMigrationService,
    DatabaseSessionService,
)
from backend.services.entity_service import EntityService
from backend.services.security_event_service import SecurityEventService

logger = logging.getLogger(__name__)


def _create_database_engine() -> DatabaseEngine:
    """Create a database engine instance.

    Local helper kept here so the module is self-contained. Identical
    to the original `_create_database_engine` in main.py.
    """
    settings = get_settings()
    return DatabaseEngine(settings)


def register(service_registry: SafetyServiceRegistry) -> None:
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
    # The unified `entity_service` (EntityService facade, registered below)
    # is the single source of truth for entity reads, control, and mapping
    # CRUD. The previous EntityQueryService / EntityControlService /
    # EntityManagementService split was scaffolded as part of an unfinished
    # migration; their implementations were stubs (empty unmapped entries,
    # no real CAN message construction, etc.) and they had zero router
    # consumers. Removed in PR #111 to eliminate ambiguity. The
    # `_require_role` defense-in-depth pattern those classes pioneered was
    # ported into EntityService in the same PR.

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

    # EntityDomainService - operationally-critical entity domain operations.
    # CRITICAL classification means startup priority + emergency-stop
    # participation, not vehicle safety -- see ADR-0004.
    from backend.services.entity_domain_service import EntityDomainService

    service_registry.register_service(
        name="entity_domain_service",
        init_func=lambda rvc_config_facade,
        auth_manager,
        entity_service,
        websocket_manager,
        entity_manager_service: EntityDomainService(
            config_service=rvc_config_facade,
            auth_manager=auth_manager,
            entity_service=entity_service,
            websocket_manager=websocket_manager,
            entity_manager=entity_manager_service,
        ),
        dependencies=[
            ServiceDependency("rvc_config_facade", DependencyType.REQUIRED),
            ServiceDependency("auth_manager", DependencyType.REQUIRED),
            ServiceDependency("entity_service", DependencyType.REQUIRED),
            ServiceDependency("websocket_manager", DependencyType.REQUIRED),
            ServiceDependency("entity_manager_service", DependencyType.REQUIRED),
        ],
        description="Safety-critical entity domain service with comprehensive safety interlocks",
        tags={"service", "entity", "domain", "safety-critical"},
        health_check=lambda s: {"healthy": s is not None, "safety_interlocks_enabled": True},
    )
