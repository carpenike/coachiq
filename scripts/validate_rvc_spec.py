#!/usr/bin/env python3
"""Validate RV-C spec structure and decode sanity against a small live fixture.

Coach mapping YAML files are partial entity maps. This harness validates them
one-way: every mapped DGN reference must exist in rvc.json, but live bus DGNs do
not need to appear in the mapping.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
RVC_SPEC_PATH = REPO_ROOT / "config" / "rvc.json"
DEFAULT_CORPUS_PATH = REPO_ROOT / "recordings" / "recon004_decode_sanity.candump"

MAPPING_METADATA_SECTIONS = {
    "coach_info",
    "dgn_pairs",
    "templates",
    "global_defaults",
    "areas",
    "lighting_scenes",
    "lighting_groups",
    "validation_rules",
    "file_metadata",
    "can_interface_mapping",
    "interface_requirements",
}

STANDARD_TP_PGNS = {0x0EAFF, 0x0EBFF, 0x0EBFC, 0x0ECFF, 0x0ECFC}

PGN_RE = re.compile(r"^0x[0-9a-fA-F]+$")
CANDUMP_RE = re.compile(
    r"\((?P<timestamp>[0-9.]+)\)\s+"
    + r"(?P<interface>can\d+)\s+"
    + r"(?P<can_id>[0-9A-Fa-f]+)#(?P<data>[0-9A-Fa-f]+)$"
)


def load_rvc_spec(path: Path) -> dict[str, Any]:
    """Load the RV-C spec JSON file."""
    with path.open(encoding="utf-8") as spec_file:
        data = json.load(spec_file)
    if not isinstance(data, dict):
        msg = "rvc spec root must be a JSON object"
        raise ValueError(msg)
    return data


def parse_pgn(value: object) -> int | None:
    """Parse a PGN string like 0x1FEDA."""
    if not isinstance(value, str) or not PGN_RE.match(value):
        return None
    return int(value, 16)


def validate_structural(spec: dict[str, Any]) -> list[str]:  # noqa: C901, PLR0912
    """Validate local structure that the legacy validator does not check."""
    errors: list[str] = []
    pgns = spec.get("pgns")
    if not isinstance(pgns, dict):
        return ["top-level pgns must be an object"]

    seen_ids: set[int] = set()
    for key, entry in pgns.items():
        if not isinstance(entry, dict):
            errors.append(f"PGN {key}: entry must be an object")
            continue

        entry_id = entry.get("id")
        if not isinstance(entry_id, int):
            errors.append(f"PGN {key}: id must be an integer")
        elif entry_id in seen_ids:
            errors.append(f"PGN {key}: duplicate raw id {entry_id}")
        else:
            seen_ids.add(entry_id)

        pgn = parse_pgn(entry.get("pgn"))
        if pgn is None:
            errors.append(f"PGN {key}: pgn must be a hex string")
        elif isinstance(entry_id, int) and ((entry_id >> 8) & 0x3FFFF) != pgn:
            errors.append(f"PGN {key}: id 0x{entry_id:08X} does not contain pgn 0x{pgn:05X}")

        length = entry.get("length", 8)
        if length is None:
            continue
        if not isinstance(length, int) or length <= 0:
            errors.append(f"PGN {key}: length must be a positive integer or null")
            continue

        used_ranges: list[tuple[int, int, str]] = []
        for signal in entry.get("signals", []):
            if not isinstance(signal, dict):
                errors.append(f"PGN {key}: signal must be an object")
                continue
            name = str(signal.get("name", "<unnamed>"))
            start_bit = signal.get("start_bit")
            signal_length = signal.get("length")
            if not isinstance(start_bit, int) or not isinstance(signal_length, int):
                errors.append(f"PGN {key} signal {name}: start_bit/length must be integers")
                continue
            end_bit = start_bit + signal_length
            if start_bit < 0 or signal_length <= 0 or end_bit > length * 8:
                errors.append(
                    f"PGN {key} signal {name}: bit range {start_bit}:{end_bit} "
                    + f"does not fit in {length} byte payload"
                )
            for other_start, other_end, other_name in used_ranges:
                if start_bit < other_end and other_start < end_bit:
                    errors.append(
                        f"PGN {key} signal {name}: overlaps {other_name} "
                        + f"({start_bit}:{end_bit} vs {other_start}:{other_end})"
                    )
            used_ranges.append((start_bit, end_bit, name))

    return errors


def classify_duplicate_pgns(spec: dict[str, Any]) -> list[str]:
    """Return informational duplicate PGN classifications."""
    variants: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for entry in spec.get("pgns", {}).values():
        if isinstance(entry, dict):
            pgn = parse_pgn(entry.get("pgn"))
            if pgn is not None:
                variants[pgn].append(entry)

    lines: list[str] = []
    for pgn, entries in sorted(variants.items()):
        if len(entries) <= 1:
            continue
        ids = sorted(entry_id for entry in entries if isinstance(entry_id := entry.get("id"), int))
        names = ", ".join(str(entry.get("name", "<unnamed>")) for entry in entries)
        lines.append(
            f"duplicate pgn 0x{pgn:05X}: {len(entries)} variants; ids={ids}; names={names}"
        )
    return lines


def validate_cross_file_references(spec: dict[str, Any], paths: list[Path]) -> list[str]:
    """Validate mapped YAML DGN references against rvc.json PGNs.

    This intentionally does not validate bus coverage against the mapping: coach
    mapping files are incomplete by design and represent surfaced entities so far.
    """
    errors: list[str] = []
    known_pgns = {
        str(entry.get("pgn", "")).removeprefix("0x").upper()
        for entry in spec.get("pgns", {}).values()
        if isinstance(entry, dict)
    }

    for path in paths:
        with path.open(encoding="utf-8") as mapping_file:
            data = yaml.safe_load(mapping_file) or {}
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if key == "dgn_pairs" and isinstance(value, dict):
                path_name = path.relative_to(REPO_ROOT)
                for command_dgn, status_dgn in value.items():
                    references = (str(command_dgn).upper(), str(status_dgn).upper())
                    errors.extend(
                        f"{path_name} dgn_pairs references unknown DGN {referenced}"
                        for referenced in references
                        if referenced not in known_pgns
                    )
                continue
            if key in MAPPING_METADATA_SECTIONS or str(key).startswith(("#", "_")):
                continue
            key_str = str(key).upper()
            if (
                all(character in "0123456789ABCDEF" for character in key_str)
                and key_str not in known_pgns
            ):
                errors.append(f"{path.relative_to(REPO_ROOT)} references unknown DGN {key_str}")
    return errors


def parse_candump(path: Path) -> list[tuple[int, bytes]]:
    """Parse candump -L lines into raw CAN IDs and payload bytes."""
    frames: list[tuple[int, bytes]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = CANDUMP_RE.match(stripped)
        if match is None:
            msg = f"invalid candump line: {line}"
            raise ValueError(msg)
        frames.append((int(match.group("can_id"), 16), bytes.fromhex(match.group("data"))))
    return frames


def build_lookup(
    spec: dict[str, Any],
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """Build raw-ID and PGN lookup tables for decode sanity checks."""
    by_id: dict[int, dict[str, Any]] = {}
    by_pgn: dict[int, dict[str, Any]] = {}
    for entry in spec.get("pgns", {}).values():
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        if isinstance(entry_id, int):
            by_id[entry_id] = entry
        pgn = parse_pgn(entry.get("pgn"))
        if pgn is None:
            continue
        current = by_pgn.get(pgn)
        if current is None or str(current.get("name", "")).startswith("UNKNOWN"):
            by_pgn[pgn] = entry
    return by_id, by_pgn


def validate_live_corpus(spec: dict[str, Any], corpus_path: Path) -> list[str]:  # noqa: C901
    """Decode the committed live-corpus fixture and check sentinel handling.

    The corpus is a curated decode fixture, not a complete coach inventory and
    not a source for coach-mapping completeness checks.
    """
    from backend.integrations.rvc.decoder_core import DecodedValue, decode_payload

    errors: list[str] = []
    by_id, by_pgn = build_lookup(spec)
    frames = parse_candump(corpus_path)
    unavailable_seen = 0
    decoded_seen = 0
    unknown_pgns: Counter[int] = Counter()

    for can_id, payload in frames:
        pgn = (can_id >> 8) & 0x3FFFF
        entry = by_id.get(can_id) or by_pgn.get(pgn)
        if entry is None:
            if pgn not in STANDARD_TP_PGNS:
                unknown_pgns[pgn] += 1
            continue
        decoded, decode_errors = decode_payload(entry, payload)
        decoded_seen += 1
        if decode_errors:
            errors.append(f"0x{can_id:08X}: {len(decode_errors)} decode errors")
        for signal_name, result in decoded.items():
            if not isinstance(result, DecodedValue):
                continue
            if result.unavailable:
                unavailable_seen += 1
                if result.value is not None:
                    errors.append(f"0x{can_id:08X}.{signal_name}: unavailable value is not None")
            elif result.raw_value in _configured_unavailable_values(entry, signal_name):
                errors.append(
                    f"0x{can_id:08X}.{signal_name}: raw sentinel {result.raw_value} was not masked"
                )

    for pgn, count in sorted(unknown_pgns.items()):
        errors.append(f"live corpus contains undecoded non-TP PGN 0x{pgn:05X} ({count} frames)")
    if decoded_seen == 0:
        errors.append("live corpus did not decode any frames")
    if unavailable_seen == 0:
        errors.append("live corpus did not exercise any unavailable_raw_values metadata")
    return errors


def _configured_unavailable_values(entry: dict[str, Any], signal_name: str) -> set[int]:
    """Return configured unavailable raw values for a signal in an entry."""
    for signal in entry.get("signals", []):
        if not isinstance(signal, dict) or signal.get("name") != signal_name:
            continue
        configured = signal.get("unavailable_raw_values", [])
        if not isinstance(configured, list):
            configured = [configured]
        values: set[int] = set()
        for value in configured:
            if isinstance(value, int):
                values.add(value)
            elif isinstance(value, str):
                values.add(int(value, 0))
        return values
    return set()


def main() -> int:
    """Run the RV-C spec validation harness."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=RVC_SPEC_PATH)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument(
        "--mapping",
        type=Path,
        action="append",
        default=[
            REPO_ROOT / "config" / "coach_mapping.default.yml",
            REPO_ROOT / "config" / "2021_Entegra_Aspire_44R.yml",
        ],
        help=(
            "YAML mapping file whose mapped DGN references must exist in rvc.json; "
            "may be passed multiple times"
        ),
    )
    args = parser.parse_args()

    spec = load_rvc_spec(args.spec)
    errors: list[str] = []
    errors.extend(validate_structural(spec))
    errors.extend(validate_cross_file_references(spec, args.mapping))
    errors.extend(validate_live_corpus(spec, args.corpus))

    duplicate_lines = classify_duplicate_pgns(spec)
    if duplicate_lines:
        print("Classified duplicate PGN variants:")
        for line in duplicate_lines:
            print(f"  - {line}")

    if errors:
        print("RV-C spec validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("RV-C spec validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
