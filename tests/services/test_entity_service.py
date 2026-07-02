"""Tests for EntityService against the wired async entity repository interface."""

from typing import TYPE_CHECKING, cast

import pytest

from backend.services.entities.entity_service import EntityService

if TYPE_CHECKING:
    from backend.repositories.entity_repository import EntityRuntimeStateRepository

pytestmark = pytest.mark.unit


class _EntityStateRepositoryFake:
    """Typed fake matching the async repository interface wired by CompositionRoot."""

    def __init__(self, states: dict[str, dict]) -> None:
        self._states = states

    async def get_all_states(self) -> dict[str, dict]:
        """Return all seeded entity states."""
        return dict(self._states)

    async def get_entity_state(self, entity_id: str) -> dict | None:
        """Return one seeded entity state."""
        return self._states.get(entity_id)


class _DiagnosticsRepositoryFake:
    """Diagnostics fake for EntityService constructor completeness."""

    def get_unmapped_entries(self) -> dict:
        """Return no unmapped entries."""
        return {}

    def get_unknown_pgns(self) -> dict:
        """Return no unknown PGNs."""
        return {}


def _service(states: dict[str, dict]) -> EntityService:
    """Create EntityService with a typed async entity repository fake."""
    return EntityService(
        websocket_manager=cast("object", None),
        entity_state_repository=cast(
            "EntityRuntimeStateRepository", _EntityStateRepositoryFake(states)
        ),
        rvc_config_repository=cast("object", None),
        diagnostics_repository=cast("object", _DiagnosticsRepositoryFake()),
    )


def _seeded_states() -> dict[str, dict]:
    """Return representative dict-shaped entity states."""
    return {
        "light_1": {
            "friendly_name": "Kitchen Light",
            "device_type": "light",
            "protocol": "rvc",
            "state": "on",
            "suggested_area": "Kitchen",
            "capabilities": ["brightness"],
            "groups": ["main"],
            "timestamp": 1_000.0,
            "available": True,
        },
        "tank_1": {
            "friendly_name": "Fresh Tank",
            "device_type": "tank",
            "protocol": "rvc",
            "state": "50",
            "suggested_area": "Utility",
            "capabilities": ["level"],
            "groups": [],
            "timestamp": 900.0,
            "available": True,
        },
    }


async def test_list_entities_uses_async_get_all_states() -> None:
    """Entity listing reads the async state repository and applies filters."""
    service = _service(_seeded_states())

    all_entities = await service.list_entities()
    light_entities = await service.list_entities(device_type="light")

    assert set(all_entities) == {"light_1", "tank_1"}
    assert list(light_entities) == ["light_1"]
    assert light_entities["light_1"]["friendly_name"] == "Kitchen Light"


async def test_metadata_uses_dict_shaped_states() -> None:
    """Metadata aggregation works with dict-shaped async repository states."""
    service = _service(_seeded_states())

    metadata = await service.get_metadata()

    assert metadata["device_types"] == ["light", "tank"]
    assert metadata["capabilities"] == ["brightness", "level"]
    assert metadata["suggested_areas"] == ["Kitchen", "Utility"]
    assert metadata["groups"] == ["main"]
    assert metadata["total_entities"] == 2


async def test_protocol_summary_uses_dict_shaped_states() -> None:
    """Protocol summary counts dict-shaped async repository states."""
    service = _service(_seeded_states())

    summary = await service.get_protocol_summary()

    assert summary == {
        "rvc": {
            "count": 2,
            "device_types": ["light", "tank"],
            "entities": ["light_1", "tank_1"],
        }
    }
