"""
Victron Cerbo GX (Venus OS) integration.

Connects to the Cerbo's local MQTT broker (dbus-flashmq) over IP and maps
Venus OS D-Bus services (vebus inverter/chargers, batteries, solar chargers,
and the system aggregate) onto CoachIQ entities. See ``client.py`` for the
transport, ``topics.py`` for topic/payload parsing, and ``catalog.py`` for
the entity definitions.
"""

from backend.integrations.victron.catalog import (
    VICTRON_ENTITY_DEFS,
    VictronEntityDef,
)
from backend.integrations.victron.client import VictronMqttClient
from backend.integrations.victron.topics import VictronUpdate, parse_notification

__all__ = [
    "VICTRON_ENTITY_DEFS",
    "VictronEntityDef",
    "VictronMqttClient",
    "VictronUpdate",
    "parse_notification",
]
