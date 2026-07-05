"""Climate control: units, encoder, command resolution, ack targets.

Wire values in these tests come from the 2021 Aspire 44R bus survey
(2026-07-04): the G6 broadcasts THERMOSTAT_STATUS_1 payloads like
``00 11 64 BA 24 BA 24 00`` (instance 0, cool, fan on 50%, both
setpoints 69.5F) and THERMOSTAT_AMBIENT_STATUS like ``00 5F 25 ...``
(78.7F). See docs/can-re-findings.md.
"""

import pytest

from backend.integrations.can.message_factory import create_thermostat_can_message
from backend.integrations.rvc import climate_units
from backend.services.entities.entity_domain_service import (
    EntityDomainService,
    SafetyControlCommandV2,
)
from backend.services.entities.entity_service import EntityService

pytestmark = [pytest.mark.unit]


def _cmd(**kw) -> SafetyControlCommandV2:
    return SafetyControlCommandV2(**kw)


# --- unit conversions -------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "fahrenheit"),
    [
        (0x24BA, 69.5),  # observed front-zone setpoint
        (0x255F, 78.7),  # observed front-zone ambient
        (0x26E1, 100.5),  # observed floor-heat setpoint
    ],
)
def test_raw_temp_to_f_observed_values(raw: int, fahrenheit: float) -> None:
    assert climate_units.raw_temp_to_f(raw) == fahrenheit


def test_raw_temp_sentinels_map_to_none() -> None:
    assert climate_units.raw_temp_to_f(0xFFFF) is None  # RV-C "not available"
    assert climate_units.raw_temp_to_f(0x1705) is None  # bay sensor-absent (-88C)
    assert climate_units.raw_temp_to_f(None) is None


@pytest.mark.parametrize("fahrenheit", [40.0, 68.0, 69.5, 72.0, 100.5, 105.0])
def test_f_raw_round_trip(fahrenheit: float) -> None:
    raw = climate_units.f_to_raw_temp(fahrenheit)
    assert climate_units.raw_temp_to_f(raw) == pytest.approx(fahrenheit, abs=0.1)


def test_derive_climate_fields() -> None:
    raw = {
        "ambient_temperature": 0x255F,
        "setpoint_heat": 0x24BA,
        "setpoint_cool": 0x24BA,
        "fan_speed": 100,
        "operating_mode": 1,
    }
    derived = climate_units.derive_climate_fields(raw)
    assert derived == {
        "current_temp_f": 78.7,
        "setpoint_heat_f": 69.5,
        "setpoint_cool_f": 69.5,
        "fan_speed_pct": 50,
    }
    assert climate_units.climate_state_label(raw) == "cool"


# --- encoder ----------------------------------------------------------------


def test_thermostat_command_frame_layout() -> None:
    """Payload must mirror the THERMOSTAT_STATUS_1 layout the G6 broadcasts."""
    msg = create_thermostat_can_message(
        instance=2,
        operating_mode=1,
        fan_mode=1,
        schedule_mode=0,
        fan_speed_raw=100,
        setpoint_heat_raw=0x24BA,
        setpoint_cool_raw=0x24BA,
    )
    assert msg.arbitration_id == 0x19FEF9F9  # prio 6, DGN 1FEF9, SA F9
    assert msg.is_extended_id
    assert msg.data == bytes([0x02, 0x11, 0x64, 0xBA, 0x24, 0xBA, 0x24, 0xFF])


# --- command resolution -----------------------------------------------------

_CURRENT = {
    "operating_mode": 1,
    "fan_mode": 1,
    "schedule_mode": 0,
    "fan_speed": 100,
    "setpoint_heat": 0x24BA,
    "setpoint_cool": 0x24BA,
}


def test_resolve_setpoint_drives_both_setpoints() -> None:
    decision = EntityService._resolve_climate_command({"setpoint_f": 72}, dict(_CURRENT))
    assert decision.setpoint_heat_raw == decision.setpoint_cool_raw
    assert climate_units.raw_temp_to_f(decision.setpoint_heat_raw) == pytest.approx(72, abs=0.1)
    # untouched fields carry the live zone state
    assert decision.operating_mode == 1
    assert decision.fan_speed_raw == 100
    assert decision.state_label == "cool"


def test_resolve_mode_change_keeps_setpoints() -> None:
    decision = EntityService._resolve_climate_command({"mode": "off"}, dict(_CURRENT))
    assert decision.operating_mode == 0
    assert decision.state_label == "off"
    assert decision.setpoint_heat_raw == 0x24BA


def test_resolve_fan_controls() -> None:
    decision = EntityService._resolve_climate_command(
        {"fan_mode": "on", "fan_speed_pct": 100}, dict(_CURRENT)
    )
    assert decision.fan_mode == 1
    assert decision.fan_speed_raw == 200


@pytest.mark.parametrize(
    ("params", "match"),
    [
        ({}, "requires parameters"),
        ({"bogus": 1}, "Unknown climate parameters"),
        ({"mode": "arctic"}, "Unknown climate mode"),
        ({"setpoint_f": 30}, "setpoint_f must be"),
        ({"setpoint_f": 130}, "setpoint_f must be"),
        ({"fan_speed_pct": 150}, "fan_speed_pct must be"),
    ],
)
def test_resolve_rejects_bad_parameters(params: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        EntityService._resolve_climate_command(params, dict(_CURRENT))


def test_read_climate_current_raw_requires_live_state() -> None:
    with pytest.raises(ValueError, match="No live thermostat state"):
        EntityService._read_climate_current_raw("climate_front", {"raw": {}})


def test_read_climate_current_raw_defaults_schedule_mode() -> None:
    raw = {k: v for k, v in _CURRENT.items() if k != "schedule_mode"}
    current = EntityService._read_climate_current_raw("climate_front", {"raw": raw})
    assert current["schedule_mode"] == 0


# --- acknowledgment targets ---------------------------------------------------


def test_expected_climate_raw_setpoint() -> None:
    cmd = _cmd(command="set", parameters={"setpoint_f": 72})
    expected = EntityDomainService._expected_climate_raw(cmd)
    raw_72 = climate_units.f_to_raw_temp(72)
    assert expected == {
        "setpoint_heat": (raw_72, 16),
        "setpoint_cool": (raw_72, 16),
    }


def test_expected_climate_raw_mode_and_fan() -> None:
    cmd = _cmd(
        command="set",
        parameters={"mode": "cool", "fan_mode": "auto", "fan_speed_pct": 50},
    )
    expected = EntityDomainService._expected_climate_raw(cmd)
    assert expected["operating_mode"] == (1, 0)
    assert expected["fan_mode"] == (0, 0)
    assert expected["fan_speed"] == (100, 4)
