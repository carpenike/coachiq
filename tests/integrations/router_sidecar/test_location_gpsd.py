"""Tests for RouterOS sidecar gpsd and location evaluation."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from backend.integrations.router_sidecar.gpsd import GpsdClient, GpsdTpv
from backend.integrations.router_sidecar.location import (
    LocationEvaluator,
    LocationEvaluatorConfig,
    haversine_distance_m,
)

pytestmark = [pytest.mark.integration, pytest.mark.smoke]


def _config(*, hysteresis_count: int = 2) -> LocationEvaluatorConfig:
    return LocationEvaluatorConfig(
        home_latitude=35.0,
        home_longitude=-75.0,
        geofence_radius_m=200.0,
        hysteresis_count=hysteresis_count,
        fix_staleness_seconds=120.0,
    )


def _fix(*, lat: float, lon: float, when: datetime, mode: int = 3) -> GpsdTpv:
    return GpsdTpv(lat=lat, lon=lon, timestamp=when, mode=mode, status=2, eph=3.0)


def test_haversine_distance_and_geofence_boundary() -> None:
    """Location evaluator treats points inside the geofence as home."""
    now = datetime.now(UTC)
    evaluator = LocationEvaluator(_config(hysteresis_count=1))

    assert haversine_distance_m(35.0, -75.0, 35.0, -75.0) == pytest.approx(0.0)
    assert evaluator.evaluate(_fix(lat=35.0, lon=-75.0, when=now), now=now) == "home"
    assert evaluator.evaluate(_fix(lat=35.01, lon=-75.0, when=now), now=now) == "away"


def test_location_hysteresis_before_flipping() -> None:
    """Location state changes only after the configured consecutive readings."""
    now = datetime.now(UTC)
    evaluator = LocationEvaluator(_config(hysteresis_count=2))

    home_fix = _fix(lat=35.0, lon=-75.0, when=now)
    away_fix = _fix(lat=35.01, lon=-75.0, when=now)

    assert evaluator.evaluate(home_fix, now=now) == "unknown"
    assert evaluator.evaluate(home_fix, now=now) == "home"
    assert evaluator.evaluate(away_fix, now=now) == "home"
    assert evaluator.evaluate(away_fix, now=now) == "away"


def test_stale_or_invalid_fix_is_unknown_immediately() -> None:
    """Stale, missing, or mode-1 GPS fixes never report home."""
    now = datetime.now(UTC)
    evaluator = LocationEvaluator(_config(hysteresis_count=1))

    assert evaluator.evaluate(_fix(lat=35.0, lon=-75.0, when=now), now=now) == "home"
    assert (
        evaluator.evaluate(_fix(lat=35.0, lon=-75.0, when=now - timedelta(minutes=3)), now=now)
        == "unknown"
    )
    assert evaluator.evaluate(_fix(lat=35.0, lon=-75.0, when=now, mode=1), now=now) == "unknown"
    assert evaluator.evaluate(None, now=now) == "unknown"


@pytest.mark.asyncio
async def test_gpsd_client_yields_tpv_from_fake_server() -> None:
    """GpsdClient reads WATCH JSON lines and yields only TPV payloads."""
    received_watch = asyncio.Event()

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        received_watch.set()
        payloads = [
            {"class": "VERSION", "release": "test"},
            {
                "class": "TPV",
                "mode": 3,
                "status": 2,
                "time": "2026-07-02T23:17:25.000Z",
                "lat": 35.578435333,
                "lon": -75.465544,
                "eph": 2.993,
            },
        ]
        for payload in payloads:
            writer.write(json.dumps(payload).encode() + b"\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        client = GpsdClient("127.0.0.1", port)
        fixes = []
        async for fix in client.watch_tpv():
            fixes.append(fix)

        assert received_watch.is_set()
        assert len(fixes) == 1
        assert fixes[0].mode == 3
        assert fixes[0].lat == pytest.approx(35.578435333)
        assert fixes[0].timestamp == datetime(2026, 7, 2, 23, 17, 25, tzinfo=UTC)
    finally:
        server.close()
        await server.wait_closed()
