"""Tests for the trip log sampling state machine (gpsd transport is faked)."""

import time
from typing import Any

from backend.core.config import TripLogSettings
from backend.integrations.router_sidecar.gpsd import GpsdTpv
from backend.services.trip_log.trip_log_service import TripLogService


class FakeTripLogRepository:
    def __init__(self) -> None:
        self.trips: dict[int, dict[str, Any]] = {}
        self.points: list[dict[str, Any]] = []
        self._next_id = 1

    async def start_trip(self, started_at: float, latitude: float, longitude: float) -> int:
        trip_id = self._next_id
        self._next_id += 1
        self.trips[trip_id] = {
            "id": trip_id,
            "started_at": started_at,
            "ended_at": None,
            "start_latitude": latitude,
            "start_longitude": longitude,
            "end_latitude": None,
            "end_longitude": None,
            "distance_m": 0.0,
            "start_place": None,
            "end_place": None,
            "matched_geometry": None,
        }
        return trip_id

    async def end_trip(
        self, trip_id: int, ended_at: float, latitude: float, longitude: float
    ) -> None:
        trip = self.trips[trip_id]
        trip["ended_at"] = ended_at
        trip["end_latitude"] = latitude
        trip["end_longitude"] = longitude

    async def get_trip(self, trip_id: int) -> dict[str, Any] | None:
        return self.trips.get(trip_id)

    async def set_trip_places(
        self, trip_id: int, start_place: str | None, end_place: str | None
    ) -> None:
        trip = self.trips[trip_id]
        if start_place is not None:
            trip["start_place"] = start_place
        if end_place is not None:
            trip["end_place"] = end_place

    async def get_trips_missing_places(self, limit: int = 20) -> list[dict[str, Any]]:
        unnamed = [
            trip
            for trip in self.trips.values()
            if trip["ended_at"] is not None
            and (trip["start_place"] is None or trip["end_place"] is None)
        ]
        unnamed.sort(key=lambda trip: -trip["started_at"])
        return unnamed[:limit]

    async def set_trip_matched_geometry(self, trip_id: int, geometry: str) -> None:
        self.trips[trip_id]["matched_geometry"] = geometry

    async def get_trips_missing_match(self, limit: int = 20) -> list[dict[str, Any]]:
        unmatched = [
            trip
            for trip in self.trips.values()
            if trip["ended_at"] is not None and trip["matched_geometry"] is None
        ]
        unmatched.sort(key=lambda trip: -trip["started_at"])
        return unmatched[:limit]

    async def get_trip_points(self, trip_id: int) -> list[dict[str, Any]]:
        points = [point for point in self.points if point["trip_id"] == trip_id]
        points.sort(key=lambda point: point["timestamp"])
        return points

    async def add_point(self, **kwargs: Any) -> None:
        self.points.append(kwargs)
        self.trips[kwargs["trip_id"]]["distance_m"] += kwargs.get("leg_distance_m", 0.0)

    async def delete_trip(self, trip_id: int) -> bool:
        existed = trip_id in self.trips
        self.trips.pop(trip_id, None)
        self.points = [point for point in self.points if point["trip_id"] != trip_id]
        return existed

    async def delete_short_trips(self, min_distance_m: float) -> int:
        doomed = [
            trip_id
            for trip_id, trip in self.trips.items()
            if trip["ended_at"] is not None and trip["distance_m"] < min_distance_m
        ]
        for trip_id in doomed:
            await self.delete_trip(trip_id)
        return len(doomed)

    async def get_active_trip(self) -> dict[str, Any] | None:
        for trip in reversed(self.trips.values()):  # type: ignore[call-overload]
            if trip["ended_at"] is None:
                return trip
        return None

    async def get_latest_point(self, trip_id: int) -> dict[str, Any] | None:
        for point in reversed(self.points):
            if point["trip_id"] == trip_id:
                return {
                    "timestamp": point["timestamp"],
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                }
        return None


