"""RouterOS sidecar cache service and poller scaffold."""

import asyncio
import contextlib
import logging

from fastapi import FastAPI

from backend.core.config import RouterSidecarSettings
from backend.integrations.router_sidecar.app import create_router_sidecar_app

logger = logging.getLogger(__name__)


class RouterSidecarService:
    """Own cached RouterOS sidecar tokens and background poller lifecycle."""

    def __init__(self, settings: RouterSidecarSettings) -> None:
        self.settings = settings
        self._location_state = "unknown"
        self._starlink_verdict = "unknown"
        self._starlink_raw = "unknown=1"
        self._tasks: set[asyncio.Task[None]] = set()
        self._running = False
        self.app: FastAPI = create_router_sidecar_app(
            location_state=self.get_location_state,
            starlink_verdict=self.get_starlink_verdict,
            starlink_raw=self.get_starlink_raw,
        )

    async def start(self) -> None:
        """Start background pollers. S1 intentionally starts with no pollers."""
        if self._running:
            return
        self._running = True
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
