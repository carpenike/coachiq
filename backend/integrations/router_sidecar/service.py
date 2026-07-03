"""RouterOS sidecar cache service and poller scaffold."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from typing import Any

from backend.integrations.router_sidecar.app import create_router_sidecar_app
from backend.integrations.router_sidecar.gpsd import GpsdClient, GpsdTpv
from backend.integrations.router_sidecar.location import (
    LocationEvaluator,
    LocationEvaluatorConfig,
)
from backend.integrations.router_sidecar.starlink import StarlinkGrpcClient, StarlinkSnapshot
from backend.integrations.router_sidecar.verdict import (
    StarlinkVerdictConfig,
    StarlinkVerdictEvaluator,
    format_starlink_raw,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from backend.core.config import RouterSidecarSettings

logger = logging.getLogger(__name__)


class RouterSidecarService:
    """Own cached RouterOS sidecar tokens and background poller lifecycle."""

    def __init__(
        self,
        settings: RouterSidecarSettings,
        gpsd_client: GpsdClient | None = None,
        location_evaluator: LocationEvaluator | None = None,
        starlink_client: StarlinkGrpcClient | None = None,
        starlink_evaluator: StarlinkVerdictEvaluator | None = None,
    ) -> None:
        self.settings = settings
        self._location_state = "unknown"
        self._starlink_verdict = "unknown"
        self._starlink_raw = "unknown=1"
        self._starlink_snapshot: StarlinkSnapshot | None = None
        self._starlink_last_error: str | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._running = False
        self._last_gps_fix: GpsdTpv | None = None
        self._gpsd_client = gpsd_client or GpsdClient(settings.gpsd_host, settings.gpsd_port)
        self._starlink_client = starlink_client or StarlinkGrpcClient(
            settings.dish_host,
            settings.dish_port,
        )
        self._location_evaluator = location_evaluator or LocationEvaluator(
            LocationEvaluatorConfig(
                home_latitude=settings.home_latitude,
                home_longitude=settings.home_longitude,
                geofence_radius_m=settings.geofence_radius_m,
                hysteresis_count=settings.location_hysteresis_count,
                fix_staleness_seconds=settings.gps_fix_staleness_seconds,
            )
        )
        self._starlink_evaluator = starlink_evaluator or StarlinkVerdictEvaluator(
            StarlinkVerdictConfig(
                obstruction_fraction_degraded=settings.starlink_obstruction_fraction_degraded,
                obstruction_fraction_recovery=settings.starlink_obstruction_fraction_recovery,
                pop_ping_drop_rate_degraded=settings.starlink_pop_ping_drop_rate_degraded,
                pop_ping_drop_rate_recovery=settings.starlink_pop_ping_drop_rate_recovery,
                pop_ping_latency_ms_degraded=settings.starlink_pop_ping_latency_ms_degraded,
                pop_ping_latency_ms_recovery=settings.starlink_pop_ping_latency_ms_recovery,
                recent_outage_count_degraded=settings.starlink_recent_outage_count_degraded,
                history_sample_window=settings.starlink_history_sample_window,
                degraded_debounce_seconds=settings.starlink_degraded_debounce_seconds,
                down_recovery_dwell_seconds=settings.starlink_down_recovery_dwell_seconds,
            )
        )
        self.app: FastAPI = create_router_sidecar_app(
            location_state=self.get_location_state,
            starlink_verdict=self.get_starlink_verdict,
            starlink_raw=self.get_starlink_raw,
            starlink_status=self.get_starlink_status_payload,
            starlink_history=self.get_starlink_history_payload,
            starlink_diagnostics=self.get_starlink_diagnostics_payload,
            starlink_device_info=self.get_starlink_device_info_payload,
        )

    async def start(self) -> None:
        """Start background pollers."""
        if self._running:
            return
        self._running = True
        if self.settings.enabled:
            self._create_task(self._gpsd_poll_loop(), "router-sidecar-gpsd")
            self._create_task(self._location_refresh_loop(), "router-sidecar-location")
            self._create_task(self._starlink_poll_loop(), "router-sidecar-starlink")
        logger.info("Router sidecar service started")

    async def stop(self) -> None:
        """Stop background pollers."""
        if not self._running:
            return
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        self._running = False
        logger.info("Router sidecar service stopped")

    def get_location_state(self) -> str:
        """Return the cached location state token."""
        return self._location_state

    def get_starlink_verdict(self) -> str:
        """Return the cached Starlink verdict token."""
        return self._starlink_verdict

    def get_starlink_raw(self) -> str:
        """Return the cached Starlink raw key-value line."""
        return self._starlink_raw

    def get_starlink_status_payload(self) -> dict[str, Any]:
        """Return cached Starlink status with staleness metadata."""
        data = self._starlink_snapshot.status if self._starlink_snapshot else None
        return self._wrap_starlink_payload(data)

    def get_starlink_history_payload(self, window: int | None = None) -> dict[str, Any]:
        """Return cached Starlink history with optional array trimming."""
        data = self._starlink_snapshot.history if self._starlink_snapshot else None
        if data is not None and window is not None:
            data = _trim_history(data, window)
        return self._wrap_starlink_payload(data)

    def get_starlink_diagnostics_payload(self) -> dict[str, Any]:
        """Return cached Starlink diagnostics with staleness metadata."""
        data = self._starlink_snapshot.diagnostics if self._starlink_snapshot else None
        return self._wrap_starlink_payload(data)

    def get_starlink_device_info_payload(self) -> dict[str, Any]:
        """Return cached Starlink device info with staleness metadata."""
        data = self._starlink_snapshot.device_info if self._starlink_snapshot else None
        return self._wrap_starlink_payload(data)

    def _create_task(self, coroutine, name: str) -> None:
        task = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _gpsd_poll_loop(self) -> None:
        while self._running:
            try:
                async for fix in self._gpsd_client.watch_tpv():
                    if not self._running:
                        return
                    self._last_gps_fix = fix
                    self._refresh_location_state()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("gpsd poll failed: %s", exc)
                self._last_gps_fix = None
                self._refresh_location_state()
            await asyncio.sleep(self.settings.gps_poll_interval_seconds)

    async def _location_refresh_loop(self) -> None:
        while self._running:
            self._refresh_location_state()
            await asyncio.sleep(min(self.settings.gps_poll_interval_seconds, 5.0))

    def _refresh_location_state(self) -> None:
        self._location_state = self._location_evaluator.evaluate(
            self._last_gps_fix,
            now=datetime.now(UTC),
        )

    async def _starlink_poll_loop(self) -> None:
        while self._running:
            try:
                snapshot = await asyncio.to_thread(self._starlink_client.fetch_snapshot_blocking)
                self._refresh_starlink(snapshot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Starlink poll failed: %s", exc)
                self._refresh_starlink(
                    StarlinkSnapshot(reachable=False, error=f"{type(exc).__name__}: {exc}")
                )
            await asyncio.sleep(self.settings.starlink_poll_interval_seconds)

    def _refresh_starlink(self, snapshot: StarlinkSnapshot) -> None:
        if snapshot.reachable:
            self._starlink_snapshot = snapshot
            self._starlink_last_error = None
            active_snapshot = snapshot
            self._starlink_verdict = self._starlink_evaluator.evaluate(
                active_snapshot,
                now=datetime.now(UTC),
            )
            self._starlink_raw = format_starlink_raw(active_snapshot)
        else:
            self._starlink_last_error = snapshot.error or "unreachable"
            self._starlink_verdict = "unknown"
            self._starlink_raw = format_starlink_raw(snapshot)

    def _wrap_starlink_payload(self, data: dict[str, Any] | None) -> dict[str, Any]:
        snapshot = self._starlink_snapshot
        if snapshot is None or snapshot.fetched_at is None:
            return {
                "fetched_at": None,
                "age_s": None,
                "stale": True,
                "error": self._starlink_last_error,
                "data": None,
            }

        age_s = max(0.0, time.time() - snapshot.fetched_at)
        stale = (
            self._starlink_last_error is not None
            or age_s > self.settings.starlink_telemetry_staleness_seconds
        )
        return {
            "fetched_at": snapshot.fetched_at,
            "age_s": age_s,
            "stale": stale,
            "error": self._starlink_last_error,
            "data": data,
        }


def _trim_history(history: dict[str, Any], window: int) -> dict[str, Any]:
    trimmed = copy.deepcopy(history)
    for key, value in list(trimmed.items()):
        if isinstance(value, list):
            trimmed[key] = value[-window:]
    return trimmed
