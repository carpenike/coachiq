"""
Victron entity catalog.

Declares which Venus OS services become CoachIQ entities and which D-Bus
paths feed which entity signals. Instances are bound at runtime by the
Victron service: the first instance seen for a service type gets the base
entity id, additional instances get an ``_<instance>`` suffix.

Path lists were verified against a live Cerbo GX (Venus OS, dbus-flashmq);
paths that a given system does not publish simply never populate.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# com.victronenergy.vebus /State and solarcharger /State share the charger
# state enum (VE.Bus adds the inverter-side values).
VEBUS_STATE_NAMES: dict[int, str] = {
    0: "off",
    1: "low_power",
    2: "fault",
    3: "bulk",
    4: "absorption",
    5: "float",
    6: "storage",
    7: "equalize",
    8: "passthru",
    9: "inverting",
    10: "power_assist",
    11: "power_supply",
    252: "external_control",
}

# com.victronenergy.system /SystemState/State extends the same enum.
SYSTEM_STATE_NAMES: dict[int, str] = {
    **VEBUS_STATE_NAMES,
    244: "sustain",
    256: "discharging",
    257: "sustain",
    258: "recharge",
    259: "scheduled_recharge",
}

# vebus /Mode (writable when /ModeIsAdjustable is 1).
VEBUS_MODE_NAMES: dict[int, str] = {
    1: "charger_only",
    2: "inverter_only",
    3: "on",
    4: "off",
}

# system /Ac/ActiveIn/Source.
AC_SOURCE_NAMES: dict[int, str] = {
    0: "unavailable",
    1: "grid",
    2: "generator",
    3: "shore",
    240: "inverting",
}


def _vebus_state(values: dict[str, Any]) -> str:
    code = values.get("vebus_state")
    if not isinstance(code, int):
        return "unknown"
    return VEBUS_STATE_NAMES.get(code, f"state_{code}")


# Below this |current| the battery is reported as idle rather than
# charging/discharging (matches GX display hysteresis).
_IDLE_CURRENT_BAND_AMPS = 0.5


def _battery_state(values: dict[str, Any]) -> str:
    current = values.get("current")
    if not isinstance(current, int | float):
        return "unknown"
    if current > _IDLE_CURRENT_BAND_AMPS:
        return "charging"
    if current < -_IDLE_CURRENT_BAND_AMPS:
        return "discharging"
    return "idle"


def _solar_state(values: dict[str, Any]) -> str:
    code = values.get("charge_state_code")
    if not isinstance(code, int):
        return "unknown"
    return VEBUS_STATE_NAMES.get(code, f"state_{code}")


def _system_state(values: dict[str, Any]) -> str:
    code = values.get("system_state")
    if not isinstance(code, int):
        return "unknown"
    return SYSTEM_STATE_NAMES.get(code, f"state_{code}")


# dbus-generator /State.
GENERATOR_STATE_NAMES: dict[int, str] = {
    0: "stopped",
    1: "running",
    2: "warm_up",
    3: "cool_down",
    10: "error",
}


def _generator_state(values: dict[str, Any]) -> str:
    code = values.get("generator_state")
    if not isinstance(code, int):
        return "unknown"
    return GENERATOR_STATE_NAMES.get(code, f"state_{code}")


def _dc_system_state(values: dict[str, Any]) -> str:
    power = values.get("power")
    if not isinstance(power, int | float):
        return "unknown"
    return "active" if abs(power) > 1 else "idle"


def _temperature_state(values: dict[str, Any]) -> str:
    if values.get("low_battery") == 1:
        return "low_battery"
    return "ok" if isinstance(values.get("temperature"), int | float) else "unknown"


def _temperature_extras(values: dict[str, Any]) -> dict[str, Any]:
    """Convert Venus °C to the `current_temp_f` field the climate UI reads."""
    celsius = values.get("temperature")
    if not isinstance(celsius, int | float):
        return {}
    return {"current_temp_f": round(celsius * 9 / 5 + 32, 1)}


def _gps_state(values: dict[str, Any]) -> str:
    fix = values.get("fix")
    if not isinstance(fix, int):
        return "unknown"
    return "fix" if fix == 1 else "no_fix"


@dataclass(frozen=True)
class VictronEntityDef:
    """Maps one Venus OS service type onto a CoachIQ entity."""

    key: str  # base entity id
    service_type: str  # Venus OS service type in MQTT topics (e.g. "vebus")
    device_type: str
    friendly_name: str
    # D-Bus path (relative to the service) -> signal name in the entity value dict.
    paths: dict[str, str] = field(default_factory=dict)
    capabilities: tuple[str, ...] = ()
    suggested_area: str = "electrical"
    # Derives the human-readable entity state string from the signal dict.
    state_fn: Callable[[dict[str, Any]], str] = _system_state
    # Optional extra derived signals (e.g. unit conversions) merged in at flush.
    derive_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


VICTRON_ENTITY_DEFS: tuple[VictronEntityDef, ...] = (
    VictronEntityDef(
        key="victron_inverter_charger",
        service_type="vebus",
        device_type="inverter_charger",
        friendly_name="Inverter/Charger",
        state_fn=_vebus_state,
        capabilities=("set_mode", "set_input_current_limit"),
        paths={
            "State": "vebus_state",
            "Mode": "mode",
            "ModeIsAdjustable": "mode_adjustable",
            "VebusChargeState": "charge_state_code",
            "Ac/ActiveIn/Connected": "ac_in_connected",
            "Ac/ActiveIn/ActiveInput": "active_input",
            "Ac/ActiveIn/CurrentLimit": "input_current_limit",
            "Ac/ActiveIn/CurrentLimitIsAdjustable": "input_current_limit_adjustable",
            "Ac/ActiveIn/P": "ac_in_power",
            "Ac/ActiveIn/L1/V": "ac_in_l1_voltage",
            "Ac/ActiveIn/L1/I": "ac_in_l1_current",
            "Ac/ActiveIn/L1/P": "ac_in_l1_power",
            "Ac/ActiveIn/L1/F": "ac_in_frequency",
            "Ac/ActiveIn/L2/V": "ac_in_l2_voltage",
            "Ac/ActiveIn/L2/I": "ac_in_l2_current",
            "Ac/ActiveIn/L2/P": "ac_in_l2_power",
            "Ac/Out/P": "ac_out_power",
            "Ac/Out/L1/V": "ac_out_l1_voltage",
            "Ac/Out/L1/I": "ac_out_l1_current",
            "Ac/Out/L1/P": "ac_out_l1_power",
            "Ac/Out/L1/F": "ac_out_frequency",
            "Ac/Out/L2/V": "ac_out_l2_voltage",
            "Ac/Out/L2/I": "ac_out_l2_current",
            "Ac/Out/L2/P": "ac_out_l2_power",
            "Ac/State/AcIn1Available": "ac_in1_available",
            "Ac/State/AcIn2Available": "ac_in2_available",
            "Dc/0/Voltage": "dc_voltage",
            "Dc/0/Current": "dc_current",
            "Dc/0/Power": "dc_power",
        },
    ),
    VictronEntityDef(
        key="victron_battery",
        service_type="battery",
        device_type="battery",
        friendly_name="House Battery",
        state_fn=_battery_state,
        paths={
            "Soc": "soc",
            "Dc/0/Voltage": "voltage",
            "Dc/0/Current": "current",
            "Dc/0/Power": "power",
            "Dc/0/Temperature": "temperature",
            "Info/MaxChargeCurrent": "max_charge_current",
            "Info/MaxChargeVoltage": "max_charge_voltage",
            "Info/MaxDischargeCurrent": "max_discharge_current",
            "System/MinCellVoltage": "min_cell_voltage",
            "System/MaxCellVoltage": "max_cell_voltage",
            "ProductName": "product_name",
        },
    ),
    VictronEntityDef(
        key="victron_solar",
        service_type="solarcharger",
        device_type="solar_controller",
        friendly_name="Solar Charger",
        state_fn=_solar_state,
        paths={
            "State": "charge_state_code",
            "MppOperationMode": "mpp_operation_mode",
            "Yield/Power": "pv_power",
            "Pv/V": "pv_voltage",
            "Dc/0/Voltage": "battery_voltage",
            "Dc/0/Current": "battery_current",
            "Yield/User": "yield_total_kwh",
            "History/Daily/0/Yield": "yield_today_kwh",
        },
    ),
    VictronEntityDef(
        key="victron_generator",
        service_type="generator",
        device_type="generator",
        friendly_name="Generator",
        state_fn=_generator_state,
        paths={
            "State": "generator_state",
            "Error": "error_code",
            "Runtime": "runtime_seconds",
            "TodayRuntime": "runtime_today_seconds",
            "AccumulatedRuntime": "runtime_total_seconds",
            "ManualStart": "manual_start",
            "AutoStartEnabled": "autostart_enabled",
            "RunningByCondition": "running_by_condition",
            "QuietHours": "quiet_hours",
        },
    ),
    VictronEntityDef(
        key="victron_dc_loads",
        service_type="dcsystem",
        device_type="dc_system",
        friendly_name="DC Loads",
        state_fn=_dc_system_state,
        paths={
            "Dc/0/Power": "power",
            "Dc/0/Voltage": "voltage",
            "Dc/0/Current": "current",
            "ProductName": "product_name",
        },
    ),
    VictronEntityDef(
        key="victron_temperature",
        service_type="temperature",
        device_type="temperature",
        friendly_name="Temperature Sensor",
        state_fn=_temperature_state,
        derive_fn=_temperature_extras,
        paths={
            "Temperature": "temperature",
            "Humidity": "humidity",
            "CustomName": "custom_name",
            "BatteryVoltage": "sensor_battery_voltage",
            "Alarms/LowBattery": "low_battery",
        },
    ),
    VictronEntityDef(
        key="victron_gps",
        service_type="gps",
        device_type="gps",
        friendly_name="GPS",
        state_fn=_gps_state,
        paths={
            "Fix": "fix",
            "Position/Latitude": "latitude",
            "Position/Longitude": "longitude",
            "Speed": "speed_mps",
            "Course": "course_deg",
            "Altitude": "altitude_m",
            "NrOfSatellites": "satellites",
        },
    ),
    VictronEntityDef(
        key="victron_power_system",
        service_type="system",
        device_type="power_system",
        friendly_name="Power System",
        state_fn=_system_state,
        paths={
            "SystemState/State": "system_state",
            "Dc/Battery/Soc": "battery_soc",
            "Dc/Battery/Power": "battery_power",
            "Dc/Battery/Voltage": "battery_voltage",
            "Dc/Battery/Current": "battery_current",
            "Dc/Battery/Temperature": "battery_temperature",
            "Dc/Pv/Power": "pv_power",
            "Ac/ActiveIn/Source": "ac_source_code",
            "Ac/ActiveIn/L1/Power": "ac_in_l1_power",
            "Ac/ActiveIn/L2/Power": "ac_in_l2_power",
            "Ac/Consumption/L1/Power": "ac_loads_l1_power",
            "Ac/Consumption/L2/Power": "ac_loads_l2_power",
        },
    ),
)

# service_type -> (path -> signal name), for O(1) update routing.
PATHS_BY_SERVICE_TYPE: dict[str, dict[str, str]] = {
    entity_def.service_type: entity_def.paths for entity_def in VICTRON_ENTITY_DEFS
}

DEFS_BY_SERVICE_TYPE: dict[str, VictronEntityDef] = {
    entity_def.service_type: entity_def for entity_def in VICTRON_ENTITY_DEFS
}
