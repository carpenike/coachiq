"""RouterOS sidecar cache service and poller scaffold."""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from fastapi import FastAPI

from backend.core.config import RouterSidecarSettings
from backend.integrations.router_sidecar.app import create_router_sidecar_app
from backend.integrations.router_sidecar.gpsd import GpsdClient, GpsdTpv
from backend.integrations.router_sidecar.location import (
    LocationEvaluator,
    LocationEvaluatorConfig,
)

logger = logging.getLogger(__name__)


class RouterSidecarService:
    """Own cached RouterOS sidecar tokens and background poller lifecycle."""

    def __init__(
        self,
        settings: RouterSidecarSettings,
        gpsd_client: GpsdClient | None = None,
        location_evaluator: LocationEvaluator | None = None,
    ) -> None:
        self.settings = settings
        self._location_state = "unknown"
        self._starlink_verdict = "unknown"
        self._starlink_raw = "unknown=1"
        self._tasks: set[asyncio.Task[None]] = set()
        self._running = False
        self._last_gps_fix: GpsdTpv | None = None
        self._gpsd_client = gpsd_client or GpsdClient(settings.gpsd_host, settings.gpsd_port)
        self._location_evaluator = location_evaluator or LocationEvaluator(
            LocationEvaluatorConfig(
                home_latitude=settings.home_latitude,
                home_longitude=settings.home_longitude,
                geofence_radius_m=settings.geofence_radius_m,
                hysteresis_count=settings.location_hysteresis_count,
                fix_staleness_seconds=settings.gps_fix_staleness_seconds,
            )
        )
        self.app: FastAPI = create_router_sidecar_app(
            location_state=self.get_location_state,
            starlink_verdict=self.get_starlink_verdict,
            starlink_raw=self.get_starlink_raw,
        )

    async def start(self) -> None:
        """Start background pollers."""
        if self._running:
            return
        self._running = True
        if self.settings.enabled:
            self._create_task(self._gpsd_poll_loop(), "router-sidecar-gpsd")
            self._create_task(self._location_refresh_loop(), "router-sidecar-location")
        logger.info("Router sidecar service started")

    async def stop(self) -> None:
        """Stop background pollers."""
        if not self._running:
            return
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
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
