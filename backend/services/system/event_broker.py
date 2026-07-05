"""In-process event broker backing the /api/events SSE stream.

Single fan-out hub for server-push state updates (entity updates, guardrail
halts, ...). Producers publish typed events; each connected SSE client owns a
bounded queue fed from here.

Design constraints this encodes:

- Monotonic event ids + a bounded replay buffer give reconnecting clients gap
  recovery via the standard ``Last-Event-ID`` header instead of bespoke
  reconnect protocols.
- Per-subscriber queues are bounded and lossy (oldest dropped first) so one
  slow reader can never stall the CAN RX path or starve other readers. All
  published events are state snapshots, so a newer event always supersedes a
  dropped older one.
- Single-process by design, like the rest of the composition root. There is no
  cross-worker fan-out; the deployment runs one uvicorn worker.
"""

import asyncio
import contextlib
import json
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BrokerEvent:
    """A published event: SSE event name plus a JSON-serialized payload."""

    id: int
    event: str
    data: str


class EventBroker:
    """Fan-out hub for server-push events with bounded replay history."""

    HISTORY_SIZE = 1000
    SUBSCRIBER_QUEUE_SIZE = 256

    def __init__(self) -> None:
        self._history: deque[BrokerEvent] = deque(maxlen=self.HISTORY_SIZE)
        self._subscribers: set[asyncio.Queue[BrokerEvent | None]] = set()
        self._next_id = 1
        self._dropped_events = 0
        self._running = False

    async def start(self) -> None:
        """Start the broker (lifecycle parity with other root services)."""
        self._running = True
        logger.info("EventBroker started")

    async def stop(self) -> None:
        """Stop the broker and wake all subscribers so their streams end."""
        self._running = False
        for queue in list(self._subscribers):
            # Sentinel wakes a blocked stream generator; full queues are being
            # drained by their reader and will observe _running on next loop.
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)
        logger.info("EventBroker stopped")

    @property
    def last_event_id(self) -> int:
        """Id of the most recently published event (0 when none yet)."""
        return self._next_id - 1

    async def publish(self, event: str, data: Any) -> None:
        """Publish an event to all subscribers and the replay buffer.

        Never blocks the publisher: a subscriber whose queue is full loses its
        oldest queued event instead.
        """
        broker_event = BrokerEvent(
            id=self._next_id, event=event, data=json.dumps(data, default=str)
        )
        self._next_id += 1
        self._history.append(broker_event)
        for queue in self._subscribers:
            try:
                queue.put_nowait(broker_event)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                self._dropped_events += 1
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(broker_event)

    def subscribe(
        self, last_event_id: int | None = None
    ) -> tuple[asyncio.Queue[BrokerEvent | None], list[BrokerEvent]]:
        """Register a subscriber queue and return events missed since last_event_id.

        Args:
            last_event_id: The client's Last-Event-ID, or None for a fresh
                connection (no replay — the client resyncs via REST instead).

        Returns:
            The subscriber's queue and the replay list, oldest first.
        """
        queue: asyncio.Queue[BrokerEvent | None] = asyncio.Queue(maxsize=self.SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(queue)
        replay: list[BrokerEvent] = []
        if last_event_id is not None:
            replay = [event for event in self._history if event.id > last_event_id]
        return queue, replay

    def unsubscribe(self, queue: asyncio.Queue[BrokerEvent | None]) -> None:
        """Remove a subscriber queue; safe to call more than once."""
        self._subscribers.discard(queue)

    def get_health_status(self) -> dict[str, Any]:
        """Health snapshot for the service registry."""
        return {
            "service": "EventBroker",
            "healthy": self._running,
            "running": self._running,
            "subscribers": len(self._subscribers),
            "last_event_id": self.last_event_id,
            "dropped_events": self._dropped_events,
        }
