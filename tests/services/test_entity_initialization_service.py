"""Tests for EntityInitializationService loading into the async runtime state repo."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

import backend.services.entities.entity_initialization_service as initialization_module
from backend.services.entities.entity_initialization_service import EntityInitializationService

if TYPE_CHECKING:
    from backend.repositories.entity_repository import EntityRuntimeStateRepository
    from backend.repositories.rvc_config_repository import RVCConfigRepository

pytestmark = pytest.mark.unit


class _SpecMeta:
    """Minimal spec metadata object with the API used by initialization."""

    def dict(self) -> dict[str, Any]:
        """Return empty spec metadata."""
        return {}


class _EntityRuntimeStateRepositoryFake:
    """Async runtime state repository fake populated by initialization."""

    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {}

    async def save_bulk_states(self, states: dict[str, dict[str, Any]]) -> int:
        """Persist initialized state dictionaries."""
        self.states = dict(states)
        return len(self.states)

    async def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Return initialized state dictionaries."""
        return dict(self.states)


class _RVCConfigRepositoryFake:
    """RVC config repository fake for initialization."""

    def __init__(self) -> None:
        self.loaded = False

    def load_configuration(self, **_kwargs: Any) -> None:
        """Record that configuration was loaded."""
        self.loaded = True

    def get_coach_info(self) -> None:
        """Return no coach info."""


def _rvc_config() -> SimpleNamespace:
    """Return a minimal structured RVC config payload."""
    entity_map = {
        "light": {
            "entity_id": "light_1",
            "device_type": "light",
            "suggested_area": "Kitchen",
            "friendly_name": "Kitchen Light",
            "capabilities": ["brightness"],
            "groups": ["main"],
            "protocol": "firefly",
            "command_dgn": "1FEDB",
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


async def test_startup_saves_initialized_entities_to_async_runtime_repo(monkeypatch) -> None:
    """Initialization startup populates the same async repo EntityService reads."""
    entity_repo = _EntityRuntimeStateRepositoryFake()
    rvc_repo = _RVCConfigRepositoryFake()
    monkeypatch.setattr(initialization_module, "get_default_paths", lambda: ("spec", "mapping"))
    monkeypatch.setattr(initialization_module, "load_config_data_v2", lambda *_args: _rvc_config())

    service = EntityInitializationService(
        entity_state_repository=cast("EntityRuntimeStateRepository", entity_repo),
        rvc_config_repository=cast("RVCConfigRepository", rvc_repo),
    )

    await service.startup()

    states = await entity_repo.get_all_states()
    assert rvc_repo.loaded is True
    assert set(states) == {"light_1", "tank_1"}
    assert states["light_1"]["device_type"] == "light"
    assert states["light_1"]["suggested_area"] == "Kitchen"
    assert states["light_1"]["state"] == "off"
    assert states["light_1"]["protocol"] == "firefly"
    assert states["light_1"]["command_dgn"] == "1FEDB"
    assert states["tank_1"]["device_type"] == "tank"
    assert service.get_initialization_status()["entity_count"] == 2
