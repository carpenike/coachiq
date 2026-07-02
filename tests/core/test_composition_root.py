"""Tests for the Phase A composition-root compatibility seam."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import dependencies
from backend.core.composition_root import CompositionRoot
from backend.core.config import Settings, get_settings
from backend.core.performance import PerformanceMonitor
from backend.core.service_status import ServiceStatus
from backend.api.domains import entities as entities_mod
from backend.core.exception_handlers import register_exception_handlers
from backend.middleware.auth import AuthenticationMiddleware
from backend.repositories.entity_repository import EntityRuntimeStateRepository
from backend.services.auth.manager import AuthMode, InvalidTokenError
from backend.repositories.security_config_repository import SecurityConfigRepository
from backend.services.persistence.persistence_service import PersistenceService
from backend.services.rvc.rvc_config_facade import RVCConfigFacade
import backend.services.entities.entity_initialization_service as initialization_module


def test_composition_root_has_no_registry_bridge_tokens() -> None:
    """Permanent ratchet: composition root must not regress to registry bridge construction."""
    source = Path("backend/core/composition_root.py").read_text(encoding="utf-8")
    forbidden_tokens = [
        "inspect.signature",
        "definition.init_func",
        "_service_definitions",
        "compat_registry",
        "startup_all",
        "shutdown_all",
        "configure_services",
        "ServiceRegistry",
    ]
    assert not any(token in source for token in forbidden_tokens)


def test_command_guardrail_service_has_no_registry_collaborator() -> None:
    """CommandGuardrailService must stay wired to the guardrail runtime coordinator."""
    source = Path("backend/services/guardrails/command_guardrail_service.py").read_text(
        encoding="utf-8"
    )
    assert "service_registry" not in source
    assert "ServiceRegistry" not in source


def _reset_dependency_globals() -> None:
    """Reset dependency globals mutated by composition-root tests."""
    dependencies._composition_root = None


def _seed_foundation_fakes(root: CompositionRoot) -> None:
    """Seed non-tested foundation handles required by A0 typed services."""
    root.set_constructed_service("rvc_config", object())
    root.set_constructed_service("performance_monitor", object())
    root.set_constructed_service("database_manager", object())
    root.set_constructed_service("edge_proxy_monitor", object())
    root.set_constructed_service("persistence_service", object())
    root.set_constructed_service("rvc_config_facade", object())


class _AuthManager:
    """Enabled auth manager for composition-root request tests."""

    auth_mode = AuthMode.SINGLE_USER

    def validate_token(self, credential: str) -> dict[str, str]:
        """Accept the known good token."""
        if credential == "good":
            return {"sub": "user", "username": "user", "role": "admin"}
        raise InvalidTokenError("invalid token")


class _WebSocketManager:
    """Minimal websocket manager for EntityService construction."""

    async def broadcast_to_data_clients(self, _data: dict[str, Any]) -> None:
        """No-op broadcast."""


class _RVCConfigRepository:
    """RVC config repository fake used by entity initialization."""

    def load_configuration(self, **_kwargs: Any) -> None:
        """Accept loaded configuration."""


class _EntityRuntimeStateRepository:
    """Async runtime state repository fake shared by initialization and EntityService."""

    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {}

    async def save_bulk_states(self, states: dict[str, dict[str, Any]]) -> int:
        """Persist initialized state dictionaries."""
        self.states = dict(states)
        return len(self.states)

    async def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Return all initialized state dictionaries."""
        return dict(self.states)

    async def get_entity_state(self, entity_id: str) -> dict[str, Any] | None:
        """Return one initialized state dictionary."""
        return self.states.get(entity_id)


class _DiagnosticsRepository:
    """Diagnostics repository fake used by EntityService."""

    def get_unmapped_entries(self) -> dict[str, Any]:
        """Return no unmapped entries."""
        return {}

    def get_unknown_pgns(self) -> dict[str, Any]:
        """Return no unknown PGNs."""
        return {}


class _EntityManagerService:
    """Expose the EntityManager instance used during initialization."""

    def __init__(self):
        from backend.core.entity_manager import EntityManager

        self._entity_manager = EntityManager()

    def get_entity_manager(self):
        """Return the test entity manager."""
        return self._entity_manager


class _SpecMeta:
    """Minimal spec metadata object."""

    def dict(self) -> dict[str, Any]:
        """Return empty spec metadata."""
        return {}


def _seeded_rvc_config() -> SimpleNamespace:
    """Return a minimal coach mapping payload with seeded entities."""
    entity_map = {
        "light": {
            "entity_id": "light_1",
            "device_type": "light",
            "suggested_area": "Kitchen",
            "friendly_name": "Kitchen Light",
            "capabilities": ["brightness"],
            "groups": ["main"],
        },
        "tank": {
            "entity_id": "tank_1",
            "device_type": "tank",
            "suggested_area": "Bay",
            "friendly_name": "Fresh Tank",
            "capabilities": ["level"],
            "groups": [],
        },
    }
    return SimpleNamespace(
        dgn_dict={},
        spec_meta=_SpecMeta(),
        mapping_dict={},
        entity_map=entity_map,
        entity_ids=list(entity_map),
        inst_map={},
        unique_instances=[],
        pgn_hex_to_name_map={},
        dgn_pairs=[],
        coach_info=None,
    )


