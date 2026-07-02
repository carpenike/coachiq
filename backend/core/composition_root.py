"""Typed composition root for backend service construction."""

import logging
import time
from dataclasses import dataclass
from typing import Any, cast

from backend.core.config import Settings
from backend.core.config_provider import RVCConfigProvider
from backend.core.guardrail_interfaces import GuardrailTier
from backend.core.guardrail_runtime_coordinator import GuardrailRuntimeCoordinator
from backend.core.performance import PerformanceMonitor
from backend.core.service_status import ServiceStatus
from backend.services.database.database_manager import DatabaseManager
from backend.services.persistence.persistence_service import PersistenceService
from backend.services.rvc.rvc_config_facade import RVCConfigFacade
from backend.services.updates.edge_proxy_monitor_service import EdgeProxyMonitorService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GuardrailServiceMetadata:
    """Root-owned guardrail metadata for a service."""

    tier: GuardrailTier
    command_halt_participant: bool
    description: str
    tags: frozenset[str] = frozenset()


ROOT_GUARDRAIL_METADATA: dict[str, GuardrailServiceMetadata] = {
    "command_guardrail_service": GuardrailServiceMetadata(
        tier=GuardrailTier.CRITICAL,
        command_halt_participant=False,
        description=(
            "API command-validation guardrails and emergency stop on the "
            "orchestration loop (see ADR-0004)"
        ),
        tags=frozenset({"service", "guardrail", "critical", "api-guardrail"}),
    ),
    "websocket_manager": GuardrailServiceMetadata(
        tier=GuardrailTier.OPERATIONAL,
        command_halt_participant=False,
        description="WebSocket connection management service",
        tags=frozenset({"service", "websocket", "realtime"}),
    ),
    "auth_manager": GuardrailServiceMetadata(
        tier=GuardrailTier.CRITICAL,
        command_halt_participant=False,
        description="Authentication service with JWT, magic links, and MFA",
        tags=frozenset({"service", "auth", "security"}),
    ),
    "can_bus_service": GuardrailServiceMetadata(
        tier=GuardrailTier.CRITICAL,
        command_halt_participant=False,
        description="CAN bus integration service for message processing",
        tags=frozenset({"service", "can", "hardware", "realtime"}),
    ),
    "can_message_injector": GuardrailServiceMetadata(
        tier=GuardrailTier.CRITICAL,
        command_halt_participant=False,
        description="Safe CAN message injection service for testing and diagnostics",
        tags=frozenset({"service", "can", "testing", "diagnostics", "safety-critical"}),
    ),
    "can_message_filter": GuardrailServiceMetadata(
        tier=GuardrailTier.OPERATIONAL,
        command_halt_participant=False,
        description="CAN message filtering system with real-time monitoring and alerting",
        tags=frozenset({"service", "can", "filtering", "monitoring", "safety"}),
    ),
    "can_bus_recorder": GuardrailServiceMetadata(
        tier=GuardrailTier.OPERATIONAL,
        command_halt_participant=False,
        description="CAN bus traffic recorder with replay capabilities",
        tags=frozenset({"service", "can", "recording", "replay", "diagnostics"}),
    ),
    "can_protocol_analyzer": GuardrailServiceMetadata(
        tier=GuardrailTier.OPERATIONAL,
        command_halt_participant=False,
        description="CAN protocol analyzer for deep packet inspection and protocol detection",
        tags=frozenset({"service", "can", "analysis", "protocol", "diagnostics"}),
    ),
    "can_facade": GuardrailServiceMetadata(
        tier=GuardrailTier.CRITICAL,
        command_halt_participant=True,
        description="Unified facade for all CAN operations with safety coordination",
        tags=frozenset({"facade", "can", "safety-critical", "coordination"}),
    ),
}


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
    oidc_client: Any = None
    oidc_state_store: Any = None
    oidc_session_code_store: Any = None
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
        "oidc_client",
        "oidc_state_store",
        "oidc_session_code_store",
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
        "can_facade",
        "can_network_telemetry_service",
        "entity_initialization_service",
        "entity_service",
        "entity_domain_service",
    )

    def __init__(self, service_catalog: set[str] | None = None) -> None:
        self.guardrail_coordinator = GuardrailRuntimeCoordinator()
        self._constructed_services: dict[str, Any] = {}
        self._constructing_services: set[str] = set()
        self._service_catalog = service_catalog or set(self._root_service_order)
        self._service_status: dict[str, ServiceStatus] = {}
        self._service_timings: dict[str, float] = {}
        self._service_start_times: dict[str, float] = {}
        self._startup_errors: dict[str, Exception] = {}
        self._startup_time: float = 0.0
        self._startup_started_at: float | None = None
        self._current_constructing_service: str | None = None
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
    def _root_service_order(self) -> tuple[str, ...]:
        """Return the root-owned service construction catalog."""
        return (
            *self._FOUNDATION_SERVICE_ORDER,
            *self._REPOSITORY_SUBSTRATE_SERVICE_ORDER,
            *self._FACADE_SERVICE_ORDER,
            *self._A2_SERVICE_ORDER,
            *self._A3_SERVICE_ORDER,
            *self._A4_SERVICE_ORDER,
        )

    async def startup(self) -> None:
        """Start all services and capture typed handles for migrated clusters."""
        self._startup_started_at = time.perf_counter()
        try:
            await self._construct_foundation_services()
            await self._construct_repository_substrate_services()
            await self._construct_facade_services()
            await self._construct_a2_services()
            await self._construct_a3_services()
            await self._construct_a4_services()
            self._startup_time = (time.perf_counter() - self._startup_started_at) * 1000
            self._started = True
        except Exception as exc:
            service_name = self._current_constructing_service or "unknown"
            self._startup_errors[service_name] = exc
            self._service_status[service_name] = ServiceStatus.FAILED
            impacted = self._get_impacted_services(service_name)
            error_lines = ["Service startup failures:", f"  • {service_name}: {exc}"]
            if impacted:
                error_lines.append(f"    Impacted services: {', '.join(impacted)}")
            logger.error("\n".join(error_lines))
            await self.shutdown()
            raise RuntimeError("\n".join(error_lines)) from exc

    async def shutdown(self) -> None:
        """Shut down services in composition-root order."""
        if not self._started:
            return

        for service_name in reversed(self._root_service_order):
            service = self._constructed_services.get(service_name)
            if service is None:
                continue
            try:
                await self._teardown_service(service_name, service)
                self._service_status[service_name] = ServiceStatus.STOPPED
            except Exception:
                self._service_status[service_name] = ServiceStatus.FAILED
                logger.exception("Error shutting down service %s", service_name)
        self._started = False

    def set_constructed_service(self, service_name: str, service: Any) -> None:
        """Store a root-constructed service without registry capture."""
        self._constructed_services[service_name] = service
        start_time = self._service_start_times.pop(service_name, None)
        self._service_timings[service_name] = (
            (time.perf_counter() - start_time) * 1000 if start_time is not None else 0.0
        )
        self._service_status[service_name] = ServiceStatus.HEALTHY
        self._apply_constructed_service_handle(service_name, service)
        self._mirror_guardrail_service(service_name, service)

    def has_service(self, service_name: str) -> bool:
        """Return whether a service is available."""
        return service_name in self._constructed_services

    def require_service(self, service_name: str) -> Any:
        """Return a root-constructed service by name."""
        if service_name in self._constructed_services:
            return self._constructed_services[service_name]
        msg = f"Service '{service_name}' not available"
        raise RuntimeError(msg)

    def get_optional_service(self, service_name: str) -> Any | None:
        """Return a service by name, or None if it is unavailable."""
        if not self.has_service(service_name):
            return None
        return self.require_service(service_name)

    def list_services(self) -> list[str]:
        """Return root-constructed service names."""
        return sorted(self._constructed_services)

    def get_service_status(self, service_name: str) -> ServiceStatus:
        """Return the cached lifecycle status for one service."""
        return self._service_status.get(service_name, ServiceStatus.PENDING)

    def get_service_count_by_status(self) -> dict[ServiceStatus, int]:
        """Return service counts by cached lifecycle status."""
        counts: dict[ServiceStatus, int] = {}
        for status in self._service_status.values():
            counts[status] = counts.get(status, 0) + 1
        return counts

    def get_service_timings(self) -> dict[str, float]:
        """Return per-service startup timings in milliseconds."""
        return self._service_timings.copy()

    def get_startup_metrics(self) -> dict[str, Any]:
        """Return root-owned startup metrics."""
        total_time = self._startup_time or sum(self._service_timings.values())
        service_count = len(self._service_timings)
        return {
            "total_startup_time_ms": total_time,
            "service_count": service_count,
            "average_service_time_ms": total_time / service_count if service_count else 0.0,
            "slowest_services": sorted(
                self._service_timings.items(), key=lambda item: item[1], reverse=True
            )[:5],
            "service_timings": self._service_timings.copy(),
            "startup_errors": {
                service_name: str(error) for service_name, error in self._startup_errors.items()
            },
        }

    async def get_health_status(self) -> dict[str, ServiceStatus]:
        """Return health status for all root-owned services."""
        return {
            service_name: await self.check_service_health(service_name)
            for service_name in self._constructed_services
        }

    async def check_service_health(self, service_name: str) -> ServiceStatus:
        """Check one root-owned service health."""
        service = self._constructed_services.get(service_name)
        if service is None:
            return ServiceStatus.PENDING
        if hasattr(service, "get_health_status"):
            try:
                health = service.get_health_status()
                if hasattr(health, "__await__"):
                    health = await health
                if isinstance(health, dict) and health.get("healthy") is False:
                    return ServiceStatus.DEGRADED
            except Exception:
                return ServiceStatus.DEGRADED
        return self._service_status.get(service_name, ServiceStatus.HEALTHY)

    async def check_system_health(self) -> dict[str, Any]:
        """Return aggregate health status for root-owned services."""
        service_status = await self.get_health_status()
        failed = [name for name, status in service_status.items() if status == ServiceStatus.FAILED]
        degraded = [
            name for name, status in service_status.items() if status == ServiceStatus.DEGRADED
        ]
        if failed:
            overall = "failed"
        elif degraded:
            overall = "degraded"
        else:
            overall = "healthy"
        return {
            "status": overall,
            "services": {name: status.value for name, status in service_status.items()},
            "failed": failed,
            "degraded": degraded,
        }

    def get_health_summary(self) -> dict[str, dict[str, str]]:
        """Return a synchronous health summary for guardrail monitoring."""
        return {
            service_name: {"status": status.name}
            for service_name, status in self._service_status.items()
        }

    async def _construct_foundation_services(self) -> None:
        """Construct A0 foundation services with typed constructors."""
        if self._should_construct("app_settings"):
            self._set_root_constructed_service("app_settings", Settings())

        if self._should_construct("performance_monitor"):
            self._set_root_constructed_service("performance_monitor", PerformanceMonitor())

        if self._should_construct("rvc_config"):
            rvc_config = RVCConfigProvider()
            await rvc_config.initialize()
            self._set_root_constructed_service("rvc_config", rvc_config)

        if self._should_construct("database_manager"):
            database_manager = DatabaseManager(
                performance_monitor=self.require_service("performance_monitor")
            )
            if not await database_manager.initialize():
                msg = "Failed to initialize database manager"
                raise RuntimeError(msg)
            self._set_root_constructed_service("database_manager", database_manager)

        if self._should_construct("edge_proxy_monitor"):
            self._set_root_constructed_service("edge_proxy_monitor", EdgeProxyMonitorService())

    async def _construct_repository_substrate_services(self) -> None:
        """Construct A0 repository substrate with typed constructors."""
        if not any(
            self._should_construct(name) for name in self._REPOSITORY_SUBSTRATE_SERVICE_ORDER
        ):
            return
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
            EntityRuntimeStateRepository,
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

        database_manager = self.require_service("database_manager")
        performance_monitor = self.require_service("performance_monitor")
        settings = self.require_service("app_settings")

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
                rvc_config_provider=self.require_service("rvc_config"),
                config={},
            ),
            "entity_state_repository": lambda: EntityRuntimeStateRepository(
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
            if self._should_construct(service_name):
                self._set_root_constructed_service(service_name, factory())

    async def _construct_facade_services(self) -> None:
        """Construct A1 persistence/config facades with typed constructors."""
        if self._should_construct("rvc_config_facade"):
            rvc_config_facade = RVCConfigFacade(self.require_service("rvc_config_repository"))
            self._set_root_constructed_service("rvc_config_facade", rvc_config_facade)

        if self._should_construct("persistence_service"):
            persistence_service = PersistenceService(
                persistence_repository=self.require_service("persistence_repository"),
                performance_monitor=self.require_service("performance_monitor"),
            )
            await persistence_service.initialize()
            self._set_root_constructed_service("persistence_service", persistence_service)

    async def _construct_a2_services(self) -> None:  # noqa: C901
        """Construct A2 protocol/facade/database services with typed constructors."""
        if not any(self._should_construct(name) for name in self._A2_SERVICE_ORDER):
            return
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

        performance_monitor = self.require_service("performance_monitor")

        if self._should_construct("database_connection_service"):
            self._set_root_constructed_service(
                "database_connection_service",
                DatabaseConnectionService(
                    database_engine=DatabaseEngine(self.require_service("app_settings")),
                    connection_repository=self.require_service("database_connection_repository"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("database_session_service"):
            self._set_root_constructed_service(
                "database_session_service",
                DatabaseSessionService(
                    database_engine=DatabaseEngine(self.require_service("app_settings")),
                    session_repository=self.require_service("database_session_repository"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("database_migration_service"):
            self._set_root_constructed_service(
                "database_migration_service",
                DatabaseMigrationService(
                    database_engine=DatabaseEngine(self.require_service("app_settings")),
                    migration_repository=self.require_service("migration_repository"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("migration_safety_validator"):
            migration_safety_validator = MigrationSafetyValidator(
                safety_repository=self.require_service("safety_repository"),
                connection_repository=self.require_service("database_connection_repository"),
                performance_monitor=performance_monitor,
            )
            await migration_safety_validator.initialize()
            self._set_root_constructed_service(
                "migration_safety_validator", migration_safety_validator
            )

        if self._should_construct("database_update_service"):
            database_update_service = DatabaseUpdateService(
                connection_repository=self.require_service("database_connection_repository"),
                migration_repository=self.require_service("database_migration_repository"),
                safety_validator=self.require_service("migration_safety_validator"),
                backup_repository=self.require_service("database_backup_repository"),
                history_repository=self.require_service("migration_history_repository"),
                websocket_repository=None,
                performance_monitor=performance_monitor,
                backup_dir=self.require_service("app_settings").persistence.get_backup_dir(),
            )
            await database_update_service.initialize()
            self._set_root_constructed_service("database_update_service", database_update_service)

        if self._should_construct("protocol_manager"):
            protocol_manager = ProtocolManager()
            await protocol_manager.start()
            self._set_root_constructed_service("protocol_manager", protocol_manager)

        if self._should_construct("rvc_service"):
            rvc_service = RVCService(
                rvc_config_repository=self.require_service("rvc_config_repository"),
                can_tracking_repository=self.require_service("can_tracking_repository"),
            )
            await rvc_service.start()
            self._set_root_constructed_service("rvc_service", rvc_service)

        # Preserve resolver behavior: device discovery's optional can_facade edge is None
        # until can_facade is constructed later in the same cluster.
        if self._should_construct("device_discovery_service"):
            self._set_root_constructed_service(
                "device_discovery_service",
                DeviceDiscoveryService(can_facade=None, config=self.require_service("rvc_config")),
            )

        if "can_facade" in self._service_catalog:
            await self._construct_lower_can_services()

        if self._should_construct("can_facade"):
            from backend.services.can.can_facade import CANFacade

            self._set_root_constructed_service(
                "can_facade",
                CANFacade(
                    bus_service=self.require_service("can_bus_service"),
                    injector=self.require_service("can_message_injector"),
                    message_filter=self.require_service("can_message_filter"),
                    recorder=self.require_service("can_bus_recorder"),
                    analyzer=self.require_service("can_protocol_analyzer"),
                    anomaly_detector=self.require_service("can_anomaly_detector"),
                    interface_service=self.require_service("can_interface_service"),
                    performance_monitor=performance_monitor,
                ),
            )

    async def _construct_a3_services(self) -> None:  # noqa: C901
        """Construct A3 auth/security/guardrail services with typed constructors."""
        if not any(self._should_construct(name) for name in self._A3_SERVICE_ORDER):
            return
        from backend.services.auth.attempt_tracker_service import AttemptTrackerService
        from backend.services.auth.lockout import LockoutService
        from backend.services.auth.mfa import MfaService
        from backend.services.auth.oidc import OIDCClient, OIDCSessionCodeStore, OIDCStateStore
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

        performance_monitor = self.require_service("performance_monitor")

        if self._should_construct("security_event_service"):
            self._set_root_constructed_service(
                "security_event_service",
                SecurityEventService(
                    event_repository=self.require_service("security_event_repository"),
                    listener_repository=self.require_service("security_listener_repository"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("attempt_tracker_service"):
            self._set_root_constructed_service(
                "attempt_tracker_service",
                AttemptTrackerService(
                    auth_event_repository=self.require_service("auth_event_repository"),
                    security_audit_repository=self.require_service("security_audit_repository"),
                    performance_monitor=performance_monitor,
                    security_event_service=self.require_service("security_event_service"),
                ),
            )

        if self._should_construct("mfa_service"):
            self._set_root_constructed_service(
                "mfa_service",
                MfaService(
                    mfa_repository=self.require_service("mfa_repository"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("session_service"):
            self._set_root_constructed_service(
                "session_service",
                SessionService(
                    session_repository=self.require_service("session_repository"),
                    token_service=self.require_service("token_service"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("security_config_service"):
            self._set_root_constructed_service(
                "security_config_service",
                SecurityConfigService(
                    self.require_service("security_config_repository"), performance_monitor
                ),
            )

        if self._should_construct("lockout_service"):
            auth_config = await self.require_service("security_config_service").get_auth_config()
            self._set_root_constructed_service(
                "lockout_service",
                LockoutService(
                    auth_event_repository=self.require_service("auth_event_repository"),
                    performance_monitor=performance_monitor,
                    max_failed_attempts=auth_config.get("max_login_attempts", 5),
                    lockout_window_minutes=auth_config.get("login_attempt_window_minutes", 15),
                    lockout_duration_minutes=auth_config.get("login_lockout_minutes", 30),
                    attempt_tracker_service=self.require_service("attempt_tracker_service"),
                ),
            )

        if self._should_construct("pin_manager"):
            pin_config = PINConfig(
                **await self.require_service("security_config_service").get_pin_config()
            )
            self._set_root_constructed_service("pin_manager", PINManager(pin_config))

        if self._should_construct("security_audit_service"):
            rate_limit_config = RateLimitConfig(
                **await self.require_service("security_config_service").get_rate_limit_config()
            )
            self._set_root_constructed_service(
                "security_audit_service",
                SecurityAuditService(
                    security_audit_repository=self.require_service("security_audit_repository"),
                    performance_monitor=performance_monitor,
                    config=rate_limit_config,
                ),
            )

        auth_settings = self.require_service("app_settings").auth
        if self._should_construct("oidc_client"):
            self._set_root_constructed_service("oidc_client", OIDCClient(auth_settings))

        if self._should_construct("oidc_state_store"):
            self._set_root_constructed_service(
                "oidc_state_store", OIDCStateStore(auth_settings.oidc_state_ttl_seconds)
            )

        if self._should_construct("oidc_session_code_store"):
            self._set_root_constructed_service(
                "oidc_session_code_store",
                OIDCSessionCodeStore(auth_settings.oidc_session_code_ttl_seconds),
            )

        if self._should_construct("auth_manager"):
            from backend.services.auth.repository import AuthRepository

            auth_service = AuthService(
                credential_repository=self.require_service("credential_repository"),
                session_repository=self.require_service("session_repository"),
                auth_event_repository=self.require_service("auth_event_repository"),
                mfa_repository=self.require_service("mfa_repository"),
                notification_service=None,
                performance_monitor=performance_monitor,
                auth_repository=AuthRepository(self.require_service("database_manager")),
                token_service=self.require_service("token_service"),
                session_service=self.require_service("session_service"),
                mfa_service=self.require_service("mfa_service"),
                lockout_service=self.require_service("lockout_service"),
                auth_settings=auth_settings,
                oidc_client=self.require_service("oidc_client"),
                oidc_state_store=self.require_service("oidc_state_store"),
                oidc_session_code_store=self.require_service("oidc_session_code_store"),
            )
            await auth_service.start()
            self._set_root_constructed_service("auth_manager", auth_service)

        if self._should_construct("security_event_manager"):
            self._set_root_constructed_service(
                "security_event_manager",
                SecurityEventManager(
                    security_event_service=self.require_service("security_event_service"),
                    attempt_tracker_service=self.require_service("attempt_tracker_service"),
                    security_config_service=self.require_service("security_config_service"),
                    security_audit_service=self.require_service("security_audit_service"),
                    auth_manager=self.require_service("auth_manager"),
                    pin_manager=self.require_service("pin_manager"),
                    lockout_service=self.require_service("lockout_service"),
                    performance_monitor=performance_monitor,
                ),
            )

        if self._should_construct("command_guardrail_service"):
            command_guardrail_service = CommandGuardrailService(
                guardrail_coordinator=self.guardrail_coordinator,
                health_check_interval=5.0,
                watchdog_timeout=15.0,
                pin_manager=self.require_service("pin_manager"),
                security_audit_service=self.require_service("security_audit_service"),
            )
            await command_guardrail_service.start_monitoring()
            self._set_root_constructed_service(
                "command_guardrail_service", command_guardrail_service
            )

    async def _construct_a4_services(self) -> None:
        """Construct A4 websocket/entity/dashboard services with typed constructors."""
        if not any(self._should_construct(name) for name in self._A4_SERVICE_ORDER):
            return
        from backend.services.analytics.analytics_dashboard_service import (
            AnalyticsDashboardService,
        )
        from backend.services.entities.entity_domain_service import EntityDomainService
        from backend.services.entities.entity_initialization_service import (
            EntityInitializationService,
        )
        from backend.services.entities.entity_service import EntityService
        from backend.services.system.dashboard_service import DashboardService

        performance_monitor = self.require_service("performance_monitor")

        await self._construct_websocket_manager()

        if self._should_construct("analytics_dashboard_service"):
            self._set_root_constructed_service(
                "analytics_dashboard_service",
                AnalyticsDashboardService(
                    performance_monitor=performance_monitor,
                    database_manager=self.require_service("database_manager"),
                    analytics_repository=self.require_service("analytics_repository"),
                ),
            )

        if self._should_construct("dashboard_service"):
            self._set_root_constructed_service(
                "dashboard_service",
                DashboardService(
                    dashboard_repository=None,
                    entity_repository=self.require_service("entity_state_repository"),
                    performance_monitor=performance_monitor,
                    websocket_manager=self.require_service("websocket_manager"),
                ),
            )

        if self._should_construct("entity_initialization_service"):
            entity_initialization_service = EntityInitializationService(
                entity_state_repository=self.require_service("entity_state_repository"),
                rvc_config_repository=self.require_service("rvc_config_repository"),
                entity_manager=self.require_service("entity_manager_service").get_entity_manager(),
            )
            await entity_initialization_service.startup()
            self._set_root_constructed_service(
                "entity_initialization_service",
                entity_initialization_service,
            )

        if self._should_construct("entity_service"):
            self._set_root_constructed_service(
                "entity_service",
                EntityService(
                    websocket_manager=self.require_service("websocket_manager"),
                    entity_state_repository=self.require_service("entity_state_repository"),
                    rvc_config_repository=self.require_service("rvc_config_repository"),
                    diagnostics_repository=self.require_service("diagnostics_repository"),
                ),
            )

        if self._should_construct("entity_domain_service"):
            self._set_root_constructed_service(
                "entity_domain_service",
                EntityDomainService(
                    config_service=self.require_service("rvc_config_facade"),
                    auth_manager=self.require_service("auth_manager"),
                    entity_service=self.require_service("entity_service"),
                    websocket_manager=self.require_service("websocket_manager"),
                    entity_manager=self.require_service("entity_manager_service"),
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
            diagnostic_handler = DiagnosticHandler(self.require_service("app_settings"))
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
                storage_path=self.require_service("app_settings").get_can_recorder_storage_path(),
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
                    can_interface_service=self.require_service("can_interface_service")
                ),
            )

        await self._construct_websocket_manager()

        if self._should_construct("can_bus_service"):
            can_bus_service = CANBusService(
                can_tracking_repository=self.require_service("can_tracking_repository"),
                system_state_repository=self.require_service("system_state_repository"),
                can_anomaly_detector=self.require_service("can_anomaly_detector"),
                diagnostic_handler=self.require_service("diagnostic_handler"),
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
                can_tracking_repository=self.require_service("can_tracking_repository"),
                system_state_repository=self.require_service("system_state_repository"),
                can_bus_recorder=self.get_optional_service("can_bus_recorder"),
                can_protocol_analyzer=self.get_optional_service("can_protocol_analyzer"),
                can_message_filter=self.get_optional_service("can_message_filter"),
            )
            await websocket_manager.start()
            self._set_root_constructed_service("websocket_manager", websocket_manager)

    def _set_root_constructed_service(self, service_name: str, service: Any) -> None:
        """Store a root-constructed service and mirror guardrail metadata."""
        self.set_constructed_service(service_name, service)

    def _should_construct(self, service_name: str) -> bool:
        """Return whether a service should be constructed for the current graph."""
        should_construct = (
            service_name not in self._constructed_services and service_name in self._service_catalog
        )
        if should_construct:
            self._service_status[service_name] = ServiceStatus.STARTING
            self._service_start_times.setdefault(service_name, time.perf_counter())
            self._current_constructing_service = service_name
        return should_construct

    def _get_impacted_services(self, service_name: str) -> list[str]:
        """Return services after the failed service in baked construction order."""
        if service_name not in self._root_service_order:
            return []
        service_index = self._root_service_order.index(service_name)
        return [
            name
            for name in self._root_service_order[service_index + 1 :]
            if name in self._service_catalog
        ]

    async def _teardown_service(self, service_name: str, service: Any) -> None:
        """Call the correct teardown method for a root-owned service."""
        method_name = self._teardown_method_name(service)
        if method_name is None:
            return
        method = getattr(service, method_name)
        result = method()
        if isinstance(result, str):
            return
        if hasattr(result, "__await__"):
            await result
        logger.debug("Tore down service %s with %s()", service_name, method_name)

    @staticmethod
    def _teardown_method_name(service: Any) -> str | None:
        """Choose the best teardown method exposed by a service."""
        for method_name in ("shutdown", "stop", "stop_monitoring"):
            method = getattr(service, method_name, None)
            if callable(method):
                return method_name
        return None

    def _mirror_guardrail_service(self, service_name: str, service: Any) -> None:
        """Mirror root guardrail metadata into the guardrail-only coordinator."""
        metadata = ROOT_GUARDRAIL_METADATA.get(service_name)
        if metadata is None:
            return

        self.guardrail_coordinator.add_guardrail_service(
            service_name=service_name,
            service=service,
            tier=metadata.tier,
            command_halt_participant=metadata.command_halt_participant,
            metadata={
                "tier": metadata.tier,
                "command_halt_participant": metadata.command_halt_participant,
                "description": metadata.description,
                "tags": sorted(metadata.tags),
            },
        )
        if service_name == "command_guardrail_service":
            service.service_registry = self.guardrail_coordinator

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
