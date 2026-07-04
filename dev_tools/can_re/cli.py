"""Unified ``coachiq-can-re`` command: capture / census / diff subcommands.

This is the console-script entry point shipped in the Nix package. It reuses
the same library functions as the ``python -m dev_tools.can_re.<tool>`` module
CLIs, so both invocation styles behave identically.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dev_tools.can_re.canframe import RvcNames
from dev_tools.can_re.capture import capture as run_capture
from dev_tools.can_re.census import census, format_census
from dev_tools.can_re.diff import apply_noise_filter, diff, format_diff
from dev_tools.can_re.loader import load_capture


def _cmd_capture(args: argparse.Namespace) -> int:
    n = run_capture(args.iface, args.seconds, args.label, args.out)
    print(
        f"captured {n} frames from {args.iface} over {args.seconds}s -> {args.out}",
        file=sys.stderr,
    )
    return 0


def _cmd_census(args: argparse.Namespace) -> int:
    frames, _meta = load_capture(args.capture)
    print(format_census(census(frames, RvcNames.load()), top=args.top))
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    names = RvcNames.load()
    idle_frames, _ = load_capture(args.idle)
    action_frames, _ = load_capture(args.action)
    result = diff(idle_frames, action_frames, names)
    if args.noise:
        noise_frames, _ = load_capture(args.noise)
        result = apply_noise_filter(result, diff(idle_frames, noise_frames, names))
    print(format_diff(result, top=args.top))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="coachiq-can-re",
        description="Reverse-engineering tools for the coach CAN bus "
        "(capture / census / diff). See the Firefly dialect notes in "
        "docs/can-re-findings.md.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="Record a labeled session to JSONL.")
    cap.add_argument("--iface", default="can1")
    cap.add_argument("--seconds", type=float, default=10.0)
    cap.add_argument("--label", required=True)
    cap.add_argument("--out", type=Path, required=True)
    cap.set_defaults(func=_cmd_capture)

    cen = sub.add_parser("census", help="Inventory a capture.")
    cen.add_argument("capture", type=Path)
    cen.add_argument("--top", type=int, default=25)
    cen.set_defaults(func=_cmd_census)

    dif = sub.add_parser("diff", help="Diff idle vs. action to find the signal.")
    dif.add_argument("idle", type=Path)
    dif.add_argument("action", type=Path)
    dif.add_argument(
        "--noise", type=Path, default=None, help="Second idle capture; subtracts churn."
    )
    dif.add_argument("--top", type=int, default=20)
    dif.set_defaults(func=_cmd_diff)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
