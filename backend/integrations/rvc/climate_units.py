"""
RV-C climate unit conversions and enums, shared by the RX state-shaping path
(can_bus_service) and the TX control path (entity_service.control_climate).

RV-C carries temperatures as uint16 in 1/32 K steps ("Table 5.3"):
    celsius = raw * 0.03125 - 273
The UI works in whole/half degrees Fahrenheit, so helpers convert both ways.
Wire layouts verified on the 2021 Entegra Aspire 44R bus (2026-07-04); see
docs/can-re-findings.md.
"""

from typing import Any

RAW_TEMP_UNAVAILABLE = 0xFFFF

# THERMOSTAT_STATUS_1 / THERMOSTAT_COMMAND_1 operating_mode (4-bit)
OPERATING_MODE_LABELS: dict[int, str] = {
    0: "off",
    1: "cool",
    2: "heat",
    3: "auto",
    4: "fan_only",
    5: "aux_heat",
    6: "window_defrost",
}
OPERATING_MODE_RAW: dict[str, int] = {v: k for k, v in OPERATING_MODE_LABELS.items()}

# fan_mode (2-bit)
FAN_MODE_LABELS: dict[int, str] = {0: "auto", 1: "on"}
FAN_MODE_RAW: dict[str, int] = {v: k for k, v in FAN_MODE_LABELS.items()}

# WATERHEATER_STATUS operating_mode
WATER_HEATER_MODE_LABELS: dict[int, str] = {
    0: "off",
    1: "combustion",
    2: "electric",
    3: "gas_electric",
    4: "automatic",
    5: "test_combustion",
    6: "test_electric",
}

# Fan speed is commanded as a percentage (encoded 0-200 half-percent raw).
FAN_SPEED_MAX_PCT = 100

# Sanity bounds for a zone setpoint command, in Fahrenheit. Floor-heat zones
# legitimately run to ~100F (observed 100.5F on the wire), so the cap sits
# above that but well below anything dangerous.
SETPOINT_MIN_F = 40.0
SETPOINT_MAX_F = 105.0

# Readings below this are treated as "sensor absent" (the bay zone broadcasts
# an impossible -88C when its sensor is disconnected).
_MIN_PLAUSIBLE_C = -40.0


def raw_temp_to_f(raw: Any) -> float | None:
    """Convert a raw RV-C uint16 temperature to Fahrenheit (None if n/a)."""
    try:
        raw_int = int(raw)
    except (TypeError, ValueError):
        return None
    if raw_int == RAW_TEMP_UNAVAILABLE:
        return None
    celsius = raw_int * 0.03125 - 273
    if celsius < _MIN_PLAUSIBLE_C:
        return None
    return round((celsius * 9 / 5 + 32) * 10) / 10


def f_to_raw_temp(fahrenheit: float) -> int:
    """Convert Fahrenheit to the raw RV-C uint16 temperature encoding."""
    celsius = (float(fahrenheit) - 32) * 5 / 9
    raw = round((celsius + 273) * 32)
    return max(0, min(0xFFFE, raw))


def _raw_int(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def derive_climate_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Derived, UI-friendly fields for a thermostat zone's raw signal dict."""
    derived: dict[str, Any] = {}
    ambient = _raw_int(raw, "ambient_temperature")
    if ambient is not None:
        derived["current_temp_f"] = raw_temp_to_f(ambient)
    heat = _raw_int(raw, "setpoint_heat")
    if heat is not None:
        derived["setpoint_heat_f"] = raw_temp_to_f(heat)
    cool = _raw_int(raw, "setpoint_cool")
    if cool is not None:
        derived["setpoint_cool_f"] = raw_temp_to_f(cool)
    fan_speed = _raw_int(raw, "fan_speed")
    if fan_speed is not None:
        derived["fan_speed_pct"] = min(100, round(fan_speed / 2))
    return derived


def climate_state_label(raw: dict[str, Any]) -> str:
    """Human-readable state for a thermostat zone ('cool', 'heat', 'off'...)."""
    mode = _raw_int(raw, "operating_mode")
    if mode is None:
        return "unknown"
    return OPERATING_MODE_LABELS.get(mode, "unknown")


def derive_ac_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Derived fields for AIR_CONDITIONER_STATUS raw signals (0-200 scale)."""
    derived: dict[str, Any] = {}
    fan_speed = _raw_int(raw, "fan_speed")
    if fan_speed is not None:
        derived["fan_speed_pct"] = min(100, round(fan_speed / 2))
    output = _raw_int(raw, "ac_output_level")
    if output is not None:
        derived["output_pct"] = min(100, round(output / 2))
    return derived


def ac_state_label(raw: dict[str, Any]) -> str:
    output = _raw_int(raw, "ac_output_level")
    if output is None:
        return "unknown"
    return "cooling" if output > 0 else "idle"


def derive_water_heater_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Derived fields for WATERHEATER_STATUS raw signals."""
    derived: dict[str, Any] = {}
    temp = _raw_int(raw, "water_temperature")
    if temp is not None:
        derived["water_temp_f"] = raw_temp_to_f(temp)
    setpoint = _raw_int(raw, "setpoint_temperature")
    if setpoint is not None:
        derived["setpoint_f"] = raw_temp_to_f(setpoint)
    return derived


def water_heater_state_label(raw: dict[str, Any]) -> str:
    mode = _raw_int(raw, "operating_mode")
    if mode is None:
        return "unknown"
    return WATER_HEATER_MODE_LABELS.get(mode, "unknown")


def water_heater_mode_bits(raw: dict[str, Any]) -> tuple[bool, bool]:
    """(burner_on, electric_on) from the operating_mode bitfield (1|2 = 3)."""
    mode = _raw_int(raw, "operating_mode") or 0
    return bool(mode & 1), bool(mode & 2)


def derive_tank_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Derived fields for TANK_STATUS raw signals: percentage full."""
    derived: dict[str, Any] = {}
    level = _raw_int(raw, "relative_level")
    resolution = _raw_int(raw, "resolution")
    if level is not None and resolution:
        if level == 0xFF or resolution == 0xFF:
            derived["level_pct"] = None
        else:
            derived["level_pct"] = max(0, min(100, round(level / resolution * 100)))
    return derived


def tank_state_label(raw: dict[str, Any]) -> str:
    pct = derive_tank_fields(raw).get("level_pct")
    return "unknown" if pct is None else f"{pct}%"


def temperature_state_label(raw: dict[str, Any]) -> str:
    ambient = _raw_int(raw, "ambient_temperature")
    fahrenheit = raw_temp_to_f(ambient) if ambient is not None else None
    return "unknown" if fahrenheit is None else f"{round(fahrenheit)}°F"
