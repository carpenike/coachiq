"""
Tests for the realtime push channel: EventBroker + the /api/events SSE endpoint.

This suite replaced tests/websocket/test_handlers.py when the /ws data socket
(and the server-side test stubs that existed only to satisfy that suite) was
removed in favor of SSE. The ``websocket`` marker is kept so realtime-channel
coverage stays inside the CI guardrail test selection.
"""

import asyncio

import pytest
from starlette.requests import Request

from backend.api.routers.events import stream_events
from backend.services.system.event_broker import EventBroker

pytestmark = pytest.mark.websocket


@pytest.mark.asyncio
class TestEventBroker:
    """Unit tests for the broker's fan-out, replay, and backpressure rules."""

    async def test_publish_assigns_monotonic_ids(self):
        broker = EventBroker()
        await broker.start()

        await broker.publish("entity_update", {"entity_id": "light_1"})
        await broker.publish("entity_update", {"entity_id": "light_2"})

        assert broker.last_event_id == 2

    async def test_subscriber_receives_published_events(self):
        broker = EventBroker()
        await broker.start()
        queue, replay = broker.subscribe()

        assert replay == []
        await broker.publish("entity_update", {"entity_id": "light_1"})

        event = queue.get_nowait()
        assert event is not None
        assert event.event == "entity_update"
        assert event.id == 1
        assert '"entity_id": "light_1"' in event.data

    async def test_replay_returns_only_events_after_last_event_id(self):
        broker = EventBroker()
        await broker.start()
        for index in range(5):
            await broker.publish("entity_update", {"seq": index})

        _queue, replay = broker.subscribe(last_event_id=3)

        assert [event.id for event in replay] == [4, 5]

    async def test_fresh_subscriber_gets_no_replay(self):
        broker = EventBroker()
        await broker.start()
        await broker.publish("entity_update", {"seq": 1})

        _queue, replay = broker.subscribe(last_event_id=None)

        assert replay == []

    async def test_slow_subscriber_drops_oldest_not_publisher(self):
        broker = EventBroker()
        await broker.start()
        queue, _replay = broker.subscribe()

        overflow = EventBroker.SUBSCRIBER_QUEUE_SIZE + 10
        for index in range(overflow):
            await broker.publish("entity_update", {"seq": index})

        # The queue holds the newest events; the oldest were dropped.
        assert queue.qsize() == EventBroker.SUBSCRIBER_QUEUE_SIZE
        first = queue.get_nowait()
        assert first is not None
        assert first.id == overflow - EventBroker.SUBSCRIBER_QUEUE_SIZE + 1
        assert broker.get_health_status()["dropped_events"] == 10

    async def test_stop_wakes_subscribers_with_sentinel(self):
        broker = EventBroker()
        await broker.start()
        queue, _replay = broker.subscribe()

        await broker.stop()

        assert await asyncio.wait_for(queue.get(), timeout=1.0) is None

    async def test_unsubscribed_queue_no_longer_receives(self):
        broker = EventBroker()
        await broker.start()
        queue, _replay = broker.subscribe()
        broker.unsubscribe(queue)

        await broker.publish("entity_update", {"seq": 1})

        assert queue.qsize() == 0


def _make_request(headers: dict[str, str] | None = None) -> Request:
    """Bare Starlette request for calling the endpoint function directly.

    The stream never ends on its own (heartbeats forever), so these tests
    drive the endpoint's generator directly instead of going through a sync
    TestClient — whose response teardown deadlocks on an infinite stream.
    """
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/events",
        "headers": raw_headers,
        "query_string": b"",
        "client": ("127.0.0.1", 4242),
    }
    return Request(scope)


async def _collect_chunks(broker: EventBroker, response, count: int) -> list[str]:
    """Read `count` chunks from the SSE body, then stop the broker to end it."""
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
        if len(chunks) >= count:
            await broker.stop()
    return chunks


@pytest.mark.asyncio
class TestEventsEndpoint:
    """Tests for GET /api/events framing and replay."""

    async def test_stream_replays_events_after_last_event_id(self):
        broker = EventBroker()
        await broker.start()
        await broker.publish("entity_update", {"entity_id": "light_1"})
        await broker.publish("entity_created", {"entity_id": "tank_1"})

        response = await stream_events(_make_request({"Last-Event-ID": "0"}), broker)
        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"

        # retry hint + both replayed frames, then the broker stops the stream.
        chunks = await _collect_chunks(broker, response, count=3)

        assert chunks[0] == "retry: 3000\n\n"
        assert chunks[1] == 'id: 1\nevent: entity_update\ndata: {"entity_id": "light_1"}\n\n'
        assert chunks[2] == 'id: 2\nevent: entity_created\ndata: {"entity_id": "tank_1"}\n\n'

    async def test_fresh_connection_gets_no_replay(self):
        broker = EventBroker()
        await broker.start()
        await broker.publish("entity_update", {"entity_id": "light_1"})

        response = await stream_events(_make_request(), broker)
        chunks = await _collect_chunks(broker, response, count=1)

        # No Last-Event-ID → no replay; just the retry hint, then shutdown.
        assert chunks == ["retry: 3000\n\n"]

    async def test_invalid_last_event_id_is_treated_as_fresh(self):
        broker = EventBroker()
        await broker.start()
        await broker.publish("entity_update", {"entity_id": "light_1"})

        response = await stream_events(_make_request({"Last-Event-ID": "not-a-number"}), broker)
        chunks = await _collect_chunks(broker, response, count=1)

        assert chunks == ["retry: 3000\n\n"]

    async def test_live_events_reach_an_open_stream(self):
        broker = EventBroker()
        await broker.start()

        response = await stream_events(_make_request(), broker)
        iterator = response.body_iterator

        assert await anext(iterator) == "retry: 3000\n\n"
        await broker.publish("entity_update", {"entity_id": "light_1"})
        assert (
            await anext(iterator)
            == 'id: 1\nevent: entity_update\ndata: {"entity_id": "light_1"}\n\n'
        )

        await broker.stop()
        with pytest.raises(StopAsyncIteration):
            await anext(iterator)