def make_service(**overrides: Any) -> tuple[TripLogService, FakeTripLogRepository]:
    kwargs: dict[str, Any] = {
        "enabled": True,
        "min_distance_m": 50.0,
        "min_interval_seconds": 0.0,  # let distance drive the tests
        "stationary_speed_mps": 1.0,
        "trip_gap_minutes": 20.0,
        # Immediate start / keep-everything defaults so lifecycle tests can
        # drive trips with single fixes; the guard tests override these.
        "start_confirm_seconds": 0.0,
        "min_trip_distance_m": 0.0,
        # Geocoding is exercised explicitly with a fake geocoder.
        "geocode_enabled": False,
        # Map matching is exercised explicitly with a fake matcher.
        "matching_enabled": False,
        # Fix-quality gates and course sampling are disabled by default so the
        # synthetic fixes below (large jumps, no timing) aren't rejected; the
        # trace-quality tests enable them explicitly.
        "max_accuracy_m": 0.0,
        "max_implied_speed_mps": 0.0,
        "min_course_change_deg": 0.0,
    }
    kwargs.update(overrides)
    settings = TripLogSettings(**kwargs)
    repository = FakeTripLogRepository()
    return TripLogService(settings, repository), repository


def fix(
    lat: float,
    lon: float,
    speed: float = 0.0,
    track: float = 90.0,
    eph: float | None = None,
) -> GpsdTpv:
    return GpsdTpv(
        lat=lat, lon=lon, timestamp=None, mode=3, speed=speed, track=track, alt=3.0, eph=eph
    )


# ~0.001 deg latitude ≈ 111 m; ~0.0001 ≈ 11 m.
LAT = 35.5784
LON = -75.4655


class TestTripLifecycle:
    async def test_parked_records_nothing(self):
        service, repository = make_service()
        for _ in range(5):
            await service._handle_fix(fix(LAT, LON, speed=0.0))
        assert repository.points == []
        assert repository.trips == {}

    async def test_movement_starts_trip_and_records(self):
        service, repository = make_service()
        await service._handle_fix(fix(LAT, LON, speed=0.0))  # parked reference
        await service._handle_fix(fix(LAT, LON, speed=5.0))  # starts moving
        assert len(repository.trips) == 1
        assert len(repository.points) == 1  # trip start point

        # Drive north ~111m -> second breadcrumb
        await service._handle_fix(fix(LAT + 0.001, LON, speed=15.0))
        assert len(repository.points) == 2

        # Creep 11m -> below min_distance, no new breadcrumb
        await service._handle_fix(fix(LAT + 0.0011, LON, speed=15.0))
        assert len(repository.points) == 2

    async def test_ignores_fixes_without_position_or_fix(self):
        service, repository = make_service()
        await service._handle_fix(GpsdTpv(lat=None, lon=None, timestamp=None, mode=3))
        await service._handle_fix(GpsdTpv(lat=LAT, lon=LON, timestamp=None, mode=1))
        assert repository.points == []

    async def test_trip_ends_after_stationary_gap(self):
        service, repository = make_service()
        await service._handle_fix(fix(LAT, LON, speed=5.0))
        assert service._active_trip_id is not None
        trip_id = service._active_trip_id

        # Simulate the RV having been parked past the gap.
        service._last_movement_at = time.time() - 21 * 60
        await service._handle_fix(fix(LAT + 0.0001, LON, speed=0.0))
        assert repository.trips[trip_id]["ended_at"] is not None
        assert service._active_trip_id is None

    async def test_resume_recent_trip_across_restart(self):
        service, repository = make_service()
        trip_id = await repository.start_trip(time.time() - 60, LAT, LON)
        await repository.add_point(
            trip_id=trip_id,
            timestamp=time.time() - 30,
            latitude=LAT,
            longitude=LON,
            leg_distance_m=0.0,
        )
        await service._resume_or_close_dangling_trip()
        assert service._active_trip_id == trip_id

    async def test_stale_dangling_trip_closed_on_restart(self):
        service, repository = make_service()
        trip_id = await repository.start_trip(time.time() - 7200, LAT, LON)
        await repository.add_point(
            trip_id=trip_id,
            timestamp=time.time() - 7000,
            latitude=LAT,
            longitude=LON,
            leg_distance_m=0.0,
        )
        await service._resume_or_close_dangling_trip()
        assert service._active_trip_id is None
        assert repository.trips[trip_id]["ended_at"] is not None


