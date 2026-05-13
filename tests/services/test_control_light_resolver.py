"""Unit tests for ``EntityService._resolve_light_command`` (pure decision tree).

Issue #112 split the brightness/state branching out of ``control_light`` so
it could be exercised in isolation without mocking the entity repo or the
CAN bus. These tests cover the resolver's full command surface:

- ``set on`` / ``set off`` (with and without explicit brightness)
- ``set`` with brightness but no state -> normalized to 'on'
- ``toggle`` from on / from off (with and without last-known brightness)
- ``brightness_up`` (always persists; clamps at 100)
- ``brightness_down`` (persists only when > 0; clamps at 0)
- Unknown command / invalid 'set' state -> ValueError

Each assertion documents both the new state AND the persistence intent
(``persist_last_known`` / ``persist_state_payload_brightness``) so that
the legacy dual-persistence path stays observable in tests.
"""

from __future__ import annotations

import pytest

from backend.models.entity import ControlCommand
from backend.services.entity_service import EntityService, _LightCommandDecision

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve(
    *,
    command: str,
    state: str | None = None,
    brightness: int | None = None,
    current_on: bool = False,
    current_brightness_ui: int = 0,
    last_brightness_ui: int = 100,
) -> _LightCommandDecision:
    """Tiny wrapper to keep test bodies focused on inputs/outputs."""
    cmd = ControlCommand(command=command, state=state, brightness=brightness)
    return EntityService._resolve_light_command(
        cmd=cmd,
        current_on=current_on,
        current_brightness_ui=current_brightness_ui,
        last_brightness_ui=last_brightness_ui,
    )


# ---------------------------------------------------------------------------
# 'set' command
# ---------------------------------------------------------------------------


class TestSetCommand:
    def test_set_on_uses_explicit_brightness(self):
        d = _resolve(command="set", state="on", brightness=75, current_on=False)
        assert d.new_state is True
        assert d.new_brightness == 75
        assert "Set ON to 75%" in d.action
        assert d.persist_last_known == 75
        assert d.persist_state_payload_brightness is False

    def test_set_on_without_brightness_uses_last_known(self):
        d = _resolve(command="set", state="on", current_on=False, last_brightness_ui=42)
        assert d.new_state is True
        assert d.new_brightness == 42
        assert d.persist_last_known == 42

    def test_set_on_with_zero_brightness_remaps_to_100(self):
        """Defensive: 'on at 0%' shouldn't silently turn the light off.

        Pre-refactor code mapped this to 100; we preserve that behavior.
        """
        d = _resolve(command="set", state="on", brightness=0)
        assert d.new_state is True
        assert d.new_brightness == 100
        # Action label still reflects what the caller asked for.
        assert "0%" in d.action

    def test_set_off_when_currently_on_emits_state_payload_persist(self):
        d = _resolve(command="set", state="off", current_on=True, current_brightness_ui=80)
        assert d.new_state is False
        assert d.new_brightness == 0
        assert d.action == "Set OFF"
        # Legacy 'set off' path uses entity-payload persistence, NOT
        # set_last_known_brightness.
        assert d.persist_state_payload_brightness is True
        assert d.persist_last_known is None

    def test_set_off_when_already_off_does_not_persist(self):
        d = _resolve(command="set", state="off", current_on=False)
        assert d.new_state is False
        assert d.new_brightness == 0
        # Only persists if the light was actually on -- matches
        # pre-refactor branch.
        assert d.persist_state_payload_brightness is False
        assert d.persist_last_known is None

    def test_set_with_brightness_but_no_state_implies_on(self):
        """The legacy normalization: 'set' + brightness + no state -> 'on'."""
        d = _resolve(command="set", state=None, brightness=60)
        assert d.new_state is True
        assert d.new_brightness == 60
        assert d.persist_last_known == 60

    def test_set_with_invalid_state_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid state for set command"):
            _resolve(command="set", state="dim")  # not 'on'/'off'


# ---------------------------------------------------------------------------
# 'toggle' command
# ---------------------------------------------------------------------------


class TestToggleCommand:
    def test_toggle_from_off_uses_last_known_brightness(self):
        d = _resolve(command="toggle", current_on=False, last_brightness_ui=65)
        assert d.new_state is True
        assert d.new_brightness == 65
        assert "Toggled ON to 65%" in d.action
        # Toggle-on doesn't write last-known (we're restoring it, not setting it).
        assert d.persist_last_known is None

    def test_toggle_from_off_with_zero_last_known_defaults_to_100(self):
        """If last_known is 0 (or invalid), toggle-on goes to full brightness."""
        d = _resolve(command="toggle", current_on=False, last_brightness_ui=0)
        assert d.new_state is True
        assert d.new_brightness == 100

    def test_toggle_from_on_persists_current_brightness(self):
        d = _resolve(command="toggle", current_on=True, current_brightness_ui=72)
        assert d.new_state is False
        assert d.new_brightness == 0
        assert d.action == "Toggled OFF"
        # Toggle-off captures the brightness we were just at, so a
        # subsequent toggle-on can restore it.
        assert d.persist_last_known == 72


# ---------------------------------------------------------------------------
# brightness_up / brightness_down
# ---------------------------------------------------------------------------


class TestBrightnessStep:
    def test_brightness_up_increments_by_10(self):
        d = _resolve(command="brightness_up", current_brightness_ui=40)
        assert d.new_state is True
        assert d.new_brightness == 50
        assert "Brightness up to 50%" in d.action
        assert d.persist_last_known == 50

    def test_brightness_up_clamps_at_100(self):
        d = _resolve(command="brightness_up", current_brightness_ui=95)
        assert d.new_brightness == 100
        assert d.persist_last_known == 100

    def test_brightness_up_from_zero_turns_on(self):
        d = _resolve(command="brightness_up", current_brightness_ui=0)
        assert d.new_state is True
        assert d.new_brightness == 10
        assert d.persist_last_known == 10

    def test_brightness_down_decrements_by_10(self):
        d = _resolve(command="brightness_down", current_brightness_ui=40)
        assert d.new_state is True
        assert d.new_brightness == 30
        assert d.persist_last_known == 30

    def test_brightness_down_clamps_at_0_and_does_not_persist(self):
        """brightness_down to 0 must NOT overwrite last-known with 0.

        Otherwise a subsequent 'toggle on' would restore to 0% (= off),
        which would be confusing and reproduces a known UX bug from
        pre-refactor versions.
        """
        d = _resolve(command="brightness_down", current_brightness_ui=5)
        assert d.new_state is False
        assert d.new_brightness == 0
        # Critical: don't write 0 to last-known.
        assert d.persist_last_known is None

    def test_brightness_down_above_zero_persists(self):
        d = _resolve(command="brightness_down", current_brightness_ui=80)
        assert d.new_brightness == 70
        assert d.persist_last_known == 70


# ---------------------------------------------------------------------------
# Unknown commands
# ---------------------------------------------------------------------------


class TestUnknownCommand:
    def test_unknown_command_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown command"):
            _resolve(command="dance_party")
