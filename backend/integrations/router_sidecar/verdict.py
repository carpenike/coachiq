"""Pure Starlink verdict evaluation for RouterOS failover."""

from dataclasses import dataclass
from datetime import UTC, datetime
import math
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

_READY_STATE_SIGNALS = {"scp", "l1l2", "xphy", "aap", "rf"}
_OK_DISABLEMENT_CODES = {None, "OKAY", "DISABLEMENT_CODE_OKAY"}


@dataclass(frozen=True, slots=True)
class StarlinkVerdictConfig:
    """Thresholds for Starlink verdict evaluation."""

    obstruction_fraction_degraded: float
    obstruction_fraction_recovery: float
    pop_ping_drop_rate_degraded: float
    pop_ping_drop_rate_recovery: float
    pop_ping_latency_ms_degraded: float
    pop_ping_latency_ms_recovery: float
    recent_outage_count_degraded: int
    history_sample_window: int
    degraded_debounce_seconds: float
    down_recovery_dwell_seconds: float


class StarlinkVerdictEvaluator:
    """Evaluate Starlink status/history snapshots with degraded debounce."""

    def __init__(self, config: StarlinkVerdictConfig) -> None:
        self._config = config
        self._committed_verdict: StarlinkVerdict = "unknown"
        self._candidate_verdict: StarlinkVerdict | None = None
        self._candidate_since: datetime | None = None

    def evaluate(
        self,
        snapshot: StarlinkSnapshot,
        now: datetime | None = None,
    ) -> StarlinkVerdict:
        """Return a debounced Starlink verdict."""
        current_time = now or datetime.now(UTC)
        target = self._target_verdict(snapshot)

        if target in {"down", "unknown"}:
            self._commit(target)
            return self._committed_verdict

        if self._committed_verdict == "unknown" and target == "healthy":
            self._commit(target)
            return self._committed_verdict

        if self._committed_verdict == "unknown":
            self._committed_verdict = "healthy"

        if target == self._committed_verdict:
            self._clear_candidate()
            return self._committed_verdict

        dwell_seconds = (
            self._config.down_recovery_dwell_seconds
            if self._committed_verdict == "down"
            else self._config.degraded_debounce_seconds
        )
        if self._candidate_verdict != target:
            self._candidate_verdict = target
            self._candidate_since = current_time
            return self._committed_verdict

        candidate_since = self._candidate_since or current_time
        if (current_time - candidate_since).total_seconds() >= dwell_seconds:
            self._commit(target)

        return self._committed_verdict

    def _target_verdict(self, snapshot: StarlinkSnapshot) -> StarlinkVerdict:
        if not snapshot.reachable:
            return "unknown"
        if self._is_immediate_down(snapshot.status):
            return "down"
        return "degraded" if self._is_degraded(snapshot) else "healthy"

    def _commit(self, verdict: StarlinkVerdict) -> None:
        self._committed_verdict = verdict
        self._clear_candidate()

    def _clear_candidate(self) -> None:
        self._candidate_verdict = None
        self._candidate_since = None

    def _is_immediate_down(self, status: dict[str, Any]) -> bool:
        return (
            bool(status.get("outage"))
            or status.get("disablement_code") not in _OK_DISABLEMENT_CODES
        )

    def _is_degraded(self, snapshot: StarlinkSnapshot) -> bool:
        status = snapshot.status
        obstruction = status.get("obstruction_stats") or {}
        in_degraded_context = (
            self._committed_verdict == "degraded" or self._candidate_verdict == "degraded"
        )
        fraction_threshold = (
            self._config.obstruction_fraction_recovery
            if in_degraded_context
            else self._config.obstruction_fraction_degraded
        )
        drop_threshold = (
            self._config.pop_ping_drop_rate_recovery
            if in_degraded_context
            else self._config.pop_ping_drop_rate_degraded
        )
        latency_threshold = (
            self._config.pop_ping_latency_ms_recovery
            if in_degraded_context
            else self._config.pop_ping_latency_ms_degraded
        )
        fraction_obstructed = _valid_float(obstruction.get("fraction_obstructed"))
        alerts = status.get("alerts") or {}
        history = snapshot.history
        outages = history.get("outages") or []

        return any(
            (
                fraction_obstructed is not None and fraction_obstructed > fraction_threshold,
                obstruction.get("currently_obstructed") is True,
                _float_or_zero(status.get("pop_ping_drop_rate")) > drop_threshold,
                _float_or_zero(status.get("pop_ping_latency_ms")) > latency_threshold,
                any(alerts.get(alert_name) is True for alert_name in _DEGRADING_ALERTS),
                any(
                    status.get("ready_states", {}).get(name) is False
                    for name in _READY_STATE_SIGNALS
                ),
                status.get("is_snr_above_noise_floor") is False,
                _recent_average(
                    history.get("pop_ping_drop_rate"), self._config.history_sample_window
                )
                > drop_threshold,
                _recent_average(
                    history.get("pop_ping_latency_ms"), self._config.history_sample_window
                )
                > latency_threshold,
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
    result = _valid_float(value)
    return result if result is not None else 0.0


def _valid_float(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(result) or math.isinf(result) else result


def _recent_average(values: Any, sample_window: int) -> float:
    if not isinstance(values, list) or not values:
        return 0.0
    recent = values[-sample_window:]
    numeric = [_float_or_zero(value) for value in recent]
    return sum(numeric) / len(numeric) if numeric else 0.0