class TestNoiseGuards:
    """The debounced start and short-trip discard that keep GPS noise out."""

    async def test_single_speed_blip_does_not_start_trip(self):
        service, repository = make_service(start_confirm_seconds=10.0)
        await service._handle_fix(fix(LAT, LON, speed=0.0))  # parked reference
        await service._handle_fix(fix(LAT, LON, speed=2.0))  # phantom-speed blip
        await service._handle_fix(fix(LAT, LON, speed=0.0))  # still again
        await service._handle_fix(fix(LAT, LON, speed=1.5))  # another blip
        assert repository.trips == {}
        assert repository.points == []

    async def test_sustained_movement_starts_trip_after_confirm_window(self):
        service, repository = make_service(start_confirm_seconds=10.0)
        await service._handle_fix(fix(LAT, LON, speed=5.0))
        assert repository.trips == {}  # pending, not yet confirmed

        # Movement persists past the confirm window.
        service._pending_start_at = time.time() - 11.0
        await service._handle_fix(fix(LAT + 0.0002, LON, speed=5.0))
        assert len(repository.trips) == 1
        assert len(repository.points) == 1

    async def test_short_trip_discarded_when_it_ends(self):
        service, repository = make_service(min_trip_distance_m=100.0)
        await service._handle_fix(fix(LAT, LON, speed=5.0))  # opens a trip
        trip_id = service._active_trip_id
        assert trip_id is not None

        # Goes still past the gap without ever covering 100 m.
        service._last_movement_at = time.time() - 21 * 60
        await service._handle_fix(fix(LAT, LON, speed=0.0))
        assert service._active_trip_id is None
        assert trip_id not in repository.trips
        assert repository.points == []

    async def test_real_trip_survives_the_short_trip_guard(self):
        service, repository = make_service(min_trip_distance_m=100.0)
        await service._handle_fix(fix(LAT, LON, speed=5.0))
        trip_id = service._active_trip_id
        # Two ~111 m legs -> ~222 m total.
        await service._handle_fix(fix(LAT + 0.001, LON, speed=15.0))
        await service._handle_fix(fix(LAT + 0.002, LON, speed=15.0))

        service._last_movement_at = time.time() - 21 * 60
        await service._handle_fix(fix(LAT + 0.002, LON, speed=0.0))
        assert repository.trips[trip_id]["ended_at"] is not None

    async def test_stale_short_dangling_trip_deleted_on_restart(self):
        service, repository = make_service(min_trip_distance_m=100.0)
        trip_id = await repository.start_trip(time.time() - 7200, LAT, LON)
        await repository.add_point(
            trip_id=trip_id,
            timestamp=time.time() - 7000,
            latitude=LAT,
            longitude=LON,
            leg_distance_m=0.0,
        )
        await service._resume_or_close_dangling_trip()
        assert service._active_trip_id is None
        assert trip_id not in repository.trips


class FakeBroker:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        self.events.append((event, data))


