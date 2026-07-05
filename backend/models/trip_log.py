"""
GPS trip log persistence models.

Breadcrumbs are distance-sampled GPS points grouped into trips (a trip is a
stretch of movement bounded by stationary gaps). Tables are created by the
startup ``Base.metadata.create_all`` pass like the analytics tables.
"""

from sqlalchemy import Float, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.database import Base, TimestampMixin


class GpsTrip(Base, TimestampMixin):
    """One contiguous stretch of movement."""

    __tablename__ = "gps_trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[float] = mapped_column(
        Float, nullable=False, index=True, comment="Unix timestamp of the first point"
    )
    ended_at: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Unix timestamp of the last point; NULL while active"
    )
    start_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    start_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    end_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_m: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="Cumulative haversine distance"
    )
    max_speed_mps: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GpsBreadcrumb(Base, TimestampMixin):
    """One recorded GPS point within a trip."""

    __tablename__ = "gps_breadcrumbs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    course_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("idx_gps_breadcrumbs_trip_timestamp", "trip_id", "timestamp"),)
