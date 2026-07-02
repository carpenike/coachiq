"""Pure Starlink verdict evaluation for RouterOS failover."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from backend.integrations.router_sidecar.starlink import StarlinkSnapshot

StarlinkVerdict = Literal["healthy", "degraded", "down", "unknown"]

_DEGRADING_ALERTS = {
    "motorsStuck",
    "thermalShutdown",
    "thermalThrottle",
    "mastNotNearVertical",
    "powerSupplyThermalThrottle",
    "lowerSignalThanPredicted",
    "obstructionMapReset",
    "dishWaterDetected",
    "routerWaterDetected",
    "noEthernetLink",
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
            return "unknown"

        if snapshot.status.get("outage"):
            self._degraded_since = None
            return "down"

        if self._is_degraded(snapshot):
            if self._degraded_since is None:
                self._degraded_since = current_time
                return "healthy"
            elapsed = (current_time - self._degraded_since).total_seconds()
            return "degraded" if elapsed >= self._config.degraded_debounce_seconds else "healthy"

        self._degraded_since = None
        return "healthy"

    def _is_degraded(self, snapshot: StarlinkSnapshot) -> bool:
        status = snapshot.status
        obstruction = status.get("obstructionStats") or {}
        fraction_obstructed = _float_or_zero(obstruction.get("fractionObstructed"))
        if fraction_obstructed > self._config.obstruction_fraction_degraded:
            return True
        if obstruction.get("currentlyObstructed") is True:
            return True

        if _float_or_zero(status.get("popPingDropRate")) > self._config.pop_ping_drop_rate_degraded:
            return True
        if (
            _float_or_zero(status.get("popPingLatencyMs"))
            > self._config.pop_ping_latency_ms_degraded
        ):
            return True

        alerts = status.get("alerts") or {}
        if any(alerts.get(alert_name) is True for alert_name in _DEGRADING_ALERTS):
            return True

        history = snapshot.history
        if (
            _recent_average(history.get("popPingDropRate"), self._config.history_sample_window)
            > self._config.pop_ping_drop_rate_degraded
        ):
            return True
        if (
            _recent_average(history.get("popPingLatencyMs"), self._config.history_sample_window)
            > self._config.pop_ping_latency_ms_degraded
        ):
            return True
        outages = history.get("outages") or []
        return len(outages) >= self._config.recent_outage_count_degraded


def format_starlink_raw(snapshot: StarlinkSnapshot) -> str:
    """Format a compact RouterOS-friendly debug line."""
    if not snapshot.reachable:
        return "reachable=0"
    status = snapshot.status
    obstruction = status.get("obstructionStats") or {}
    alerts = status.get("alerts") or {}
    ready_states = status.get("readyStates") or {}
    ready_values = [value for key, value in ready_states.items() if key != "cady"]
    ready = int(bool(ready_values) and all(value is True for value in ready_values))
    thermal = int(
        alerts.get("thermalShutdown") is True
        or alerts.get("thermalThrottle") is True
        or alerts.get("powerSupplyThermalThrottle") is True
    )
    return (
        f"obstruct={_float_or_zero(obstruction.get('fractionObstructed')) * 100:.2f} "
        f"outage={int(bool(status.get('outage')))} "
        f"droprate={_float_or_zero(status.get('popPingDropRate')):.3f} "
        f"lat={_float_or_zero(status.get('popPingLatencyMs')):.1f} "
        f"thermal={thermal} ready={ready}"
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
