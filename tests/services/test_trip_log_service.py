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
        }
        return trip_id

    async def end_trip(
        self, trip_id: int, ended_at: float, latitude: float, longitude: float
    ) -> None:
        self.trips[trip_id]["ended_at"] = ended_at

    async def add_point(self, **kwargs: Any) -> None:
        self.points.append(kwargs)

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
    settings = TripLogSettings(
        enabled=True,
        min_distance_m=50.0,
        min_interval_seconds=0.0,  # let distance drive the tests
        stationary_speed_mps=1.0,
        trip_gap_minutes=20.0,
        **overrides,
    )
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


class TestReadSide:
    async def test_current_position_reflects_last_fix(self):
        service, _ = make_service()
        await service._handle_fix(fix(LAT, LON, speed=2.5))
        position = service.get_current_position()
        assert position["latitude"] == LAT
        assert position["fix"] is True
        assert position["speed_mps"] == 2.5
