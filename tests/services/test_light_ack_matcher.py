"""Acknowledgment matching for light commands.

Regression: the old matcher compared pre-command state with broken field
logic and always timed out, so working commands surfaced as errors. These
tests pin the target derivation and the status match.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.entities.entity_domain_service import (
    EntityDomainService,
    SafetyControlCommandV2,
)

pytestmark = [pytest.mark.unit]


def _cmd(**kw: Any) -> SafetyControlCommandV2:
    return SafetyControlCommandV2(**kw)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (_cmd(command="set", state=False), 0),  # off -> 0
        (_cmd(command="set", state=True, brightness=50), 100),  # 50% -> 0-200 scale
        (_cmd(command="set", state=True, brightness=100), 200),  # full
        (_cmd(command="set", state=True, brightness=0), 0),
        (_cmd(command="set", state=True), None),  # on, unspecified level
        (_cmd(command="toggle"), None),  # non-set: any resulting on-state
    ],
)
def test_expected_operating_status(command: SafetyControlCommandV2, expected: int | None) -> None:
    actual = EntityDomainService._expected_operating_status(  # pyright: ignore[reportPrivateUsage]
        command
    )
    assert actual == expected


@pytest.mark.parametrize(
    ("current", "expected", "ok"),
    [
        (0, 0, True),  # off confirmed
        (5, 0, False),  # still on -> not off
        (None, 0, False),  # unknown -> not confirmed off
        (100, 100, True),  # exact level
        (104, 100, True),  # within tolerance
        (150, 100, False),  # too far
        (100, None, True),  # "on at any level"
        (0, None, False),  # off does not confirm an on-command
        (None, None, False),
    ],
)
def test_status_acknowledged(current: int | None, expected: int | None, ok: bool) -> None:
    actual = EntityDomainService._status_acknowledged(  # pyright: ignore[reportPrivateUsage]
        current,
        expected,
    )
    assert actual is ok


@pytest.mark.asyncio
async def test_control_uses_pi_acknowledgment_timeout_floor() -> None:
    """A caller's five-second timeout is raised above measured Pi RX backlog."""
    entity_service = MagicMock()
    entity_service.control_entity = AsyncMock(return_value=SimpleNamespace(status="success"))
    service = EntityDomainService(
        config_service=MagicMock(),
        auth_manager=MagicMock(),
        entity_service=entity_service,
        event_broker=MagicMock(),
        entity_manager=MagicMock(),
    )
    await_command_ack = AsyncMock(return_value=(True, 5500.0))
    service._await_command_ack = await_command_ack  # pyright: ignore[reportPrivateUsage]
    command = SafetyControlCommandV2(
        command="set",
        state=False,
        brightness=None,
        parameters=None,
        safety_confirmation=True,
        timeout_seconds=5.0,
    )

    result = await service.control_entity_safe(
        "bedroom_ceiling_light",
        command,
        user_context={"role": "user"},
    )

    assert result.status == "success"
    assert result.acknowledged is True
    await_args = await_command_ack.await_args
    assert await_args is not None
    assert await_args.args[2] == 10.0
