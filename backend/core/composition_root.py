"""Typed composition root for backend service construction.

Phase A keeps the existing GuardrailCoordinator-backed registry as a temporary
compatibility layer while introducing a typed container that future clusters can
populate through constructor injection.
"""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from backend.core.config import Settings
from backend.core.config_provider import RVCConfigProvider
from backend.core.guardrail_coordinator import GuardrailCoordinator
from backend.core.guardrail_runtime_coordinator import GuardrailRuntimeCoordinator
from backend.core.performance import PerformanceMonitor
from backend.core.service_dependency_resolver import DependencyType
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

    async def _construct_a2_services(self) -> None:
        """Construct A2 through the HOF-053 compatibility bridge.

        TODO(HOF-053): replace this bridge with typed constructor calls before
        deleting the registry/resolver.
        """
        for service_name in self._A2_SERVICE_ORDER:
            await self._construct_registered_service(service_name)

    async def _construct_a3_services(self) -> None:
        """Construct A3 through the HOF-053 compatibility bridge.

        TODO(HOF-053): replace this bridge with typed constructor calls before
        deleting the registry/resolver.
        """
        for service_name in self._A3_SERVICE_ORDER:
            await self._construct_registered_service(service_name)

    async def _construct_a4_services(self) -> None:
        """Construct A4 through the HOF-053 compatibility bridge.

        TODO(HOF-053): replace this bridge with typed constructor calls before
        deleting the registry/resolver.
        """
        for service_name in self._A4_SERVICE_ORDER:
            await self._construct_registered_service(service_name)

    def _set_root_constructed_service(self, service_name: str, service: Any) -> None:
        """Store a root-constructed service and mirror it for compatibility startup."""
        self.set_constructed_service(service_name, service)
        self._replace_compat_init_func(service_name, service)
        self._mirror_guardrail_service(service_name, service)

    async def _construct_registered_service(self, service_name: str) -> None:
        """Construct one A2-A4 bridge service and mirror it into compatibility startup.

        TODO(HOF-053): replace this registry-definition bridge before deleting
        the registry/resolver. A0/A1 must not call this path.
        """
        if service_name in self._constructed_services:
            self._replace_compat_init_func(service_name, self._constructed_services[service_name])
            self._mirror_guardrail_service(service_name, self._constructed_services[service_name])
            return
        if service_name in self._constructing_services:
            msg = f"Circular root construction detected for service '{service_name}'"
            raise RuntimeError(msg)

        definition = self.compat_registry._service_definitions.get(service_name)  # noqa: SLF001
        if definition is None:
            return

        self._constructing_services.add(service_name)
        try:
            await self._construct_required_dependencies(definition)
            service = await self._construct_from_definition(definition)
            self.set_constructed_service(service_name, service)
            self._replace_compat_init_func(service_name, service)
            self._mirror_guardrail_service(service_name, service)
        finally:
            self._constructing_services.discard(service_name)

    async def _construct_required_dependencies(self, definition: Any) -> None:
        """Construct required dependencies that are still registered only in compatibility."""
        for dependency in definition.dependencies:
            if dependency.type != DependencyType.REQUIRED:
                continue
            if dependency.name in self._constructed_services:
                continue
            await self._construct_registered_service(dependency.name)

    async def _construct_from_definition(self, definition: Any) -> Any:
        """Construct an A2-A4 compatibility service from a registered definition.

        TODO(HOF-053): remove this bridge after the remaining services move to
        explicit constructor calls.
        """
        dependency_kwargs: dict[str, Any] = {}
        for dependency in definition.dependencies:
            if dependency.name in self._constructed_services:
                param_name = dependency.inject_as or dependency.name.replace("-", "_")
                dependency_kwargs[param_name] = self._constructed_services[dependency.name]

        try:
            signature = inspect.signature(definition.init_func)
            accepted_params = set(signature.parameters.keys())
            dependency_kwargs = {
                name: value for name, value in dependency_kwargs.items() if name in accepted_params
            }
        except (TypeError, ValueError) as exc:
            msg = (
                "Cannot inspect compatibility factory for service "
                f"'{getattr(definition, 'name', '<unknown>')}'"
            )
            raise RuntimeError(msg) from exc

        if asyncio.iscoroutinefunction(definition.init_func):
            return await definition.init_func(**dependency_kwargs)
        return definition.init_func(**dependency_kwargs)

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