class TestTraceQuality:
    """Fix-quality gates and corner-capturing course sampling."""

    async def test_rejects_imprecise_fix_by_eph(self):
        service, repository = make_service(max_accuracy_m=25.0)
        await service._handle_fix(fix(LAT, LON, speed=5.0, eph=10.0))  # good fix
        good_points = len(repository.points)
        assert good_points == 1

        # A wildly imprecise fix (eph 80 m) is dropped: no point, and it does
        # not even become the current position.
        await service._handle_fix(fix(LAT + 0.001, LON, speed=5.0, eph=80.0))
        assert len(repository.points) == good_points
        assert service._last_fix is not None
        assert service._last_fix.eph == 10.0

    async def test_rejects_teleport_spike_by_implied_speed(self):
        service, _ = make_service(max_implied_speed_mps=55.0)
        await service._handle_fix(fix(LAT, LON, speed=5.0))
        anchor = service._last_fix

        # ~1 km jump one moment later implies ~1000 m/s — multipath, dropped.
        service._last_fix_at = time.time() - 1.0
        await service._handle_fix(fix(LAT + 0.009, LON, speed=5.0))
        assert service._last_fix is anchor  # unchanged; spike ignored

    async def test_relocation_accepted_after_gap(self):
        # The same jump is legitimate once enough time passes (left a tunnel).
        service, _ = make_service(max_implied_speed_mps=55.0)
        await service._handle_fix(fix(LAT, LON, speed=5.0))
        service._last_fix_at = time.time() - 60.0  # a minute of dead reckoning
        await service._handle_fix(fix(LAT + 0.009, LON, speed=5.0))
        assert service._last_fix is not None
        assert service._last_fix.lat == LAT + 0.009

    async def test_course_change_records_corner_point(self):
        service, repository = make_service(
            min_distance_m=200.0,  # far enough that distance alone won't fire
            min_course_change_deg=12.0,
        )
        # Drive east, recording the trip's first point (heading 90).
        await service._handle_fix(fix(LAT, LON, speed=10.0, track=90.0))
        assert len(repository.points) == 1

        # ~11 m further but now heading north: a sharp turn under the distance
        # threshold still earns a breadcrumb so the corner isn't cut.
        service._last_recorded_at = time.time() - 3.0
        await service._handle_fix(fix(LAT, LON + 0.0001, speed=10.0, track=0.0))
        assert len(repository.points) == 2

    async def test_gentle_curve_below_threshold_adds_no_point(self):
        service, repository = make_service(
            min_distance_m=200.0,
            min_course_change_deg=12.0,
        )
        await service._handle_fix(fix(LAT, LON, speed=10.0, track=90.0))
        service._last_recorded_at = time.time() - 3.0
        # Only a 5-degree drift and under the distance threshold: no point.
        await service._handle_fix(fix(LAT, LON + 0.0001, speed=10.0, track=95.0))
        assert len(repository.points) == 1


class TestPositionPublishing:
    async def test_publishes_heartbeat_then_throttles(self):
        service, _ = make_service()
        broker = FakeBroker()
        service._event_broker = broker

        await service._handle_fix(fix(LAT, LON, speed=0.0))
        assert len(broker.events) == 1
        assert broker.events[0][0] == "location_update"

        # Same spot moments later: inside min interval, no second event.
        await service._handle_fix(fix(LAT, LON, speed=0.0))
        assert len(broker.events) == 1

    async def test_publishes_immediately_on_trip_transition(self):
        service, _ = make_service()
        broker = FakeBroker()
        service._event_broker = broker

        await service._handle_fix(fix(LAT, LON, speed=0.0))  # heartbeat, parked
        await service._handle_fix(fix(LAT, LON, speed=5.0))  # trip starts
        assert len(broker.events) == 2
        assert broker.events[-1][1]["active_trip_id"] is not None


class FakeGeocoder:
    def __init__(self, results: list[str | None]) -> None:
        self._results = results
        self.calls: list[tuple[float, float]] = []

    async def reverse(self, latitude: float, longitude: float) -> str | None:
        self.calls.append((latitude, longitude))
        return self._results.pop(0) if self._results else None


