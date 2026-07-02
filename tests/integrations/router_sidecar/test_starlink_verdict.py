"""Tests for RouterOS sidecar Starlink client and verdict evaluation."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.integrations.router_sidecar.starlink import StarlinkGrpcClient, StarlinkSnapshot
from backend.integrations.router_sidecar.verdict import (
    StarlinkVerdictConfig,
    StarlinkVerdictEvaluator,
    format_starlink_raw,
)

pytestmark = [pytest.mark.integration, pytest.mark.smoke]


def _config() -> StarlinkVerdictConfig:
    return StarlinkVerdictConfig(
        obstruction_fraction_degraded=0.03,
        pop_ping_drop_rate_degraded=0.05,
        pop_ping_latency_ms_degraded=100.0,
        recent_outage_count_degraded=3,
        history_sample_window=5,
        degraded_debounce_seconds=60.0,
    )


def _healthy_snapshot(**status_overrides) -> StarlinkSnapshot:
    status = {
        "obstructionStats": {"fractionObstructed": 0.001, "currentlyObstructed": False},
        "alerts": {},
        "popPingDropRate": 0.0,
        "popPingLatencyMs": 22.0,
        "readyStates": {
            "cady": False,
            "scp": True,
            "l1l2": True,
            "xphy": True,
            "aap": True,
            "rf": True,
        },
    }
    status.update(status_overrides)
    return StarlinkSnapshot(
        reachable=True,
        status=status,
        history={"popPingDropRate": [0.0] * 5, "popPingLatencyMs": [20.0] * 5},
    )


def test_starlink_unreachable_and_active_outage_verdicts() -> None:
    """Unreachable dishes are unknown; active outage is down."""
    evaluator = StarlinkVerdictEvaluator(_config())

    assert evaluator.evaluate(StarlinkSnapshot(reachable=False, error="timeout")) == "unknown"
    assert evaluator.evaluate(_healthy_snapshot(outage={"cause": "NO_PINGS"})) == "down"


def test_cady_false_does_not_mark_working_dish_down() -> None:
    """The dish-verified cady=false ready state is not used as a down signal."""
    evaluator = StarlinkVerdictEvaluator(_config())

    assert evaluator.evaluate(_healthy_snapshot()) == "healthy"


def test_degraded_requires_sustained_poor_signal() -> None:
    """Poor obstruction must persist through the debounce window before degraded."""
    evaluator = StarlinkVerdictEvaluator(_config())
    start = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)
    poor = _healthy_snapshot(
        obstructionStats={"fractionObstructed": 0.2, "currentlyObstructed": True}
    )

    assert evaluator.evaluate(poor, now=start) == "healthy"
    assert evaluator.evaluate(poor, now=start + timedelta(seconds=30)) == "healthy"
    assert evaluator.evaluate(poor, now=start + timedelta(seconds=61)) == "degraded"
    assert evaluator.evaluate(_healthy_snapshot(), now=start + timedelta(seconds=62)) == "healthy"


@pytest.mark.asyncio
async def test_starlink_client_uses_fake_handle_call() -> None:
    """Starlink client can be tested against a fake Device/Handle transport."""
    calls: list[str] = []

    def fake_handle(request_field: str) -> dict:
        calls.append(request_field)
        if request_field == "get_status":
            return {"dishGetStatus": _healthy_snapshot().status}
        return {"dishGetHistory": {"popPingDropRate": [0.0], "popPingLatencyMs": [21.0]}}

    client = StarlinkGrpcClient("dish", 9200, handle_call=fake_handle)
    snapshot = await __import__("asyncio").to_thread(client.fetch_snapshot_blocking)

    assert calls == ["get_status", "get_history"]
    assert snapshot.reachable is True
    assert snapshot.status["popPingLatencyMs"] == 22.0
    assert snapshot.history["popPingLatencyMs"] == [21.0]


def test_raw_line_is_single_key_value_line() -> None:
    """Raw Starlink output is RouterOS-friendly key=value text."""
    raw = format_starlink_raw(_healthy_snapshot())

    assert raw == "obstruct=0.10 outage=0 droprate=0.000 lat=22.0 thermal=0 ready=1"
    assert "\n" not in raw
