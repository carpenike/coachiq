"""
Location API

Current GPS position and the trip log (breadcrumb trails) recorded by the
TripLogService. GPX export lets the trails travel to other mapping apps.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Response
from starlette import status

from backend.core.dependencies import create_optional_service_dependency

logger = logging.getLogger(__name__)

get_optional_trip_log_service = create_optional_service_dependency("trip_log_service")
get_optional_trip_log_repository = create_optional_service_dependency("trip_log_repository")

router = APIRouter(
    prefix="/api/location",
    tags=["location"],
    responses={
        401: {"description": "Authentication required"},
        503: {"description": "Trip log disabled or unavailable"},
    },
)


def _require(service: Any, what: str) -> Any:
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{what} is not enabled (set COACHIQ_TRIP_LOG__ENABLED=true)",
        )
    return service


@router.get("", summary="Current GPS position and recording state")
async def get_current_location(
    trip_log_service: Annotated[Any, Depends(get_optional_trip_log_service)],
) -> dict[str, Any]:
    """Latest gpsd fix plus whether a trip is being recorded."""
    service = _require(trip_log_service, "Trip log")
    return service.get_current_position()


@router.get("/trips", summary="List recorded trips (newest first)")
async def list_trips(
    trip_log_repository: Annotated[Any, Depends(get_optional_trip_log_repository)],
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Trips with start/end position, distance, and point counts."""
    repository = _require(trip_log_repository, "Trip log")
    trips = await repository.get_trips(limit=min(limit, 200), offset=max(offset, 0))
    return {"trips": trips, "count": len(trips)}


@router.get("/trips/{trip_id}/points", summary="Breadcrumbs for one trip")
async def get_trip_points(
    trip_id: int,
    trip_log_repository: Annotated[Any, Depends(get_optional_trip_log_repository)],
) -> dict[str, Any]:
    """Chronological breadcrumbs for the trip, ready for a map polyline."""
    repository = _require(trip_log_repository, "Trip log")
    trip = await repository.get_trip(trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    points = await repository.get_trip_points(trip_id)
    return {"trip": trip, "points": points}


@router.get(
    "/trips/{trip_id}/gpx",
    summary="Export one trip as GPX",
    response_class=Response,
)
async def export_trip_gpx(
    trip_id: int,
    trip_log_repository: Annotated[Any, Depends(get_optional_trip_log_repository)],
) -> Response:
    """GPX 1.1 track for use in other mapping tools."""
    repository = _require(trip_log_repository, "Trip log")
    trip = await repository.get_trip(trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    points = await repository.get_trip_points(trip_id)

    started = datetime.fromtimestamp(trip["started_at"], tz=UTC)
    name = escape(f"CoachIQ trip {started.strftime('%Y-%m-%d %H:%M')}")
    segments = []
    for point in points:
        point_time = datetime.fromtimestamp(point["timestamp"], tz=UTC).isoformat()
        elevation = (
            f"<ele>{point['altitude_m']:.1f}</ele>" if point["altitude_m"] is not None else ""
        )
        segments.append(
            f'<trkpt lat="{point["latitude"]:.6f}" lon="{point["longitude"]:.6f}">'
            f"{elevation}<time>{point_time}</time></trkpt>"
        )
    gpx = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="CoachIQ" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><name>{name}</name><trkseg>{''.join(segments)}</trkseg></trk></gpx>"
    )
    filename = f"coachiq-trip-{trip_id}-{started.strftime('%Y%m%d')}.gpx"
    return Response(
        content=gpx,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
