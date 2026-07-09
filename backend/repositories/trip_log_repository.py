"""Repository for GPS trip log persistence (trips + breadcrumbs)."""

import logging
from typing import Any

from sqlalchemy import delete, func, select, text, update

from backend.core.performance import PerformanceMonitor
from backend.models.trip_log import GpsBreadcrumb, GpsTrip
from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class TripLogRepository(MonitoredRepository):
    """Persist and query GPS trips and their breadcrumbs."""

    def __init__(
        self,
        database_manager: Any,
        performance_monitor: PerformanceMonitor,
    ):
        super().__init__(database_manager, performance_monitor)
        self._db_manager = database_manager

    async def ensure_tables(self) -> None:
        """Create the trip log tables if missing.

        The startup ``create_all`` pass runs before this module is imported,
        so the tables are created here (idempotent) when the trip log starts.
        """
        from backend.models.database import Base

        async with self._db_manager.get_session() as session:
            connection = await session.connection()
            await connection.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn,
                    tables=[GpsTrip.__table__, GpsBreadcrumb.__table__],
                )
            )
            # create_all never alters existing tables, so columns added after
            # the feature first shipped are patched in here (SQLite ALTER).
            result = await session.execute(text("PRAGMA table_info(gps_trips)"))
            existing = {row[1] for row in result}
            for column in ("start_place", "end_place", "matched_geometry"):
                if column not in existing:
                    await session.execute(
                        text(f"ALTER TABLE gps_trips ADD COLUMN {column} VARCHAR")
                    )
            await session.commit()

    @MonitoredRepository._monitored_operation("start_trip")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def start_trip(self, started_at: float, latitude: float, longitude: float) -> int:
        """Create a new active trip and return its id."""
        trip = GpsTrip(
            started_at=started_at,
            start_latitude=latitude,
            start_longitude=longitude,
        )
        async with self._db_manager.get_session() as session:
            session.add(trip)
            await session.commit()
            await session.refresh(trip)
            return trip.id

    @MonitoredRepository._monitored_operation("end_trip")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def end_trip(
        self, trip_id: int, ended_at: float, latitude: float, longitude: float
    ) -> None:
        """Close a trip with its final position."""
        async with self._db_manager.get_session() as session:
            await session.execute(
                update(GpsTrip)
                .where(GpsTrip.id == trip_id)
                .values(ended_at=ended_at, end_latitude=latitude, end_longitude=longitude)
            )
            await session.commit()

    @MonitoredRepository._monitored_operation("add_point")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def add_point(  # noqa: PLR0913 - one argument per breadcrumb column
        self,
        trip_id: int,
        timestamp: float,
        latitude: float,
        longitude: float,
        leg_distance_m: float,
        speed_mps: float | None = None,
        course_deg: float | None = None,
        altitude_m: float | None = None,
    ) -> None:
        """Append a breadcrumb and roll its leg into the trip totals."""
        point = GpsBreadcrumb(
            trip_id=trip_id,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude,
            speed_mps=speed_mps,
            course_deg=course_deg,
            altitude_m=altitude_m,
        )
        async with self._db_manager.get_session() as session:
            session.add(point)
            await session.execute(
                update(GpsTrip)
                .where(GpsTrip.id == trip_id)
                .values(
                    distance_m=GpsTrip.distance_m + leg_distance_m,
                    point_count=GpsTrip.point_count + 1,
                    max_speed_mps=(
                        GpsTrip.max_speed_mps
                        if speed_mps is None
                        else func_greatest(GpsTrip.max_speed_mps, speed_mps)
                    ),
                )
            )
            await session.commit()

    @MonitoredRepository._monitored_operation("get_active_trip")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def get_active_trip(self) -> dict[str, Any] | None:
        """Return the most recent trip without an end time, if any."""
        async with self._db_manager.get_session() as session:
            result = await session.execute(
                select(GpsTrip)
                .where(GpsTrip.ended_at.is_(None))
                .order_by(GpsTrip.started_at.desc())
                .limit(1)
            )
            trip = result.scalar_one_or_none()
            return _trip_to_dict(trip) if trip else None

    @MonitoredRepository._monitored_operation("get_latest_point")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def get_latest_point(self, trip_id: int) -> dict[str, Any] | None:
        """Return the newest breadcrumb of a trip."""
        async with self._db_manager.get_session() as session:
            result = await session.execute(
                select(GpsBreadcrumb)
                .where(GpsBreadcrumb.trip_id == trip_id)
                .order_by(GpsBreadcrumb.timestamp.desc())
                .limit(1)
            )
            point = result.scalar_one_or_none()
            return _point_to_dict(point) if point else None

    @MonitoredRepository._monitored_operation("get_trips")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def get_trips(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Return trips, newest first."""
        async with self._db_manager.get_session() as session:
            result = await session.execute(
                select(GpsTrip).order_by(GpsTrip.started_at.desc()).limit(limit).offset(offset)
            )
            return [_trip_to_dict(trip) for trip in result.scalars()]

    @MonitoredRepository._monitored_operation("get_trip_points")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def get_trip_points(self, trip_id: int) -> list[dict[str, Any]]:
        """Return a trip's breadcrumbs in chronological order."""
        async with self._db_manager.get_session() as session:
            result = await session.execute(
                select(GpsBreadcrumb)
                .where(GpsBreadcrumb.trip_id == trip_id)
                .order_by(GpsBreadcrumb.timestamp.asc())
            )
            return [_point_to_dict(point) for point in result.scalars()]

    @MonitoredRepository._monitored_operation("get_trip")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def get_trip(self, trip_id: int) -> dict[str, Any] | None:
        """Return one trip by id."""
        async with self._db_manager.get_session() as session:
            result = await session.execute(select(GpsTrip).where(GpsTrip.id == trip_id))
            trip = result.scalar_one_or_none()
            return _trip_to_dict(trip) if trip else None

    @MonitoredRepository._monitored_operation("delete_trip")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def delete_trip(self, trip_id: int) -> bool:
        """Delete one trip and its breadcrumbs; True if the trip existed."""
        async with self._db_manager.get_session() as session:
            await session.execute(delete(GpsBreadcrumb).where(GpsBreadcrumb.trip_id == trip_id))
            result = await session.execute(delete(GpsTrip).where(GpsTrip.id == trip_id))
            await session.commit()
            return bool(result.rowcount)

    @MonitoredRepository._monitored_operation("delete_short_trips")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def delete_short_trips(self, min_distance_m: float) -> int:
        """Delete closed trips (and their breadcrumbs) shorter than the minimum.

        Cleans up noise trips recorded before the short-trip discard guard
        existed; active trips are never touched.
        """
        async with self._db_manager.get_session() as session:
            result = await session.execute(
                select(GpsTrip.id).where(
                    GpsTrip.ended_at.is_not(None), GpsTrip.distance_m < min_distance_m
                )
            )
            trip_ids = list(result.scalars())
            if not trip_ids:
                return 0
            await session.execute(delete(GpsBreadcrumb).where(GpsBreadcrumb.trip_id.in_(trip_ids)))
            await session.execute(delete(GpsTrip).where(GpsTrip.id.in_(trip_ids)))
            await session.commit()
            return len(trip_ids)

    @MonitoredRepository._monitored_operation("get_trip_summary")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def get_trip_summary(self, since: float | None = None) -> dict[str, Any]:
        """Aggregate stats over closed trips, optionally started after ``since``."""
        conditions = [GpsTrip.ended_at.is_not(None)]
        if since is not None:
            conditions.append(GpsTrip.started_at >= since)
        async with self._db_manager.get_session() as session:
            result = await session.execute(
                select(
                    func.count(GpsTrip.id),
                    func.coalesce(func.sum(GpsTrip.distance_m), 0.0),
                    func.coalesce(func.sum(GpsTrip.ended_at - GpsTrip.started_at), 0.0),
                    func.coalesce(func.max(GpsTrip.max_speed_mps), 0.0),
                ).where(*conditions)
            )
            count, distance_m, duration_s, max_speed = result.one()
            return {
                "trip_count": int(count),
                "distance_m": float(distance_m),
                "duration_s": float(duration_s),
                "max_speed_mps": float(max_speed),
            }

    @MonitoredRepository._monitored_operation("get_previous_trip")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def get_previous_trip(self, trip_id: int) -> dict[str, Any] | None:
        """Return the closed trip that immediately precedes the given one."""
        async with self._db_manager.get_session() as session:
            anchor = await session.get(GpsTrip, trip_id)
            if anchor is None:
                return None
            result = await session.execute(
                select(GpsTrip)
                .where(
                    GpsTrip.ended_at.is_not(None),
                    GpsTrip.started_at < anchor.started_at,
                    GpsTrip.id != trip_id,
                )
                .order_by(GpsTrip.started_at.desc())
                .limit(1)
            )
            trip = result.scalar_one_or_none()
            return _trip_to_dict(trip) if trip else None

    @MonitoredRepository._monitored_operation("merge_trips")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def merge_trips(
        self, source_id: int, target_id: int, bridge_distance_m: float = 0.0
    ) -> dict[str, Any] | None:
        """Fold ``source`` (the newer trip) into ``target`` (the older one).

        Breadcrumbs move to the target; distance sums (plus the gap bridge),
        the end position/place comes from the source, and the source row is
        deleted. Returns the merged trip.
        """
        async with self._db_manager.get_session() as session:
            source = await session.get(GpsTrip, source_id)
            target = await session.get(GpsTrip, target_id)
            if source is None or target is None:
                return None
            await session.execute(
                update(GpsBreadcrumb)
                .where(GpsBreadcrumb.trip_id == source_id)
                .values(trip_id=target_id)
            )
            target.ended_at = source.ended_at
            target.end_latitude = source.end_latitude
            target.end_longitude = source.end_longitude
            target.end_place = source.end_place
            target.distance_m = target.distance_m + source.distance_m + bridge_distance_m
            target.max_speed_mps = max(target.max_speed_mps, source.max_speed_mps)
            target.point_count = target.point_count + source.point_count
            # The merged trail differs from either matched geometry; drop it so
            # the backfill re-snaps rather than showing a stale partial road.
            target.matched_geometry = None
            await session.delete(source)
            await session.commit()
            await session.refresh(target)
            return _trip_to_dict(target)

    @MonitoredRepository._monitored_operation("set_trip_places")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def set_trip_places(
        self, trip_id: int, start_place: str | None, end_place: str | None
    ) -> None:
        """Store reverse-geocoded place names on a trip (None values are kept as-is)."""
        values: dict[str, str] = {}
        if start_place is not None:
            values["start_place"] = start_place
        if end_place is not None:
            values["end_place"] = end_place
        if not values:
            return
        async with self._db_manager.get_session() as session:
            await session.execute(update(GpsTrip).where(GpsTrip.id == trip_id).values(**values))
            await session.commit()

    @MonitoredRepository._monitored_operation("get_trips_missing_places")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def get_trips_missing_places(self, limit: int = 20) -> list[dict[str, Any]]:
        """Newest closed trips that have no geocoded place names yet."""
        async with self._db_manager.get_session() as session:
            result = await session.execute(
                select(GpsTrip)
                .where(
                    GpsTrip.ended_at.is_not(None),
                    GpsTrip.start_place.is_(None) | GpsTrip.end_place.is_(None),
                )
                .order_by(GpsTrip.started_at.desc())
                .limit(limit)
            )
            return [_trip_to_dict(trip) for trip in result.scalars()]

    @MonitoredRepository._monitored_operation("set_trip_matched_geometry")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def set_trip_matched_geometry(self, trip_id: int, geometry: str) -> None:
        """Store snap-to-road geometry (JSON) on a trip."""
        async with self._db_manager.get_session() as session:
            await session.execute(
                update(GpsTrip).where(GpsTrip.id == trip_id).values(matched_geometry=geometry)
            )
            await session.commit()

    @MonitoredRepository._monitored_operation("get_trips_missing_match")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def get_trips_missing_match(self, limit: int = 20) -> list[dict[str, Any]]:
        """Newest closed trips that have not been map-matched yet."""
        async with self._db_manager.get_session() as session:
            result = await session.execute(
                select(GpsTrip)
                .where(
                    GpsTrip.ended_at.is_not(None),
                    GpsTrip.matched_geometry.is_(None),
                )
                .order_by(GpsTrip.started_at.desc())
                .limit(limit)
            )
            return [_trip_to_dict(trip) for trip in result.scalars()]

    @MonitoredRepository._monitored_operation("prune_older_than")  # noqa: SLF001 - repo-standard decorator (see analytics_repository)
    async def prune_older_than(self, cutoff_timestamp: float) -> int:
        """Delete breadcrumbs (and fully-pruned trips) older than the cutoff."""
        async with self._db_manager.get_session() as session:
            result = await session.execute(
                delete(GpsBreadcrumb).where(GpsBreadcrumb.timestamp < cutoff_timestamp)
            )
            await session.execute(
                delete(GpsTrip).where(
                    GpsTrip.ended_at.is_not(None), GpsTrip.ended_at < cutoff_timestamp
                )
            )
            await session.commit()
            return result.rowcount or 0

    def get_health_status(self) -> dict[str, Any]:
        """Health status for monitoring."""
        return {"service": "TripLogRepository", "healthy": True}


def _trip_to_dict(trip: GpsTrip) -> dict[str, Any]:
    return {
        "id": trip.id,
        "started_at": trip.started_at,
        "ended_at": trip.ended_at,
        "start_latitude": trip.start_latitude,
        "start_longitude": trip.start_longitude,
        "end_latitude": trip.end_latitude,
        "end_longitude": trip.end_longitude,
        "distance_m": trip.distance_m,
        "max_speed_mps": trip.max_speed_mps,
        "point_count": trip.point_count,
        "start_place": trip.start_place,
        "end_place": trip.end_place,
        "matched_geometry": trip.matched_geometry,
        "active": trip.ended_at is None,
    }


def _point_to_dict(point: GpsBreadcrumb) -> dict[str, Any]:
    return {
        "timestamp": point.timestamp,
        "latitude": point.latitude,
        "longitude": point.longitude,
        "speed_mps": point.speed_mps,
        "course_deg": point.course_deg,
        "altitude_m": point.altitude_m,
    }


def func_greatest(column: Any, value: float) -> Any:
    """SQLite lacks GREATEST; scalar MAX(x, y) is the SQLite spelling."""
    return func.max(column, value)
