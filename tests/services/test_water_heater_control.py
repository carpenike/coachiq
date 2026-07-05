"""Aqua-Hot / water heater control: encoder, mode resolution, tank/temp shaping.

The command dialect (WATERHEATER_COMMAND, DGN 1FFF6) is NOT yet wire-verified
against the coach's Aqua-Hot node — these tests pin the encoding and the
service-layer bit composition so the eventual wire test only has to confirm
the node honors the frame.
"""

import pytest

from backend.integrations.can.message_factory import create_water_heater_can_message
from backend.integrations.rvc import climate_units
from backend.services.entities.entity_domain_service import (
    EntityDomainService,
    SafetyControlCommandV2,
)
from backend.services.entities.entity_service import EntityService

pytestmark = [pytest.mark.unit]


def test_water_heater_command_frame() -> None:
    msg = create_water_heater_can_message(instance=1, operating_mode=3)
    assert msg.arbitration_id == 0x19FFF6F9  # prio 6, DGN 1FFF6, SA F9
    assert msg.is_extended_id
    # instance, mode, then setpoint = no-change sentinel
    assert msg.data == bytes([0x01, 0x03, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])


@pytest.mark.parametrize(
    ("params", "current_mode", "expected_mode"),
    [
        ({"electric": True}, 0, 2),  # off -> electric
        ({"burner": True}, 2, 3),  # electric on, add burner -> gas/electric
        ({"burner": False}, 3, 2),  # drop burner, keep electric
        ({"electric": False, "burner": False}, 3, 0),  # all off
        ({"mode": "automatic"}, 0, 4),  # explicit mode label
        ({"mode": "off"}, 3, 0),
    ],
)
def test_resolve_mode(params: dict, current_mode: int, expected_mode: int) -> None:
    mode, _action = EntityService._resolve_water_heater_mode(
        params, {"operating_mode": current_mode}
    )
    assert mode == expected_mode


def test_bit_toggle_preserves_the_other_bit() -> None:
    # Turning the burner on must not clear a running electric element.
    mode, _ = EntityService._resolve_water_heater_mode({"burner": True}, {"operating_mode": 2})
    burner_on, electric_on = climate_units.water_heater_mode_bits({"operating_mode": mode})
    assert burner_on
    assert electric_on


@pytest.mark.parametrize(
    ("params", "match"),
    [
        ({}, "requires parameters"),
        ({"bogus": True}, "Unknown water heater parameters"),
        ({"mode": "nuclear"}, "Unknown water heater mode"),
    ],
)
def test_resolve_mode_rejects_bad_params(params: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        EntityService._resolve_water_heater_mode(params, {"operating_mode": 0})


def test_expected_ack_only_for_explicit_mode() -> None:
    # An explicit mode is ack-verifiable; bit toggles are not (resolved
    # against live state in the service), so they yield no expectation.
    cmd = SafetyControlCommandV2(command="set", parameters={"mode": "electric"})
    assert EntityDomainService._expected_water_heater_raw(cmd) == {"operating_mode": (2, 0)}

    cmd2 = SafetyControlCommandV2(command="set", parameters={"burner": True})
    assert EntityDomainService._expected_water_heater_raw(cmd2) == {}


# --- tank + temperature shaping ------------------------------------------------


@pytest.mark.parametrize(
    ("level", "resolution", "pct"),
    [
        (3, 28, 11),  # observed fresh-tank frame
        (24, 24, 100),  # full
        (0, 24, 0),  # empty
        (0xFF, 24, None),  # sensor unavailable
    ],
)
def test_tank_level(level: int, resolution: int, pct: int | None) -> None:
    raw = {"relative_level": level, "resolution": resolution}
    assert climate_units.derive_tank_fields(raw).get("level_pct") == pct


def test_temperature_label() -> None:
    # THERMOSTAT_AMBIENT_STATUS raw at ~91 F
    raw = {"ambient_temperature": climate_units.f_to_raw_temp(91)}
    assert climate_units.temperature_state_label(raw) == "91°F"
    assert climate_units.temperature_state_label({}) == "unknown"
