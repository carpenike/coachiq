"""
Trip Log Service - GPS breadcrumb recording.

Reads position from the local gpsd (the same daemon that feeds the Cerbo GX
and the router sidecar) and records a thoughtful trail rather than a 1 Hz
firehose:

- a breadcrumb is recorded only after moving ``min_distance_m`` from the
  last recorded point (and at most every ``min_interval_seconds``),
- nothing is recorded while parked,
- a trip starts only after movement persists for ``start_confirm_seconds``
  (single-fix GPS speed jitter while parked never opens a trip),
- movement after ``trip_gap_minutes`` of stillness starts a new trip; the
  trip closes (with distance/max-speed stats) when the RV goes still again,
- trips that end having covered less than ``min_trip_distance_m`` are
  discarded rather than stored.

The gpsd connection reconnects with backoff, so GPS or gpsd restarts only
pause recording.
"""

import asyncio
import contextlib
import time
from typing import Any

from backend.core.config import TripLogSettings
from backend.core.structured_logging import get_logger
from backend.integrations.router_sidecar.gpsd import GpsdClient, GpsdTpv
from backend.integrations.router_sidecar.location import haversine_distance_m

logger = get_logger(__name__, "TripLogService")

# gpsd TPV mode 2 = 2D fix, 3 = 3D fix.
_MIN_FIX_MODE = 2
_RECONNECT_DELAY_SECONDS = 5.0
_MAX_RECONNECT_DELAY_SECONDS = 60.0
_PRUNE_INTERVAL_SECONDS = 24 * 3600.0


