"""Tests for rolling CAN network telemetry sampling."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.core.composition_root import CompositionRoot
from backend.services.can.can_network_telemetry_service import CANNetworkTelemetryService

pytestmark = pytest.mark.can


class FakeCANInterfaceService:
    """Deterministic CAN interface provider for sampler tests."""

    def __init__(self, snapshots: list[dict[str, dict[str, Any]]]) -> None:
        self._snapshots = snapshots
        self._index = 0

    async def get_interface_stats(self) -> dict[str, dict[str, Any]]:
        """Return the next deterministic snapshot."""
        snapshot = self._snapshots[min(self._index, len(self._snapshots) - 1)]
        self._index += 1
        return snapshot


class FakeClocks:
    """Paired monotonic and UTC clocks for deterministic sampler tests."""

    def __init__(self) -> None:
        self.monotonic_values = [100.0, 102.0, 104.0]
        self.utc_values = [
            datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 6, 26, 12, 0, 2, tzinfo=UTC),
            datetime(2026, 6, 26, 12, 0, 4, tzinfo=UTC),
        ]
        self._monotonic_index = 0
        self._utc_index = 0

    def monotonic(self) -> float:
        """Return the next monotonic timestamp."""
        value = self.monotonic_values[self._monotonic_index]
        self._monotonic_index += 1
        return value

    def utc(self) -> datetime:
        """Return the next UTC timestamp."""
        value = self.utc_values[self._utc_index]
        self._utc_index += 1
        return value


def _snapshot(
    rx_packets: int | None,
    tx_packets: int | None,
    rx_bytes: int | None,
    tx_bytes: int | None,
    bitrate: int | None = 250000,
) -> dict[str, dict[str, Any]]:
    """Build a single-interface cumulative counter snapshot."""
    return {
        "can0": {
            "rx_packets": rx_packets,
            "tx_packets": tx_packets,
            "rx_bytes": rx_bytes,
            "tx_bytes": tx_bytes,
            "bitrate": bitrate,
        }
    }


@pytest.mark.asyncio
async def test_sampler_cold_start_returns_null_rolling_fields() -> None:
    """The first sample establishes a baseline without fabricating rates."""
    clocks = FakeClocks()
    service = CANNetworkTelemetryService(
        can_interface_service=FakeCANInterfaceService([_snapshot(10, 5, 80, 40)]),
        monotonic_clock=clocks.monotonic,
        utc_clock=clocks.utc,
    )

    await service.sample_once()

    assert service.get_rolling_telemetry() == {
        "can0": {"message_rate": None, "bus_load_percent": None, "last_activity": None}
    }


@pytest.mark.asyncio
async def test_sampler_computes_rate_load_and_last_activity() -> None:
    """Two samples with known deltas produce deterministic rolling telemetry."""
    clocks = FakeClocks()
    service = CANNetworkTelemetryService(
        can_interface_service=FakeCANInterfaceService(
            [_snapshot(0, 0, 0, 0), _snapshot(160, 6, 10240, 384)]
        ),
        monotonic_clock=clocks.monotonic,
        utc_clock=clocks.utc,
    )

    await service.sample_once()
    await service.sample_once()

    telemetry = service.get_rolling_telemetry()["can0"]
    assert telemetry["message_rate"] == 83.0
    assert telemetry["bus_load_percent"] == pytest.approx(20.1856)
    assert telemetry["last_activity"] == "2026-06-26T12:00:02+00:00"


@pytest.mark.asyncio
async def test_sampler_unknown_bitrate_keeps_load_null_but_rate_valid() -> None:
    """Unknown bitrate only suppresses approximate bus load."""
    clocks = FakeClocks()
    service = CANNetworkTelemetryService(
        can_interface_service=FakeCANInterfaceService(
            [_snapshot(0, 0, 0, 0, None), _snapshot(10, 10, 80, 80, None)]
        ),
        monotonic_clock=clocks.monotonic,
        utc_clock=clocks.utc,
    )

    await service.sample_once()
    await service.sample_once()

    telemetry = service.get_rolling_telemetry()["can0"]
    assert telemetry["message_rate"] == 10.0
    assert telemetry["bus_load_percent"] is None
    assert telemetry["last_activity"] == "2026-06-26T12:00:02+00:00"


@pytest.mark.asyncio
async def test_sampler_counter_reset_returns_null_and_resets_baseline() -> None:
    """Negative cumulative deltas are treated as reset/missing data, not rates."""
    clocks = FakeClocks()
    service = CANNetworkTelemetryService(
        can_interface_service=FakeCANInterfaceService(
            [_snapshot(100, 100, 800, 800), _snapshot(1, 1, 8, 8), _snapshot(11, 11, 88, 88)]
        ),
        monotonic_clock=clocks.monotonic,
        utc_clock=clocks.utc,
    )

    await service.sample_once()
    await service.sample_once()
    reset_telemetry = service.get_rolling_telemetry()["can0"]
    await service.sample_once()
    recovered_telemetry = service.get_rolling_telemetry()["can0"]

    assert reset_telemetry == {
        "message_rate": None,
        "bus_load_percent": None,
        "last_activity": None,
    }
    assert recovered_telemetry["message_rate"] == 10.0
    assert recovered_telemetry["last_activity"] == "2026-06-26T12:00:04+00:00"


@pytest.mark.asyncio
async def test_sampler_empty_provider_returns_empty_state() -> None:
    """An empty provider, including non-Linux degradation, yields no fabricated telemetry."""
    clocks = FakeClocks()
    service = CANNetworkTelemetryService(
        can_interface_service=FakeCANInterfaceService([{}]),
        monotonic_clock=clocks.monotonic,
        utc_clock=clocks.utc,
    )

    await service.sample_once()

    assert service.get_rolling_telemetry() == {}


@pytest.mark.asyncio
async def test_sampler_missing_counters_return_null_fields() -> None:
    """Missing counters keep rolling fields nullable rather than returning zero."""
    clocks = FakeClocks()
    service = CANNetworkTelemetryService(
        can_interface_service=FakeCANInterfaceService(
            [_snapshot(None, 0, None, 0), _snapshot(None, 10, None, 80)]
        ),
        monotonic_clock=clocks.monotonic,
        utc_clock=clocks.utc,
    )

    await service.sample_once()
    await service.sample_once()

    assert service.get_rolling_telemetry()["can0"] == {
        "message_rate": None,
        "bus_load_percent": None,
        "last_activity": None,
    }


@pytest.mark.asyncio
async def test_sampler_startup_shutdown_use_registry_hooks() -> None:
    """Sampler lifecycle uses ServiceRegistry startup/shutdown hooks."""
    service = CANNetworkTelemetryService(
        can_interface_service=FakeCANInterfaceService([{}]),
        sample_interval_seconds=60.0,
    )

    await service.startup()
    assert service.get_health_status()["running"] is True
    await service.shutdown()
    assert service.get_health_status()["running"] is False


@pytest.mark.asyncio
async def test_composition_root_shutdown_invokes_sampler_shutdown() -> None:
    """CompositionRoot shutdown drives sampler shutdown."""
    service = CANNetworkTelemetryService(
        can_interface_service=FakeCANInterfaceService([{}]),
        sample_interval_seconds=60.0,
    )
    await service.startup()
    assert service.get_health_status()["running"] is True
    root = CompositionRoot(service_catalog=set())
    root.set_constructed_service("can_network_telemetry_service", service)
    root._started = True

    await root.shutdown()

    assert service.get_health_status()["running"] is False


@pytest.mark.asyncio
async def test_sampler_normalizes_naive_utc_clock_to_aware_iso_timestamp() -> None:
    """Naive injected UTC timestamps are normalized before serialization."""
    naive_time = datetime(2026, 6, 26, 12, 0, 2, tzinfo=UTC).replace(tzinfo=None)
    clocks = FakeClocks()
    clocks.utc_values[1] = naive_time
    service = CANNetworkTelemetryService(
        can_interface_service=FakeCANInterfaceService(
            [_snapshot(0, 0, 0, 0), _snapshot(1, 1, 8, 8)]
        ),
        monotonic_clock=clocks.monotonic,
        utc_clock=clocks.utc,
    )

    await service.sample_once()
    await service.sample_once()
    assert service.get_rolling_telemetry()["can0"]["last_activity"] == (
        naive_time.replace(tzinfo=UTC).isoformat()
    )


def test_fake_clock_values_remain_distinct() -> None:
    """Guard the deterministic clock fixture against accidental wall-clock coupling."""
    clocks = FakeClocks()

    assert clocks.monotonic_values[1] == 102.0
    assert clocks.utc_values[1] == datetime(2026, 6, 26, 12, 0, 2, tzinfo=UTC)
    assert clocks.utc_values[1] + timedelta(seconds=2) == clocks.utc_values[2]
