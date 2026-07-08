"""In-process log streaming: ring buffer + SSE fan-out.

``LogStreamHandler`` is a ``logging.Handler`` attached to the root logger that

1. appends every record (as a JSON-serializable dict) to a bounded in-memory
   ring buffer with a monotonically increasing sequence id — this backs the
   ``GET /api/logs/history`` memory fallback and the initial batch of
   ``GET /api/logs/stream``, and
2. fans records out to per-subscriber ``asyncio.Queue``s that the SSE stream
   endpoint drains — this backs live streaming.

``emit()`` may run on any thread (CAN reader threads, executors, ...), so the
fan-out hops onto the event loop via ``loop.call_soon_threadsafe``. Ring-buffer
appends work even before the loop reference is set so startup logs are
captured. A full subscriber queue drops the entry (and counts the drop) rather
than ever blocking ``emit``.

This replaces the retired WebSocket log path (``/ws/logs`` +
``WebSocketLogHandler``); live logs now ride SSE at ``GET /api/logs/stream``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from backend.core.sensitive_data_filter import SensitiveDataLogFilter

if TYPE_CHECKING:
    from collections.abc import Iterable

RING_BUFFER_SIZE = 5000
SUBSCRIBER_QUEUE_SIZE = 1000


class LogStreamHandler(logging.Handler):
    """Logging handler that buffers records and fans them out to SSE subscribers."""

    def __init__(self, buffer_size: int = RING_BUFFER_SIZE) -> None:
        """Initialize the handler at DEBUG with secret redaction attached.

        Args:
            buffer_size: Maximum number of entries kept in the ring buffer.
        """
        super().__init__(level=logging.DEBUG)
        # Redact secrets before they are buffered or leave the process.
        self.addFilter(SensitiveDataLogFilter())

        # Ring buffer of (sequence_id, entry) pairs, oldest -> newest.
        self._buffer: deque[tuple[int, dict[str, Any]]] = deque(maxlen=buffer_size)
        self._seq = 0

        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: dict[int, asyncio.Queue[dict[str, Any]]] = {}
        self._drop_counts: dict[int, int] = {}
        self._next_subscriber_id = 0

        # Guards buffer/subscriber/loop state. emit() runs under the inherited
        # handler lock, but subscribe/unsubscribe/get_recent run on other
        # threads (the event loop), so shared state needs its own lock.
        self._state_lock = threading.Lock()

    # ── logging.Handler interface ───────────────────────────────────────────

    def emit(self, record: logging.LogRecord) -> None:
        """Buffer the record and fan it out to subscribers.

        Never raises and never logs: any failure here would recurse straight
        back into this handler.
        """
        with contextlib.suppress(Exception):
            entry = {
                "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name,
                "service": "coachiq",
                "thread": record.thread,
            }
            with self._state_lock:
                self._seq += 1
                self._buffer.append((self._seq, entry))
                loop = self._loop
            if loop is not None and not loop.is_closed():
                loop.call_soon_threadsafe(self._dispatch, entry)

    def _dispatch(self, entry: dict[str, Any]) -> None:
        """Deliver one entry to every subscriber queue (runs on the event loop)."""
        with self._state_lock:
            subscribers = list(self._subscribers.items())
        for subscriber_id, queue in subscribers:
            try:
                queue.put_nowait(entry)
            except asyncio.QueueFull:
                # Slow consumer: drop rather than block or buffer unboundedly.
                with self._state_lock:
                    self._drop_counts[subscriber_id] = self._drop_counts.get(subscriber_id, 0) + 1

    # ── subscription API ────────────────────────────────────────────────────

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop used for thread-safe fan-out to subscriber queues."""
        with self._state_lock:
            self._loop = loop

    def subscribe(self) -> tuple[int, asyncio.Queue[dict[str, Any]]]:
        """Register a new subscriber.

        Returns:
            A (subscriber_id, queue) pair. Pass the id to :meth:`unsubscribe`
            when the consumer disconnects.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        with self._state_lock:
            self._next_subscriber_id += 1
            subscriber_id = self._next_subscriber_id
            self._subscribers[subscriber_id] = queue
            self._drop_counts[subscriber_id] = 0
        return subscriber_id, queue

    def unsubscribe(self, subscriber_id: int) -> None:
        """Remove a subscriber; unknown ids are ignored."""
        with self._state_lock:
            self._subscribers.pop(subscriber_id, None)
            self._drop_counts.pop(subscriber_id, None)

    def get_drop_count(self, subscriber_id: int) -> int:
        """Return how many entries were dropped for a subscriber's full queue."""
        with self._state_lock:
            return self._drop_counts.get(subscriber_id, 0)

    @property
    def subscriber_count(self) -> int:
        """Number of currently registered subscribers."""
        with self._state_lock:
            return len(self._subscribers)

    # ── ring buffer queries ─────────────────────────────────────────────────

    @staticmethod
    def entry_matches(
        entry: dict[str, Any],
        min_levelno: int = logging.DEBUG,
        module_prefixes: Iterable[str] | None = None,
    ) -> bool:
        """Return True if an entry passes the level / logger-prefix filters."""
        levelno = getattr(logging, str(entry.get("level", "")), None)
        if not isinstance(levelno, int):
            levelno = logging.DEBUG
        if levelno < min_levelno:
            return False
        prefixes = list(module_prefixes) if module_prefixes else []
        if prefixes:
            logger_name = str(entry.get("logger", ""))
            return any(logger_name.startswith(prefix) for prefix in prefixes)
        return True

    def get_recent(
        self,
        limit: int = 100,
        min_levelno: int = logging.DEBUG,
        module_prefixes: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` most recent matching entries, oldest first.

        Args:
            limit: Maximum number of entries to return.
            min_levelno: Minimum python log level number to include.
            module_prefixes: Optional logger-name prefixes; empty/None = all.
        """
        with self._state_lock:
            snapshot = list(self._buffer)
        matched: list[dict[str, Any]] = []
        for _seq, entry in reversed(snapshot):
            if self.entry_matches(entry, min_levelno, module_prefixes):
                matched.append(entry)
                if len(matched) >= limit:
                    break
        matched.reverse()
        return matched

    def get_history(
        self,
        limit: int = 100,
        min_levelno: int = logging.DEBUG,
        module_prefixes: Iterable[str] | None = None,
        before_seq: int | None = None,
    ) -> tuple[list[tuple[int, dict[str, Any]]], bool]:
        """Return a newest-first page of (sequence_id, entry) pairs for /history.

        Args:
            limit: Maximum entries per page.
            min_levelno: Minimum python log level number to include.
            module_prefixes: Optional logger-name prefixes; empty/None = all.
            before_seq: Cursor — only entries with a strictly smaller sequence
                id are returned, so subsequent pages are strictly older.

        Returns:
            (page, has_more) where page is newest-first.
        """
        with self._state_lock:
            snapshot = list(self._buffer)
        page: list[tuple[int, dict[str, Any]]] = []
        has_more = False
        for seq, entry in reversed(snapshot):
            if before_seq is not None and seq >= before_seq:
                continue
            if not self.entry_matches(entry, min_levelno, module_prefixes):
                continue
            if len(page) >= limit:
                has_more = True
                break
            page.append((seq, entry))
        return page, has_more


# Process-wide singleton, created eagerly (construction is cheap and has no
# side effects; it only starts receiving records once attached to a logger).
_log_stream_handler = LogStreamHandler()


def get_log_stream_handler() -> LogStreamHandler:
    """Return the process-wide :class:`LogStreamHandler` singleton."""
    return _log_stream_handler


def setup_log_streaming() -> None:
    """Wire the log stream handler into the running application.

    Sets the running event loop on the singleton handler (enabling live
    fan-out) and attaches it to the root logger. Idempotent: calling this
    multiple times attaches the handler at most once. Must be called from
    within a running event loop (the FastAPI lifespan).
    """
    handler = get_log_stream_handler()
    handler.set_loop(asyncio.get_running_loop())
    root_logger = logging.getLogger()
    if handler not in root_logger.handlers:
        root_logger.addHandler(handler)