@pytest.mark.asyncio
async def test_composition_root_starts_and_captures_typed_settings() -> None:
    """CompositionRoot starts from its root-owned catalog and captures typed services."""
    root = CompositionRoot(service_catalog={"app_settings"})
    settings = get_settings()

    await root.startup()
    try:
        assert root.has_service("app_settings")
        assert isinstance(root.require_service("app_settings"), Settings)
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
        repository = root.require_service("security_config_repository")
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
        assert isinstance(root.require_service("rvc_config_facade"), RVCConfigFacade)
        assert isinstance(root.require_service("persistence_service"), PersistenceService)
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


@pytest.mark.asyncio
async def test_root_startup_metrics_are_owned_by_composition_root() -> None:
    """CompositionRoot exposes startup metrics without a registry backend."""
    root = CompositionRoot(service_catalog={"app_settings"})

    await root.startup()
    try:
        metrics = root.get_startup_metrics()
        assert metrics["service_count"] == 1
        assert "app_settings" in metrics["service_timings"]
        assert root.get_service_status("app_settings") == ServiceStatus.HEALTHY
        assert root.get_health_summary()["app_settings"]["status"] == "HEALTHY"
    finally:
        await root.shutdown()


@pytest.mark.asyncio
async def test_composition_root_startup_seeds_entities_for_authenticated_api(
    monkeypatch,
) -> None:
    """CompositionRoot boot seeds configured entities into the API-visible repo."""
    _reset_dependency_globals()
    monkeypatch.setattr(initialization_module, "get_default_paths", lambda: ("spec", "mapping"))
    monkeypatch.setattr(
        initialization_module,
        "load_config_data_v2",
        lambda *_args: _seeded_rvc_config(),
    )

    root = CompositionRoot(service_catalog={"entity_initialization_service", "entity_service"})
    root.set_constructed_service("performance_monitor", PerformanceMonitor())
    root.set_constructed_service(
        "entity_state_repository",
        cast("EntityRuntimeStateRepository", _EntityRuntimeStateRepository()),
    )
    root.set_constructed_service("rvc_config_repository", _RVCConfigRepository())
    root.set_constructed_service("entity_manager_service", _EntityManagerService())
    root.set_constructed_service("websocket_manager", _WebSocketManager())
    root.set_constructed_service("diagnostics_repository", _DiagnosticsRepository())

    await root.startup()
    dependencies.initialize_composition_root(root)
    try:
        states = await root.services.entity_state_repository.get_all_states()
        assert len(states) == 2

        app = FastAPI()
        register_exception_handlers(app)
        app.add_middleware(AuthenticationMiddleware, auth_manager=_AuthManager())
        app.include_router(entities_mod.create_entities_router(), prefix="/api/v1/entities")

        client = TestClient(app)
        response = client.get(
            "/api/v1/entities",
            headers={"Accept": "application/json", "Authorization": "Bearer good"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_count"] == 2
        assert [entity["entity_id"] for entity in payload["entities"]] == [
            "light_1",
            "tank_1",
        ]
        assert payload["entities"][0]["name"] == "Kitchen Light"
    finally:
        await root.shutdown()
        _reset_dependency_globals()


@pytest.mark.asyncio
async def test_root_shutdown_uses_service_specific_teardown_methods() -> None:
    """Root shutdown fixes services that expose stop-only teardown methods."""
    events: list[str] = []

    class ShutdownOnly:
        async def shutdown(self) -> None:
            events.append("shutdown")

    class StopOnly:
        async def stop(self) -> None:
            events.append("stop")

    class StopMonitoringOnly:
        async def stop_monitoring(self) -> None:
            events.append("stop_monitoring")

    root = CompositionRoot(service_catalog=set())
    root.set_constructed_service("app_settings", ShutdownOnly())
    root.set_constructed_service("performance_monitor", StopOnly())
    root.set_constructed_service("rvc_config", StopMonitoringOnly())
    root._started = True

    await root.shutdown()

    assert events == ["stop_monitoring", "stop", "shutdown"]
    assert root.get_service_status("app_settings") == ServiceStatus.STOPPED
    assert root.get_service_status("performance_monitor") == ServiceStatus.STOPPED
    assert root.get_service_status("rvc_config") == ServiceStatus.STOPPED


def test_root_guardrail_metadata_declares_only_can_facade_as_halt_participant() -> None:
    """Root guardrail metadata has the approved command-halt participant set."""
    from backend.core.composition_root import ROOT_GUARDRAIL_METADATA

    halt_targets = sorted(
        name
        for name, metadata in ROOT_GUARDRAIL_METADATA.items()
        if metadata.command_halt_participant
    )

    assert halt_targets == ["can_facade"]
