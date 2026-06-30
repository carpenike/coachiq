"""Typed composition root for backend service construction.

Phase A keeps the existing GuardrailCoordinator-backed registry as a temporary
compatibility layer while introducing a typed container that future clusters can
populate through constructor injection.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from backend.core.config import Settings
from backend.core.config_provider import RVCConfigProvider
from backend.core.guardrail_coordinator import GuardrailCoordinator
from backend.core.performance import PerformanceMonitor
from backend.services.database.database_manager import DatabaseManager
from backend.services.persistence.persistence_service import PersistenceService
from backend.services.rvc.rvc_config_facade import RVCConfigFacade

logger = logging.getLogger(__name__)

ConfigureServices = Callable[[GuardrailCoordinator], Awaitable[None]]


@dataclass(slots=True)
class CompositionServices:
    """Typed service handles captured during the compatibility phase."""

    settings: Settings | None = None
    rvc_config: RVCConfigProvider | None = None
    performance_monitor: PerformanceMonitor | None = None
    persistence_service: PersistenceService | None = None
    database_manager: DatabaseManager | None = None
    rvc_config_facade: RVCConfigFacade | None = None


class CompositionRoot:
    """Own backend service lifecycle and expose typed service handles."""

    def __init__(self, compat_registry: GuardrailCoordinator | None = None) -> None:
        self.compat_registry = compat_registry or GuardrailCoordinator()
        self._constructed_services: dict[str, Any] = {}
        self.services = CompositionServices()
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

    def _capture_registry_services(self) -> None:
        """Temporarily cache registry handles during HOF-052 Phase A.

        This is transitional scaffolding for ADR-0014 only. Each migrated
        cluster must replace these string-lookups with root construction via
        ``set_constructed_service`` and make the corresponding field
        non-optional once the handle no longer comes from the compatibility
        registry.
        """
        self.services = CompositionServices(
            settings=self.get_optional_service("app_settings"),
            rvc_config=self.get_optional_service("rvc_config"),
            performance_monitor=self.get_optional_service("performance_monitor"),
            persistence_service=self.get_optional_service("persistence_service"),
            database_manager=self.get_optional_service("database_manager"),
            rvc_config_facade=self.get_optional_service("rvc_config_facade"),
        )
        logger.info("CompositionRoot captured typed service handles")

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
