"""CAN RX pipeline wiring regression tests.

Covers the root-cause fixes for live-data gaps in the RX pipeline:

- Device lookup key normalization: spec entries carry ``dgn_hex`` values like
  ``"0x1FEDA"`` while coach-mapping device_lookup keys are bare uppercase hex
  like ``"1FEDA"``. Before the fix every lookup missed, so no entity ever
  updated from live CAN traffic.
- DiagnosticsRepository upsert helpers used to record unknown PGNs and
  unmapped devices from the RX path (count increments, first-seen preserved).
- Decoder entry lookup: the exact-match branch keys off the wire-captured
  29-bit arbitration id (``frame_id_dict``), not ``dgn_dict`` whose keys are
  ``(priority << 18) | pgn`` with an assumed priority 6 and therefore can
  never equal a real arbitration id.
- Simulation frame ids: ``_simulate_can_messages`` must emit wire-captured
  29-bit ids so simulated frames round-trip through the RX decode path.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.repositories.diagnostics_repository import DiagnosticsRepository
from backend.services.can.can_bus_service import CANBusService, _device_lookup_key

pytestmark = [pytest.mark.unit]


def _make_message(
    arbitration_id: int = 0x19FEDA80, data: bytes = b"\x01\x02\x03\x04"
) -> SimpleNamespace:
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


class TestEntityInterfaceOwnership:
    def test_logical_interface_accepts_configured_physical_bus(self):
        service = _make_service(None)
        service.settings.can.interface_mappings = {"house": "can1", "chassis": "can0"}

        assert service._entity_interface_matches({"interface": "house"}, {"interface": "can1"})

    def test_logical_interface_rejects_bridged_copy(self):
        service = _make_service(None)
        service.settings.can.interface_mappings = {"house": "can1", "chassis": "can0"}

        assert not service._entity_interface_matches({"interface": "house"}, {"interface": "can0"})

    def test_missing_interface_metadata_preserves_legacy_processing(self):
        service = _make_service(None)

        assert service._entity_interface_matches({"interface": "house"}, {})


class TestCompositeClimateSourceMerging:
    def test_auxiliary_sources_preserve_canonical_thermostat_state(self):
        """Ambient and load sources must not replace the thermostat mode or instance."""
        thermostat_raw = {
            "instance": 1,
            "operating_mode": 1,
            "fan_mode": 0,
            "fan_speed": 200,
            "setpoint_heat": 0x24BA,
            "setpoint_cool": 0x24BA,
        }
        entity = SimpleNamespace(
            get_state=lambda: SimpleNamespace(value=thermostat_raw, raw=thermostat_raw)
        )

        ambient_data = {"instance": 5, "ambient_temperature": 0x25A2}
        ambient_value, ambient_raw = CANBusService._normalize_entity_source_signals(
            "climate", "0x1FF9C", ambient_data, ambient_data
        )
        merged_value, merged_raw = CANBusService._merged_signal_dicts(
            entity, ambient_value, ambient_raw
        )

        entity = SimpleNamespace(
            get_state=lambda: SimpleNamespace(value=merged_value, raw=merged_raw)
        )
        load_data = {
            "instance": 208,
            "group": 255,
            "operating_status": 200,
            "operating_mode": 0,
        }
        load_value, load_raw = CANBusService._normalize_entity_source_signals(
            "climate", "1FFBF", load_data, load_data
        )
        _merged_value, merged_raw = CANBusService._merged_signal_dicts(entity, load_value, load_raw)

        payload: dict[str, Any] = {}
        CANBusService._update_climate_family_state("climate", payload, merged_raw)

        assert merged_raw["instance"] == 1
        assert merged_raw["operating_mode"] == 1
        assert merged_raw["ambient_instance"] == 5
        assert merged_raw["load_instance"] == 208
        assert merged_raw["load_operating_mode"] == 0
        assert merged_raw["load_operating_status"] == 200
        assert merged_raw["shed"] is False
        assert payload["state"] == "cool"

    def test_namespaced_load_status_still_drives_shed(self):
        """The load namespace must retain the climate card's shed indicator."""
        merged_raw = {"operating_mode": 1, "load_operating_status": 0xFD}
        payload: dict[str, Any] = {}

        CANBusService._update_climate_family_state("climate", payload, merged_raw)

        assert merged_raw["shed"] is True
        assert payload["state"] == "cool"


