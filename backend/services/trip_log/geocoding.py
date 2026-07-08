"""
Reverse geocoding for trip start/end place names.

Uses a Nominatim-compatible endpoint (default: the public OSM instance) to
turn coordinates into a short "Locality, Region" label. Failures are soft —
the RV is frequently offline, so callers treat ``None`` as "try again later".

The public Nominatim usage policy requires a descriptive User-Agent and at
most one request per second; callers are responsible for the pacing.
"""

from typing import Any

import httpx

from backend.core.structured_logging import get_logger

logger = get_logger(__name__, "ReverseGeocoder")

_TIMEOUT_SECONDS = 10.0
_USER_AGENT = "CoachIQ/1.0 (https://github.com/carpenike/coachiq)"
# Nominatim zoom 10 resolves to city/town granularity.
_ZOOM = 10

# Most-specific-first keys Nominatim uses for the locality.
_LOCALITY_KEYS = ("city", "town", "village", "hamlet", "municipality", "locality", "county")


def _short_place(payload: dict[str, Any]) -> str | None:
    """Reduce a Nominatim response to "Locality, Region"."""
    address = payload.get("address") or {}
    locality = next(
        (address[key] for key in _LOCALITY_KEYS if address.get(key)),
        None,
    )
    region = address.get("state") or address.get("region")
    if locality and region:
        return f"{locality}, {region}"
    if locality:
        return str(locality)
    display = payload.get("display_name")
    if isinstance(display, str) and display:
        return ", ".join(part.strip() for part in display.split(",")[:2])
    return None


class ReverseGeocoder:
    """Thin async client for Nominatim ``/reverse``."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def reverse(self, latitude: float, longitude: float) -> str | None:
        """Return a short place label for the coordinates, or None on any failure."""
        params = {
            "format": "jsonv2",
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "zoom": str(_ZOOM),
            "addressdetails": "1",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    self._url, params=params, headers={"User-Agent": _USER_AGENT}
                )
                response.raise_for_status()
                return _short_place(response.json())
        except Exception as exc:  # offline or rate-limited: normal on the road
            logger.debug("Reverse geocode failed (%s); will retry later", exc)
            return None
