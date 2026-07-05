"""
Time Sync Service - RV-C time master and GPS broadcaster.

Takes over the coach's timekeeping from the (dead) factory GPS node:

- Broadcasts DATE_TIME_STATUS (1FFFF) every second from this controller's
  source address. Master arbitration is by source address — ours (0xF9)
  outranks the factory panel (0x9C) and the broken GPS (0x75), so every
  spec-compliant node continuously re-syncs to our GPS-disciplined clock,
  even while the broken node keeps spamming stale SET commands.
- Broadcasts GPS_POSITION / GPS_STATUS / GPS_TIME_STATUS at the same
  cadence whenever the local gpsd has a fix (position comes from the trip
  log service's live fix; time comes from the chrony-disciplined system
  clock, which is itself GPS-backed).
- Announces GPS_DATE_TIME_STATUS once at startup per spec 6.4.4.

The system time is only trustworthy because chrony disciplines it from the
same GPS — so time broadcasting is gated on the position provider reporting
a fix unless GPS sending is disabled entirely (in which case the operator
has decided the clock source is trustworthy, e.g. NTP).
"""

import asyncio
import contextlib
from datetime import datetime
from typing import Any, Protocol

from backend.core.config import TimeSyncSettings
from backend.core.structured_logging import get_logger
from backend.integrations.rvc.time_broadcast import (
    DGN_DATE_TIME_STATUS,
    DGN_GPS_DATE_TIME_STATUS,
    DGN_GPS_POSITION,
    DGN_GPS_STATUS,
    DGN_GPS_TIME_STATUS,
    encode_date_time,
    encode_gps_position,
    encode_gps_status,
    encode_gps_time_status,
    rvc_arbitration_id,
    timezone_code,
    utc_now,
)

logger = get_logger(__name__, "TimeSyncService")

# GPS_DATE_TIME_STATUS and SET_DATE_TIME use priority 5 per spec; status
# broadcasts use the default 6.
_PRIORITY_STATUS = 6
_PRIORITY_GPS_DATE_TIME = 5


class PositionProvider(Protocol):
    """Anything that can report the current GPS fix (the trip log service)."""

    def get_current_position(self) -> dict[str, Any]: ...


class TimeSyncService:
    """Broadcast coach time and GPS data onto the RV-C bus."""

    def __init__(
        self,
        settings: TimeSyncSettings,
        can_facade: Any,
        source_address: int,
        position_provider: PositionProvider | None = None,
    ) -> None:
        self._settings = settings
        self._can_facade = can_facade
        self._source_address = source_address
        self._position_provider = position_provider

        self._running = False
        self._task: asyncio.Task | None = None
        self._announced_gps_time = False
        self._tx_count = 0
        self._tx_errors = 0

    async def start(self) -> None:
        """Start the broadcast loop."""
        if self._running:
            return
        logger.info(
            "Starting Time Sync Service",
            source_address=f"0x{self._source_address:02X}",
            interface=self._settings.interface,
        )
        self._running = True
        self._task = asyncio.create_task(self._broadcast_loop())
        logger.info("Time Sync Service started")

    async def stop(self) -> None:
        """Stop broadcasting (the previous master resumes per spec)."""
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("Time Sync Service stopped")

    # ------------------------------------------------------------------

    async def _broadcast_loop(self) -> None:
        while self._running:
            try:
                await self._broadcast_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error broadcasting time/GPS frames")
            await asyncio.sleep(self._settings.broadcast_interval_seconds)

    async def _broadcast_once(self) -> None:
        position = (
            self._position_provider.get_current_position()
            if self._position_provider is not None
            else None
        )
        has_fix = bool(position and position.get("fix"))

        # Clock trustworthiness: chrony disciplines the system clock from
        # this same GPS. Without a fix (and with GPS sending configured) we
        # stay quiet rather than propagate a possibly free-running clock.
        if self._settings.send_gps and self._position_provider is not None and not has_fix:
            return

        now_utc = utc_now()
        now_local = now_utc.astimezone()

        await self._send(
            rvc_arbitration_id(DGN_DATE_TIME_STATUS, self._source_address, _PRIORITY_STATUS),
            encode_date_time(now_local, timezone_code()),
        )

        if not self._announced_gps_time:
            await self._send(
                rvc_arbitration_id(
                    DGN_GPS_DATE_TIME_STATUS, self._source_address, _PRIORITY_GPS_DATE_TIME
                ),
                encode_date_time(now_local, timezone_code()),
            )
            self._announced_gps_time = True

        if self._settings.send_gps and has_fix and position is not None:
            await self._send_gps_frames(position, now_utc)

    async def _send_gps_frames(self, position: dict[str, Any], now_utc: datetime) -> None:
        latitude = position.get("latitude")
        longitude = position.get("longitude")
        if latitude is None or longitude is None:
            return
        await self._send(
            rvc_arbitration_id(DGN_GPS_POSITION, self._source_address, _PRIORITY_STATUS),
            encode_gps_position(latitude, longitude),
        )
        await self._send(
            rvc_arbitration_id(DGN_GPS_STATUS, self._source_address, _PRIORITY_STATUS),
            encode_gps_status(
                heading_deg=position.get("course_deg"),
                speed_mps=position.get("speed_mps"),
                altitude_m=position.get("altitude_m"),
                satellites=None,  # not exposed by the position provider
                fix_mode=3,
            ),
        )
        await self._send(
            rvc_arbitration_id(DGN_GPS_TIME_STATUS, self._source_address, _PRIORITY_STATUS),
            encode_gps_time_status(now_utc),
        )

    async def _send(self, arbitration_id: int, data: bytes) -> None:
        result = await self._can_facade.send_raw_message(
            arbitration_id=arbitration_id,
            data=data,
            interface=self._settings.interface,
        )
        if result.get("success"):
            self._tx_count += 1
        else:
            self._tx_errors += 1
            logger.warning(
                "Time sync TX failed: %s (id=0x%08X)",
                result.get("error", "unknown"),
                arbitration_id,
            )

    # ------------------------------------------------------------------

    def get_health_status(self) -> dict[str, Any]:
        """Health for the composition root."""
        return {
            "service": "TimeSyncService",
            "healthy": self._running,
            "running": self._running,
            "frames_sent": self._tx_count,
            "tx_errors": self._tx_errors,
        }
