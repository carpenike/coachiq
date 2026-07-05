"""Energy-managed AC load control (Aqua-Hot electric/burner) + tank/temp shaping.

The Aqua-Hot electric element (AC_LOAD instance 0xD4) and burner (0xD2) are
controlled via AC_LOAD_COMMAND (1FFBE) and report on/off/shed via
AC_LOAD_STATUS (1FFBF) level: 0xC8 on, 0x00 off, 0xFD shed. All values
verified on the coach 2026-07-05 (docs/can-re-findings.md).
"""

import pytest

from backend.integrations.can.message_factory import create_ac_load_can_message
from backend.integrations.rvc import climate_units
from backend.services.entities.entity_domain_service import (
    EntityDomainService,
    SafetyControlCommandV2,
)

pytestmark = [pytest.mark.unit]


# --- encoder -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("instance", "level"),
    [(0xD4, 0xC8), (0xD4, 0x00), (0xD2, 0xC8), (0xD2, 0x00)],
)
def test_ac_load_command_frame(instance: int, level: int) -> None:
    msg = create_ac_load_can_message(instance=instance, level=level)
    assert msg.arbitration_id == 0x19FFBEF9  # prio 6, DGN 1FFBE, SA F9
    assert msg.is_extended_id
    assert msg.data[0] == instance
    assert msg.data[2] == level  # byte 2 = desired level


# --- on/off/shed decode --------------------------------------------------------


@pytest.mark.parametrize(
    ("level", "state", "shed"),
    [
        (0xC8, "on", False),  # energized (observed)
        (0x00, "off", False),
        (0xFD, "shed", True),  # requested but deferred (observed while Mira showed "Shed")
        (0xFC, "shed", True),  # load-delay-active variant
    ],
)
def test_ac_load_state(level: int, state: str, shed: bool) -> None:
    label, is_shed = climate_units.ac_load_state({"operating_status": level})
    assert label == state
    assert is_shed is shed


def test_ac_load_derived_fields() -> None:
    # requested_on stays True while shed (mirrors the Mira: button on + "Shed")
    assert climate_units.derive_ac_load_fields({"operating_status": 0xFD}) == {
        "shed": True,
        "requested_on": True,
    }
    assert climate_units.derive_ac_load_fields({"operating_status": 0x00}) == {
        "shed": False,
        "requested_on": False,
    }


# --- acknowledgment ------------------------------------------------------------


def test_off_is_ack_verifiable() -> None:
    cmd = SafetyControlCommandV2(command="set", state=False)
    assert EntityDomainService._expected_ac_load_raw(cmd) == {"operating_status": (0x00, 0)}


def test_on_has_no_ack_expectation_because_it_may_shed() -> None:
    # ON is a request; the energy manager may shed it, so we don't assert a
    # target level - the AC_LOAD_STATUS echo drives on-vs-shed in the UI.
    cmd = SafetyControlCommandV2(command="set", state=True)
    assert EntityDomainService._expected_ac_load_raw(cmd) == {}
    assert EntityDomainService._expected_ac_load_raw(SafetyControlCommandV2(command="toggle")) == {}


# --- tank + temperature shaping (unchanged, still on the RX path) --------------


@pytest.mark.parametrize(
    ("level", "resolution", "pct"),
    [
        (3, 28, 11),  # observed fresh-tank frame
        (24, 24, 100),
        (0, 24, 0),
        (0xFF, 24, None),  # sensor unavailable
    ],
)
def test_tank_level(level: int, resolution: int, pct: int | None) -> None:
    raw = {"relative_level": level, "resolution": resolution}
    assert climate_units.derive_tank_fields(raw).get("level_pct") == pct


def test_temperature_label() -> None:
    raw = {"ambient_temperature": climate_units.f_to_raw_temp(91)}
    assert climate_units.temperature_state_label(raw) == "91°F"
    assert climate_units.temperature_state_label({}) == "unknown"
