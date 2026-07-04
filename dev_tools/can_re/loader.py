"""Load capture JSONL (or raw candump logs) into Frame lists."""

from __future__ import annotations

import json
from pathlib import Path

from dev_tools.can_re.canframe import Frame, parse_candump_line

_MIN_TS_FOR_SPAN = 2


def load_capture(path: str | Path) -> tuple[list[Frame], dict]:
    """Load a capture file, returning ``(frames, meta)``.

    Accepts our JSONL captures (with a ``_meta`` header line) and also raw
    ``candump`` text logs, so a plain ``candump -ta … > file`` works too.
    """
    frames: list[Frame] = []
    meta: dict = {}
    text = Path(path).read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if "_meta" in obj:
                meta = obj["_meta"]
                continue
            if "can_id" in obj:
                frames.append(Frame.from_record(obj))
                continue
        else:
            frame = parse_candump_line(line)
            if frame is not None:
                frames.append(frame)
    return frames, meta


def span_seconds(frames: list[Frame]) -> float:
    """Wall-clock span covered by the frames (0.0 if <2 timestamped frames)."""
    ts = [f.timestamp for f in frames if f.timestamp]
    if len(ts) < _MIN_TS_FOR_SPAN:
        return 0.0
    return max(ts) - min(ts)