class TestGeocoding:
    async def test_geocode_trip_fills_missing_places(self, monkeypatch):
        import backend.services.trip_log.trip_log_service as module

        monkeypatch.setattr(module, "_GEOCODE_PACING_SECONDS", 0.0)
        service, repository = make_service()
        service._geocoder = FakeGeocoder(["Nags Head, North Carolina", "Richmond, Virginia"])

        trip_id = await repository.start_trip(time.time() - 3600, LAT, LON)
        await repository.end_trip(trip_id, time.time(), LAT + 0.5, LON)
        assert await service._geocode_trip(repository.trips[trip_id]) is True
        assert repository.trips[trip_id]["start_place"] == "Nags Head, North Carolina"
        assert repository.trips[trip_id]["end_place"] == "Richmond, Virginia"

    async def test_backfill_stops_when_offline(self, monkeypatch):
        import backend.services.trip_log.trip_log_service as module

        monkeypatch.setattr(module, "_GEOCODE_PACING_SECONDS", 0.0)
        service, repository = make_service()
        geocoder = FakeGeocoder([])  # every lookup fails (offline)
        service._geocoder = geocoder

        for offset in (7200, 3600):
            trip_id = await repository.start_trip(time.time() - offset, LAT, LON)
            await repository.end_trip(trip_id, time.time() - offset + 600, LAT + 0.1, LON)

        await service._geocode_backfill()
        # First trip failed both lookups; the loop must not hammer the rest.
        assert len(geocoder.calls) == 2
        assert all(trip["start_place"] is None for trip in repository.trips.values())


class FakeMatcher:
    def __init__(
        self, geometry: str | None = None, *, results: list[str | None] | None = None
    ) -> None:
        # `geometry` is returned for every call; `results` is consumed one per
        # call (then None) to script per-trip success/failure.
        self._geometry = geometry
        self._results = list(results) if results is not None else None
        self.calls: list[tuple[int, float]] = []

    async def match(self, points: list[dict[str, Any]], raw_distance_m: float) -> str | None:
        self.calls.append((len(points), raw_distance_m))
        if self._results is not None:
            return self._results.pop(0) if self._results else None
        return self._geometry


