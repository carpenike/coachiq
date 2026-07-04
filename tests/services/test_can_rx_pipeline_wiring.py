"""CAN RX pipeline wiring regression tests.

Covers the root-cause fixes for live-data gaps in the RX pipeline:

- Device lookup key normalization: spec entries carry ``dgn_hex`` values like
  ``"0x1FEDA"`` while coach-mapping device_lookup keys are bare uppercase hex
  like ``"1FEDA"``. Before the fix every lookup missed, so no entity ever
  updated from live CAN traffic.
- DiagnosticsRepository upsert helpers used to record unknown PGNs and
  unmapped devices from the RX path (count increments, first-seen preserved).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.repositories.diagnostics_repository import DiagnosticsRepository
from backend.services.can.can_bus_service import CANBusService, _device_lookup_key

pytestmark = [pytest.mark.unit]


def _make_message(arbitration_id: int = 0x19FEDA80, data: bytes = b"\x01\x02\x03\x04") -> SimpleNamespace:
    """Build a minimal python-can-like message stub for the sniffer path."""
    return SimpleNamespace(
        arbitration_id=arbitration_id,
        data=data,
        dlc=len(data),
        is_extended_id=True,
        is_error_frame=False,
    )


def _make_service(websocket_manager: object | None) -> CANBusService:
    """Construct a CANBusService with only the sniffer-path deps wired."""
    return CANBusService(
        can_tracking_repository=MagicMock(),
        system_state_repository=MagicMock(),
        websocket_manager=websocket_manager,
    )


class TestSnifferBroadcastWiring:
    @pytest.mark.asyncio
    async def test_add_sniffer_entry_broadcasts_live_frame(self):
        websocket_manager = MagicMock()
        websocket_manager.broadcast_can_sniffer_entry = AsyncMock()
        service = _make_service(websocket_manager)

        await service._add_sniffer_entry(_make_message(), "can0", "rx")

        # Recorded to the tracking repository AND broadcast to sniffer clients.
        service._can_tracking_repository.add_can_sniffer_entry.assert_called_once()
        websocket_manager.broadcast_can_sniffer_entry.assert_awaited_once()

        frame = websocket_manager.broadcast_can_sniffer_entry.await_args.args[0]
        # Shape matches the frontend CANMessage the sniffer page consumes.
        assert frame["pgn"] == "1FEDA"  # (0x19FEDA80 >> 8) & 0x3FFFF
        assert frame["source"] == 0x80  # 0x19FEDA80 & 0xFF
        assert frame["data"] == [0x01, 0x02, 0x03, 0x04]
        assert frame["interface"] == "can0"
        assert frame["direction"] == "rx"
        assert frame["error"] is False

    @pytest.mark.asyncio
    async def test_add_sniffer_entry_without_websocket_manager_is_noop(self):
        service = _make_service(None)

        # Must not raise when no websocket manager is injected.
        await service._add_sniffer_entry(_make_message(), "can0", "rx")

        service._can_tracking_repository.add_can_sniffer_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_failure_does_not_break_rx_path(self):
        websocket_manager = MagicMock()
        websocket_manager.broadcast_can_sniffer_entry = AsyncMock(
            side_effect=RuntimeError("client exploded")
        )
        service = _make_service(websocket_manager)

        # A broken broadcast must be swallowed, never propagated to the RX path.
        await service._add_sniffer_entry(_make_message(), "can0", "rx")

        service._can_tracking_repository.add_can_sniffer_entry.assert_called_once()


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
