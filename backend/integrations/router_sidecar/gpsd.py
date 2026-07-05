"""Async gpsd JSON watch client for the RouterOS sidecar."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class GpsdTpv:
    """A gpsd TPV fix (position, and motion fields when the receiver reports them)."""

    lat: float | None
    lon: float | None
    timestamp: datetime | None
    mode: int
    status: int | None = None
    eph: float | None = None
    # Motion/altitude fields used by the trip log (None when absent from TPV).
    speed: float | None = None  # m/s over ground
    track: float | None = None  # course over ground, degrees true
    alt: float | None = None  # meters (altMSL preferred over legacy alt)

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "GpsdTpv | None":
        """Build a TPV object from a gpsd JSON payload."""
        if payload.get("class") != "TPV":
            return None

        return cls(
            lat=_float_or_none(payload.get("lat")),
            lon=_float_or_none(payload.get("lon")),
            timestamp=_parse_gps_time(payload.get("time")),
            mode=int(payload.get("mode") or 0),
            status=int(payload["status"]) if payload.get("status") is not None else None,
            eph=_float_or_none(payload.get("eph")),
            speed=_float_or_none(payload.get("speed")),
            track=_float_or_none(payload.get("track")),
            alt=_first_not_none(
                _float_or_none(payload.get("altMSL")), _float_or_none(payload.get("alt"))
            ),
        )


class GpsdClient:
    """Read gpsd TPV messages from the JSON WATCH stream."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    async def watch_tpv(self) -> AsyncIterator[GpsdTpv]:
        """Yield TPV fixes from gpsd until the socket closes or errors."""
        reader, writer = await asyncio.open_connection(self._host, self._port)
        try:
            writer.write(b'?WATCH={"enable":true,"json":true};\n')
            await writer.drain()

            while True:
                line = await reader.readline()
                if not line:
                    return
                try:
                    payload = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue

                tpv = GpsdTpv.from_json(payload)
                if tpv is not None:
                    yield tpv
        finally:
            writer.close()
            await writer.wait_closed()


def _first_not_none(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_gps_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
