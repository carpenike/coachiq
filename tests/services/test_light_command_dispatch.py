"""Tests for authoritative-state boundaries during light command dispatch."""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.entities.entity_service import EntityService


@pytest.mark.asyncio
async def test_light_dispatch_queues_intent_without_publishing_state() -> None:
    """Only physical status may mutate or publish authoritative light state."""
    entity: dict[str, Any] = {
        "entity_id": "bedroom_ceiling_light",
        "instance": 25,
        "command_instances": [25, 26],
        "interface": "house",
        "raw": {"operating_status": 50},
        "state": "on",
    }
    repository = MagicMock()
    repository.get_entity_state = AsyncMock(return_value=entity)
    repository.save_entity_state = AsyncMock()
    event_broker = MagicMock()
    event_broker.publish = AsyncMock()
    service = EntityService(
        event_broker=event_broker,
        entity_state_repository=repository,
        rvc_config_repository=MagicMock(),
        diagnostics_repository=MagicMock(),
    )
    tx_queue: asyncio.Queue[tuple[Any, str]] = asyncio.Queue()
    can_settings = SimpleNamespace(
        interface_mappings={"house": "can1"},
        all_interfaces=["can0", "can1"],
    )

    with (
        patch("backend.services.entities.entity_service.can_tx_queue", tx_queue),
        patch(
            "backend.services.entities.entity_service.get_can_settings",
            return_value=can_settings,
        ),
    ):
        result = await service._execute_light_command(  # pyright: ignore[reportPrivateUsage]
            "bedroom_ceiling_light",
            target_brightness_ui=0,
            action_description="Set OFF",
        )

    repository.save_entity_state.assert_not_awaited()
    event_broker.publish.assert_not_awaited()
    assert entity["raw"]["operating_status"] == 50
    assert result.state == "off"

    first_message, first_interface = tx_queue.get_nowait()
    second_message, second_interface = tx_queue.get_nowait()
    assert first_interface == second_interface == "can1"
    assert [first_message.data[0], second_message.data[0]] == [25, 26]
    assert [first_message.data[2], second_message.data[2]] == [0, 0]
