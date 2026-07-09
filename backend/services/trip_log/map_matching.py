"""
Map matching (snap-to-road) for recorded trips.

Sends a trip's raw GPS breadcrumbs to a self-hosted Valhalla ``/trace_route``
endpoint (Meili map matching) and returns the snapped road geometry as a JSON
``[[lat, lon], ...]`` string. Failures are soft — the RV is frequently offline
or parked somewhere OSM doesn't map (campgrounds, boondocking sites), so callers
treat ``None`` as "keep the raw breadcrumbs and try again later".

The raw breadcrumbs are never modified; matched geometry is a separate, derived
field the UI can toggle off, so a low-confidence snap must return ``None`` rather
than a plausible-looking wrong road.
"""

import json
from itertools import pairwise
from typing import Any

import httpx

from backend.core.structured_logging import get_logger
from backend.integrations.router_sidecar.location import haversine_distance_m

logger = get_logger(__name__, "RouteMatcher")

_TIMEOUT_SECONDS = 30.0
_USER_AGENT = "CoachIQ/1.0 (https://github.com/carpenike/coachiq)"

# A path needs at least two points.
_MIN_POINTS = 2
# Valhalla accepts large shapes, but keep each request bounded and stitch the
# chunks so a cross-country trip can't build one pathological request.
_MAX_POINTS_PER_REQUEST = 1000
# Reject a match whose total length differs from the raw trail by more than this
# fraction — the matcher snapped to the wrong road (common near unmapped
# campgrounds) and the raw trail is the more trustworthy record.
_LENGTH_TOLERANCE = 0.5

# Google/Valhalla encoded-polyline codec. Valhalla emits precision 6 (1e6).
_POLYLINE_PRECISION = 1_000_000.0
_POLYLINE_CHUNK_BITS = 5
_POLYLINE_CONTINUATION_BIT = 0x20
_POLYLINE_CHUNK_MASK = 0x1F
_POLYLINE_ASCII_OFFSET = 63
# Round stored coordinates to Valhalla's precision-6 resolution (~0.1 m).
_STORED_COORD_DECIMALS = 6


def _decode_polyline6(encoded: str) -> list[tuple[float, float]]:
    """Decode a Valhalla precision-6 encoded polyline into (lat, lon) pairs."""
    coordinates: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lon = 0
    length = len(encoded)
    while index < length:
        deltas = [0, 0]
        for axis in (0, 1):  # 0 = latitude, 1 = longitude
            shift = 0
            result = 0
            while True:
                byte = ord(encoded[index]) - _POLYLINE_ASCII_OFFSET
                index += 1
                result |= (byte & _POLYLINE_CHUNK_MASK) << shift
                shift += _POLYLINE_CHUNK_BITS
                if byte < _POLYLINE_CONTINUATION_BIT:
                    break
            deltas[axis] = ~(result >> 1) if result & 1 else (result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coordinates.append((lat / _POLYLINE_PRECISION, lon / _POLYLINE_PRECISION))
    return coordinates


def _extract_geometry(payload: dict[str, Any]) -> list[tuple[float, float]]:
    """Concatenate the decoded shape of every leg in a Valhalla trace_route."""
    trip = payload.get("trip") or {}
    coordinates: list[tuple[float, float]] = []
    for leg in trip.get("legs") or []:
        shape = leg.get("shape")
        if isinstance(shape, str) and shape:
            coordinates.extend(_decode_polyline6(shape))
    return coordinates


class RouteMatcher:
    """Thin async client for Valhalla ``/trace_route``."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def match(self, points: list[dict[str, Any]], raw_distance_m: float) -> str | None:
        """Snap breadcrumbs to roads.

        Returns a JSON ``[[lat, lon], ...]`` string, or ``None`` on any failure
        (offline, empty result, or an implausible match). Never raises.
        """
        if len(points) < _MIN_POINTS:
            return None
        try:
            matched: list[tuple[float, float]] = []
            for start in range(0, len(points), _MAX_POINTS_PER_REQUEST):
                chunk = points[start : start + _MAX_POINTS_PER_REQUEST]
                if len(chunk) < _MIN_POINTS:
                    break
                geometry = await self._match_chunk(chunk)
                if not geometry:
                    return None
                matched.extend(geometry)
        except Exception as exc:  # offline or unmapped: normal on the road
            logger.debug("Map match failed (%s); will retry later", exc)
            return None
        if len(matched) < _MIN_POINTS or not self._is_plausible(matched, raw_distance_m):
            logger.debug("Map match implausible for %.0fm trip; keeping raw", raw_distance_m)
            return None
        return json.dumps(
            [
                [round(lat, _STORED_COORD_DECIMALS), round(lon, _STORED_COORD_DECIMALS)]
                for lat, lon in matched
            ]
        )

    async def _match_chunk(self, chunk: list[dict[str, Any]]) -> list[tuple[float, float]]:
        payload = {
            "shape": [{"lat": point["latitude"], "lon": point["longitude"]} for point in chunk],
            "costing": "auto",
            "shape_match": "map_snap",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            # The httpx stub pyright resolves models AsyncClient.post without any
            # request-body parameter, so it wrongly rejects ``json=`` (and
            # ``content=``). httpx 0.28.1 has it at runtime; suppress the stale-
            # stub false positive rather than hand-encode the body.
            response = await client.post(
                self._url,
                json=payload,  # pyright: ignore[reportCallIssue]
                headers={"User-Agent": _USER_AGENT},
            )
            response.raise_for_status()
            return _extract_geometry(response.json())

    @staticmethod
    def _is_plausible(matched: list[tuple[float, float]], raw_distance_m: float) -> bool:
        """A match is plausible when its length is within tolerance of the raw trail."""
        if raw_distance_m <= 0:
            return True
        matched_distance_m = sum(
            haversine_distance_m(previous[0], previous[1], current[0], current[1])
            for previous, current in pairwise(matched)
        )
        low = raw_distance_m * (1.0 - _LENGTH_TOLERANCE)
        high = raw_distance_m * (1.0 + _LENGTH_TOLERANCE)
        return low <= matched_distance_m <= high
