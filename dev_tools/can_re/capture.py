"""Capture a labeled CAN session to JSONL.

Runs on the coach (Raspberry Pi) against a live SocketCAN interface via
``candump``. No CoachIQ app, auth, or python-can dependency required.

Usage:
    python -m dev_tools.can_re.capture --iface can1 --seconds 6 \
        --label bedroom-ceiling-on --out captures/bedroom-ceiling-on.jsonl

Then diff two captures (e.g. an idle baseline vs. an action) with
``python -m dev_tools.can_re.diff idle.jsonl bedroom-ceiling-on.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from dev_tools.can_re.canframe import parse_candump_line


def capture(iface: str, seconds: float, label: str, out_path: Path) -> int:
    """Capture for ``seconds`` from ``iface`` into ``out_path`` (JSONL).

    Returns the number of frames written. The first line is a ``_meta`` record;
    every subsequent line is a frame in RecordedMessage field shape.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # `-ta` gives absolute timestamps we can diff/rate on. `timeout` bounds
    # the run so this always exits without a manual Ctrl-C.
    cmd = ["timeout", str(seconds), "candump", "-ta", iface]
    started = time.time()
    # Fixed argv, no shell — inputs are a numeric duration and an interface name.
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603

    frames = 0
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "_meta": {
                        "label": label,
                        "interface": iface,
                        "seconds": seconds,
                        "started_at": started,
                    }
                }
            )
            + "\n"
        )
        for line in proc.stdout.splitlines():
            frame = parse_candump_line(line)
            if frame is None:
                continue
            fh.write(json.dumps(frame.to_record()) + "\n")
            frames += 1
    return frames


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Capture a labeled CAN session to JSONL.")
    ap.add_argument("--iface", default="can1", help="SocketCAN interface (default: can1)")
    ap.add_argument("--seconds", type=float, default=6.0, help="Capture duration")
    ap.add_argument("--label", required=True, help="Human label, e.g. 'bedroom-ceiling-on'")
    ap.add_argument("--out", type=Path, required=True, help="Output .jsonl path")
    args = ap.parse_args(argv)

    n = capture(args.iface, args.seconds, args.label, args.out)
    print(
        f"captured {n} frames from {args.iface} over {args.seconds}s -> {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
