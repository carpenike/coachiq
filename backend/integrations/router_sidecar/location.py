"""Pure home/away location evaluation for the RouterOS sidecar."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from backend.integrations.router_sidecar.gpsd import GpsdTpv

LocationState = Literal["home", "away", "unknown"]

_EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True, slots=True)
class LocationEvaluatorConfig:
    """Configuration for home/away evaluation."""

    home_latitude: float | None
    home_longitude: float | None
    geofence_radius_m: float
    hysteresis_count: int
    fix_staleness_seconds: float


class LocationEvaluator:
    """Evaluate cached GPS fixes with staleness checks and hysteresis."""

    def __init__(self, config: LocationEvaluatorConfig) -> None:
        self._config = config
        self._state: LocationState = "unknown"
        self._candidate: LocationState | None = None
        self._candidate_count = 0

    def evaluate(self, fix: GpsdTpv | None, now: datetime | None = None) -> LocationState:
        """Return stable location state for the latest cached fix."""
        instant = self._instant_state(fix, now or datetime.now(UTC))
        if instant == "unknown":
            self._state = "unknown"
            self._candidate = None
            self._candidate_count = 0
            return self._state

        if instant == self._state:
            self._candidate = None
            self._candidate_count = 0
            return self._state

        if instant != self._candidate:
            self._candidate = instant
            self._candidate_count = 1
        else:
            self._candidate_count += 1

        if self._candidate_count >= self._config.hysteresis_count:
            self._state = instant
            self._candidate = None
            self._candidate_count = 0

        return self._state

    def _instant_state(self, fix: GpsdTpv | None, now: datetime) -> LocationState:
        if (
            fix is None
            or fix.mode < 2
            or fix.lat is None
            or fix.lon is None
            or fix.timestamp is None
            or self._config.home_latitude is None
            or self._config.home_longitude is None
        ):
            return "unknown"

        age = (now - fix.timestamp).total_seconds()
        if age < 0 or age > self._config.fix_staleness_seconds:
            return "unknown"

        distance_m = haversine_distance_m(
            fix.lat,
            fix.lon,
            self._config.home_latitude,
            self._config.home_longitude,
        )
        return "home" if distance_m <= self._config.geofence_radius_m else "away"


def haversine_distance_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Return distance in meters between two WGS84 points."""
    lat1 = math.radians(lat_a)
    lat2 = math.radians(lat_b)
    delta_lat = math.radians(lat_b - lat_a)
    delta_lon = math.radians(lon_b - lon_a)

    sin_lat = math.sin(delta_lat / 2)
    sin_lon = math.sin(delta_lon / 2)
    a = sin_lat * sin_lat + math.cos(lat1) * math.cos(lat2) * sin_lon * sin_lon
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_M * c
