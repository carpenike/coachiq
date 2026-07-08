"""
API router for log endpoints (admin-only).

- ``GET /api/logs/history``: paginated historical logs, from journald when
  available, otherwise from the in-process ring buffer.
- ``GET /api/logs/stream``: live log streaming over SSE (replaces the retired
  ``/ws/logs`` WebSocket endpoint).
"""

import asyncio
import datetime
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.dependencies import AuthenticatedAdmin
from backend.services.logging import log_history
from backend.services.logging.log_stream import get_log_stream_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])

# Mirror the /api/events SSE stream parameters (see backend/api/routers/events.py).
HEARTBEAT_INTERVAL_S = 15.0
RETRY_HINT_MS = 3000
BATCH_INTERVAL_S = 0.5
MAX_BATCH_SIZE = 100
INITIAL_BATCH_LIMIT = 100


class LogEntry(BaseModel):
    timestamp: str = Field(..., description="UTC ISO8601 timestamp of the log entry")
    level: int | None = Field(None, description="Syslog priority (numeric)")
    message: str = Field(..., description="Log message")
    module: str | None = Field(None, description="Logger/module name")
    cursor: str = Field(..., description="Opaque cursor for pagination")


class LogHistoryResponse(BaseModel):
    entries: list[LogEntry]
    next_cursor: str | None = Field(None, description="Cursor for next page of results")
    has_more: bool = Field(..., description="True if more results are available")
    source: str | None = Field(
        None, description='Where the entries came from: "journald" or "memory"'
    )


def _min_levelno(level: str | None, default: int = logging.DEBUG) -> int:
    """Map a python level name (case-insensitive) to its numeric value."""
    if not level:
        return default
    levelno = getattr(logging, level.upper(), None)
    return levelno if isinstance(levelno, int) else default


