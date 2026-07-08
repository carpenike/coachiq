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
    }
    kwargs.update(overrides)
    settings = TripLogSettings(**kwargs)
    repository = FakeTripLogRepository()
    return TripLogService(settings, repository), repository


def fix(lat: float, lon: float, speed: float = 0.0) -> GpsdTpv:
    return GpsdTpv(lat=lat, lon=lon, timestamp=None, mode=3, speed=speed, track=90.0, alt=3.0)


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


class TestReadSide:
    async def test_current_position_reflects_last_fix(self):
        service, _ = make_service()
        await service._handle_fix(fix(LAT, LON, speed=2.5))
        position = service.get_current_position()
        assert position["latitude"] == LAT
        assert position["fix"] is True
        assert position["speed_mps"] == 2.5
