"""Tests for RouterOS sidecar Nighthawk M6 Pro scraping and verdicts."""

import time
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from backend.core.config import RouterSidecarSettings
from backend.integrations.router_sidecar import RouterSidecarService
from backend.integrations.router_sidecar.nighthawk import (
    NighthawkClient,
    NighthawkSnapshot,
    NighthawkVerdictConfig,
    NighthawkVerdictEvaluator,
    format_nighthawk_raw,
)

pytestmark = [pytest.mark.integration, pytest.mark.smoke]


def _config() -> NighthawkVerdictConfig:
    return NighthawkVerdictConfig(
        rsrp_degraded=-105.0,
        rsrp_recovery=-100.0,
        rsrq_degraded=-18.0,
        rsrq_recovery=-15.0,
        sinr_degraded=5.0,
        sinr_recovery=8.0,
        radio_quality_degraded=30.0,
        radio_quality_recovery=40.0,
        sample_window_seconds=60.0,
        dwell_seconds=60.0,
    )


def _model(
    *,
    connection: str = "Connected",
    rsrp: int | None = -96,
    rsrq: int | None = -17,
    sinr: int | None = 22,
    radio_quality: int | None = 57,
    nr5g_rsrp: int | None = -32768,
) -> dict[str, Any]:
    return {
        "secToken": "do-not-expose",
        "writeConfig": {"enabled": True},
        "wwan": {
            "connection": connection,
            "connectionText": "5G",
            "currentPSserviceType": "5GSUB6",
            "RAT": "Only4G5G",
            "signalStrength": {
                "sessionId": "do-not-expose",
                "rssi": -65,
                "rsrp": rsrp,
                "rsrq": rsrq,
                "sinr": sinr,
                "bars": 5,
                "nr5gRsrp": nr5g_rsrp,
                "nr5gRsrq": -32768,
                "nr5gSinr": -32768,
            },
        },
        "wwanadv": {
            "curBand": "LTE B66",
            "radioQuality": radio_quality,
            "MCC": "310",
            "MNC": "410",
        },
        "dataTransferredRx": None,
        "dataTransferredTx": None,
    }


def _snapshot(data: dict[str, Any] | None = None, *, reachable: bool = True) -> NighthawkSnapshot:
    return NighthawkSnapshot(
        reachable=reachable,
        data=data if data is not None else _model(),
        fetched_at=time.time() if reachable else None,
        error=None if reachable else "timeout",
    )


def test_nighthawk_client_uses_fake_model_json_fetch() -> None:
    """Nighthawk client wraps fetched model.json data in a snapshot."""
    client = NighthawkClient("http://cpe", fetch_json=lambda: _model())

    snapshot = client.fetch_snapshot_blocking()

    assert snapshot.reachable is True
    data = snapshot.data
    assert data is not None
    assert "secToken" not in data
    assert "writeConfig" not in data
    assert "sessionId" not in data["wwan"]["signalStrength"]
    assert data["wwan"]["signalStrength"]["rsrp"] == -96
    assert snapshot.fetched_at is not None


def test_nighthawk_healthy_current_sample() -> None:
    """The host-observed borderline-fair sample is healthy with defaults."""
    evaluator = NighthawkVerdictEvaluator(_config())

    assert evaluator.evaluate(_snapshot()) == "healthy"


def test_nighthawk_down_is_immediate_when_disconnected() -> None:
    """No cellular connection publishes down immediately."""
    evaluator = NighthawkVerdictEvaluator(_config())

    assert evaluator.evaluate(_snapshot(_model(connection="Disconnected"))) == "down"


def test_nighthawk_unreachable_is_unknown() -> None:
    """Unreachable CPE publishes unknown."""
    evaluator = NighthawkVerdictEvaluator(_config())

    assert evaluator.evaluate(_snapshot(reachable=False)) == "unknown"


def test_nighthawk_degraded_requires_sustained_rolling_average() -> None:
    """Weak signal must persist through dwell before degraded is published."""
    evaluator = NighthawkVerdictEvaluator(_config())
    start = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    weak = _snapshot(_model(rsrp=-112, rsrq=-20, sinr=2, radio_quality=20))

    assert evaluator.evaluate(weak, now=start) == "healthy"
    assert evaluator.evaluate(weak, now=start + timedelta(seconds=30)) == "healthy"
    assert evaluator.evaluate(weak, now=start + timedelta(seconds=61)) == "degraded"


def test_nighthawk_hysteresis_prevents_recovery_flap() -> None:
    """Degraded holds until the rolling average clears recovery thresholds with dwell."""
    evaluator = NighthawkVerdictEvaluator(_config())
    start = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    weak = _snapshot(_model(rsrp=-112, rsrq=-20, sinr=2, radio_quality=20))
    good = _snapshot(_model(rsrp=-92, rsrq=-12, sinr=18, radio_quality=60))

    assert evaluator.evaluate(weak, now=start) == "healthy"
    assert evaluator.evaluate(weak, now=start + timedelta(seconds=61)) == "degraded"
    assert evaluator.evaluate(good, now=start + timedelta(seconds=62)) == "degraded"
    assert evaluator.evaluate(good, now=start + timedelta(seconds=123)) == "degraded"
    assert evaluator.evaluate(good, now=start + timedelta(seconds=184)) == "healthy"


def test_nighthawk_sentinel_nr5g_values_are_ignored() -> None:
    """NSA not-populated nr5g sentinels are ignored by verdict math."""
    evaluator = NighthawkVerdictEvaluator(_config())
    start = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    nsa = _snapshot(_model(nr5g_rsrp=-32768, rsrp=-96, rsrq=-17, sinr=22, radio_quality=57))

    assert evaluator.evaluate(nsa, now=start) == "healthy"
    assert evaluator.evaluate(nsa, now=start + timedelta(seconds=120)) == "healthy"


def test_nighthawk_status_last_good_stale_and_unknown_verdict() -> None:
    """Unreachable CPE keeps last-good status stale while verdict becomes unknown."""
    service = RouterSidecarService(RouterSidecarSettings(enabled=False))
    client = TestClient(cast("Any", service.app))
    refresh_nighthawk = service._refresh_nighthawk  # pyright: ignore[reportPrivateUsage]
    refresh_nighthawk(_snapshot())
    refresh_nighthawk(_snapshot(reachable=False))

    status = client.get("/5g/status").json()

    assert status["stale"] is True
    assert "secToken" not in status["data"]
    assert "writeConfig" not in status["data"]
    assert status["data"]["wwan"]["signalStrength"]["rsrp"] == -96
    assert client.get("/5g/verdict").text == "unknown\n"
    assert client.get("/5g/raw").text == "reachable=0\n"


def test_nighthawk_status_never_polled_envelope() -> None:
    """Never-polled CPE status mirrors the Starlink staleness envelope."""
    service = RouterSidecarService(RouterSidecarSettings(enabled=False))
    response = TestClient(cast("Any", service.app)).get("/5g/status")

    assert response.status_code == 200
    assert response.json() == {
        "fetched_at": None,
        "age_s": None,
        "stale": True,
        "error": None,
        "data": None,
    }


def test_nighthawk_raw_line() -> None:
    """Raw Nighthawk line exposes compact signal facts."""
    raw = format_nighthawk_raw(_snapshot())

    assert raw == ('conn=5G rsrp=-96 rsrq=-17 sinr=22 rq=57 band="LTE B66" carrier=310/410 bars=5')
    assert "\n" not in raw
