"""Nighthawk M6 Pro model.json client and verdict evaluation."""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

NighthawkVerdict = Literal["healthy", "degraded", "down", "unknown"]

_SENTINEL_ABSENT_VALUES = {-32768}
_PRIVATE_KEY_NAMES = {"sectoken", "sessionid", "sessiontoken"}


@dataclass(frozen=True, slots=True)
class NighthawkSnapshot:
    """Cached Nighthawk model.json snapshot."""

    reachable: bool
    data: dict[str, Any] | None = None
    fetched_at: float | None = None
    error: str | None = None


class NighthawkClient:
    """Fetch Nighthawk model.json, following session redirects."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5.0,
        fetch_json: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._fetch_json = fetch_json

    def fetch_snapshot_blocking(self) -> NighthawkSnapshot:
        """Fetch a model.json snapshot. Call from a worker thread."""
        try:
            data = self._fetch_json() if self._fetch_json else self._fetch_model_json()
            return NighthawkSnapshot(
                reachable=True,
                data=sanitize_nighthawk_model(data),
                fetched_at=time.time(),
            )
        except Exception as exc:  # pragma: no cover - exercised through fake error paths
            return NighthawkSnapshot(reachable=False, error=f"{type(exc).__name__}: {exc}")

    def _fetch_model_json(self) -> dict[str, Any]:
        url = f"{self._base_url}/api/model.json"
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"}:
            msg = "Nighthawk base URL must use http or https"
            raise ValueError(msg)
        opener = build_opener(HTTPRedirectHandler(), HTTPCookieProcessor(CookieJar()))
        request = Request(url, headers={"Accept": "*/*"})  # noqa: S310
        with opener.open(request, timeout=self._timeout_seconds) as response:
            parsed_payload = json.loads(response.read().decode("utf-8", "replace"))
        if not isinstance(parsed_payload, dict):
            msg = "Nighthawk model.json did not contain a JSON object"
            raise ValueError(msg)
        payload = sanitize_nighthawk_model(parsed_payload)
        _log_signal_subset(payload)
        return payload


def sanitize_nighthawk_model(data: dict[str, Any]) -> dict[str, Any]:
    """Remove session/write fields before caching or exposing Nighthawk telemetry."""
    return {
        key: _sanitize_nighthawk_value(value)
        for key, value in data.items()
        if not _is_private_nighthawk_key(key)
    }


def _sanitize_nighthawk_value(value: Any) -> Any:
    if isinstance(value, dict):
        return sanitize_nighthawk_model(value)
    if isinstance(value, list):
        return [_sanitize_nighthawk_value(item) for item in value]
    return value


def _is_private_nighthawk_key(key: str) -> bool:
    normalized = key.replace("_", "").replace("-", "").lower()
    return normalized in _PRIVATE_KEY_NAMES or normalized.startswith("write")


@dataclass(frozen=True, slots=True)
class NighthawkVerdictConfig:
    """Thresholds for Nighthawk 5G verdict evaluation."""

    rsrp_degraded: float
    rsrp_recovery: float
    rsrq_degraded: float
    rsrq_recovery: float
    sinr_degraded: float
    sinr_recovery: float
    radio_quality_degraded: float
    radio_quality_recovery: float
    sample_window_seconds: float
    dwell_seconds: float


@dataclass(frozen=True, slots=True)
class _SignalSample:
    timestamp: datetime
    rsrp: float | None = None
    rsrq: float | None = None
    sinr: float | None = None
    radio_quality: float | None = None


class NighthawkVerdictEvaluator:
    """Evaluate Nighthawk model data with rolling averages, hysteresis, and dwell."""

    def __init__(self, config: NighthawkVerdictConfig) -> None:
        self._config = config
        self._samples: deque[_SignalSample] = deque()
        self._committed_verdict: NighthawkVerdict = "unknown"
        self._candidate_verdict: NighthawkVerdict | None = None
        self._candidate_since: datetime | None = None

    def evaluate(
        self,
        snapshot: NighthawkSnapshot,
        now: datetime | None = None,
    ) -> NighthawkVerdict:
        """Return a debounced Nighthawk verdict."""
        current_time = now or datetime.now(UTC)
        target = self._target_verdict(snapshot, current_time)

        if target in {"down", "unknown"}:
            self._commit(target)
            return self._committed_verdict

        if self._committed_verdict in {"unknown", "down"}:
            if target == "healthy":
                self._commit(target)
                return self._committed_verdict
            self._committed_verdict = "healthy"

        if target == self._committed_verdict:
            self._clear_candidate()
            return self._committed_verdict

        if self._candidate_verdict != target:
            self._candidate_verdict = target
            self._candidate_since = current_time
            return self._committed_verdict

        candidate_since = self._candidate_since or current_time
        if (current_time - candidate_since).total_seconds() >= self._config.dwell_seconds:
            self._commit(target)
        return self._committed_verdict

    def _target_verdict(self, snapshot: NighthawkSnapshot, now: datetime) -> NighthawkVerdict:
        if not snapshot.reachable or not snapshot.data:
            return "unknown"
        if _connection(snapshot.data) != "Connected":
            return "down"

        sample = _extract_signal_sample(snapshot.data, now)
        if sample is not None:
            self._samples.append(sample)
        self._trim_samples(now)
        averages = self._averages()
        if not averages:
            return "unknown"
        return "degraded" if self._is_degraded(averages) else "healthy"

    def _is_degraded(self, averages: dict[str, float]) -> bool:
        in_degraded_context = (
            self._committed_verdict == "degraded" or self._candidate_verdict == "degraded"
        )
        thresholds = {
            "rsrp": self._threshold(
                in_degraded_context, self._config.rsrp_recovery, self._config.rsrp_degraded
            ),
            "rsrq": self._threshold(
                in_degraded_context, self._config.rsrq_recovery, self._config.rsrq_degraded
            ),
            "sinr": self._threshold(
                in_degraded_context, self._config.sinr_recovery, self._config.sinr_degraded
            ),
            "radio_quality": self._config.radio_quality_recovery
            if in_degraded_context
            else self._config.radio_quality_degraded,
        }
        return any(
            averages.get(metric) is not None and averages[metric] < threshold
            for metric, threshold in thresholds.items()
        )

    @staticmethod
    def _threshold(in_degraded_context: bool, recovery: float, degraded: float) -> float:
        return recovery if in_degraded_context else degraded

    def _trim_samples(self, now: datetime) -> None:
        cutoff_seconds = self._config.sample_window_seconds
        while self._samples and (now - self._samples[0].timestamp).total_seconds() > cutoff_seconds:
            self._samples.popleft()

    def _averages(self) -> dict[str, float]:
        averages: dict[str, float] = {}
        for metric in ("rsrp", "rsrq", "sinr", "radio_quality"):
            values = [
                value for sample in self._samples if (value := getattr(sample, metric)) is not None
            ]
            if values:
                averages[metric] = sum(values) / len(values)
        return averages

    def _commit(self, verdict: NighthawkVerdict) -> None:
        self._committed_verdict = verdict
        self._clear_candidate()

    def _clear_candidate(self) -> None:
        self._candidate_verdict = None
        self._candidate_since = None


def format_nighthawk_raw(snapshot: NighthawkSnapshot) -> str:
    """Format compact Nighthawk status for RouterOS and HA template checks."""
    if not snapshot.reachable or not snapshot.data:
        return "reachable=0"
    signal = _signal_strength(snapshot.data)
    wwan = snapshot.data.get("wwan") or {}
    wwanadv = snapshot.data.get("wwanadv") or {}
    band = str(wwanadv.get("curBand") or "")
    carrier = _carrier(snapshot.data)
    return (
        f"conn={wwan.get('connectionText') or wwan.get('currentPSserviceType') or 'unknown'} "
        f"rsrp={_raw_value(signal.get('rsrp'))} "
        f"rsrq={_raw_value(signal.get('rsrq'))} "
        f"sinr={_raw_value(signal.get('sinr'))} "
        f"rq={_raw_value(wwanadv.get('radioQuality'))} "
        f'band="{band}" carrier={carrier} bars={_raw_value(signal.get("bars"))}'
    )


def _extract_signal_sample(data: dict[str, Any], now: datetime) -> _SignalSample | None:
    signal = _signal_strength(data)
    wwanadv = data.get("wwanadv") or {}
    sample = _SignalSample(
        timestamp=now,
        rsrp=_metric_value(signal.get("rsrp")),
        rsrq=_metric_value(signal.get("rsrq")),
        sinr=_metric_value(signal.get("sinr")),
        radio_quality=_metric_value(wwanadv.get("radioQuality")),
    )
    if all(getattr(sample, metric) is None for metric in ("rsrp", "rsrq", "sinr", "radio_quality")):
        return None
    return sample


def _connection(data: dict[str, Any]) -> str | None:
    return (data.get("wwan") or {}).get("connection")


def _signal_strength(data: dict[str, Any]) -> dict[str, Any]:
    return (data.get("wwan") or {}).get("signalStrength") or {}


def _metric_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        metric = float(value)
    except (TypeError, ValueError):
        return None
    return None if metric in _SENTINEL_ABSENT_VALUES else metric


def _raw_value(value: Any) -> str:
    metric = _metric_value(value)
    if metric is None:
        return "na"
    return str(int(metric)) if metric.is_integer() else f"{metric:.1f}"


def _carrier(data: dict[str, Any]) -> str:
    wwan = data.get("wwan") or {}
    wwanadv = data.get("wwanadv") or {}
    for key in ("networkName", "operator", "carrier"):
        value = wwan.get(key) or wwanadv.get(key)
        if value:
            return str(value).replace(" ", "_")
    mcc = wwanadv.get("MCC")
    mnc = wwanadv.get("MNC")
    return f"{mcc}/{mnc}" if mcc and mnc else "unknown"


def _log_signal_subset(data: dict[str, Any]) -> None:
    signal = _signal_strength(data)
    wwan = data.get("wwan") or {}
    wwanadv = data.get("wwanadv") or {}
    logger.debug(
        "Nighthawk signal: connection=%s rsrp=%s rsrq=%s sinr=%s radioQuality=%s band=%s",
        wwan.get("connection"),
        signal.get("rsrp"),
        signal.get("rsrq"),
        signal.get("sinr"),
        wwanadv.get("radioQuality"),
        wwanadv.get("curBand"),
    )
