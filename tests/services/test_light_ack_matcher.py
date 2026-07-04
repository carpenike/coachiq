"""Acknowledgment matching for light commands.

Regression: the old matcher compared pre-command state with broken field
logic and always timed out, so working commands surfaced as errors. These
tests pin the target derivation and the status match.
"""

import pytest

from backend.services.entities.entity_domain_service import (
    EntityDomainService,
    SafetyControlCommandV2,
)

pytestmark = [pytest.mark.unit]


def _cmd(**kw) -> SafetyControlCommandV2:
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
    assert EntityDomainService._expected_operating_status(command) == expected


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
    assert EntityDomainService._status_acknowledged(current, expected) is ok
