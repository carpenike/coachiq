"""Tests for honest runtime entity timestamp semantics."""

from datetime import UTC, datetime

import pytest

from backend.repositories.entity_repository import EntityRuntimeStateRepository


@pytest.mark.asyncio
async def test_repeated_observation_preserves_state_change_time() -> None:
    """Fresh observations advance last-seen time without fabricating a state change."""
    repository = EntityRuntimeStateRepository(database_manager=None, performance_monitor=None)

    await repository.save_entity_state(
        "light_1",
        {
            "raw": {"operating_status": 0},
            "value": {"operating_status": "0"},
            "state": "off",
            "timestamp": 1_783_776_000.0,
        },
    )
    first = await repository.get_entity_state("light_1")

    await repository.save_entity_state(
        "light_1",
        {
            "raw": {"operating_status": 0},
            "value": {"operating_status": "0"},
            "state": "off",
            "timestamp": 1_783_776_100.0,
        },
    )
    repeated = await repository.get_entity_state("light_1")

    assert first is not None
    assert repeated is not None
    assert repeated["last_seen_at"] == datetime.fromtimestamp(1_783_776_100.0, tz=UTC).isoformat()
    assert repeated["state_changed_at"] == first["state_changed_at"]
    assert repeated["data_received_at"] != ""


@pytest.mark.asyncio
async def test_operational_change_advances_state_change_time() -> None:
    """A changed operational payload advances state_changed_at to source time."""
    repository = EntityRuntimeStateRepository(database_manager=None, performance_monitor=None)

    await repository.save_entity_state(
        "light_1",
        {
            "raw": {"operating_status": 0},
            "value": {"operating_status": "0"},
            "state": "off",
            "timestamp": 1_783_776_000.0,
        },
    )
    await repository.save_entity_state(
        "light_1",
        {
            "raw": {"operating_status": 200},
            "value": {"operating_status": "200"},
            "state": "on",
            "timestamp": 1_783_776_100.0,
        },
    )
    changed = await repository.get_entity_state("light_1")

    assert changed is not None
    assert changed["state_changed_at"] == changed["last_seen_at"]
