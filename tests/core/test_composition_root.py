"""Tests for the Phase A composition-root compatibility seam."""

from pathlib import Path

import pytest

from backend.core import dependencies
from backend.core.composition_root import CompositionRoot
from backend.core.config import Settings, get_settings
from backend.core.performance import PerformanceMonitor
from backend.repositories.security_config_repository import SecurityConfigRepository
from backend.services.persistence.persistence_service import PersistenceService
from backend.services.rvc.rvc_config_facade import RVCConfigFacade


def test_composition_root_has_no_registry_bridge_tokens() -> None:
    """Permanent ratchet: composition root must not regress to registry bridge construction."""
    source = Path("backend/core/composition_root.py").read_text(encoding="utf-8")
    forbidden_tokens = ["inspect.signature", "definition.init_func", "_service_definitions"]
    assert not any(token in source for token in forbidden_tokens)


def _reset_dependency_globals() -> None:
    """Reset dependency globals mutated by composition-root tests."""
    dependencies._composition_root = None
    dependencies._service_registry = None


def _seed_foundation_fakes(root: CompositionRoot) -> None:
    """Seed non-tested foundation handles required by A0 typed services."""
    root.set_constructed_service("rvc_config", object())
    root.set_constructed_service("performance_monitor", object())
    root.set_constructed_service("database_manager", object())
    root.set_constructed_service("edge_proxy_monitor", object())
    root.set_constructed_service("persistence_service", object())
    root.set_constructed_service("rvc_config_facade", object())


@pytest.mark.asyncio
async def test_composition_root_starts_and_captures_typed_settings() -> None:
    """CompositionRoot starts from its root-owned catalog and captures typed services."""
    root = CompositionRoot(service_catalog={"app_settings"})
    settings = get_settings()

    await root.startup()
    try:
        assert root.has_service("app_settings")
        assert isinstance(root.get_service("app_settings"), Settings)
        assert root.services.settings.app_name == settings.app_name
    finally:
        await root.shutdown()


@pytest.mark.asyncio
async def test_repository_substrate_receives_root_constructed_dependencies() -> None:
    """A0 repository substrate construction uses root-owned foundation services."""
    root = CompositionRoot(service_catalog={"security_config_repository"})
    settings = get_settings()
    performance_monitor = PerformanceMonitor()
    database_manager = object()

    root.set_constructed_service("app_settings", settings)
    root.set_constructed_service("rvc_config", object())
    root.set_constructed_service("performance_monitor", performance_monitor)
    root.set_constructed_service("database_manager", database_manager)
    root.set_constructed_service("edge_proxy_monitor", object())
    root.set_constructed_service("persistence_service", object())
    root.set_constructed_service("rvc_config_facade", object())

    await root.startup()
    try:
        repository = root.get_service("security_config_repository")
        assert isinstance(repository, SecurityConfigRepository)
        assert repository._db_manager is database_manager
        assert repository._monitor is performance_monitor
    finally:
        await root.shutdown()


@pytest.mark.asyncio
async def test_facade_services_receive_root_constructed_repositories() -> None:
    """A1 facades are constructed from root-owned repository substrate handles."""
    root = CompositionRoot(service_catalog={"rvc_config_facade", "persistence_service"})
    rvc_config_repository = object()
    persistence_repository = object()
    performance_monitor = PerformanceMonitor()

    root.set_constructed_service("app_settings", get_settings())
    root.set_constructed_service("rvc_config", object())
    root.set_constructed_service("performance_monitor", performance_monitor)
    root.set_constructed_service("database_manager", object())
    root.set_constructed_service("edge_proxy_monitor", object())
    root.set_constructed_service("rvc_config_repository", rvc_config_repository)
    root.set_constructed_service("persistence_repository", persistence_repository)

    await root.startup()
    try:
        assert isinstance(root.get_service("rvc_config_facade"), RVCConfigFacade)
        assert isinstance(root.get_service("persistence_service"), PersistenceService)
    finally:
        await root.shutdown()


@pytest.mark.asyncio
async def test_a0_a1_services_bypass_registry_factories() -> None:
    """Converted A0/A1 services are built by typed constructors, not registry factories."""
    root = CompositionRoot(service_catalog={"app_settings", "rvc_config_facade"})
    rvc_config_repository = object()

    root.set_constructed_service("rvc_config", object())
    root.set_constructed_service("performance_monitor", object())
    root.set_constructed_service("database_manager", object())
    root.set_constructed_service("edge_proxy_monitor", object())
    root.set_constructed_service("persistence_service", object())
    root.set_constructed_service("rvc_config_repository", rvc_config_repository)

    await root.startup()
    try:
        assert isinstance(root.services.settings, Settings)
        assert isinstance(root.services.rvc_config_facade, RVCConfigFacade)
    finally:
        await root.shutdown()


@pytest.mark.asyncio
async def test_guardrail_metadata_reads_from_runtime_coordinator() -> None:
    """Guardrail reads use the root-owned guardrail-only coordinator."""

    class HaltTarget:
        def __init__(self) -> None:
            self.reasons: list[str] = []

        async def halt_command_emission(self, reason: str) -> None:
            self.reasons.append(reason)

    target = HaltTarget()
    root = CompositionRoot(service_catalog=set())
    root.set_constructed_service("can_facade", target)

    try:
        assert root.guardrail_coordinator.get_command_halt_targets() == ["can_facade"]
        metadata = root.guardrail_coordinator.get_guardrail_metadata("can_facade")
        assert metadata is not None
        assert metadata["command_halt_participant"] is True

        result = await root.guardrail_coordinator.halt_command_emission("test", "pytest")
        assert result == {"can_facade": True}
        assert target.reasons == ["test"]
    finally:
        await root.shutdown()


@pytest.mark.asyncio
async def test_service_dependency_delegates_to_composition_root() -> None:
    """Dependency providers resolve through CompositionRoot when it is initialized."""
    _reset_dependency_globals()
    root = CompositionRoot(service_catalog={"app_settings"})
    settings = get_settings()

    await root.startup()
    dependencies.initialize_composition_root(root)
    try:
        provider = dependencies.root_service_dependency("app_settings")
        assert isinstance(provider(), Settings)
        assert provider().app_name == settings.app_name
    finally:
        await root.shutdown()
        _reset_dependency_globals()


def test_root_constructed_service_is_settable_without_registry_capture() -> None:
    """Root-constructed services resolve without a registry-backed capture."""
    _reset_dependency_globals()
    root = CompositionRoot()
    settings = get_settings()

    root.set_constructed_service("app_settings", settings)
    dependencies.initialize_composition_root(root)
    try:
        provider = dependencies.root_service_dependency("app_settings")
        assert provider() is settings
        assert root.services.settings is settings
    finally:
        _reset_dependency_globals()


def test_initialize_service_registry_accepts_composition_root_alias() -> None:
    """The legacy initializer accepts the root during the transition."""
    _reset_dependency_globals()
    root = CompositionRoot()

    dependencies.initialize_composition_root(root)
    try:
        dependencies.initialize_service_registry(root)
        assert dependencies.get_service_registry() is root
    finally:
        _reset_dependency_globals()


def test_initialize_service_registry_rejects_divergent_registry() -> None:
    """A second registry cannot silently diverge after the root is initialized."""
    _reset_dependency_globals()
    root = CompositionRoot()
    other_registry = object()

    dependencies.initialize_composition_root(root)
    try:
        with pytest.raises(RuntimeError, match="divergent ServiceRegistry"):
            dependencies.initialize_service_registry(other_registry)
        assert dependencies.get_service_registry() is root
    finally:
        _reset_dependency_globals()
