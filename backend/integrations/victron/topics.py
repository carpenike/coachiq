"""
Venus OS MQTT topic and payload parsing.

Venus OS (dbus-flashmq) publishes notifications as::

    N/<portal_id>/<service_type>/<device_instance>/<dbus_path...>

with JSON payloads of the form ``{"value": <value>}`` (writable settings also
carry ``min``/``max``). Reads are requested on ``R/...`` topics and writes are
published to ``W/...`` topics with the same ``{"value": ...}`` payload shape.
"""

import json
from dataclasses import dataclass
from typing import Any

# N / <portal_id> / <service_type> / <instance> / <path with at least one segment>
_MIN_NOTIFICATION_PARTS = 5
_MIN_PORTAL_PARTS = 2


@dataclass(frozen=True, slots=True)
class VictronUpdate:
    """One decoded Venus OS notification."""

    portal_id: str
    service_type: str
    # Device instance as published (usually numeric, but e.g. the rvc
    # service publishes under its CAN interface name like "can0").
    instance: str
    # D-Bus path relative to the service, e.g. "Ac/ActiveIn/L1/P".
    path: str
    value: Any
    minimum: float | None = None
    maximum: float | None = None


def parse_notification(topic: str, payload: bytes | bytearray | str) -> VictronUpdate | None:
    """Parse an ``N/...`` MQTT message into a VictronUpdate.

    Returns None for topics that are not notifications, have no D-Bus path
    (e.g. ``N/<portal>/keepalive`` echoes), or carry unparseable payloads.
    """
    parts = topic.split("/")
    if len(parts) < _MIN_NOTIFICATION_PARTS or parts[0] != "N":
        return None

    if isinstance(payload, bytes | bytearray):
        payload = payload.decode("utf-8", errors="replace")
    try:
        body = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None

    minimum = body.get("min")
    maximum = body.get("max")
    return VictronUpdate(
        portal_id=parts[1],
        service_type=parts[2],
        instance=parts[3],
        path="/".join(parts[4:]),
        value=body.get("value"),
        minimum=float(minimum) if isinstance(minimum, int | float) else None,
        maximum=float(maximum) if isinstance(maximum, int | float) else None,
    )


def portal_id_from_topic(topic: str) -> str | None:
    """Extract the portal id from any ``N/<portal_id>/...`` topic."""
    parts = topic.split("/")
    if len(parts) >= _MIN_PORTAL_PARTS and parts[0] == "N" and parts[1]:
        return parts[1]
    return None


def keepalive_topic(portal_id: str) -> str:
    """Topic used to keep the broker publishing (required at least every 60s)."""
    return f"R/{portal_id}/keepalive"


# Payload for periodic keepalives: keeps data flowing without triggering a
# full republish of every topic (which an empty payload would).
KEEPALIVE_SUPPRESS_REPUBLISH = json.dumps({"keepalive-options": ["suppress-republish"]})


def write_topic(portal_id: str, service_type: str, instance: str, path: str) -> str:
    """Topic for writing a value to a Venus OS D-Bus path."""
    return f"W/{portal_id}/{service_type}/{instance}/{path}"


def write_payload(value: Any) -> str:
    """JSON payload for a Venus OS write."""
    return json.dumps({"value": value})
