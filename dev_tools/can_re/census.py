"""Summarize a capture: what talks, how fast, standard vs proprietary.

Usage:
    python -m dev_tools.can_re.census captures/idle.jsonl
"""

from __future__ import annotations

import argparse
import collections
from pathlib import Path

from dev_tools.can_re.canframe import Frame, RvcNames, classify_pgn, decompose_arbitration_id
from dev_tools.can_re.loader import load_capture, span_seconds

# Dimmer PGNs whose payload byte 0 is an addressable instance worth breaking out.
INSTANCE_PGNS = (0x1FEDA, 0x1FEDB)


def census(frames: list[Frame], names: RvcNames | None = None) -> dict:
    """Compute a structured census over ``frames``."""
    names = names or RvcNames({})
    per_key: collections.Counter[tuple[int, int]] = collections.Counter()
    instances: dict[int, collections.Counter[int]] = {
        pgn: collections.Counter() for pgn in INSTANCE_PGNS
    }
    for f in frames:
        pgn, sa, _pf = decompose_arbitration_id(f.can_id)
        per_key[(pgn, sa)] += 1
        if pgn in instances and f.instance is not None:
            instances[pgn][f.instance] += 1

    span = span_seconds(frames) or 1.0
    proprietary = sum(1 for (pgn, _sa) in per_key if classify_pgn(pgn) == "proprietary")
    rows = [
        {
            "pgn": pgn,
            "sa": sa,
            "count": count,
            "rate": round(count / span, 1),
            "name": names.name(pgn),
            "kind": classify_pgn(pgn),
        }
        for (pgn, sa), count in per_key.most_common()
    ]
    return {
        "frames": len(frames),
        "span_seconds": round(span, 1),
        "distinct_keys": len(per_key),
        "proprietary_keys": proprietary,
        "rows": rows,
        "instances": {pgn: dict(sorted(c.items())) for pgn, c in instances.items() if c},
    }


def format_census(result: dict, top: int = 25) -> str:
    lines = [
        f"{result['frames']} frames over {result['span_seconds']}s "
        f"(~{round(result['frames'] / (result['span_seconds'] or 1))}/s), "
        f"{result['distinct_keys']} distinct (PGN,SA); "
        f"{result['proprietary_keys']} proprietary",
        "",
        f"{'PGN':>6}  {'SA':>2}  {'count':>6}  {'rate/s':>7}  kind         name",
    ]
    lines.extend(
        f"{r['pgn']:>6X}  {r['sa']:>02X}  {r['count']:>6}  {r['rate']:>7}  "
        f"{r['kind']:<11}  {r['name'] or ''}"
        for r in result["rows"][:top]
    )
    for pgn, dist in result["instances"].items():
        pretty = ", ".join(f"{k:02X}:{v}" for k, v in dist.items())
        lines.append(f"\n{pgn:X} payload-byte0 (instances): {pretty}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Census a CAN capture.")
    ap.add_argument("capture", type=Path)
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args(argv)
    frames, _meta = load_capture(args.capture)
    print(format_census(census(frames, RvcNames.load()), top=args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
