"""Tests for ``backend.services.logging.log_stream``.

Covers the ring buffer (entry shape, sequence ids, filtering, history
pagination), the thread/loop-safe subscriber fan-out (delivery, full-queue
drops), secret redaction, and ``setup_log_streaming`` idempotency.
"""

from __future__ import annotations

import asyncio
import datetime
import logging

import pytest

from backend.services.logging.log_stream import (
    LogStreamHandler,
    get_log_stream_handler,
    setup_log_streaming,
)


def make_record(
    msg: str,
    level: int = logging.INFO,
    name: str = "backend.test",
) -> logging.LogRecord:
    """Build a minimal log record for handler tests."""
    return logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=42,
        msg=msg,
        args=None,
        exc_info=None,
    )


@pytest.fixture
def handler() -> LogStreamHandler:
    """A fresh (non-singleton) handler so tests don't share buffer state."""
    return LogStreamHandler(buffer_size=50)


@pytest.mark.unit
class TestRingBuffer:
    """Ring buffer behavior of LogStreamHandler.emit / get_recent / get_history."""

    def test_emit_produces_contract_shaped_entry(self, handler: LogStreamHandler) -> None:
        handler.handle(make_record("hello world", logging.WARNING, "backend.foo"))

        entries = handler.get_recent()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["level"] == "WARNING"
        assert entry["message"] == "hello world"
        assert entry["logger"] == "backend.foo"
        assert entry["service"] == "coachiq"
        assert "thread" in entry
        # ISO8601, timezone-aware UTC
        parsed = datetime.datetime.fromisoformat(entry["timestamp"])
        assert parsed.tzinfo is not None

    def test_sequence_ids_increase(self, handler: LogStreamHandler) -> None:
        for i in range(5):
            handler.handle(make_record(f"msg {i}"))

        rows, has_more = handler.get_history(limit=10)
        seqs = [seq for seq, _ in rows]
        assert seqs == sorted(seqs, reverse=True)  # newest-first
        assert len(set(seqs)) == 5
        assert has_more is False

    def test_buffer_is_bounded(self) -> None:
        small = LogStreamHandler(buffer_size=3)
        for i in range(10):
            small.handle(make_record(f"msg {i}"))

        entries = small.get_recent(limit=100)
        assert len(entries) == 3
        assert [e["message"] for e in entries] == ["msg 7", "msg 8", "msg 9"]

    def test_get_recent_level_filtering(self, handler: LogStreamHandler) -> None:
        handler.handle(make_record("debug msg", logging.DEBUG))
        handler.handle(make_record("info msg", logging.INFO))
        handler.handle(make_record("error msg", logging.ERROR))

        entries = handler.get_recent(min_levelno=logging.INFO)
        assert [e["message"] for e in entries] == ["info msg", "error msg"]

    def test_get_recent_module_prefix_filtering(self, handler: LogStreamHandler) -> None:
        handler.handle(make_record("can msg", name="backend.can.interface"))
        handler.handle(make_record("core msg", name="backend.core.config"))
        handler.handle(make_record("uvicorn msg", name="uvicorn.error"))

        entries = handler.get_recent(module_prefixes=["backend.can", "uvicorn"])
        assert [e["message"] for e in entries] == ["can msg", "uvicorn msg"]

    def test_get_recent_returns_most_recent_oldest_first(self, handler: LogStreamHandler) -> None:
        for i in range(10):
            handler.handle(make_record(f"msg {i}"))

        entries = handler.get_recent(limit=3)
        assert [e["message"] for e in entries] == ["msg 7", "msg 8", "msg 9"]

    def test_get_history_cursor_pagination_strictly_older(self, handler: LogStreamHandler) -> None:
        for i in range(10):
            handler.handle(make_record(f"msg {i}"))

        page1, has_more1 = handler.get_history(limit=4)
        assert has_more1 is True
        assert [e["message"] for _, e in page1] == ["msg 9", "msg 8", "msg 7", "msg 6"]

        oldest_seq = page1[-1][0]
        page2, _ = handler.get_history(limit=4, before_seq=oldest_seq)
        assert [e["message"] for _, e in page2] == ["msg 5", "msg 4", "msg 3", "msg 2"]
        assert all(seq < oldest_seq for seq, _ in page2)

    def test_redaction_applied_to_buffered_entries(self, handler: LogStreamHandler) -> None:
        # handle() runs the handler's filters (SensitiveDataLogFilter) then emit().
        handler.handle(make_record("login with password=hunter22 failed"))

        entries = handler.get_recent()
        assert len(entries) == 1
        assert "hunter22" not in entries[0]["message"]
        assert "password=***" in entries[0]["message"]

    def test_emit_never_raises(self, handler: LogStreamHandler) -> None:
        record = make_record("boom %s %s")
        record.args = ("only-one",)  # getMessage() raises TypeError: not enough args
        handler.emit(record)  # must swallow, not raise
        # And a poisoned buffer state must not break subsequent emits.
        handler.handle(make_record("still works"))
        assert any(e["message"] == "still works" for e in handler.get_recent())


@pytest.mark.unit
class TestFanOut:
    """Subscriber queue fan-out via the event loop."""

    async def test_subscriber_receives_entries_when_loop_set(
        self, handler: LogStreamHandler
    ) -> None:
        handler.set_loop(asyncio.get_running_loop())
        _sub_id, queue = handler.subscribe()

        handler.handle(make_record("live entry"))
        entry = await asyncio.wait_for(queue.get(), timeout=2.0)

        assert entry["message"] == "live entry"

    async def test_unsubscribed_queue_gets_nothing(self, handler: LogStreamHandler) -> None:
        handler.set_loop(asyncio.get_running_loop())
        sub_id, queue = handler.subscribe()
        handler.unsubscribe(sub_id)

        handler.handle(make_record("after unsubscribe"))
        await asyncio.sleep(0.05)  # let call_soon_threadsafe callbacks run

        assert queue.empty()

    async def test_full_queue_drops_without_blocking(self, handler: LogStreamHandler) -> None:
        handler.set_loop(asyncio.get_running_loop())
        sub_id, queue = handler.subscribe()

        # Fill the queue to capacity so the next dispatch must drop.
        while not queue.full():
            queue.put_nowait({"message": "filler"})

        handler.handle(make_record("dropped entry"))
        await asyncio.sleep(0.05)

        assert handler.get_drop_count(sub_id) == 1
        # The entry still made it into the ring buffer.
        assert any(e["message"] == "dropped entry" for e in handler.get_recent())

    def test_buffering_works_before_loop_is_set(self, handler: LogStreamHandler) -> None:
        # No set_loop() call: startup logs must still land in the ring buffer.
        handler.handle(make_record("startup log"))
        assert [e["message"] for e in handler.get_recent()] == ["startup log"]


@pytest.mark.unit
class TestSetupLogStreaming:
    """setup_log_streaming wiring and idempotency."""

    async def test_idempotent_and_attaches_singleton(self) -> None:
        root_logger = logging.getLogger()
        handler = get_log_stream_handler()
        originally_attached = handler in root_logger.handlers
        try:
            setup_log_streaming()
            setup_log_streaming()

            attached = [h for h in root_logger.handlers if h is handler]
            assert len(attached) == 1
            assert handler.level == logging.DEBUG
        finally:
            if not originally_attached:
                root_logger.removeHandler(handler)

    async def test_singleton_accessor_returns_same_instance(self) -> None:
        assert get_log_stream_handler() is get_log_stream_handler()
