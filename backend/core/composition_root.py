"""Typed composition root for backend service construction."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from backend.core.config import Settings
from backend.core.config_provider import RVCConfigProvider
from backend.core.guardrail_coordinator import GuardrailCoordinator
from backend.core.guardrail_runtime_coordinator import GuardrailRuntimeCoordinator
from backend.core.performance import PerformanceMonitor
from backend.services.database.database_manager import DatabaseManager
from backend.services.persistence.persistence_service import PersistenceService
from backend.services.rvc.rvc_config_facade import RVCConfigFacade
from backend.services.updates.edge_proxy_monitor_service import EdgeProxyMonitorService

logger = logging.getLogger(__name__)

ConfigureServices = Callable[[GuardrailCoordinator], Awaitable[None]]


@dataclass(slots=True)
class CompositionServices:
    """Typed service handles captured during the compatibility phase."""

    settings: Settings
    rvc_config: RVCConfigProvider
    performance_monitor: PerformanceMonitor
    database_manager: DatabaseManager
    edge_proxy_monitor: EdgeProxyMonitorService
    persistence_service: PersistenceService
    rvc_config_facade: RVCConfigFacade
    rvc_config_repository: Any = None
    system_state_repository: Any = None
    can_tracking_repository: Any = None
    diagnostics_repository: Any = None
    database_connection_repository: Any = None
    database_session_repository: Any = None
    migration_repository: Any = None
    database_backup_repository: Any = None
    database_migration_repository: Any = None
    migration_history_repository: Any = None
    safety_repository: Any = None
    analytics_repository: Any = None
    auth_event_repository: Any = None
    can_command_repository: Any = None
    credential_repository: Any = None
    entity_config_repository: Any = None
    entity_history_repository: Any = None
    entity_manager_service: Any = None
    entity_state_repository: Any = None
    mfa_repository: Any = None
    persistence_repository: Any = None
    security_audit_repository: Any = None
    security_config_repository: Any = None
    security_event_repository: Any = None
    security_listener_repository: Any = None
    session_repository: Any = None
    token_service: Any = None
    database_connection_service: Any = None
    database_session_service: Any = None
    database_migration_service: Any = None
    migration_safety_validator: Any = None
    database_update_service: Any = None
    protocol_manager: Any = None
    rvc_service: Any = None
    device_discovery_service: Any = None
    can_facade: Any = None
    security_event_service: Any = None
    attempt_tracker_service: Any = None
    mfa_service: Any = None
    session_service: Any = None
    security_config_service: Any = None
    lockout_service: Any = None
    pin_manager: Any = None
    security_audit_service: Any = None
    auth_manager: Any = None
    security_event_manager: Any = None
    command_guardrail_service: Any = None
    can_anomaly_detector: Any = None
    can_bus_recorder: Any = None
    can_interface_service: Any = None
    can_message_filter: Any = None
    can_message_injector: Any = None
    can_protocol_analyzer: Any = None
    dashboard_service: Any = None
    diagnostic_handler: Any = None
    websocket_manager: Any = None
    analytics_dashboard_service: Any = None
    can_bus_service: Any = None
    can_network_telemetry_service: Any = None
    entity_initialization_service: Any = None
    entity_service: Any = None
    entity_domain_service: Any = None


class CompositionRoot:
    """Own backend service lifecycle and expose typed service handles."""

    _FOUNDATION_SERVICE_ORDER = (
        "app_settings",
        "performance_monitor",
        "rvc_config",
        "database_manager",
        "edge_proxy_monitor",
    )
    _REPOSITORY_SUBSTRATE_SERVICE_ORDER = (
        "rvc_config_repository",
        "system_state_repository",
        "can_tracking_repository",
        "diagnostics_repository",
        "database_connection_repository",
        "database_session_repository",
        "migration_repository",
        "database_backup_repository",
        "database_migration_repository",
        "migration_history_repository",
        "safety_repository",
        "analytics_repository",
        "auth_event_repository",
        "can_command_repository",
        "credential_repository",
        "entity_config_repository",
        "entity_history_repository",
        "entity_manager_service",
        "entity_state_repository",
        "mfa_repository",
        "persistence_repository",
        "security_audit_repository",
        "security_config_repository",
        "security_event_repository",
        "security_listener_repository",
        "session_repository",
        "token_service",
    )
    _FACADE_SERVICE_ORDER = (
        "rvc_config_facade",
        "persistence_service",
    )
    _A2_SERVICE_ORDER = (
        "database_connection_service",
        "database_session_service",
        "database_migration_service",
        "migration_safety_validator",
        "database_update_service",
        "protocol_manager",
        "rvc_service",
        "device_discovery_service",
        "can_facade",
    )
    _A3_SERVICE_ORDER = (
        "security_event_service",
        "attempt_tracker_service",
        "mfa_service",
        "session_service",
        "security_config_service",
        "lockout_service",
        "pin_manager",
        "security_audit_service",
        "auth_manager",
        "security_event_manager",
        "command_guardrail_service",
    )
    _A4_SERVICE_ORDER = (
        "can_anomaly_detector",
        "can_bus_recorder",
        "can_interface_service",
        "can_message_filter",
        "can_message_injector",
        "can_protocol_analyzer",
        "dashboard_service",
        "diagnostic_handler",
        "websocket_manager",
        "analytics_dashboard_service",
        "can_bus_service",
        "can_network_telemetry_service",
        "entity_initialization_service",
        "entity_service",
        "entity_domain_service",
    )

    def __init__(self, compat_registry: GuardrailCoordinator | None = None) -> None:
        self.compat_registry = compat_registry or GuardrailCoordinator()
        self.guardrail_coordinator = GuardrailRuntimeCoordinator()
        self._constructed_services: dict[str, Any] = {}
        self._constructing_services: set[str] = set()
        self.services = CompositionServices(
            settings=cast("Settings", None),
            rvc_config=cast("RVCConfigProvider", None),
            performance_monitor=cast("PerformanceMonitor", None),
            database_manager=cast("DatabaseManager", None),
            edge_proxy_monitor=cast("EdgeProxyMonitorService", None),
            persistence_service=cast("PersistenceService", None),
            rvc_config_facade=cast("RVCConfigFacade", None),
        )
        self._configured = False
        self._started = False

    @property
    def service_registry(self) -> GuardrailCoordinator:
        """Temporary compatibility alias for pre-HOF-052 call sites."""
        return self.compat_registry

    async def configure(self, configure_services: ConfigureServices) -> None:
        """Register services with the compatibility registry."""
        if self._configured:
            return

        await configure_services(self.compat_registry)
        self._configured = True

    async def startup(self, configure_services: ConfigureServices | None = None) -> None:
        """Start all services and capture typed handles for migrated clusters."""
        if configure_services is not None:
            await self.configure(configure_services)

        await self._construct_foundation_services()
        await self._construct_repository_substrate_services()
        await self._construct_facade_services()
        await self._construct_a2_services()
        await self._construct_a3_services()
        await self._construct_a4_services()
        await self.compat_registry.startup_all()
        self._mirror_remaining_guardrail_services()
        self._capture_registry_services()
        self._started = True

    async def shutdown(self) -> None:
        """Shut down services in composition-root order."""
        if not self._started:
            return

        await self.compat_registry.shutdown_all()
        self._started = False

    def set_constructed_service(self, service_name: str, service: Any) -> None:
        """Store a root-constructed service without registry capture."""
        self._constructed_services[service_name] = service
        self._apply_constructed_service_handle(service_name, service)

    def has_service(self, service_name: str) -> bool:
        """Return whether a service is available."""
        return service_name in self._constructed_services or self.compat_registry.has_service(
            service_name
        )

    def get_service(self, service_name: str) -> Any:
        """Return a service by name from root construction or compatibility registry."""
        if service_name in self._constructed_services:
            return self._constructed_services[service_name]
        return self.compat_registry.get_service(service_name)

    def get_optional_service(self, service_name: str) -> Any | None:
        """Return a service by name, or None if it is unavailable."""
        if not self.has_service(service_name):
            return None
        return self.get_service(service_name)

    def __getattr__(self, name: str) -> Any:
        """Delegate legacy registry APIs during Phase A compatibility."""
        return getattr(self.compat_registry, name)

    def _capture_registry_services(self) -> None:
        """Temporarily cache registry handles during HOF-052 Phase A.

        This is transitional scaffolding for ADR-0014 only. Each migrated
        cluster must replace these string-lookups with root construction via
        ``set_constructed_service`` and make the corresponding field
        non-optional once the handle no longer comes from the compatibility
        registry.
        """
        self.services = CompositionServices(
            settings=self.get_service("app_settings"),
            rvc_config=self.get_service("rvc_config"),
            performance_monitor=self.get_service("performance_monitor"),
            database_manager=self.get_service("database_manager"),
            edge_proxy_monitor=self.get_service("edge_proxy_monitor"),
            persistence_service=self.get_service("persistence_service"),
            rvc_config_facade=self.get_service("rvc_config_facade"),
        )
        logger.info("CompositionRoot captured typed service handles")

    async def _construct_foundation_services(self) -> None:
        """Construct A0 foundation services with typed constructors."""
        if (
            "app_settings" not in self._constructed_services
            and self.compat_registry.has_service_definition("app_settings")
        ):
            self._set_root_constructed_service("app_settings", Settings())

        if (
            "performance_monitor" not in self._constructed_services
            and self.compat_registry.has_service_definition("performance_monitor")
        ):
            self._set_root_constructed_service("performance_monitor", PerformanceMonitor())

        if (
            "rvc_config" not in self._constructed_services
            and self.compat_registry.has_service_definition("rvc_config")
        ):
            rvc_config = RVCConfigProvider()
            await rvc_config.initialize()
            self._set_root_constructed_service("rvc_config", rvc_config)

        if (
            "database_manager" not in self._constructed_services
            and self.compat_registry.has_service_definition("database_manager")
        ):
            database_manager = DatabaseManager(
                performance_monitor=self.get_service("performance_monitor")
            )
            if not await database_manager.initialize():
                msg = "Failed to initialize database manager"
                raise RuntimeError(msg)
            self._set_root_constructed_service("database_manager", database_manager)

        if (
            "edge_proxy_monitor" not in self._constructed_services
            and self.compat_registry.has_service_definition("edge_proxy_monitor")
        ):
            self._set_root_constructed_service("edge_proxy_monitor", EdgeProxyMonitorService())

    async def _construct_repository_substrate_services(self) -> None:
        """Construct A0 repository substrate with typed constructors."""
        if all(
            name in self._constructed_services for name in self._REPOSITORY_SUBSTRATE_SERVICE_ORDER
        ):
            return

        from backend.repositories import (
            CANTrackingRepository,
            DiagnosticsRepository,
            RVCConfigRepository,
            SystemStateRepository,
        )
        from backend.repositories.analytics_repository import AnalyticsRepository
        from backend.repositories.auth_repository import (
            AuthEventRepository,
            CredentialRepository,
            MfaRepository,
            SessionRepository,
        )
        from backend.repositories.database_repository import (
            DatabaseSessionRepository,
            MigrationRepository,
        )
        from backend.repositories.database_update_repository import (
            DatabaseBackupRepository,
            DatabaseConnectionRepository,
            DatabaseMigrationRepository,
            MigrationHistoryRepository,
            SafetyRepository,
        )
        from backend.repositories.entity_repository import (
            CanCommandRepository,
            EntityConfigRepository,
            EntityHistoryRepository,
            EntityStateRepository,
        )
        from backend.repositories.persistence_repository import PersistenceRepository
        from backend.repositories.security_audit_repository import SecurityAuditRepository
        from backend.repositories.security_config_repository import SecurityConfigRepository
        from backend.repositories.security_event_repository import (
            SecurityEventRepository,
            SecurityListenerRepository,
        )
        from backend.services.auth.tokens import TokenService
        from backend.services.entities.entity_manager_service import EntityManagerService

        database_manager = self.get_service("database_manager")
        performance_monitor = self.get_service("performance_monitor")
        settings = self.get_service("app_settings")

        repository_factories = {
            "rvc_config_repository": lambda: RVCConfigRepository(),
            "system_state_repository": lambda: SystemStateRepository(),
            "can_tracking_repository": lambda: CANTrackingRepository(),
            "diagnostics_repository": lambda: DiagnosticsRepository(),
            "database_session_repository": lambda: DatabaseSessionRepository(
                database_manager, performance_monitor
            ),
            "migration_repository": lambda: MigrationRepository(
                database_manager, performance_monitor
            ),
            "database_backup_repository": lambda: DatabaseBackupRepository(
                database_manager.get_session
            ),
            "database_connection_repository": lambda: DatabaseConnectionRepository(
                database_manager.get_session,
                settings.database.get_database_url(),
                settings.database.get_database_path(),
            ),
            "database_migration_repository": lambda: DatabaseMigrationRepository(
                database_manager.get_session, None
            ),
            "migration_history_repository": lambda: MigrationHistoryRepository(
                database_manager.get_session
            ),
            "safety_repository": lambda: SafetyRepository(database_manager.get_session),
            "analytics_repository": lambda: AnalyticsRepository(
                database_manager, performance_monitor
            ),
            "auth_event_repository": lambda: AuthEventRepository(
                database_manager, performance_monitor
            ),
            "can_command_repository": lambda: CanCommandRepository(
                database_manager, performance_monitor
            ),
            "credential_repository": lambda: CredentialRepository(
                database_manager, performance_monitor
            ),
            "entity_config_repository": lambda: EntityConfigRepository(
                database_manager, performance_monitor
            ),
            "entity_history_repository": lambda: EntityHistoryRepository(
                database_manager, performance_monitor
            ),
            "entity_manager_service": lambda: EntityManagerService(
                database_manager=database_manager,
                rvc_config_provider=self.get_service("rvc_config"),
                config={},
            ),
            "entity_state_repository": lambda: EntityStateRepository(
                database_manager, performance_monitor
            ),
            "mfa_repository": lambda: MfaRepository(database_manager, performance_monitor),
            "persistence_repository": lambda: PersistenceRepository(
                database_manager=database_manager,
                performance_monitor=performance_monitor,
                data_dir=settings.data_dir,
            ),
            "security_audit_repository": lambda: SecurityAuditRepository(
                database_manager, performance_monitor
            ),
            "security_config_repository": lambda: SecurityConfigRepository(
                database_manager, performance_monitor
            ),
            "security_event_repository": lambda: SecurityEventRepository(
                database_manager, performance_monitor
            ),
            "security_listener_repository": lambda: SecurityListenerRepository(
                database_manager, performance_monitor
            ),
            "session_repository": lambda: SessionRepository(database_manager, performance_monitor),
            "token_service": lambda: TokenService(
                jwt_secret=settings.auth.secret_key,
                jwt_algorithm=settings.auth.jwt_algorithm,
                access_token_expire_minutes=settings.auth.jwt_expire_minutes,
                magic_link_expire_minutes=settings.auth.magic_link_expire_minutes,
            ),
        }

        for service_name, factory in repository_factories.items():
            if (
                service_name not in self._constructed_services
                and self.compat_registry.has_service_definition(service_name)
            ):
                self._set_root_constructed_service(service_name, factory())

    async def _construct_facade_services(self) -> None:
        """Construct A1 persistence/config facades with typed constructors."""
        if (
            "rvc_config_facade" not in self._constructed_services
            and self.compat_registry.has_service_definition("rvc_config_facade")
        ):
            rvc_config_facade = RVCConfigFacade(self.get_service("rvc_config_repository"))
            self._set_root_constructed_service("rvc_config_facade", rvc_config_facade)

        if (
            "persistence_service" not in self._constructed_services
            and self.compat_registry.has_service_definition("persistence_service")
        ):
            persistence_service = PersistenceService(
                persistence_repository=self.get_service("persistence_repository"),
                performance_monitor=self.get_service("performance_monitor"),
            )
            await persistence_service.initialize()
            self._set_root_constructed_service("persistence_service", persistence_service)

    async def _construct_a2_services(self) -> None:  # noqa: C901
        """Construct A2 protocol/facade/database services with typed constructors."""
        from backend.services.database.database_engine import DatabaseEngine
        from backend.services.database.database_services import (
            DatabaseConnectionService,
            DatabaseMigrationService,
            DatabaseSessionService,
        )
        from backend.services.database.database_update_service import DatabaseUpdateService
        from backend.services.database.migration_safety_validator import MigrationSafetyValidator
        from backend.services.discovery.device_discovery_service import DeviceDiscoveryService
        from backend.services.protocols.protocol_manager import ProtocolManager
        from backend.services.rvc.rvc_service import RVCService

        performance_monitor = self.get_service("performance_monitor")

        if self._should_construct("database_connection_service"):
            self._set_root_constructed_service(
                "database_connection_service",
                DatabaseConnectionService(
                    database_engine=DatabaseEngine(self.get_service("app_settings")),
                    connection_repository=self.get_service("database_connection_repository"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("database_session_service"):
            self._set_root_constructed_service(
                "database_session_service",
                DatabaseSessionService(
                    database_engine=DatabaseEngine(self.get_service("app_settings")),
                    session_repository=self.get_service("database_session_repository"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("database_migration_service"):
            self._set_root_constructed_service(
                "database_migration_service",
                DatabaseMigrationService(
                    database_engine=DatabaseEngine(self.get_service("app_settings")),
                    migration_repository=self.get_service("migration_repository"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("migration_safety_validator"):
            migration_safety_validator = MigrationSafetyValidator(
                safety_repository=self.get_service("safety_repository"),
                connection_repository=self.get_service("database_connection_repository"),
                performance_monitor=performance_monitor,
            )
            await migration_safety_validator.initialize()
            self._set_root_constructed_service(
                "migration_safety_validator", migration_safety_validator
            )

        if self._should_construct("database_update_service"):
            database_update_service = DatabaseUpdateService(
                connection_repository=self.get_service("database_connection_repository"),
                migration_repository=self.get_service("database_migration_repository"),
                safety_validator=self.get_service("migration_safety_validator"),
                backup_repository=self.get_service("database_backup_repository"),
                history_repository=self.get_service("migration_history_repository"),
                websocket_repository=None,
                performance_monitor=performance_monitor,
                backup_dir=self.get_service("app_settings").persistence.get_backup_dir(),
            )
            await database_update_service.initialize()
            self._set_root_constructed_service("database_update_service", database_update_service)

        if self._should_construct("protocol_manager"):
            protocol_manager = ProtocolManager()
            await protocol_manager.start()
            self._set_root_constructed_service("protocol_manager", protocol_manager)

        if self._should_construct("rvc_service"):
            rvc_service = RVCService(
                rvc_config_repository=self.get_service("rvc_config_repository"),
                can_tracking_repository=self.get_service("can_tracking_repository"),
            )
            await rvc_service.start()
            self._set_root_constructed_service("rvc_service", rvc_service)

        # Preserve resolver behavior: device discovery's optional can_facade edge is None
        # until can_facade is constructed later in the same cluster.
        if self._should_construct("device_discovery_service"):
            self._set_root_constructed_service(
                "device_discovery_service",
                DeviceDiscoveryService(can_facade=None, config=self.get_service("rvc_config")),
            )

        if self.compat_registry.has_service_definition("can_facade"):
            await self._construct_lower_can_services()

        if self._should_construct("can_facade"):
            from backend.services.can.can_facade import CANFacade

            self._set_root_constructed_service(
                "can_facade",
                CANFacade(
                    bus_service=self.get_service("can_bus_service"),
                    injector=self.get_service("can_message_injector"),
                    message_filter=self.get_service("can_message_filter"),
                    recorder=self.get_service("can_bus_recorder"),
                    analyzer=self.get_service("can_protocol_analyzer"),
                    anomaly_detector=self.get_service("can_anomaly_detector"),
                    interface_service=self.get_service("can_interface_service"),
                    performance_monitor=performance_monitor,
                ),
            )

    async def _construct_a3_services(self) -> None:  # noqa: C901
        """Construct A3 auth/security/guardrail services with typed constructors."""
        from backend.services.auth.attempt_tracker_service import AttemptTrackerService
        from backend.services.auth.lockout import LockoutService
        from backend.services.auth.mfa import MfaService
        from backend.services.auth.pin_manager import PINConfig, PINManager
        from backend.services.auth.service import AuthService
        from backend.services.auth.sessions import SessionService
        from backend.services.guardrails.command_guardrail_service import CommandGuardrailService
        from backend.services.security.security_audit_service import (
            RateLimitConfig,
            SecurityAuditService,
        )
        from backend.services.security.security_config_service import SecurityConfigService
        from backend.services.security.security_event_manager import SecurityEventManager
        from backend.services.security.security_event_service import SecurityEventService

        performance_monitor = self.get_service("performance_monitor")

        if self._should_construct("security_event_service"):
            self._set_root_constructed_service(
                "security_event_service",
                SecurityEventService(
                    event_repository=self.get_service("security_event_repository"),
                    listener_repository=self.get_service("security_listener_repository"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("attempt_tracker_service"):
            self._set_root_constructed_service(
                "attempt_tracker_service",
                AttemptTrackerService(
                    auth_event_repository=self.get_service("auth_event_repository"),
                    security_audit_repository=self.get_service("security_audit_repository"),
                    performance_monitor=performance_monitor,
                    security_event_service=self.get_service("security_event_service"),
                ),
            )

        if self._should_construct("mfa_service"):
            self._set_root_constructed_service(
                "mfa_service",
                MfaService(
                    mfa_repository=self.get_service("mfa_repository"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("session_service"):
            self._set_root_constructed_service(
                "session_service",
                SessionService(
                    session_repository=self.get_service("session_repository"),
                    token_service=self.get_service("token_service"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("security_config_service"):
            self._set_root_constructed_service(
                "security_config_service",
                SecurityConfigService(
                    self.get_service("security_config_repository"), performance_monitor
                ),
            )

        if self._should_construct("lockout_service"):
            auth_config = await self.get_service("security_config_service").get_auth_config()
            self._set_root_constructed_service(
                "lockout_service",
                LockoutService(
                    auth_event_repository=self.get_service("auth_event_repository"),
                    performance_monitor=performance_monitor,
                    max_failed_attempts=auth_config.get("max_login_attempts", 5),
                    lockout_window_minutes=auth_config.get("login_attempt_window_minutes", 15),
                    lockout_duration_minutes=auth_config.get("login_lockout_minutes", 30),
                    attempt_tracker_service=self.get_service("attempt_tracker_service"),
                ),
            )

        if self._should_construct("pin_manager"):
            pin_config = PINConfig(
                **await self.get_service("security_config_service").get_pin_config()
            )
            self._set_root_constructed_service("pin_manager", PINManager(pin_config))

        if self._should_construct("security_audit_service"):
            rate_limit_config = RateLimitConfig(
                **await self.get_service("security_config_service").get_rate_limit_config()
            )
            self._set_root_constructed_service(
                "security_audit_service",
                SecurityAuditService(
                    security_audit_repository=self.get_service("security_audit_repository"),
                    performance_monitor=performance_monitor,
                    config=rate_limit_config,
                ),
            )

        if self._should_construct("auth_manager"):
            from backend.services.auth.repository import AuthRepository

            auth_service = AuthService(
                credential_repository=self.get_service("credential_repository"),
                session_repository=self.get_service("session_repository"),
                auth_event_repository=self.get_service("auth_event_repository"),
                mfa_repository=self.get_service("mfa_repository"),
                notification_service=None,
                performance_monitor=performance_monitor,
                auth_repository=AuthRepository(self.get_service("database_manager")),
                token_service=self.get_service("token_service"),
                session_service=self.get_service("session_service"),
                mfa_service=self.get_service("mfa_service"),
                lockout_service=self.get_service("lockout_service"),
                auth_settings=self.get_service("app_settings").auth,
            )
            await auth_service.start()
            self._set_root_constructed_service("auth_manager", auth_service)

        if self._should_construct("security_event_manager"):
            self._set_root_constructed_service(
                "security_event_manager",
                SecurityEventManager(
                    security_event_service=self.get_service("security_event_service"),
                    attempt_tracker_service=self.get_service("attempt_tracker_service"),
                    security_config_service=self.get_service("security_config_service"),
                    security_audit_service=self.get_service("security_audit_service"),
                    auth_manager=self.get_service("auth_manager"),
                    pin_manager=self.get_service("pin_manager"),
                    lockout_service=self.get_service("lockout_service"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("command_guardrail_service"):
            command_guardrail_service = CommandGuardrailService(
                service_registry=self.guardrail_coordinator,
                health_check_interval=5.0,
                watchdog_timeout=15.0,
                pin_manager=self.get_service("pin_manager"),
                security_audit_service=self.get_service("security_audit_service"),
            )
            await command_guardrail_service.start_monitoring()
            self._set_root_constructed_service(
                "command_guardrail_service", command_guardrail_service
            )

    async def _construct_a4_services(self) -> None:
        """Construct A4 websocket/entity/dashboard services with typed constructors."""
        from backend.services.analytics.analytics_dashboard_service import (
            AnalyticsDashboardService,
        )
        from backend.services.entities.entity_domain_service import EntityDomainService
        from backend.services.entities.entity_initialization_service import (
            EntityInitializationService,
        )
        from backend.services.entities.entity_service import EntityService
        from backend.services.system.dashboard_service import DashboardService
        performance_monitor = self.get_service("performance_monitor")

        await self._construct_websocket_manager()

        if self._should_construct("analytics_dashboard_service"):
            self._set_root_constructed_service(
                "analytics_dashboard_service",
                AnalyticsDashboardService(
                    performance_monitor=performance_monitor,
                    database_manager=self.get_service("database_manager"),
                    analytics_repository=self.get_service("analytics_repository"),
                ),
            )

        if self._should_construct("dashboard_service"):
            self._set_root_constructed_service(
                "dashboard_service",
                DashboardService(
                    dashboard_repository=None,
                    entity_repository=self.get_service("entity_state_repository"),
                    performance_monitor=performance_monitor,
                    websocket_manager=self.get_service("websocket_manager"),
                ),
            )

        if self._should_construct("entity_initialization_service"):
            self._set_root_constructed_service(
                "entity_initialization_service",
                EntityInitializationService(
                    entity_state_repository=self.get_service("entity_state_repository"),
                    rvc_config_repository=self.get_service("rvc_config_repository"),
                    entity_manager=self.get_service("entity_manager_service").get_entity_manager(),
                ),
            )

        if self._should_construct("entity_service"):
            self._set_root_constructed_service(
                "entity_service",
                EntityService(
                    websocket_manager=self.get_service("websocket_manager"),
                    entity_state_repository=self.get_service("entity_state_repository"),
                    rvc_config_repository=self.get_service("rvc_config_repository"),
                    diagnostics_repository=self.get_service("diagnostics_repository"),
                ),
            )

        if self._should_construct("entity_domain_service"):
            self._set_root_constructed_service(
                "entity_domain_service",
                EntityDomainService(
                    config_service=self.get_service("rvc_config_facade"),
                    auth_manager=self.get_service("auth_manager"),
                    entity_service=self.get_service("entity_service"),
                    websocket_manager=self.get_service("websocket_manager"),
                    entity_manager=self.get_service("entity_manager_service"),
                ),
            )

    async def _construct_lower_can_services(self) -> None:  # noqa: C901
        """Construct lower-CAN prerequisites before CANFacade."""
        from backend.integrations.can.anomaly_detector import CANAnomalyDetector
        from backend.integrations.can.can_bus_recorder import CANBusRecorder
        from backend.integrations.can.message_filter import MessageFilter
        from backend.integrations.can.message_injector import CANMessageInjector, SafetyLevel
        from backend.integrations.can.protocol_analyzer import ProtocolAnalyzer
        from backend.integrations.diagnostics.handler import DiagnosticHandler
        from backend.services.can.can_bus_service import CANBusService
        from backend.services.can.can_interface_service import CANInterfaceService
        from backend.services.can.can_network_telemetry_service import CANNetworkTelemetryService

        if self._should_construct("can_anomaly_detector"):
            self._set_root_constructed_service("can_anomaly_detector", CANAnomalyDetector())

        if self._should_construct("diagnostic_handler"):
            diagnostic_handler = DiagnosticHandler(self.get_service("app_settings"))
            await diagnostic_handler.startup()
            self._set_root_constructed_service("diagnostic_handler", diagnostic_handler)

        if self._should_construct("can_interface_service"):
            self._set_root_constructed_service("can_interface_service", CANInterfaceService())

        if self._should_construct("can_message_injector"):

            async def audit_injection(request: Any, result: Any) -> None:
                security_audit = self.get_optional_service("security_audit_service")
                if security_audit and hasattr(security_audit, "log_injection"):
                    await security_audit.log_injection(request, result)

            self._set_root_constructed_service(
                "can_message_injector",
                CANMessageInjector(
                    safety_level=SafetyLevel.MODERATE, audit_callback=audit_injection
                ),
            )

        if self._should_construct("can_message_filter"):

            async def alert_callback(alert_data: Any) -> None:
                websocket_manager = self.get_optional_service("websocket_manager")
                if websocket_manager:
                    await websocket_manager.broadcast_can_filter_update("filter_alert", alert_data)

            self._set_root_constructed_service(
                "can_message_filter",
                MessageFilter(
                    max_rules=100,
                    alert_callback=alert_callback,
                    capture_buffer_size=10000,
                ),
            )

        if self._should_construct("can_bus_recorder"):
            recorder = CANBusRecorder(
                buffer_size=100000,
                storage_path=self.get_service("app_settings").get_can_recorder_storage_path(),
                auto_save_interval=60.0,
                max_file_size_mb=100.0,
            )
            self._set_root_constructed_service("can_bus_recorder", recorder)

        if self._should_construct("can_protocol_analyzer"):
            self._set_root_constructed_service(
                "can_protocol_analyzer",
                ProtocolAnalyzer(buffer_size=10000, pattern_window_ms=5000.0),
            )

        if self._should_construct("can_network_telemetry_service"):
            self._set_root_constructed_service(
                "can_network_telemetry_service",
                CANNetworkTelemetryService(
                    can_interface_service=self.get_service("can_interface_service")
                ),
            )

        await self._construct_websocket_manager()

        if self._should_construct("can_bus_service"):
            can_bus_service = CANBusService(
                can_tracking_repository=self.get_service("can_tracking_repository"),
                system_state_repository=self.get_service("system_state_repository"),
                can_anomaly_detector=self.get_service("can_anomaly_detector"),
                diagnostic_handler=self.get_service("diagnostic_handler"),
                can_bus_recorder=self.get_optional_service("can_bus_recorder"),
                can_protocol_analyzer=self.get_optional_service("can_protocol_analyzer"),
                can_message_filter=self.get_optional_service("can_message_filter"),
                device_discovery_service=self.get_optional_service("device_discovery_service"),
                entity_manager_service=self.get_optional_service("entity_manager_service"),
                websocket_manager=self.get_optional_service("websocket_manager"),
            )
            await can_bus_service.start()
            self._set_root_constructed_service("can_bus_service", can_bus_service)

    async def _construct_websocket_manager(self) -> None:
        """Construct the websocket manager once its optional CAN tools are available."""
        from backend.services.system.websocket_service import WebSocketService

        if self._should_construct("websocket_manager"):
            websocket_manager = WebSocketService(
                can_tracking_repository=self.get_service("can_tracking_repository"),
                system_state_repository=self.get_service("system_state_repository"),
                can_bus_recorder=self.get_optional_service("can_bus_recorder"),
                can_protocol_analyzer=self.get_optional_service("can_protocol_analyzer"),
                can_message_filter=self.get_optional_service("can_message_filter"),
            )
            await websocket_manager.start()
            self._set_root_constructed_service("websocket_manager", websocket_manager)

    def _set_root_constructed_service(self, service_name: str, service: Any) -> None:
        """Store a root-constructed service and mirror it for compatibility startup."""
        self.set_constructed_service(service_name, service)
        self._replace_compat_init_func(service_name, service)
        self._mirror_guardrail_service(service_name, service)

    def _should_construct(self, service_name: str) -> bool:
        """Return whether a service should be constructed for the current graph."""
        return (
            service_name not in self._constructed_services
            and self.compat_registry.has_service_definition(service_name)
        )

    def _replace_compat_init_func(self, service_name: str, service: Any) -> None:
        """Make the compatibility registry return a root-constructed service."""
        self.compat_registry.provide_service_instance(service_name, service)

    def _mirror_guardrail_service(self, service_name: str, service: Any) -> None:
        """Mirror guardrail metadata into the guardrail-only coordinator."""
        guardrail_tiers = self.compat_registry._guardrail_tiers  # noqa: SLF001
        if service_name not in guardrail_tiers:
            return

        self.guardrail_coordinator.register_guardrail_service(
            service_name=service_name,
            service=service,
            tier=guardrail_tiers[service_name],
            command_halt_participant=(
                service_name in self.compat_registry.get_command_halt_targets()
            ),
            metadata=self.compat_registry.get_guardrail_metadata(service_name),
        )
        if service_name == "command_guardrail_service":
            service.service_registry = self.guardrail_coordinator

    def _mirror_remaining_guardrail_services(self) -> None:
        """Mirror guardrail services outside the normal construction order."""
        for service_name in self.compat_registry.list_guardrail_services():
            if service_name in self._constructed_services:
                continue
            if not self.compat_registry.has_service(service_name):
                continue
            service = self.compat_registry.get_service(service_name)
            self.set_constructed_service(service_name, service)
            self._mirror_guardrail_service(service_name, service)

    def _apply_constructed_service_handle(self, service_name: str, service: Any) -> None:
        """Update typed handles for services that have migrated to root construction."""
        if service_name == "app_settings":
            self.services.settings = service
        elif service_name == "rvc_config":
            self.services.rvc_config = service
        elif service_name == "performance_monitor":
            self.services.performance_monitor = service
        elif service_name == "persistence_service":
            self.services.persistence_service = service
        elif service_name == "database_manager":
            self.services.database_manager = service
        elif service_name == "rvc_config_facade":
            self.services.rvc_config_facade = service
        elif hasattr(self.services, service_name):
            setattr(self.services, service_name, service)
