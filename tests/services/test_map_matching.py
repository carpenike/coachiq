"""Tests for the Valhalla map-matching client's distance-aware chunking."""

from itertools import pairwise
from typing import Any

from backend.integrations.router_sidecar.location import haversine_distance_m
from backend.services.trip_log.map_matching import (
    _MAX_CHUNK_DISTANCE_M,
    _MAX_POINTS_PER_REQUEST,
    RouteMatcher,
    _chunk_points,
)

# ~0.009 deg latitude ≈ 1 km; a straight run north from Harrisburg, PA.
_BASE_LAT = 40.2732
_BASE_LON = -76.8867


def _line(count: int, step_deg: float = 0.009) -> list[dict[str, Any]]:
    return [{"latitude": _BASE_LAT + i * step_deg, "longitude": _BASE_LON} for i in range(count)]


def _path_distance_m(points: list[dict[str, Any]]) -> float:
    return sum(
        haversine_distance_m(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
        for a, b in pairwise(points)
    )


class TestChunkPoints:
    def test_short_trip_is_one_chunk(self):
        points = _line(10)  # ~9 km
        chunks = _chunk_points(points)
        assert len(chunks) == 1
        assert chunks[0] == points

    def test_long_trip_splits_under_the_distance_limit(self):
        # ~400 km of breadcrumbs — well past Valhalla's 200 km single-request cap.
        points = _line(400)
        chunks = _chunk_points(points)
        assert len(chunks) > 1
        for chunk in chunks:
            assert _path_distance_m(chunk) <= _MAX_CHUNK_DISTANCE_M

    def test_consecutive_chunks_overlap_for_stitching(self):
        points = _line(400)
        chunks = _chunk_points(points)
        for previous, following in pairwise(chunks):
            # The last point of one chunk is the first of the next so the snapped
            # segments join without a gap.
            assert previous[-1] == following[0]

    def test_splits_on_point_count_even_when_short(self):
        # Dense, tiny steps: distance stays small but the count bound must split.
        points = _line(_MAX_POINTS_PER_REQUEST + 50, step_deg=0.00001)
        chunks = _chunk_points(points)
        assert len(chunks) > 1
        assert all(len(chunk) <= _MAX_POINTS_PER_REQUEST for chunk in chunks)


class TestMatchStitching:
    async def test_match_splits_long_trip_and_stitches(self, monkeypatch):
        matcher = RouteMatcher("http://valhalla.invalid/trace_route")
        seen: list[int] = []

        async def fake_match_chunk(chunk: list[dict[str, Any]]) -> list[tuple[float, float]]:
            seen.append(len(chunk))
            return [
                (chunk[0]["latitude"], chunk[0]["longitude"]),
                (chunk[-1]["latitude"], chunk[-1]["longitude"]),
            ]

        monkeypatch.setattr(matcher, "_match_chunk", fake_match_chunk)

        # raw_distance_m=0 disables the plausibility gate so we test only stitching.
        result = await matcher.match(_line(400), raw_distance_m=0.0)
        assert result is not None
        assert len(seen) > 1  # the long trip was sent as multiple requests
