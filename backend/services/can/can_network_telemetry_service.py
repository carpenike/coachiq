"""Rolling CAN network telemetry derived from cumulative interface counters."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

CAN_FRAME_OVERHEAD_BITS = 96
DEFAULT_SAMPLE_INTERVAL_SECONDS = 2.0


@dataclass(frozen=True)
class RollingInterfaceTelemetry:
    """Nullable rolling telemetry for one CAN interface."""

    message_rate: float | None = None
    bus_load_percent: float | None = None
    last_activity: str | None = None

    def model_dump(self) -> dict[str, float | str | None]:
        """Return a dictionary matching the networks v2 response fields."""
        return {
            "message_rate": self.message_rate,
            "bus_load_percent": self.bus_load_percent,
            "last_activity": self.last_activity,
        }


@dataclass(frozen=True)
class _InterfaceSnapshot:
    """Single point-in-time cumulative counter snapshot for one interface."""

    monotonic_time: float
    utc_time: datetime
    packet_count: int | None
    byte_count: int | None
    bitrate: int | None


class CANNetworkTelemetryService:
    """Stateful rolling telemetry sampler for CAN network interfaces.

    The service samples the HOF-002 cumulative SocketCAN counters and derives
    per-interface rates over time. Bus load is an approximation using the
    classic-CAN framing estimate validated against the Pi `canbusload` sample.
    """

    def __init__(
        self,
        can_interface_service: Any,
        sample_interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
        monotonic_clock: Callable[[], float] = time.monotonic,
        utc_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._can_interface_service = can_interface_service
        self._sample_interval_seconds = sample_interval_seconds
        self._monotonic_clock = monotonic_clock
        self._utc_clock = utc_clock or (lambda: datetime.now(UTC))
        self._previous_snapshots: dict[str, _InterfaceSnapshot] = {}
        self._rolling: dict[str, RollingInterfaceTelemetry] = {}
        self._last_activity: dict[str, str] = {}
        self._task: asyncio.Task[None] | None = None

    async def startup(self) -> None:
        """Start the registry-managed telemetry polling task."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._poll_loop(), name="can_network_telemetry")

    async def shutdown(self) -> None:
        """Cancel the registry-managed telemetry polling task."""
        if self._task is None:
            return

        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _poll_loop(self) -> None:
        """Continuously sample interface counters until cancelled."""
        while True:
            await self.sample_once()
            await asyncio.sleep(self._sample_interval_seconds)

    async def sample_once(self) -> None:
        """Capture one counter snapshot and update rolling telemetry state."""
        interface_stats = await self._can_interface_service.get_interface_stats()
        monotonic_time = self._monotonic_clock()
        utc_time = _normalize_utc(self._utc_clock())

        current_interfaces = set(interface_stats)
        missing_interfaces = set(self._previous_snapshots) - current_interfaces
        for interface_name in missing_interfaces:
            self._previous_snapshots.pop(interface_name, None)
            self._rolling[interface_name] = RollingInterfaceTelemetry()

        for interface_name, stats in interface_stats.items():
            snapshot = _snapshot_from_stats(stats, monotonic_time, utc_time)
            previous = self._previous_snapshots.get(interface_name)
            if previous is None:
                self._previous_snapshots[interface_name] = snapshot
                self._rolling[interface_name] = RollingInterfaceTelemetry(
                    last_activity=self._last_activity.get(interface_name)
                )
                continue

            rolling = self._calculate_rolling(interface_name, previous, snapshot)
            self._previous_snapshots[interface_name] = snapshot
            self._rolling[interface_name] = rolling

    def get_rolling_telemetry(self) -> dict[str, dict[str, float | str | None]]:
        """Return the latest rolling telemetry by physical interface name."""
        return {name: telemetry.model_dump() for name, telemetry in self._rolling.items()}

    def get_health_status(self) -> dict[str, Any]:
        """Return basic sampler health for ServiceRegistry health checks."""
        running = self._task is not None and not self._task.done()
        return {
            "healthy": self._task is None or running,
            "running": running,
            "sample_interval_seconds": self._sample_interval_seconds,
            "interfaces": len(self._rolling),
        }

    def _calculate_rolling(
        self,
        interface_name: str,
        previous: _InterfaceSnapshot,
        current: _InterfaceSnapshot,
    ) -> RollingInterfaceTelemetry:
        """Calculate rolling telemetry from two cumulative counter snapshots."""
        delta_seconds = current.monotonic_time - previous.monotonic_time
        if delta_seconds <= 0:
            return RollingInterfaceTelemetry(last_activity=self._last_activity.get(interface_name))

        packet_delta = _counter_delta(previous.packet_count, current.packet_count)
        byte_delta = _counter_delta(previous.byte_count, current.byte_count)
        if packet_delta is None:
            self._last_activity.pop(interface_name, None)
            return RollingInterfaceTelemetry()

        if packet_delta > 0:
            self._last_activity[interface_name] = current.utc_time.isoformat()

        bus_load_percent = None
        if byte_delta is not None and current.bitrate is not None and current.bitrate > 0:
            estimated_bits = byte_delta * 8 + packet_delta * CAN_FRAME_OVERHEAD_BITS
            bus_load_percent = min(
                max((estimated_bits / (current.bitrate * delta_seconds)) * 100.0, 0.0),
                100.0,
            )

        return RollingInterfaceTelemetry(
            message_rate=packet_delta / delta_seconds,
            bus_load_percent=bus_load_percent,
            last_activity=self._last_activity.get(interface_name),
        )


def _normalize_utc(timestamp: datetime) -> datetime:
    """Normalize a wall-clock timestamp to timezone-aware UTC."""
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _snapshot_from_stats(
    stats: Mapping[str, Any], monotonic_time: float, utc_time: datetime
) -> _InterfaceSnapshot:
    """Build a typed snapshot from HOF-002 interface statistics."""
    return _InterfaceSnapshot(
        monotonic_time=monotonic_time,
        utc_time=utc_time,
        packet_count=_counter_sum(stats, "rx_packets", "tx_packets"),
        byte_count=_counter_sum(stats, "rx_bytes", "tx_bytes"),
        bitrate=_positive_int(stats.get("bitrate")),
    )


def _counter_sum(stats: Mapping[str, Any], *field_names: str) -> int | None:
    """Sum required integer counters or return None if any are unavailable."""
    total = 0
    for field_name in field_names:
        value = _non_negative_int(stats.get(field_name))
        if value is None:
            return None
        total += value
    return total


def _counter_delta(previous: int | None, current: int | None) -> int | None:
    """Return a non-negative cumulative counter delta, or None for resets/missing data."""
    if previous is None or current is None:
        return None
    delta = current - previous
    return delta if delta >= 0 else None


def _non_negative_int(value: Any) -> int | None:
    """Return a non-negative integer counter value when one is available."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _positive_int(value: Any) -> int | None:
    """Return a positive integer value when one is available."""
    integer_value = _non_negative_int(value)
    if integer_value is None or integer_value <= 0:
        return None
    return integer_value
