"""Tests for Venus OS MQTT topic and payload parsing.

Payload shapes below were captured from a live Cerbo GX (dbus-flashmq).
"""

import json

from backend.integrations.victron.topics import (
    KEEPALIVE_SUPPRESS_REPUBLISH,
    keepalive_topic,
    parse_notification,
    portal_id_from_topic,
    write_payload,
    write_topic,
)

PORTAL = "d41243d318d2"


class TestParseNotification:
    def test_parses_numeric_value(self):
        update = parse_notification(f"N/{PORTAL}/vebus/276/Ac/ActiveIn/L1/P", b'{"value":372}')
        assert update is not None
        assert update.portal_id == PORTAL
        assert update.service_type == "vebus"
        assert update.instance == "276"
        assert update.path == "Ac/ActiveIn/L1/P"
        assert update.value == 372
        assert update.minimum is None
        assert update.maximum is None

    def test_parses_min_max_bounds(self):
        update = parse_notification(
            f"N/{PORTAL}/vebus/276/Ac/ActiveIn/CurrentLimit",
            b'{"max":100.0,"min":0.0,"value":45.0}',
        )
        assert update is not None
        assert update.value == 45.0
        assert update.minimum == 0.0
        assert update.maximum == 100.0

    def test_parses_null_value(self):
        update = parse_notification(f"N/{PORTAL}/vebus/276/Ac/ActiveIn/L3/V", b'{"value":null}')
        assert update is not None
        assert update.value is None

    def test_parses_string_value(self):
        update = parse_notification(f"N/{PORTAL}/battery/512/ProductName", b'{"value":"EG4     "}')
        assert update is not None
        assert update.value == "EG4     "

    def test_non_numeric_instance_kept_as_string(self):
        # The rvc service publishes under its CAN interface name.
        update = parse_notification(f"N/{PORTAL}/rvc/can0/State", b'{"value":1}')
        assert update is not None
        assert update.instance == "can0"

    def test_rejects_non_notification_topics(self):
        assert parse_notification(f"R/{PORTAL}/keepalive", b"") is None
        assert parse_notification(f"W/{PORTAL}/vebus/276/Mode", b'{"value":3}') is None

    def test_rejects_topics_without_dbus_path(self):
        assert parse_notification(f"N/{PORTAL}/keepalive", b"") is None
        assert parse_notification(f"N/{PORTAL}/full_publish_completed", b'{"value":1}') is None

    def test_rejects_malformed_payloads(self):
        topic = f"N/{PORTAL}/vebus/276/Mode"
        assert parse_notification(topic, b"not json") is None
        assert parse_notification(topic, b"[1,2,3]") is None

    def test_empty_payload_yields_none_value(self):
        update = parse_notification(f"N/{PORTAL}/vebus/276/Mode", b"")
        assert update is not None
        assert update.value is None


class TestTopicHelpers:
    def test_portal_id_from_topic(self):
        assert portal_id_from_topic(f"N/{PORTAL}/system/0/Serial") == PORTAL
        assert portal_id_from_topic("bogus") is None

    def test_keepalive_topic_and_options(self):
        assert keepalive_topic(PORTAL) == f"R/{PORTAL}/keepalive"
        assert json.loads(KEEPALIVE_SUPPRESS_REPUBLISH) == {
            "keepalive-options": ["suppress-republish"]
        }

    def test_write_topic_and_payload(self):
        assert (
            write_topic(PORTAL, "vebus", "276", "Ac/ActiveIn/CurrentLimit")
            == f"W/{PORTAL}/vebus/276/Ac/ActiveIn/CurrentLimit"
        )
        assert json.loads(write_payload(30.0)) == {"value": 30.0}