def _as_utc(dt: datetime.datetime | None) -> datetime.datetime | None:
    """Normalize a query datetime to aware-UTC (naive values are assumed UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(datetime.UTC)


def _within_window(
    entry: dict,
    since_utc: datetime.datetime | None,
    until_utc: datetime.datetime | None,
) -> bool:
    """Best-effort check that a ring-buffer entry falls in the [since, until] window."""
    if since_utc is None and until_utc is None:
        return True
    try:
        ts = datetime.datetime.fromisoformat(entry["timestamp"])
    except (KeyError, ValueError):
        return True  # unparseable timestamps pass through rather than vanish
    if since_utc and ts < since_utc:
        return False
    return not (until_utc and ts > until_utc)


def _memory_history(
    level: str | None,
    module: str | None,
    cursor: str | None,
    limit: int,
    window: tuple[datetime.datetime | None, datetime.datetime | None],
) -> LogHistoryResponse:
    """Serve /history from the in-process ring buffer (no-journald fallback)."""
    handler = get_log_stream_handler()
    before_seq = int(cursor) if cursor and cursor.isdigit() else None
    rows, has_more = handler.get_history(
        limit=limit,
        min_levelno=_min_levelno(level),
        module_prefixes=[module] if module else None,
        before_seq=before_seq,
    )

    since_utc, until_utc = _as_utc(window[0]), _as_utc(window[1])
    entries = []
    for seq, entry in rows:
        if not _within_window(entry, since_utc, until_utc):
            continue
        entries.append(
            LogEntry(
                timestamp=entry.get("timestamp", ""),
                level=log_history.PRIORITY_FROM_LEVEL_NAME.get(str(entry.get("level", "")).upper()),
                message=entry.get("message", ""),
                module=entry.get("logger"),
                cursor=str(seq),
            )
        )

    next_cursor = str(rows[-1][0]) if rows else None
    return LogHistoryResponse(
        entries=entries, next_cursor=next_cursor, has_more=has_more, source="memory"
    )


@router.get(
    "/history",
    response_model=LogHistoryResponse,
    summary="Get historical logs",
    description=(
        "Query historical logs with filtering by time, level, module, and cursor "
        "pagination. Served from journald when available, otherwise from the "
        "in-process ring buffer (see the `source` response field). Admin only."
    ),
    response_model_exclude_none=True,
)
def get_log_history(
    _admin: AuthenticatedAdmin,
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    level: str | None = None,
    module: str | None = None,
    cursor: str | None = None,
    limit: int = Query(100, ge=1, le=500, description="Max number of log entries to return"),
) -> LogHistoryResponse:
    """
    Get historical logs with optional filters and pagination.
    """
    filters = []
    if since:
        filters.append(f"since={since.isoformat()}")
    if until:
        filters.append(f"until={until.isoformat()}")
    if level:
        filters.append(f"level={level}")
    if module:
        filters.append(f"module={module}")
    if cursor:
        filters.append(f"cursor={cursor[:10]}...")
    filter_str = f" with filters: {', '.join(filters)}" if filters else ""

    logger.debug("GET /logs/history - Retrieving log history (limit=%d)%s", limit, filter_str)

    # Memory cursors are bare sequence numbers; journald cursors are opaque
    # "s=...;i=..." strings. A digit cursor means pagination started from the
    # ring buffer, so stay on that source for subsequent pages.
    if not log_history.is_journald_available() or (cursor and cursor.isdigit()):
        return _memory_history(level, module, cursor, limit, (since, until))

    try:
        result = log_history.query_journald_logs(
            since=since,
            until=until,
            level=level,
            module=module,
            cursor=cursor,
            limit=limit,
        )
        if not result["entries"] and cursor is None:
            # Readable-but-empty journal (common on dev machines): fall back to
            # the in-process ring buffer so the History tab still shows data.
            return _memory_history(level, module, cursor, limit, (since, until))
        return LogHistoryResponse(**result, source="journald")
    except Exception as e:
        logger.exception("Error retrieving log history%s", filter_str)
        raise HTTPException(status_code=500, detail="Internal server error") from e


def _format_batch(entries: list[dict]) -> str:
    """Format a batch of log entries as one SSE `logs` event."""
    return f"event: logs\ndata: {json.dumps(entries)}\n\n"


async def _live_frames(
    handler,
    queue: asyncio.Queue,
    min_levelno: int,
    module_prefixes: list[str],
) -> AsyncGenerator[str, None]:
    """Yield SSE frames for live log entries from a subscriber queue.

    Entries are batched: a batch is flushed when ``BATCH_INTERVAL_S`` elapses
    with pending entries or ``MAX_BATCH_SIZE`` entries accumulate. When idle, a
    keepalive comment is emitted every ``HEARTBEAT_INTERVAL_S`` seconds.
    """
    pending: list[dict] = []
    batch_deadline = 0.0
    loop = asyncio.get_running_loop()
    while True:
        timeout = max(0.0, batch_deadline - loop.time()) if pending else HEARTBEAT_INTERVAL_S
        try:
            entry = await asyncio.wait_for(queue.get(), timeout=timeout)
        except TimeoutError:
            if pending:
                yield _format_batch(pending)
                pending = []
            else:
                yield ": keepalive\n\n"
            continue
        if handler.entry_matches(entry, min_levelno, module_prefixes):
            if not pending:
                batch_deadline = loop.time() + BATCH_INTERVAL_S
            pending.append(entry)
            if len(pending) >= MAX_BATCH_SIZE:
                yield _format_batch(pending)
                pending = []


@router.get(
    "/stream",
    summary="Stream live logs (SSE)",
    description=(
        "Server-Sent Events stream of live log entries, batched as "
        "`event: logs` frames with a JSON array payload. On connect the most "
        "recent matching entries are replayed from the ring buffer. Admin only."
    ),
)
async def stream_logs(
    request: Request,
    _admin: AuthenticatedAdmin,
    level: str = Query("debug", description="Minimum python log level name (case-insensitive)"),
    modules: str | None = Query(
        None, description="Comma-separated logger-name prefixes; empty = all"
    ),
) -> StreamingResponse:
    """Stream live log entries as SSE, mirroring the /api/events endpoint style."""
    min_levelno = _min_levelno(level)
    module_prefixes = (
        [prefix.strip() for prefix in modules.split(",") if prefix.strip()] if modules else []
    )
    handler = get_log_stream_handler()

    async def log_stream() -> AsyncGenerator[str, None]:
        subscriber_id, queue = handler.subscribe()
        client = request.client
        client_label = f"{client.host}:{client.port}" if client else "unknown"
        logger.info("Log SSE client connected: %s", client_label)
        try:
            yield f"retry: {RETRY_HINT_MS}\n\n"
            yield _format_batch(
                handler.get_recent(INITIAL_BATCH_LIMIT, min_levelno, module_prefixes)
            )
            async for frame in _live_frames(handler, queue, min_levelno, module_prefixes):
                yield frame
        finally:
            dropped = handler.get_drop_count(subscriber_id)
            handler.unsubscribe(subscriber_id)
            if dropped:
                logger.warning(
                    "Log SSE client %s: dropped %d entries (slow consumer)",
                    client_label,
                    dropped,
                )
            logger.info("Log SSE client disconnected: %s", client_label)

    return StreamingResponse(
        log_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tell buffering reverse proxies (nginx/Caddy) to pass chunks through.
            "X-Accel-Buffering": "no",
        },
    )