class TestMapMatching:
    async def _finished_trip_with_points(
        self, repository: FakeTripLogRepository, started_offset: float = 3600
    ) -> int:
        trip_id = await repository.start_trip(time.time() - started_offset, LAT, LON)
        await repository.add_point(
            trip_id=trip_id, timestamp=time.time() - started_offset, latitude=LAT, longitude=LON
        )
        await repository.add_point(
            trip_id=trip_id,
            timestamp=time.time() - started_offset + 60,
            latitude=LAT + 0.01,
            longitude=LON,
        )
        await repository.end_trip(trip_id, time.time(), LAT + 0.01, LON)
        return trip_id

    async def test_match_at_end_stores_geometry(self):
        service, repository = make_service()
        geometry = "[[35.5784, -75.4655], [35.5884, -75.4655]]"
        service._matcher = FakeMatcher(geometry)

        trip_id = await self._finished_trip_with_points(repository)
        points_before = [dict(point) for point in repository.points]

        assert await service._match_trip(repository.trips[trip_id]) is True
        assert repository.trips[trip_id]["matched_geometry"] == geometry
        # Raw breadcrumbs must be left completely untouched.
        assert repository.points == points_before

    async def test_backfill_stops_when_matcher_unreachable(self):
        service, repository = make_service()
        matcher = FakeMatcher(None)  # every match fails (Valhalla down)
        service._matcher = matcher

        for offset in (10800, 7200, 3600, 1800, 900):  # five unmatched trips
            await self._finished_trip_with_points(repository, started_offset=offset)

        await service._match_backfill()
        # Bails out after N consecutive failures instead of hammering all five.
        assert len(matcher.calls) == 3
        assert all(trip["matched_geometry"] is None for trip in repository.trips.values())

    async def test_backfill_skips_unmappable_trip_and_continues(self):
        service, repository = make_service()
        geometry = "[[35.5784, -75.4655], [35.5884, -75.4655]]"
        # Newest trip is unmappable (None); the two older ones match. Backfill
        # must not let the one failure block the trips behind it.
        service._matcher = FakeMatcher(results=[None, geometry, geometry])

        newest = await self._finished_trip_with_points(repository, started_offset=1800)
        older = await self._finished_trip_with_points(repository, started_offset=3600)
        oldest = await self._finished_trip_with_points(repository, started_offset=7200)

        await service._match_backfill()
        assert repository.trips[newest]["matched_geometry"] is None
        assert repository.trips[older]["matched_geometry"] == geometry
        assert repository.trips[oldest]["matched_geometry"] == geometry

    async def test_low_confidence_leaves_field_null_and_raw_untouched(self):
        service, repository = make_service()
        # A rejected (low-confidence) match returns None from the matcher.
        service._matcher = FakeMatcher(None)

        trip_id = await self._finished_trip_with_points(repository)
        points_before = [dict(point) for point in repository.points]

        assert await service._match_trip(repository.trips[trip_id]) is False
        assert repository.trips[trip_id]["matched_geometry"] is None
        assert repository.points == points_before

    async def test_backfill_keeps_draining_past_unmappable_run_once_online(self):
        service, repository = make_service()
        geometry = "[[35.5784, -75.4655], [35.5884, -75.4655]]"
        # One match proves connectivity, then a long run of unmappable trips
        # (more than the consecutive-failure limit) must NOT stop the drain —
        # the trip after them still matches.
        service._matcher = FakeMatcher(results=[geometry, None, None, None, None, geometry])

        ids = [
            await self._finished_trip_with_points(repository, started_offset=offset)
            for offset in (600, 1200, 1800, 2400, 3000, 3600)
        ]

        await service._match_backfill()
        assert repository.trips[ids[0]]["matched_geometry"] == geometry
        assert repository.trips[ids[5]]["matched_geometry"] == geometry  # reached despite 4 misses
        assert all(repository.trips[ids[i]]["matched_geometry"] is None for i in (1, 2, 3, 4))

    async def test_enrichment_pass_runs_geocode_and_match(self, monkeypatch):
        import backend.services.trip_log.trip_log_service as module

        monkeypatch.setattr(module, "_GEOCODE_PACING_SECONDS", 0.0)
        service, repository = make_service(geocode_enabled=True, matching_enabled=True)
        geometry = "[[35.5784, -75.4655], [35.5884, -75.4655]]"
        service._matcher = FakeMatcher(geometry)
        service._geocoder = FakeGeocoder(
            ["Nags Head, North Carolina", "Kitty Hawk, North Carolina"]
        )

        trip_id = await self._finished_trip_with_points(repository)

        await service._run_enrichment_once()
        assert repository.trips[trip_id]["matched_geometry"] == geometry
        assert repository.trips[trip_id]["start_place"] == "Nags Head, North Carolina"

    async def test_enrichment_loop_repeats_until_stopped(self, monkeypatch):
        import backend.services.trip_log.trip_log_service as module

        monkeypatch.setattr(module, "_ENRICHMENT_INTERVAL_SECONDS", 0.0)
        service, _ = make_service(matching_enabled=True)

        passes = 0

        async def counting_pass() -> None:
            nonlocal passes
            passes += 1
            if passes >= 3:  # let it tick a few times, then stop the loop
                service._running = False

        service._run_enrichment_once = counting_pass  # type: ignore[method-assign]
        service._running = True
        await service._enrichment_loop()
        assert passes == 3  # ran repeatedly, not just once


class TestReadSide:
    async def test_current_position_reflects_last_fix(self):
        service, _ = make_service()
        await service._handle_fix(fix(LAT, LON, speed=2.5))
        position = service.get_current_position()
        assert position["latitude"] == LAT
        assert position["fix"] is True
        assert position["speed_mps"] == 2.5