class TestDecoderEntryLookup:
    """_get_decoder_entry: exact arbitration-id match first, PGN fallback second."""

    # ATS_AC_STATUS_1 broadcasts at priority 3 from source 0x4F: id 0x0DFFAD4F,
    # PGN 0x1FFAD. Its dgn_dict key would be (6 << 18) | 0x1FFAD — never the id.
    ATS_ARBITRATION_ID = 0x0DFFAD4F
    ATS_PGN = 0x1FFAD

    def _service_with_decoders(self) -> CANBusService:
        service = _make_service(None)
        self.exact_entry = {"name": "ATS_AC_STATUS_1", "pgn": "0x1FFAD"}
        self.fallback_entry = {"name": "GENERIC_AC_STATUS", "pgn": "0x1FFAD"}
        service.decoder_frame_id_map = {self.ATS_ARBITRATION_ID: self.exact_entry}
        service.decoder_pgn_map = {self.ATS_PGN: self.fallback_entry}
        return service

    def test_exact_arbitration_id_match_wins_over_pgn_fallback(self):
        service = self._service_with_decoders()

        entry = service._get_decoder_entry(self.ATS_ARBITRATION_ID, self.ATS_PGN)

        assert entry is self.exact_entry

    def test_unknown_source_address_falls_back_to_pgn(self):
        service = self._service_with_decoders()

        # Same frame from a different source address: no exact-id hit.
        entry = service._get_decoder_entry(0x0DFFAD99, self.ATS_PGN)

        assert entry is self.fallback_entry

    def test_synthesized_dgn_key_is_not_treated_as_exact_match(self):
        """A dgn_dict-style key must never satisfy the exact-id branch."""
        service = self._service_with_decoders()
        dgn_key = (6 << 18) | self.ATS_PGN
        service.decoder_frame_id_map = {}
        service.decoder_map = {dgn_key: self.exact_entry}
        service.decoder_pgn_map = {}

        assert service._get_decoder_entry(self.ATS_ARBITRATION_ID, self.ATS_PGN) is None

    def test_no_match_returns_none(self):
        service = self._service_with_decoders()

        assert service._get_decoder_entry(0x18FF0102, 0x1FF01) is None


class TestFrameIdDictWiring:
    """The spec's wire-captured ids must reach the service's exact-id map."""

    @pytest.fixture(scope="class")
    def rvc_config(self):
        from backend.integrations.rvc import load_config_data_v2

        return load_config_data_v2()

    def test_frame_id_dict_keys_are_wire_arbitration_ids(self, rvc_config):
        assert rvc_config.frame_id_dict
        for frame_id, entry in rvc_config.frame_id_dict.items():
            assert frame_id == entry["id"]
            # The embedded PGN must round-trip out of the arbitration id,
            # otherwise the exact-match and fallback branches would disagree.
            assert (frame_id >> 8) & 0x3FFFF == int(entry["pgn"], 16)

    def test_priority_3_ats_frames_are_reachable_by_exact_id(self, rvc_config):
        # ATS_AC_STATUS_* broadcast at priority 3 (0x0DFFxxxx). dgn_dict keys
        # assume priority 6, so only the id-keyed map can exact-match them.
        ats_ids = [
            frame_id
            for frame_id, entry in rvc_config.frame_id_dict.items()
            if str(entry.get("name", "")).startswith("ATS_AC_STATUS")
        ]
        assert ats_ids, "expected ATS_AC_STATUS_* entries in the spec"
        for frame_id in ats_ids:
            assert (frame_id >> 26) & 0x7 == 3
            assert frame_id not in rvc_config.dgn_dict

    def test_every_dgn_dict_entry_is_reachable_by_exact_id(self, rvc_config):
        # Entries sharing a PGN overwrite each other in dgn_dict, so the
        # id-keyed map is a superset: every surviving dgn_dict entry must be
        # reachable through its own wire id.
        assert len(rvc_config.frame_id_dict) >= len(rvc_config.dgn_dict)
        for entry in rvc_config.dgn_dict.values():
            assert rvc_config.frame_id_dict[entry["id"]] == entry


class TestSimulationFrameIds:
    """Simulated frames must carry ids the RX decode path can round-trip."""

    ATS_ARBITRATION_ID = 0x0DFFAD4F
    ATS_PGN = 0x1FFAD

    @pytest.mark.asyncio
    async def test_simulated_frame_id_decodes_back_to_entry_pgn(self):
        service = _make_service(None)
        entry = {"name": "ATS_AC_STATUS_1", "pgn": "0x1FFAD", "length": 8}
        # Both maps populated: simulation must pick the wire id, not the
        # synthesized (priority << 18) | pgn dgn_dict key.
        service.decoder_frame_id_map = {self.ATS_ARBITRATION_ID: entry}
        service.decoder_map = {(6 << 18) | self.ATS_PGN: entry}
        service._running = True

        simulated: list[dict] = []

        async def capture(msg: dict) -> None:
            simulated.append(msg)
            service._running = False

        service._process_message = capture

        with patch("backend.services.can.can_bus_service.asyncio.sleep", new=AsyncMock()):
            await service._simulate_can_messages()

        [msg] = simulated
        arbitration_id = msg["arbitration_id"]
        assert arbitration_id == self.ATS_ARBITRATION_ID

        # The RX path's PGN extraction must recover the entry's PGN, and the
        # decoder lookup must land back on the same entry.
        pgn = (arbitration_id >> 8) & 0x3FFFF
        assert pgn == int(entry["pgn"], 16)
        assert service._get_decoder_entry(arbitration_id, pgn) is entry


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
