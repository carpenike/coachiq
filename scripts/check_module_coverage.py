#!/usr/bin/env python3
"""Per-module coverage ratchet for CoachIQ guardrail paths.

This script intentionally checks only high-value guardrail modules. It replaces
the previous whole-repo pytest ``--cov-fail-under`` floor, which made focused
marker runs fail because most unrelated modules were not exercised.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MODULE_FLOORS = {
    "backend/services/can/can_facade.py": 65.0,
    # safety_service.py was renamed in HOF-051; floor carried over.
    "backend/services/guardrails/command_guardrail_service.py": 42.0,
    "backend/services/auth/service.py": 80.0,
    "backend/services/auth/manager.py": 32.0,
    "backend/middleware/secure_auth.py": 60.0,
    "backend/websocket/auth_handler.py": 85.0,
}


def normalize_filename(filename: str) -> str:
    """Normalize coverage.py filenames to repo-relative backend paths."""
    normalized = filename.replace("\\", "/")
    if normalized.startswith("backend/"):
        return normalized
    return f"backend/{normalized}"


def read_module_coverage(coverage_xml: Path) -> dict[str, float]:
    """Read module line coverage percentages from a coverage.py XML report."""
    root = ET.parse(coverage_xml).getroot()  # noqa: S314  # nosec B314 - trusted local coverage.py output
    coverage: dict[str, float] = {}
    for class_node in root.findall(".//class"):
        filename = class_node.get("filename")
        line_rate = class_node.get("line-rate")
        if filename is None or line_rate is None:
            continue
        coverage[normalize_filename(filename)] = float(line_rate) * 100
    return coverage


def main() -> int:
    """Validate configured module coverage floors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "coverage_xml",
        nargs="?",
        default="coverage.xml",
        type=Path,
        help="Path to coverage.py XML report",
    )
    args = parser.parse_args()

    if not args.coverage_xml.exists():
        print(f"coverage report not found: {args.coverage_xml}", file=sys.stderr)
        return 2

    coverage = read_module_coverage(args.coverage_xml)
    failures: list[str] = []

    print("Per-module guardrail coverage ratchet:")
    for module, floor in MODULE_FLOORS.items():
        measured = coverage.get(module)
        if measured is None:
            failures.append(f"{module}: missing from coverage report (floor {floor:.1f}%)")
            continue

        status = "OK" if measured >= floor else "LOW"
        print(f"  {status:3} {module}: {measured:.1f}% >= {floor:.1f}%")
        if measured < floor:
            failures.append(f"{module}: {measured:.1f}% < {floor:.1f}%")

    if failures:
        print("\nCoverage ratchet failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
