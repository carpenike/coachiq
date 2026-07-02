"""Managed uvicorn server for the RouterOS sidecar app."""

import asyncio
import logging
from typing import Any

import uvicorn
from fastapi import FastAPI

from backend.core.config import RouterSidecarSettings

logger = logging.getLogger(__name__)


class RouterSidecarServer:
    """Run the RouterOS sidecar app as a second uvicorn listener."""

    def __init__(
        self,
        settings: RouterSidecarSettings,
        app: FastAPI,
        log_config: dict[str, Any] | None = None,
    ) -> None:
        self._settings = settings
        self._app = app
        self._log_config = log_config
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the sidecar listener if it is enabled."""
        if not self._settings.enabled:
            logger.info("Router sidecar listener disabled")
            return
        if self._task is not None:
            return

        config = uvicorn.Config(
            self._app,
            host=self._settings.host,
            port=self._settings.port,
            log_level="info",
            log_config=self._log_config,
            access_log=self._settings.access_log,
            lifespan="on",
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve(), name="router-sidecar-uvicorn")

        for _ in range(100):
            if self._server.started:
                logger.info(
                    "Router sidecar listener started on %s:%s",
                    self._settings.host,
                    self._settings.port,
                )
                return
            if self._task.done():
                break
            await asyncio.sleep(0.05)

        if self._task.done():
            self._task.result()
        msg = "Router sidecar listener did not start within timeout"
        raise RuntimeError(msg)

    async def stop(self) -> None:
        """Stop the sidecar listener."""
        if self._server is None or self._task is None:
            return

        self._server.should_exit = True
        try:
            await asyncio.wait_for(self._task, timeout=5)
        except TimeoutError:
            logger.warning("Router sidecar listener did not stop cleanly; cancelling")
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        finally:
            self._server = None
            self._task = None
