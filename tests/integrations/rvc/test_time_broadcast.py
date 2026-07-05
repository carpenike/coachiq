"""Tests for RV-C time/GPS frame encoders.

The date/time golden vector comes off the live coach bus: the factory GPS
node's SET_DATE_TIME_COMMAND for Friday 2025-10-03 16:32:04 EST was
``19 0A 03 06 10 20 04 05``.
"""

from datetime import UTC, datetime

from backend.integrations.rvc.time_broadcast import (
    DGN_DATE_TIME_STATUS,
    DGN_GPS_POSITION,
    encode_date_time,
    encode_gps_position,
    encode_gps_status,
    encode_gps_time_status,
    rvc_arbitration_id,
    rvc_day_of_week,
)


class TestArbitrationId:
    def test_date_time_status_matches_observed_master_pattern(self):
        # Observed on-wire: 19FFFF9C = DATE_TIME_STATUS, priority 6, SA 0x9C.
        assert rvc_arbitration_id(DGN_DATE_TIME_STATUS, 0x9C) == 0x19FFFF9C
        assert rvc_arbitration_id(DGN_DATE_TIME_STATUS, 0xF9) == 0x19FFFFF9

    def test_gps_position_uses_low_dgn_page(self):
        assert rvc_arbitration_id(DGN_GPS_POSITION, 0xF9) == 0x18FEF3F9


class TestDateTimeEncoding:
    def test_golden_vector_from_coach_bus(self):
        # Friday 2025-10-03 16:32:04, tz code 5 (EST). Naive datetime is the
        # contract: encode_date_time takes local wall time.
        dt = datetime(2025, 10, 3, 16, 32, 4)  # noqa: DTZ001
        assert encode_date_time(dt, 5) == bytes.fromhex("190A030610200405")

    def test_day_of_week_sunday_is_one(self):
        assert rvc_day_of_week(datetime(2026, 7, 5)) == 1  # noqa: DTZ001 - a Sunday
        assert rvc_day_of_week(datetime(2026, 7, 6)) == 2  # noqa: DTZ001 - Monday
        assert rvc_day_of_week(datetime(2026, 7, 4)) == 7  # noqa: DTZ001 - Saturday


class TestGpsEncoding:
    def test_position_round_trips(self):
        payload = encode_gps_position(35.578453, -75.465530)
        lat = int.from_bytes(payload[0:4], "little") / 1e7 - 210
        lon = int.from_bytes(payload[4:8], "little") / 1e7 - 210
        assert abs(lat - 35.578453) < 1e-6
        assert abs(lon - -75.465530) < 1e-6

    def test_equator_reference_value(self):
        """The spec pins the equator at a raw value of 2,100,000,000."""
        payload = encode_gps_position(0.0, 0.0)
        assert int.from_bytes(payload[0:4], "little") == 2_100_000_000

    def test_status_encoding(self):
        payload = encode_gps_status(
            heading_deg=180.0, speed_mps=25.0, altitude_m=2.0, satellites=12, fix_mode=3
        )
        assert int.from_bytes(payload[0:2], "little") == 180 * 128
        assert int.from_bytes(payload[2:4], "little") == round(25.0 * 3.6 * 128)
        assert int.from_bytes(payload[4:6], "little") == round(502.0 * 10)
        assert payload[6] == 12
        assert payload[7] == 3

    def test_status_not_available_markers(self):
        payload = encode_gps_status(None, None, None, None, 0)
        assert payload == bytes.fromhex("FFFFFFFFFFFFFF00")

    def test_time_status_utc(self):
        payload = encode_gps_time_status(datetime(2026, 7, 5, 18, 30, 15, tzinfo=UTC))
        assert payload == bytes([26, 7, 5, 0xFF, 18, 30, 15, 0xFF])
