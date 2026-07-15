"""Tests for canonical entity runtime metadata."""

from backend.models.entity_model import Entity


def test_light_off_preserves_positive_last_known_brightness() -> None:
    """Current Off brightness is zero while the next-On restore level remains positive."""
    entity = Entity("light_1", {"device_type": "light"})

    entity.update_state({"state": "on", "brightness": 25, "raw": {"operating_status": 50}})
    entity.update_state({"state": "off", "brightness": 0, "raw": {"operating_status": 0}})

    serialized = entity.to_dict()
    assert serialized["raw"]["operating_status"] == 0
    assert serialized["last_known_brightness"] == 25
