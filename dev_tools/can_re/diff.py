"""Diff two captures to isolate the frames an action produced.

Compares a baseline (idle) capture against an action capture (e.g. taken while
pressing a Vegatouch Mira button) and surfaces:

  * NEW keys       — (PGN, SA) frame types that appeared only during the action
  * GONE keys      — frame types that stopped during the action
  * CHANGED bytes  — for shared (PGN, SA), payload byte positions that took a
                     value during the action that was never seen at idle

The changed-byte report is the payload delta that reveals which frame carries
the command/state a button toggles. Candidates are ranked to float the most
likely control signal (proprietary channel + a small, specific set of new
values) to the top.

Usage:
    python -m dev_tools.can_re.diff captures/idle.jsonl captures/action.jsonl
"""

from __future__ import annotations

import argparse
import collections
from dataclasses import dataclass
from pathlib import Path

from dev_tools.can_re.canframe import Frame, RvcNames, classify_pgn, decompose_arbitration_id
from dev_tools.can_re.loader import load_capture

Key = tuple[int, int]  # (pgn, sa)


@dataclass
class ByteChange:
    index: int
    new_values: list[int]  # values seen in action, never at idle


@dataclass
class ChangedKey:
    pgn: int
    sa: int
    name: str | None
    kind: str
    byte_changes: list[ByteChange]

    @property
    def score(self) -> float:
        """Higher = more likely the signal a button toggled.

        Proprietary frames (Firefly's private channel) rank up; a change
        concentrated in few byte positions with few new values ranks up
        (a specific edit, not noise); status/command dimmer PGNs rank up.
        """
        total_new = sum(len(bc.new_values) for bc in self.byte_changes)
        specificity = 1.0 / (1 + total_new)
        s = specificity + 0.5 / (1 + len(self.byte_changes))
        if self.kind == "proprietary":
            s += 1.0
        if self.pgn in (0x1FEDA, 0x1FEDB):
            s += 0.5
        return s


@dataclass
class DiffResult:
    new_keys: list[tuple[int, int, str | None]]
    gone_keys: list[tuple[int, int, str | None]]
    changed: list[ChangedKey]


def _index(frames: list[Frame]) -> dict[Key, list[bytes]]:
    idx: dict[Key, list[bytes]] = collections.defaultdict(list)
    for f in frames:
        pgn, sa, _pf = decompose_arbitration_id(f.can_id)
        idx[(pgn, sa)].append(f.data)
    return idx


def _byte_value_sets(payloads: list[bytes]) -> list[set[int]]:
    """Per-byte-index set of values observed across payloads."""
    width = max((len(p) for p in payloads), default=0)
    sets: list[set[int]] = [set() for _ in range(width)]
    for p in payloads:
        for i, b in enumerate(p):
            sets[i].add(b)
    return sets


def diff(idle: list[Frame], action: list[Frame], names: RvcNames | None = None) -> DiffResult:
    names = names or RvcNames({})
    idle_idx = _index(idle)
    action_idx = _index(action)
    idle_keys = set(idle_idx)
    action_keys = set(action_idx)

    new_keys = sorted(
        ((pgn, sa, names.name(pgn)) for (pgn, sa) in action_keys - idle_keys),
        key=lambda t: (t[0], t[1]),
    )
    gone_keys = sorted(
        ((pgn, sa, names.name(pgn)) for (pgn, sa) in idle_keys - action_keys),
        key=lambda t: (t[0], t[1]),
    )

    changed: list[ChangedKey] = []
    for key in idle_keys & action_keys:
        pgn, sa = key
        idle_sets = _byte_value_sets(idle_idx[key])
        action_sets = _byte_value_sets(action_idx[key])
        byte_changes: list[ByteChange] = []
        for i, act_vals in enumerate(action_sets):
            idle_vals = idle_sets[i] if i < len(idle_sets) else set()
            new = sorted(act_vals - idle_vals)
            if new:
                byte_changes.append(ByteChange(index=i, new_values=new))
        if byte_changes:
            changed.append(
                ChangedKey(
                    pgn=pgn,
                    sa=sa,
                    name=names.name(pgn),
                    kind=classify_pgn(pgn),
                    byte_changes=byte_changes,
                )
            )
    changed.sort(key=lambda c: c.score, reverse=True)
    return DiffResult(new_keys=new_keys, gone_keys=gone_keys, changed=changed)


def apply_noise_filter(result: DiffResult, noise: DiffResult) -> DiffResult:
    """Subtract a noise-floor diff (idle-vs-idle) from an action diff.

    The bus has legitimate background churn — clocks counting up, slow
    periodic frames sampled in one window but not another, free-running
    counters. Diffing two *idle* captures characterizes that churn; anything
    it flags is not caused by the action, so we drop it here. What survives is
    the signal a button press actually produced.
    """
    noise_new = {(pgn, sa) for pgn, sa, _ in noise.new_keys}
    noise_bytes: set[tuple[int, int, int]] = {
        (c.pgn, c.sa, bc.index) for c in noise.changed for bc in c.byte_changes
    }

    new_keys = [t for t in result.new_keys if (t[0], t[1]) not in noise_new]
    gone_keys = [t for t in result.gone_keys if (t[0], t[1]) not in noise_new]

    changed: list[ChangedKey] = []
    for c in result.changed:
        kept = [bc for bc in c.byte_changes if (c.pgn, c.sa, bc.index) not in noise_bytes]
        if kept:
            changed.append(
                ChangedKey(pgn=c.pgn, sa=c.sa, name=c.name, kind=c.kind, byte_changes=kept)
            )
    changed.sort(key=lambda c: c.score, reverse=True)
    return DiffResult(new_keys=new_keys, gone_keys=gone_keys, changed=changed)


def format_diff(result: DiffResult, top: int = 20) -> str:
    lines: list[str] = []
    lines.append(f"NEW frame types during action ({len(result.new_keys)}):")
    for pgn, sa, name in result.new_keys:
        lines.append(f"  PGN {pgn:05X}  SA {sa:02X}  {name or ''}")
    lines.append(f"\nGONE frame types during action ({len(result.gone_keys)}):")
    for pgn, sa, name in result.gone_keys:
        lines.append(f"  PGN {pgn:05X}  SA {sa:02X}  {name or ''}")
    lines.append(f"\nCHANGED payloads, ranked ({len(result.changed)} keys; top {top}):")
    for c in result.changed[:top]:
        deltas = "; ".join(
            f"byte{bc.index}+={{{','.join(f'{v:02X}' for v in bc.new_values)}}}"
            for bc in c.byte_changes
        )
        lines.append(f"  PGN {c.pgn:05X}  SA {c.sa:02X}  [{c.kind}] {c.name or ''}")
        lines.append(f"      {deltas}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Diff two CAN captures (idle vs. action).")
    ap.add_argument("idle", type=Path, help="Baseline capture (nothing pressed)")
    ap.add_argument("action", type=Path, help="Capture taken during the action")
    ap.add_argument(
        "--noise",
        type=Path,
        default=None,
        help="A second idle capture; its idle-vs-idle churn is subtracted for a cleaner signal.",
    )
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args(argv)
    names = RvcNames.load()
    idle_frames, _ = load_capture(args.idle)
    action_frames, _ = load_capture(args.action)
    result = diff(idle_frames, action_frames, names)
    if args.noise:
        noise_frames, _ = load_capture(args.noise)
        result = apply_noise_filter(result, diff(idle_frames, noise_frames, names))
    print(format_diff(result, top=args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