class TripLogService:
    """Background recorder of GPS breadcrumbs segmented into trips."""

    def __init__(self, settings: TripLogSettings, trip_log_repository: Any) -> None:
        self._settings = settings
        self._repository = trip_log_repository
        self._client = GpsdClient(settings.gpsd_host, settings.gpsd_port)

        self._running = False
        self._task: asyncio.Task | None = None
        self._prune_task: asyncio.Task | None = None
        self._connected = False

        # Sampling state
        self._active_trip_id: int | None = None
        self._active_trip_distance_m = 0.0
        self._pending_start_at: float | None = None
        self._last_recorded: tuple[float, float] | None = None  # (lat, lon)
        self._last_recorded_at = 0.0
        self._last_movement_at = 0.0
        self._last_fix: GpsdTpv | None = None
        self._last_fix_at = 0.0

    async def start(self) -> None:
        """Resume any dangling trip, then start the gpsd watch loop."""
        if self._running:
            return
        logger.info(
            "Starting Trip Log Service",
            gpsd=f"{self._settings.gpsd_host}:{self._settings.gpsd_port}",
        )
        await self._repository.ensure_tables()
        if self._settings.min_trip_distance_m > 0:
            removed = await self._repository.delete_short_trips(self._settings.min_trip_distance_m)
            if removed:
                logger.info("Removed %d short noise trips from the log", removed)
        await self._resume_or_close_dangling_trip()
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        if self._settings.retention_days > 0:
            self._prune_task = asyncio.create_task(self._prune_loop())
        logger.info("Trip Log Service started")

    async def stop(self) -> None:
        """Stop background tasks; an active trip stays open for resume."""
        if not self._running:
            return
        self._running = False
        for task in (self._task, self._prune_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._task = None
        self._prune_task = None
        logger.info("Trip Log Service stopped")

    # ------------------------------------------------------------------
    # gpsd session
    # ------------------------------------------------------------------

    async def _watch_loop(self) -> None:
        delay = _RECONNECT_DELAY_SECONDS
        while self._running:
            try:
                async for tpv in self._client.watch_tpv():
                    if not self._running:
                        break
                    self._connected = True
                    delay = _RECONNECT_DELAY_SECONDS
                    try:
                        await self._handle_fix(tpv)
                    except Exception:
                        logger.exception("Error handling GPS fix")
            except asyncio.CancelledError:
                raise
            except OSError as exc:
                logger.warning("gpsd connection lost (%s); retrying in %.0fs", exc, delay)
            self._connected = False
            if not self._running:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, _MAX_RECONNECT_DELAY_SECONDS)

    # ------------------------------------------------------------------
    # Sampling state machine
    # ------------------------------------------------------------------

    async def _handle_fix(self, tpv: GpsdTpv) -> None:
        if tpv.mode < _MIN_FIX_MODE or tpv.lat is None or tpv.lon is None:
            return

        now = time.time()
        self._last_fix = tpv
        self._last_fix_at = now

        speed = tpv.speed or 0.0
        moving_by_speed = speed >= self._settings.stationary_speed_mps
        distance_from_last = (
            haversine_distance_m(self._last_recorded[0], self._last_recorded[1], tpv.lat, tpv.lon)
            if self._last_recorded is not None
            else None
        )
        moving = moving_by_speed or (
            distance_from_last is not None and distance_from_last >= self._settings.min_distance_m
        )

        if moving:
            self._last_movement_at = now

        if self._active_trip_id is None:
            if not moving:
                self._pending_start_at = None
                if self._last_recorded is None:
                    # Parked: just remember where we are so the first movement
                    # has a reference point.
                    self._last_recorded = (tpv.lat, tpv.lon)
                return
            # Movement must persist before a trip opens: a single fix with
            # phantom speed (GPS jitter while parked) would otherwise create
            # a zero-distance trip.
            if self._pending_start_at is None:
                self._pending_start_at = now
            if now - self._pending_start_at >= self._settings.start_confirm_seconds:
                self._pending_start_at = None
                await self._start_trip(tpv, now)
            return

        # Active trip: close it after a long stationary gap...
        gap_seconds = self._settings.trip_gap_minutes * 60
        if not moving and now - self._last_movement_at > gap_seconds:
            await self._end_trip()
            return

        # ...or record the next breadcrumb once we've gone far enough.
        if (
            distance_from_last is not None
            and distance_from_last >= self._settings.min_distance_m
            and now - self._last_recorded_at >= self._settings.min_interval_seconds
        ):
            await self._record_point(tpv, now, distance_from_last)

    async def _start_trip(self, tpv: GpsdTpv, now: float) -> None:
        if tpv.lat is None or tpv.lon is None:  # narrowed by caller; keeps pyright honest
            return
        self._active_trip_id = await self._repository.start_trip(now, tpv.lat, tpv.lon)
        self._active_trip_distance_m = 0.0
        self._last_movement_at = now
        logger.info("Trip started", trip_id=self._active_trip_id, lat=tpv.lat, lon=tpv.lon)
        await self._record_point(tpv, now, 0.0)

    async def _record_point(self, tpv: GpsdTpv, now: float, leg_distance_m: float) -> None:
        if tpv.lat is None or tpv.lon is None:  # narrowed by caller; keeps pyright honest
            return
        await self._repository.add_point(
            trip_id=self._active_trip_id,
            timestamp=now,
            latitude=tpv.lat,
            longitude=tpv.lon,
            leg_distance_m=leg_distance_m,
            speed_mps=tpv.speed,
            course_deg=tpv.track,
            altitude_m=tpv.alt,
        )
        self._active_trip_distance_m += leg_distance_m
        self._last_recorded = (tpv.lat, tpv.lon)
        self._last_recorded_at = now

    async def _end_trip(self) -> None:
        trip_id = self._active_trip_id
        if trip_id is None or self._last_recorded is None:
            self._active_trip_id = None
            return
        if self._active_trip_distance_m < self._settings.min_trip_distance_m:
            # The RV never really went anywhere — GPS noise opened the trip.
            await self._repository.delete_trip(trip_id)
            logger.info(
                "Discarded short trip",
                trip_id=trip_id,
                distance_m=round(self._active_trip_distance_m, 1),
            )
        else:
            await self._repository.end_trip(
                trip_id,
                ended_at=self._last_movement_at,
                latitude=self._last_recorded[0],
                longitude=self._last_recorded[1],
            )
            logger.info("Trip ended", trip_id=trip_id)
        self._active_trip_id = None
        self._active_trip_distance_m = 0.0

    async def _resume_or_close_dangling_trip(self) -> None:
        """After a restart, resume a recent active trip or close a stale one."""
        trip = await self._repository.get_active_trip()
        if trip is None:
            return
        distance_m = trip.get("distance_m") or 0.0
        too_short = distance_m < self._settings.min_trip_distance_m
        last_point = await self._repository.get_latest_point(trip["id"])
        gap_seconds = self._settings.trip_gap_minutes * 60
        if last_point is None:
            if too_short:
                await self._repository.delete_trip(trip["id"])
            else:
                await self._repository.end_trip(
                    trip["id"],
                    ended_at=trip["started_at"],
                    latitude=trip["start_latitude"],
                    longitude=trip["start_longitude"],
                )
            return
        if time.time() - last_point["timestamp"] > gap_seconds:
            if too_short:
                await self._repository.delete_trip(trip["id"])
                logger.info("Discarded stale short trip %s from before restart", trip["id"])
            else:
                await self._repository.end_trip(
                    trip["id"],
                    ended_at=last_point["timestamp"],
                    latitude=last_point["latitude"],
                    longitude=last_point["longitude"],
                )
                logger.info("Closed stale trip %s from before restart", trip["id"])
        else:
            self._active_trip_id = trip["id"]
            self._active_trip_distance_m = distance_m
            self._last_recorded = (last_point["latitude"], last_point["longitude"])
            self._last_recorded_at = last_point["timestamp"]
            self._last_movement_at = last_point["timestamp"]
            logger.info("Resumed active trip %s across restart", trip["id"])

    async def _prune_loop(self) -> None:
        while True:
            await asyncio.sleep(_PRUNE_INTERVAL_SECONDS)
            cutoff = time.time() - self._settings.retention_days * 24 * 3600
            try:
                pruned = await self._repository.prune_older_than(cutoff)
                if pruned:
                    logger.info("Pruned %d old breadcrumbs", pruned)
            except Exception:
                logger.exception("Error pruning trip log")

    # ------------------------------------------------------------------
    # Read side
    # ------------------------------------------------------------------

    def get_current_position(self) -> dict[str, Any]:
        """Latest fix plus recording state, for the API."""
        tpv = self._last_fix
        return {
            "connected": self._connected,
            "fix": tpv is not None and tpv.mode >= _MIN_FIX_MODE,
            "latitude": tpv.lat if tpv else None,
            "longitude": tpv.lon if tpv else None,
            "speed_mps": tpv.speed if tpv else None,
            "course_deg": tpv.track if tpv else None,
            "altitude_m": tpv.alt if tpv else None,
            "fix_age_seconds": (time.time() - self._last_fix_at) if tpv else None,
            "active_trip_id": self._active_trip_id,
        }

    def get_health_status(self) -> dict[str, Any]:
        """Health for the composition root."""
        return {
            "service": "TripLogService",
            "healthy": self._running,
            "running": self._running,
            "gpsd_connected": self._connected,
            "active_trip_id": self._active_trip_id,
        }
