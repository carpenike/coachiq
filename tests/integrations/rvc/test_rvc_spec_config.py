"""
Structural sanity checks for config/rvc.json.

The spec file has a history of LLM-fabricated entries (invented layouts,
truncated or shuffled PGNs, UNKNOWN_* placeholders shadowing real DGNs) that
caused real decode bugs (PRs #190/#191, 2026-07-05 audit). These tests pin the
invariants the runtime decoder depends on:

- the PGN fallback map in CANBusService keys entries by ``int(entry["pgn"], 16)``
  and matches incoming frames on ``(arbitration_id >> 8) & 0x3FFFF``, so every
  entry's ``pgn`` field must be derivable from its own ``id``;
- the loader keys ``dgn_dict`` by ``(priority << 18) | pgn`` with
  last-entry-wins, so duplicate keys silently shadow earlier entries.
"""

import json
from pathlib import Path

import pytest

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "rvc.json"


@pytest.fixture(scope="module")
def spec_entries() -> dict:
    with CONFIG_PATH.open() as f:
        return json.load(f)["pgns"]


def test_pgn_field_matches_arbitration_id(spec_entries):
    """entry['pgn'] must equal the PGN the decoder derives from a wire frame."""
    mismatches = []
    for key, entry in spec_entries.items():
        derived = (entry["id"] >> 8) & 0x3FFFF
        stored = int(entry["pgn"], 16)
        if derived != stored:
            mismatches.append(
                f"{entry['name']} (key {key}): pgn={stored:X}, id derives {derived:X}"
            )
    assert not mismatches, "pgn field contradicts the entry's own CAN id:\n" + "\n".join(mismatches)


def test_keys_match_ids(spec_entries):
    for key, entry in spec_entries.items():
        assert int(key) == entry["id"], f"{entry['name']}: key {key} != id {entry['id']}"


def test_entry_names_unique(spec_entries):
    names = [e["name"] for e in spec_entries.values()]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"Duplicate entry names: {dupes}"


def test_no_duplicate_dgn_keys(spec_entries):
    """Two entries on the same (priority << 18) | pgn key shadow each other."""
    seen: dict[int, str] = {}
    for entry in spec_entries.values():
        dgn = (int(entry.get("priority", "6"), 16) << 18) | int(entry["pgn"], 16)
        assert dgn not in seen, (
            f"{entry['name']} collides with {seen[dgn]} on DGN key {dgn:X}; "
            "the loader would silently keep only the last one"
        )
        seen[dgn] = entry["name"]


def test_unknown_entries_are_quarantined(spec_entries):
    """UNKNOWN_* placeholders must be named after their captured CAN id so a
    fabricated pgn cannot hide under a plausible-looking label."""
    for entry in spec_entries.values():
        if entry["name"].startswith("UNKNOWN_"):
            assert entry["name"] == f"UNKNOWN_{entry['id']:08X}", (
                f"{entry['name']}: quarantine name should be UNKNOWN_{entry['id']:08X}"
            )


def test_dm_entries_cover_both_dialects(spec_entries):
    """The bus carries J1939 DM1 (FECA) and RV-C DM_RV (1FECA); both must
    decode with the shared DM payload layout the diagnostic handler reads."""
    by_name = {e["name"]: e for e in spec_entries.values()}
    assert int(by_name["J1939_DM1"]["pgn"], 16) == 0xFECA
    assert int(by_name["DM_RV"]["pgn"], 16) == 0x1FECA
    for name in ("J1939_DM1", "DM_RV"):
        signals = {s["name"]: s for s in by_name[name]["signals"]}
        for required in (
            "SPN_MSB",
            "SPN_ISB",
            "SPN_LSB",
            "FMI",
            "occurrence_count",
            "yellow_lamp_status",
            "red_lamp_status",
        ):
            assert required in signals, f"{name} missing signal {required}"
        # RV-C Table 3.2.5.1b: byte 4 = FMI in bits 0-4, SPN top bits in 5-7
        assert (signals["FMI"]["start_bit"], signals["FMI"]["length"]) == (32, 5)
        assert (signals["SPN_LSB"]["start_bit"], signals["SPN_LSB"]["length"]) == (37, 3)


def test_16bit_temperatures_use_table_5_3_scale(spec_entries):
    """Any 16-bit deg-C signal must carry the Table 5.3 scale (0.03125, -273)."""
    bad = []
    for entry in spec_entries.values():
        for s in entry.get("signals", []):
            if (
                s.get("unit") == "deg C"
                and s.get("length") == 16
                and (s.get("scale") != 0.03125 or s.get("offset") != -273)
            ):
                bad.append(f"{entry['name']}.{s['name']}")
    assert not bad, f"16-bit temperature signals missing Table 5.3 scale/offset: {bad}"


def test_loader_warns_on_duplicate_dgn_key(tmp_path, caplog):
    """The loader must not silently accept two entries on the same DGN key."""
    import warnings

    from backend.integrations.rvc import decode

    spec = {
        "version": "test",
        "pgns": {
            "1": {"name": "REAL_ENTRY", "id": 1, "pgn": "0x1FEDA", "signals": []},
            "2": {"name": "SHADOWING_ENTRY", "id": 2, "pgn": "0x1FEDA", "signals": []},
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    mapping_path = Path(__file__).resolve().parents[3] / "config" / "coach_mapping.default.yml"

    decode.clear_config_cache()
    try:
        with caplog.at_level("WARNING"), warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            decode.load_config_data(str(spec_path), str(mapping_path))
        assert any(
            "Duplicate DGN key" in r.getMessage() and "SHADOWING_ENTRY" in r.getMessage()
            for r in caplog.records
        ), "expected a duplicate-DGN warning from the spec loader"
    finally:
        decode.clear_config_cache()
