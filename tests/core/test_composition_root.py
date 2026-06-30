"""Tests for the Phase A composition-root compatibility seam."""

import pytest

from backend.core import dependencies
from backend.core.composition_root import CompositionRoot
from backend.core.config import get_settings
from backend.core.guardrail_coordinator import GuardrailCoordinator
from backend.core.guardrail_interfaces import GuardrailTier
from backend.core.service_dependency_resolver import DependencyType, ServiceDependency


def _reset_dependency_globals() -> None:
    """Reset dependency globals mutated by composition-root tests."""
    dependencies._composition_root = None
    dependencies._service_registry = None


def _seed_foundation_fakes(root: CompositionRoot) -> None:
    """Seed non-tested foundation handles required by A0 typed services."""
    root.set_constructed_service("rvc_config", object())
    root.set_constructed_service("performance_monitor", object())
    root.set_constructed_service("database_manager", object())
    root.set_constructed_service("persistence_service", object())
    root.set_constructed_service("rvc_config_facade", object())


@pytest.mark.asyncio
async def test_composition_root_starts_registry_and_captures_typed_settings() -> None:
    """CompositionRoot starts the compatibility registry and captures typed services."""
    root = CompositionRoot()
    settings = get_settings()
    _seed_foundation_fakes(root)

    async def configure(registry: GuardrailCoordinator) -> None:
        registry.register_service(
            name="app_settings",
            init_func=lambda: settings,
            dependencies=[],
            description="Test settings service",
        )

    await root.startup(configure)
    try:
        assert root.has_service("app_settings")
        assert root.get_service("app_settings") is settings
        assert root.services.settings is settings
    finally:
        await root.shutdown()


@pytest.mark.asyncio
async def test_repository_substrate_receives_root_constructed_dependencies() -> None:
    """A0 repository substrate construction uses root-owned foundation services."""
    root = CompositionRoot()
    settings = get_settings()
    performance_monitor = object()
    database_manager = object()

    root.set_constructed_service("app_settings", settings)
    root.set_constructed_service("rvc_config", object())
    root.set_constructed_service("performance_monitor", performance_monitor)
    root.set_constructed_service("database_manager", database_manager)
    root.set_constructed_service("persistence_service", object())
    root.set_constructed_service("rvc_config_facade", object())

    async def configure(registry: GuardrailCoordinator) -> None:
        registry.register_service(
            name="performance_monitor",
            init_func=lambda: performance_monitor,
            dependencies=[],
            description="Test performance monitor",
        )
        registry.register_service(
            name="database_manager",
            init_func=lambda: database_manager,
            dependencies=[],
            description="Test database manager",
        )
        registry.register_service(
            name="security_config_repository",
            init_func=lambda database_manager, performance_monitor: {
                "database_manager": database_manager,
                "performance_monitor": performance_monitor,
            },
            dependencies=[
                ServiceDependency("database_manager", DependencyType.REQUIRED),
                ServiceDependency("performance_monitor", DependencyType.REQUIRED),
            ],
            description="Test repository service",
        )

    await root.startup(configure)
    try:
        repository = root.get_service("security_config_repository")
        assert repository == {
            "database_manager": database_manager,
            "performance_monitor": performance_monitor,
        }
        assert root.compat_registry.get_service("security_config_repository") is repository
    finally:
        await root.shutdown()


@pytest.mark.asyncio
async def test_facade_services_receive_root_constructed_repositories() -> None:
    """A1 facades are constructed from root-owned repository substrate handles."""
    root = CompositionRoot()
    rvc_config_repository = object()
    persistence_repository = object()
    performance_monitor = object()

    root.set_constructed_service("app_settings", get_settings())
    root.set_constructed_service("rvc_config", object())
    root.set_constructed_service("performance_monitor", performance_monitor)
    root.set_constructed_service("database_manager", object())
    root.set_constructed_service("rvc_config_repository", rvc_config_repository)
    root.set_constructed_service("persistence_repository", persistence_repository)

    async def configure(registry: GuardrailCoordinator) -> None:
        registry.register_service(
            name="performance_monitor",
            init_func=lambda: performance_monitor,
            dependencies=[],
            description="Test performance monitor",
        )
        registry.register_service(
            name="rvc_config_repository",
            init_func=lambda: rvc_config_repository,
            dependencies=[],
            description="Test RV-C config repository",
        )
        registry.register_service(
            name="persistence_repository",
            init_func=lambda: persistence_repository,
            dependencies=[],
            description="Test persistence repository",
        )
        registry.register_service(
            name="rvc_config_facade",
            init_func=lambda rvc_config_repository: {
                "rvc_config_repository": rvc_config_repository
            },
            dependencies=[ServiceDependency("rvc_config_repository", DependencyType.REQUIRED)],
            description="Test RV-C config facade",
        )
        registry.register_service(
            name="persistence_service",
            init_func=lambda persistence_repository, performance_monitor: {
                "persistence_repository": persistence_repository,
                "performance_monitor": performance_monitor,
            },
            dependencies=[
                ServiceDependency("persistence_repository", DependencyType.REQUIRED),
                ServiceDependency("performance_monitor", DependencyType.REQUIRED),
            ],
            description="Test persistence service",
        )

    await root.startup(configure)
    try:
        assert root.get_service("rvc_config_facade") == {
            "rvc_config_repository": rvc_config_repository
        }
        assert root.get_service("persistence_service") == {
            "persistence_repository": persistence_repository,
            "performance_monitor": performance_monitor,
        }
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

    root = CompositionRoot()
    _seed_foundation_fakes(root)
    root.set_constructed_service("app_settings", get_settings())
    target = HaltTarget()

    async def configure(registry: GuardrailCoordinator) -> None:
        registry.register_guardrail_service(
            name="can_facade",
            init_func=lambda: target,
            guardrail_tier=GuardrailTier.CRITICAL,
            command_halt_participant=True,
            dependencies=[],
            description="Test CAN facade",
        )

    await root.startup(configure)
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
    root = CompositionRoot()
    settings = get_settings()
    _seed_foundation_fakes(root)

    async def configure(registry: GuardrailCoordinator) -> None:
        registry.register_service(
            name="app_settings",
            init_func=lambda: settings,
            dependencies=[],
            description="Test settings service",
        )

    await root.startup(configure)
    dependencies.initialize_composition_root(root)
    try:
        provider = dependencies.create_service_dependency("app_settings")
        assert provider() is settings
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
        provider = dependencies.create_service_dependency("app_settings")
        assert provider() is settings
        assert root.services.settings is settings
    finally:
        _reset_dependency_globals()


def test_initialize_service_registry_accepts_composition_root_compat_registry() -> None:
    """The compatibility registry remains the only registry source after root init."""
    _reset_dependency_globals()
    root = CompositionRoot()

    dependencies.initialize_composition_root(root)
    try:
        dependencies.initialize_service_registry(root.compat_registry)
        assert dependencies.get_service_registry() is root.compat_registry
    finally:
        _reset_dependency_globals()


def test_initialize_service_registry_rejects_divergent_registry() -> None:
    """A second registry cannot silently diverge after the root is initialized."""
    _reset_dependency_globals()
    root = CompositionRoot()
    other_registry = GuardrailCoordinator()

    dependencies.initialize_composition_root(root)
    try:
        with pytest.raises(RuntimeError, match="divergent ServiceRegistry"):
            dependencies.initialize_service_registry(other_registry)
        assert dependencies.get_service_registry() is root.compat_registry
    finally:
        _reset_dependency_globals()
