"""CAN RX pipeline wiring regression tests.

Covers the root-cause fixes for live-data gaps in the RX pipeline:

- Device lookup key normalization: spec entries carry ``dgn_hex`` values like
  ``"0x1FEDA"`` while coach-mapping device_lookup keys are bare uppercase hex
  like ``"1FEDA"``. Before the fix every lookup missed, so no entity ever
  updated from live CAN traffic.
- DiagnosticsRepository upsert helpers used to record unknown PGNs and
  unmapped devices from the RX path (count increments, first-seen preserved).
"""

import pytest

from backend.repositories.diagnostics_repository import DiagnosticsRepository
from backend.services.can.can_bus_service import _device_lookup_key

pytestmark = [pytest.mark.unit]


class TestDeviceLookupKeyNormalization:
    def test_spec_prefixed_dgn_hex_hits_bare_hex_lookup(self):
        device_lookup = {("1FEDA", "25"): {"entity_id": "light_25"}}

        key = _device_lookup_key("0x1FEDA", 25)

        assert key == ("1FEDA", "25")
        assert device_lookup[key] == {"entity_id": "light_25"}

    def test_bare_hex_dgn_is_unchanged(self):
        assert _device_lookup_key("1FEDA", 25) == ("1FEDA", "25")

    def test_lowercase_prefix_and_hex_are_uppercased(self):
        assert _device_lookup_key("0x1feda", "25") == ("1FEDA", "25")


class TestDiagnosticsRepositoryUpserts:
    def test_unknown_pgn_first_upsert_sets_count_one(self):
        repo = DiagnosticsRepository()

        merged = repo.upsert_unknown_pgn(
            "1EF65",
            {
                "arbitration_id_hex": "19EF6580",
                "first_seen_timestamp": 100.0,
                "last_seen_timestamp": 100.0,
                "last_data_hex": "0102030405060708",
            },
        )

        assert merged["count"] == 1
        stored = repo.get_unknown_pgns()["1EF65"]
        assert stored["arbitration_id_hex"] == "19EF6580"
        assert stored["first_seen_timestamp"] == 100.0
        assert stored["last_seen_timestamp"] == 100.0

    def test_unknown_pgn_second_upsert_increments_count_and_keeps_first_seen(self):
        repo = DiagnosticsRepository()
        repo.upsert_unknown_pgn(
            "1EF65",
            {
                "arbitration_id_hex": "19EF6580",
                "first_seen_timestamp": 100.0,
                "last_seen_timestamp": 100.0,
                "last_data_hex": "0102030405060708",
            },
        )

        merged = repo.upsert_unknown_pgn(
            "1EF65",
            {
                "arbitration_id_hex": "19EF6580",
                "first_seen_timestamp": 200.0,
                "last_seen_timestamp": 200.0,
                "last_data_hex": "AABBCCDDEEFF0011",
            },
        )

        assert merged["count"] == 2
        assert merged["first_seen_timestamp"] == 100.0
        assert merged["last_seen_timestamp"] == 200.0
        assert merged["last_data_hex"] == "AABBCCDDEEFF0011"

    def test_unmapped_entry_upsert_roundtrip_and_count_increment(self):
        repo = DiagnosticsRepository()
        entry = {
            "pgn_hex": "1FEDA",
            "dgn_hex": "1FEDA",
            "instance": "25",
            "last_data_hex": "0102030405060708",
            "first_seen_timestamp": 100.0,
            "last_seen_timestamp": 100.0,
        }

        first = repo.upsert_unmapped_entry("1FEDA-25", entry)
        assert first["count"] == 1

        second = repo.upsert_unmapped_entry(
            "1FEDA-25", {**entry, "first_seen_timestamp": 300.0, "last_seen_timestamp": 300.0}
        )

        assert second["count"] == 2
        assert second["first_seen_timestamp"] == 100.0
        assert second["last_seen_timestamp"] == 300.0
        assert repo.get_unmapped_entries()["1FEDA-25"] == second
