"""Pure Starlink verdict evaluation for RouterOS failover."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from backend.integrations.router_sidecar.starlink import StarlinkSnapshot

StarlinkVerdict = Literal["healthy", "degraded", "down", "unknown"]

_DEGRADING_ALERTS = {
    "motors_stuck",
    "thermal_shutdown",
    "thermal_throttle",
    "mast_not_near_vertical",
    "power_supply_thermal_throttle",
    "lower_signal_than_predicted",
    "obstruction_map_reset",
    "dish_water_detected",
    "router_water_detected",
    "no_ethernet_link",
}


@dataclass(frozen=True, slots=True)
class StarlinkVerdictConfig:
    """Thresholds for Starlink verdict evaluation."""

    obstruction_fraction_degraded: float
    pop_ping_drop_rate_degraded: float
    pop_ping_latency_ms_degraded: float
    recent_outage_count_degraded: int
    history_sample_window: int
    degraded_debounce_seconds: float


class StarlinkVerdictEvaluator:
    """Evaluate Starlink status/history snapshots with degraded debounce."""

    def __init__(self, config: StarlinkVerdictConfig) -> None:
        self._config = config
        self._degraded_since: datetime | None = None

    def evaluate(
        self,
        snapshot: StarlinkSnapshot,
        now: datetime | None = None,
    ) -> StarlinkVerdict:
        """Return a debounced Starlink verdict."""
        current_time = now or datetime.now(UTC)
        if not snapshot.reachable:
            self._degraded_since = None
            verdict: StarlinkVerdict = "unknown"
        elif snapshot.status.get("outage"):
            self._degraded_since = None
            verdict = "down"
        elif self._is_degraded(snapshot):
            if self._degraded_since is None:
                self._degraded_since = current_time
                verdict = "healthy"
            else:
                elapsed = (current_time - self._degraded_since).total_seconds()
                verdict = (
                    "degraded" if elapsed >= self._config.degraded_debounce_seconds else "healthy"
                )
        else:
            self._degraded_since = None
            verdict = "healthy"
        return verdict

    def _is_degraded(self, snapshot: StarlinkSnapshot) -> bool:
        status = snapshot.status
        obstruction = status.get("obstruction_stats") or {}
        fraction_obstructed = _float_or_zero(obstruction.get("fraction_obstructed"))
        alerts = status.get("alerts") or {}
        history = snapshot.history
        outages = history.get("outages") or []

        return any(
            (
                fraction_obstructed > self._config.obstruction_fraction_degraded,
                obstruction.get("currently_obstructed") is True,
                _float_or_zero(status.get("pop_ping_drop_rate"))
                > self._config.pop_ping_drop_rate_degraded,
                _float_or_zero(status.get("pop_ping_latency_ms"))
                > self._config.pop_ping_latency_ms_degraded,
                any(alerts.get(alert_name) is True for alert_name in _DEGRADING_ALERTS),
                _recent_average(
                    history.get("pop_ping_drop_rate"), self._config.history_sample_window
                )
                > self._config.pop_ping_drop_rate_degraded,
                _recent_average(
                    history.get("pop_ping_latency_ms"), self._config.history_sample_window
                )
                > self._config.pop_ping_latency_ms_degraded,
                len(outages) >= self._config.recent_outage_count_degraded,
            )
        )


def format_starlink_raw(snapshot: StarlinkSnapshot) -> str:
    """Format a compact RouterOS-friendly debug line."""
    if not snapshot.reachable:
        return "reachable=0"
    status = snapshot.status
    history = snapshot.history
    obstruction = status.get("obstruction_stats") or {}
    alerts = status.get("alerts") or {}
    ready_states = status.get("ready_states") or {}
    ready_values = [value for key, value in ready_states.items() if key != "cady"]
    ready = int(bool(ready_values) and all(value is True for value in ready_values))
    thermal = int(
        alerts.get("thermal_shutdown") is True
        or alerts.get("thermal_throttle") is True
        or alerts.get("power_supply_thermal_throttle") is True
    )
    drop_avg = _recent_average(history.get("pop_ping_drop_rate"), 60)
    latency_avg = _recent_average(history.get("pop_ping_latency_ms"), 60)
    alignment = status.get("alignment_stats") or {}
    sw_update = status.get("software_update_state", "UNKNOWN")
    return (
        f"obstruct={_float_or_zero(obstruction.get('fraction_obstructed')) * 100:.2f} "
        f"outage={int(bool(status.get('outage')))} "
        f"droprate={_float_or_zero(status.get('pop_ping_drop_rate')):.3f} "
        f"lat={_float_or_zero(status.get('pop_ping_latency_ms')):.1f} "
        f"thermal={thermal} ready={ready} "
        f"snr_ok={int(status.get('is_snr_above_noise_floor') is not False)} "
        f"dl_bps={_float_or_zero(status.get('downlink_throughput_bps')):.0f} "
        f"ul_bps={_float_or_zero(status.get('uplink_throughput_bps')):.0f} "
        f"drop_avg={drop_avg:.3f} lat_avg={latency_avg:.1f} "
        f"tilt={_float_or_zero(alignment.get('tilt_angle_deg')):.1f} "
        f"att_uncert={_float_or_zero(alignment.get('attitude_uncertainty_deg')):.1f} "
        f"align_ok={int(alignment.get('attitude_estimation_state') != 'FILTER_RESET')} "
        f"ready_scp={int(ready_states.get('scp') is True)} "
        f"ready_l1l2={int(ready_states.get('l1l2') is True)} "
        f"ready_xphy={int(ready_states.get('xphy') is True)} "
        f"ready_aap={int(ready_states.get('aap') is True)} "
        f"ready_rf={int(ready_states.get('rf') is True)} "
        f"disable_code={status.get('disablement_code', 'UNKNOWN')} "
        f"outages_recent={len(history.get('outages') or [])} sw_update={sw_update}"
    )


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _recent_average(values: Any, sample_window: int) -> float:
    if not isinstance(values, list) or not values:
        return 0.0
    recent = values[-sample_window:]
    numeric = [_float_or_zero(value) for value in recent]
    return sum(numeric) / len(numeric) if numeric else 0.0
