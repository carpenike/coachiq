"""Historical log queries via the ``journalctl`` CLI.

Earlier versions imported the ``systemd.journal`` python bindings, which were
never an installed dependency, so ``GET /api/logs/history`` always failed with
501. This module shells out to ``journalctl -o json`` instead: it is present on
every systemd host (including the NixOS target), needs no python bindings, and
its ``__CURSOR`` field gives us stable pagination.

Pagination model: pages are newest-first (``--reverse``). A page's
``next_cursor`` is the ``__CURSOR`` of its oldest returned entry; passing it
back seeks the journal to that entry (``--cursor`` is inclusive, so the first
returned row is the cursor entry itself and is skipped), yielding a
strictly-older next page.
"""

from __future__ import annotations

import datetime
import functools
import json
import shutil
import subprocess
from typing import Any

JOURNALCTL_TIMEOUT_S = 5

# Python level name -> syslog priority (RFC 5424).
PRIORITY_FROM_LEVEL_NAME = {
    "CRITICAL": 2,
    "ERROR": 3,
    "WARNING": 4,
    "INFO": 6,
    "DEBUG": 7,
}


@functools.lru_cache(maxsize=1)
def _probe_journald() -> bool:
    """Check that journalctl exists and can actually read a journal.

    Probed once per process; call ``_probe_journald.cache_clear()`` to re-probe
    (used by tests).
    """
    if shutil.which("journalctl") is None:
        return False
    try:
        # Fixed argv, no user input; journalctl resolved from PATH by design
        # (its location differs across distros, e.g. NixOS vs FHS).
        proc = subprocess.run(  # noqa: S603
            ["journalctl", "-o", "json", "-n", "1", "--quiet"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=JOURNALCTL_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    # rc 0 = readable journal (possibly empty); rc 1 without stderr shows up on
    # some systems for an empty/absent journal and is still usable.
    return proc.returncode == 0 or (proc.returncode == 1 and not proc.stderr.strip())


def is_journald_available() -> bool:
    """Return True if journalctl is present and usable (probed once, cached)."""
    return _probe_journald()


def _get_journald_unit() -> str | None:
    """Return the configured systemd unit to scope journal queries to."""
    from backend.core.config import get_settings

    return get_settings().logging.journald_unit


def _build_journalctl_command(
    since: datetime.datetime | None,
    until: datetime.datetime | None,
    level: str | None,
    cursor: str | None,
    fetch_count: int,
) -> list[str]:
    """Assemble the journalctl argv for one history page."""
    cmd = [
        "journalctl",
        "-o",
        "json",
        "--no-pager",
        "--quiet",
        "--reverse",
        "-n",
        str(fetch_count),
    ]
    unit = _get_journald_unit()
    if unit:
        cmd.extend(["-u", unit])
    if level:
        priority = PRIORITY_FROM_LEVEL_NAME.get(level.upper())
        if priority is not None:
            cmd.extend(["-p", str(priority)])
    if since:
        cmd.extend(["--since", since.isoformat()])
    if until:
        cmd.extend(["--until", until.isoformat()])
    if cursor:
        # --cursor is inclusive: with --reverse the first returned row is the
        # cursor entry itself, which the caller skips (see query_journald_logs).
        cmd.append(f"--cursor={cursor}")
    return cmd


def _decode_raw_message(obj: dict[str, Any]) -> str:
    """Return the journald ``MESSAGE`` field as a string."""
    raw_message = obj.get("MESSAGE", "")
    if isinstance(raw_message, list):
        # journald encodes non-UTF8 messages as byte arrays.
        try:
            return bytes(raw_message).decode("utf-8", errors="replace")
        except (TypeError, ValueError):
            return str(raw_message)
    if not isinstance(raw_message, str):
        return str(raw_message)
    return raw_message


def _extract_structured_fields(raw_message: str) -> tuple[str, str | None, int | None] | None:
    """Extract (message, logger, syslog level) from one of our JSON log lines.

    Returns None when the message is not a structured line from our
    ``JsonFormatter``.
    """
    if not raw_message.startswith("{"):
        return None
    try:
        structured = json.loads(raw_message)
    except json.JSONDecodeError:
        return None
    if not isinstance(structured, dict) or "message" not in structured:
        return None
    return (
        str(structured.get("message", raw_message)),
        structured.get("logger"),
        PRIORITY_FROM_LEVEL_NAME.get(str(structured.get("level", "")).upper()),
    )


def _parse_journal_line(line: str) -> dict[str, Any] | None:
    """Parse one ``journalctl -o json`` line into a LogEntry-shaped dict.

    Our own log lines arrive as JSON inside ``MESSAGE`` (see ``JsonFormatter``);
    for those the inner ``message``/``logger``/``level`` are extracted. Anything
    else (other units, plain-text lines) falls back to the raw ``MESSAGE`` and
    journald's ``PRIORITY``.
    """
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None

    raw_message = _decode_raw_message(obj)
    message = raw_message
    module = obj.get("SYSLOG_IDENTIFIER")
    level: int | None = None

    structured = _extract_structured_fields(raw_message)
    if structured is not None:
        message, structured_logger, level = structured
        module = structured_logger or module

    if level is None:
        try:
            priority = obj.get("PRIORITY")
            level = int(priority) if priority is not None else None
        except (TypeError, ValueError):
            level = None

    timestamp_us = obj.get("__REALTIME_TIMESTAMP")
    try:
        timestamp = datetime.datetime.fromtimestamp(
            int(timestamp_us) / 1_000_000, tz=datetime.UTC
        ).isoformat()
    except (TypeError, ValueError):
        timestamp = datetime.datetime.now(tz=datetime.UTC).isoformat()

    return {
        "timestamp": timestamp,
        "level": level,
        "message": message,
        "module": module,
        "cursor": obj.get("__CURSOR", ""),
    }


def query_journald_logs(
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    level: str | None = None,
    module: str | None = None,
    cursor: str | None = None,
    limit: int = 100,
) -> dict[str, object]:
    """Query one newest-first page of logs from journald.

    Args:
        since: Only entries at or after this time.
        until: Only entries at or before this time.
        level: Minimum python level name (e.g. ``"WARNING"``); mapped to a
            syslog priority for ``journalctl -p``.
        module: Logger-name prefix filter, applied post-parse (a filtered page
            may therefore contain fewer than ``limit`` entries).
        cursor: ``next_cursor`` from the previous page; the next page is
            strictly older.
        limit: Maximum entries per page.

    Returns:
        Dict with ``entries`` (newest first), ``next_cursor`` and ``has_more``.

    Raises:
        RuntimeError: If journalctl fails, times out, or is unavailable.
    """
    if not is_journald_available():
        msg = "journalctl is not available on this system."
        raise RuntimeError(msg)

    # +1 row to detect has_more; +1 more when paginating because --cursor is
    # inclusive and the cursor entry itself gets skipped below.
    fetch_count = limit + (2 if cursor else 1)
    cmd = _build_journalctl_command(since, until, level, cursor, fetch_count)

    try:
        # argv is assembled from fixed flags and validated/typed API params
        # (datetimes, mapped priorities, opaque cursor as a single argv item —
        # never shell-interpreted).
        proc = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=JOURNALCTL_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        msg = f"journalctl timed out after {JOURNALCTL_TIMEOUT_S}s"
        raise RuntimeError(msg) from e
    except OSError as e:
        msg = f"Failed to execute journalctl: {e}"
        raise RuntimeError(msg) from e

    if proc.returncode not in (0, 1):
        stderr = proc.stderr.strip()
        msg = f"journalctl exited with code {proc.returncode}: {stderr or 'no error output'}"
        raise RuntimeError(msg)

    rows = [
        parsed
        for line in proc.stdout.splitlines()
        if line.strip() and (parsed := _parse_journal_line(line)) is not None
    ]

    # --cursor seeks to the cursor entry inclusively; drop it so pagination
    # returns strictly-older entries. Guarded by an equality check in case a
    # journalctl version/rotation boundary starts elsewhere.
    if cursor and rows and rows[0].get("cursor") == cursor:
        rows = rows[1:]

    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = page[-1]["cursor"] if page else None

    if module:
        page = [row for row in page if row.get("module") and str(row["module"]).startswith(module)]

    return {"entries": page, "next_cursor": next_cursor, "has_more": has_more}
