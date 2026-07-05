"""
RV-C date/time and GPS frame encoders (spec section 6.4 and 6.34).

Pure encoding functions for the frames the time sync service transmits:

- DATE_TIME_STATUS (1FFFF): the coach-wide clock. Master arbitration is by
  source address — the highest SA broadcasting this DGN is the system time
  master and all other nodes set their clocks to match.
- GPS_DATE_TIME_STATUS (1FEA0): same payload, announces a GPS-quality time
  source on unit initialization.
- GPS_POSITION (0FEF3): lat/lon, 1e-7 degree resolution, +210° offset.
- GPS_STATUS (1FED3): heading, speed, altitude, satellites, fix type.
- GPS_TIME_STATUS (1FDDF): UTC date/time + HDOP.

Wire-verified against the coach's existing (broken) GPS node: its
SET_DATE_TIME_COMMAND payload for 2025-10-03 (a Friday) 16:32:04 EST was
``19 0A 03 06 10 20 04 05`` — matching this encoding, including the
1=Sunday day-of-week convention.
"""

import time
from datetime import UTC, datetime

DGN_DATE_TIME_STATUS = 0x1FFFF
DGN_SET_DATE_TIME_COMMAND = 0x1FFFE
DGN_GPS_DATE_TIME_STATUS = 0x1FEA0
DGN_GPS_POSITION = 0x0FEF3
DGN_GPS_STATUS = 0x1FED3
DGN_GPS_TIME_STATUS = 0x1FDDF
DGN_COMPASS_BEARING_STATUS = 0x1FFA0

# RV-C timezone codes confirmed from spec table 6.4.2b (fragments); zones we
# cannot map are sent as 255 (not available).
_TZ_CODES = {
    "GMT": 0,
    "UTC": 0,
    "EDT": 4,
    "EST": 5,
    "PDT": 7,
    "PST": 8,
}
TZ_NOT_AVAILABLE = 0xFF

_NOT_AVAILABLE_U8 = 0xFF


def rvc_arbitration_id(dgn: int, source_address: int, priority: int = 6) -> int:
    """Build the 29-bit arbitration id for a DGN broadcast."""
    return (priority << 26) | (dgn << 8) | (source_address & 0xFF)


def rvc_day_of_week(dt: datetime) -> int:
    """RV-C day of week: 1 = Sunday … 7 = Saturday."""
    return dt.isoweekday() % 7 + 1


def timezone_code(tm: time.struct_time | None = None) -> int:
    """Best-effort RV-C timezone code for the system's local timezone."""
    tm = tm if tm is not None else time.localtime()
    return _TZ_CODES.get(tm.tm_zone or "", TZ_NOT_AVAILABLE)


def encode_date_time(dt_local: datetime, tz_code: int) -> bytes:
    """Payload shared by DATE_TIME_STATUS / SET_DATE_TIME / GPS_DATE_TIME."""
    return bytes(
        [
            max(0, dt_local.year - 2000) & 0xFF,
            dt_local.month,
            dt_local.day,
            rvc_day_of_week(dt_local),
            dt_local.hour,
            dt_local.minute,
            dt_local.second,
            tz_code & 0xFF,
        ]
    )


def encode_gps_position(latitude: float, longitude: float) -> bytes:
    """GPS_POSITION payload: two uint32 LE, 1e-7 deg, offset -210°."""

    def encode(degrees: float) -> int:
        raw = round((degrees + 210.0) * 1e7)
        return max(0, min(raw, 0xFFFF_FFFE))

    return encode(latitude).to_bytes(4, "little") + encode(longitude).to_bytes(4, "little")


def encode_gps_status(
    heading_deg: float | None,
    speed_mps: float | None,
    altitude_m: float | None,
    satellites: int | None,
    fix_mode: int,
) -> bytes:
    """GPS_STATUS payload (heading/speed 1/128 units, altitude 0.1 m -500 offset)."""
    heading_raw = min(round(heading_deg * 128), 0xFFFE) if heading_deg is not None else 0xFFFF
    speed_raw = min(round(speed_mps * 3.6 * 128), 0xFFFE) if speed_mps is not None else 0xFFFF
    altitude_raw = (
        max(0, min(round((altitude_m + 500.0) * 10), 0xFFFE)) if altitude_m is not None else 0xFFFF
    )
    # gpsd mode 2/3 matches the RV-C fix-type encoding (2 = 2D, 3 = 3D).
    fix = fix_mode if fix_mode in (2, 3) else 0
    return (
        heading_raw.to_bytes(2, "little")
        + speed_raw.to_bytes(2, "little")
        + altitude_raw.to_bytes(2, "little")
        + bytes([satellites if satellites is not None else _NOT_AVAILABLE_U8, fix])
    )


def encode_compass_bearing(bearing_deg: float | None) -> bytes:
    """COMPASS_BEARING_STATUS payload (spec 6.34.2).

    Bearing uint16 at 1/128°, calibration offset 0 (GPS course has none),
    calibration status 00b = calibrated. Bytes 5-7 are undefined (0xFF).
    """
    bearing_raw = (
        min(round((bearing_deg % 360.0) * 128), 0xFFFE) if bearing_deg is not None else 0xFFFF
    )
    return (
        bearing_raw.to_bytes(2, "little")
        + (0).to_bytes(2, "little")
        + bytes([0b1111_1100, 0xFF, 0xFF, 0xFF])
    )


def encode_gps_time_status(dt_utc: datetime) -> bytes:
    """GPS_TIME_STATUS payload: UTC date/time; byte 3 and HDOP not available."""
    return bytes(
        [
            max(0, dt_utc.year - 2000) & 0xFF,
            dt_utc.month,
            dt_utc.day,
            _NOT_AVAILABLE_U8,
            dt_utc.hour,
            dt_utc.minute,
            dt_utc.second,
            _NOT_AVAILABLE_U8,
        ]
    )


def utc_now() -> datetime:
    """UTC now (wrapped for test monkeypatching)."""
    return datetime.now(UTC)
