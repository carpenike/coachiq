"""Server-Sent Events endpoint streaming realtime updates to the frontend.

One authenticated GET /api/events stream replaces the old /ws data socket:
commands stay on REST, server push rides SSE. Auth is enforced by the standard
AuthenticationMiddleware (Authorization: Bearer header), unlike the old
WebSocket path which carried the token in the query string.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.core.dependencies import EventBrokerDep
from backend.services.system.event_broker import BrokerEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["events"])

# Proxies (and the client's staleness watchdog) need periodic bytes on an idle
# stream; SSE comment lines are the protocol's built-in keepalive.
HEARTBEAT_INTERVAL_S = 15.0
# Reconnect delay hint honored by EventSource-style clients.
RETRY_HINT_MS = 3000


def _format_sse(event: BrokerEvent) -> str:
    return f"id: {event.id}\nevent: {event.event}\ndata: {event.data}\n\n"


def _parse_last_event_id(request: Request) -> int | None:
    raw = request.headers.get("last-event-id")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@router.get("/events")
async def stream_events(request: Request, event_broker: EventBrokerDep) -> StreamingResponse:
    """Stream realtime events (entity_update, entity_created, ...) as SSE.

    Reconnecting clients send Last-Event-ID and get the gap replayed from the
    broker's ring buffer; fresh connections get no replay and resync via REST.
    """
    last_event_id = _parse_last_event_id(request)

    async def event_stream() -> AsyncGenerator[str, None]:
        queue, replay = event_broker.subscribe(last_event_id)
        client = request.client
        client_label = f"{client.host}:{client.port}" if client else "unknown"
        logger.info(
            "SSE client connected: %s (replaying %d events since id %s)",
            client_label,
            len(replay),
            last_event_id,
        )
        try:
            yield f"retry: {RETRY_HINT_MS}\n\n"
            for event in replay:
                yield _format_sse(event)
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL_S)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    break  # broker shutdown
                yield _format_sse(item)
        finally:
            event_broker.unsubscribe(queue)
            logger.info("SSE client disconnected: %s", client_label)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tell buffering reverse proxies (nginx/Caddy) to pass chunks through.
            "X-Accel-Buffering": "no",
        },
    )
