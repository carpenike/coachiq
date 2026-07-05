"""
Async MQTT client for a Venus OS (Cerbo GX) local broker.

Handles the dbus-flashmq session protocol:

- subscribes to ``N/#`` and discovers the portal id from the first
  notification (or uses a configured one),
- sends an initial bare keepalive to trigger a full republish of all topics,
- then keeps the broker publishing with suppress-republish keepalives at
  least every 60 seconds (the broker goes silent without them),
- reconnects with capped exponential backoff,
- publishes ``W/...`` writes for control paths.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiomqtt

from backend.integrations.victron.topics import (
    KEEPALIVE_SUPPRESS_REPUBLISH,
    VictronUpdate,
    keepalive_topic,
    parse_notification,
    portal_id_from_topic,
    write_payload,
    write_topic,
)

logger = logging.getLogger(__name__)

UpdateCallback = Callable[[VictronUpdate], Awaitable[None]]
ConnectionCallback = Callable[[bool], Awaitable[None]]


class VictronMqttClient:
    """Maintains the MQTT session to a Venus OS broker and dispatches updates."""

    def __init__(  # noqa: PLR0913 - keyword-only session/auth/timing knobs, intentional API
        self,
        *,
        host: str,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        portal_id: str | None = None,
        keepalive_interval: float = 30.0,
        reconnect_delay: float = 2.0,
        max_reconnect_delay: float = 60.0,
        on_update: UpdateCallback,
        on_connection_change: ConnectionCallback | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._portal_id = portal_id
        self._keepalive_interval = keepalive_interval
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._on_update = on_update
        self._on_connection_change = on_connection_change

        self._client: aiomqtt.Client | None = None
        self._portal_discovered = asyncio.Event()
        if portal_id:
            self._portal_discovered.set()
        self._stopping = False
        self._connected = False

    @property
    def portal_id(self) -> str | None:
        """Portal id in use (configured or discovered from traffic)."""
        return self._portal_id

    @property
    def connected(self) -> bool:
        """Whether an MQTT session is currently established."""
        return self._connected

    async def run(self) -> None:
        """Run the session forever, reconnecting until stop() is called."""
        delay = self._reconnect_delay
        while not self._stopping:
            try:
                await self._run_session()
                delay = self._reconnect_delay
            except aiomqtt.MqttError as exc:
                if self._stopping:
                    break
                logger.warning(
                    "Victron MQTT connection to %s:%s lost (%s); retrying in %.0fs",
                    self._host,
                    self._port,
                    exc,
                    delay,
                )
            await self._set_connected(False)
            if self._stopping:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._max_reconnect_delay)

    async def stop(self) -> None:
        """Stop the session loop; run() returns after the current iteration."""
        self._stopping = True

    async def _run_session(self) -> None:
        async with aiomqtt.Client(
            self._host,
            port=self._port,
            username=self._username,
            password=self._password,
        ) as client:
            self._client = client
            keepalive_task = asyncio.create_task(self._keepalive_loop())
            try:
                await client.subscribe("N/#")
                await self._set_connected(True)
                logger.info("Victron MQTT connected to %s:%s", self._host, self._port)
                async for message in client.messages:
                    if self._stopping:
                        break
                    await self._handle_message(str(message.topic), message.payload)
            finally:
                self._client = None
                keepalive_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await keepalive_task

    async def _handle_message(self, topic: str, payload: Any) -> None:
        if self._portal_id is None:
            portal_id = portal_id_from_topic(topic)
            if portal_id:
                self._portal_id = portal_id
                self._portal_discovered.set()
                logger.info("Discovered Victron portal id: %s", portal_id)

        if not isinstance(payload, bytes | bytearray | str):
            return
        update = parse_notification(topic, payload)
        if update is None:
            return
        try:
            await self._on_update(update)
        except Exception:
            logger.exception("Error handling Victron update for %s", topic)

    async def _keepalive_loop(self) -> None:
        """Keep the broker publishing.

        The first keepalive is sent bare, which makes dbus-flashmq republish
        every topic — that is our initial full-state sync. Subsequent ones
        suppress the republish to keep traffic down.
        """
        await self._portal_discovered.wait()
        portal_id = self._portal_id
        client = self._client
        if portal_id is None or client is None:
            return
        topic = keepalive_topic(portal_id)
        await client.publish(topic, "")
        while True:
            await asyncio.sleep(self._keepalive_interval)
            client = self._client
            if client is None:
                return
            await client.publish(topic, KEEPALIVE_SUPPRESS_REPUBLISH)

    async def write_value(self, service_type: str, instance: str, path: str, value: Any) -> None:
        """Write a value to a Venus OS D-Bus path over MQTT.

        Raises RuntimeError when no session is established yet (callers
        surface this as a 503-style condition).
        """
        client = self._client
        portal_id = self._portal_id
        if client is None or portal_id is None or not self._connected:
            msg = "Victron MQTT client is not connected"
            raise RuntimeError(msg)
        topic = write_topic(portal_id, service_type, instance, path)
        await client.publish(topic, write_payload(value))
        logger.info("Victron write: %s = %r", topic, value)

    async def _set_connected(self, connected: bool) -> None:
        if connected == self._connected:
            return
        self._connected = connected
        if self._on_connection_change is not None:
            try:
                await self._on_connection_change(connected)
            except Exception:
                logger.exception("Error in Victron connection-change callback")
