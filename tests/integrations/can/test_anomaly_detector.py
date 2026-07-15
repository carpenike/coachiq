"""Tests for CAN anomaly detector rate calibration."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from backend.integrations.can.anomaly_detector import (
    RECON_007_RATE_LIMIT_PROFILES,
    AnomalyType,
    CANAnomalyDetector,
    SecurityAlert,
)
from backend.services.can.can_bus_service import CANBusService

pytestmark = pytest.mark.can


RECON_007_NORMAL_CADENCE = [
    (0x9C, 0x15FCE, 103, 3.0),
    (0x9C, 0x1FEDB, 66, 3.0),
    (0x8F, 0x1FEDA, 47, 3.0),
    (0x8E, 0x1FEDA, 18, 3.0),
    (0x9C, 0x1FACE, 36, 3.0),
]


def _arbitration_id(source_address: int, pgn: int) -> int:
    """Build a 29-bit CAN arbitration ID from source and PGN."""
    return (pgn << 8) | source_address


async def _replay_messages(
    detector: CANAnomalyDetector,
    source_address: int,
    pgn: int,
    count: int,
    duration_seconds: float,
    start_time: float,
) -> list[dict[str, Any]]:
    """Replay a synthetic source/PGN cadence through the anomaly detector."""
    results = []
    step = duration_seconds / max(count - 1, 1)
    for index in range(count):
        results.append(
            await detector.analyze_message(
                _arbitration_id(source_address, pgn),
                b"\x00" * 8,
                start_time + (index * step),
                source_address=source_address,
                pgn=pgn,
            )
        )
    return results


def _rate_limit_alerts(results: list[dict[str, Any]]) -> list[SecurityAlert]:
    """Extract rate-limit alerts from detector results."""
    return [
        alert
        for result in results
        for alert in result["anomalies_detected"]
        if alert.anomaly_type == AnomalyType.RATE_LIMIT_VIOLATION
    ]


@pytest.mark.asyncio
async def test_recon007_normal_cadence_does_not_raise_rate_limit_alerts() -> None:
    """RECON-007 normal high-frequency PGNs do not trigger rate-limit alerts."""
    detector = CANAnomalyDetector()

    for offset, (source_address, pgn, count, duration_seconds) in enumerate(
        RECON_007_NORMAL_CADENCE
    ):
        results = await _replay_messages(
            detector,
            source_address,
            pgn,
            count,
            duration_seconds,
            start_time=1000.0 + (offset * 10.0),
        )

        assert _rate_limit_alerts(results) == []

    assert detector.stats["rate_limited_messages"] == 0


@pytest.mark.asyncio
async def test_over_baseline_recon007_pgn_still_raises_rate_limit_alert() -> None:
    """A burst above a calibrated RECON-007 baseline still alerts."""
    detector = CANAnomalyDetector()
    source_address = 0x9C
    pgn = 0x1FEDB
    profile = RECON_007_RATE_LIMIT_PROFILES[(source_address, pgn)]

    results = await _replay_messages(
        detector,
        source_address,
        pgn,
        count=int(profile.capacity) + 5,
        duration_seconds=0.0,
        start_time=2000.0,
    )

    assert _rate_limit_alerts(results)
    assert "rate_limited" in results[-1]["actions_taken"]
    assert detector.stats["rate_limited_messages"] > 0


@pytest.mark.asyncio
async def test_unknown_pgn_keeps_default_rate_guardrail() -> None:
    """Unknown PGNs still use the default bucket and alert on clear floods."""
    detector = CANAnomalyDetector()

    results = await _replay_messages(
        detector,
        source_address=0xAA,
        pgn=0x12345,
        count=30,
        duration_seconds=0.0,
        start_time=3000.0,
    )

    assert _rate_limit_alerts(results)


@pytest.mark.asyncio
async def test_inbound_anomaly_detector_is_not_on_authoritative_rx_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CANBusService decodes traffic without invoking advisory anomaly logic."""
    anomaly_detector = AsyncMock()
    anomaly_detector.analyze_message = AsyncMock(
        return_value={"actions_taken": ["rate_limited"], "anomalies_detected": [object()]}
    )
    service = CANBusService(
        can_tracking_repository=Mock(),
        system_state_repository=Mock(),
        can_anomaly_detector=anomaly_detector,
    )
    process_message = AsyncMock()
    monkeypatch.setattr(service, "_add_sniffer_entry", AsyncMock())
    monkeypatch.setattr(service, "_process_message", process_message)
    message = SimpleNamespace(
        arbitration_id=_arbitration_id(0x9C, 0x1FEDB),
        data=b"\x00" * 8,
        dlc=8,
        is_extended_id=True,
    )

    process_received_message = service._process_received_message  # pyright: ignore[reportPrivateUsage]
    await process_received_message(message, "can0")

    anomaly_detector.analyze_message.assert_not_awaited()
    process_message.assert_awaited_once()
