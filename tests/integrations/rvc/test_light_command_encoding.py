"""
Tests for the verified DC_DIMMER_COMMAND_2 (DGN 0x1FEDB) light-command dialect.

The exact byte layout and CAN id here were reverse-engineered from the live
coach bus and confirmed on the wire (see docs/can-re-findings.md):

    can_id = 0x19FEDBF9  (priority 6, PGN 0x1FEDB, SA 0xF9)
    payload = [instance, 0xFF, level, 0x00, 0xFF, 0x00, 0xFF, 0xFF]
        byte0 = instance
        byte1 = 0xFF   group = none
        byte2 = level  0-200 scale (0xC8 = 100%, 0x00 = off)
        byte3 = 0x00   command = set brightness/level
        byte4 = 0xFF   duration = instant
        byte5 = 0x00
        byte6 = 0xFF
        byte7 = 0xFF

These tests exercise the encoder against the real coach config so they also
cover the config wiring (rvc.json PGN + coach mapping command_instances).
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.integrations.rvc import decode
from backend.integrations.rvc.encoder import RVCEncoder
from backend.models.entity import ControlCommand

REPO_ROOT = Path(__file__).resolve().parents[3]
RVC_SPEC_PATH = REPO_ROOT / "config" / "rvc.json"
COACH_MAPPING_PATH = REPO_ROOT / "config" / "2021_Entegra_Aspire_44R.yml"

EXPECTED_CAN_ID = 0x19FEDBF9  # priority 6, PGN 0x1FEDB, SA 0xF9


@pytest.fixture
def encoder():
    """Build an encoder from the real coach config (SA 0xF9)."""
    # load_config_data_v2 is @functools.cache'd; clear it so edits to the
    # config between test runs are always reflected.
    decode.load_config_data_v2.cache_clear()

    settings = Mock()
    settings.controller_source_addr = "0xF9"
    settings.rvc_spec_path = str(RVC_SPEC_PATH)
    settings.rvc_coach_mapping_path = str(COACH_MAPPING_PATH)
    return RVCEncoder(settings)


@pytest.mark.unit
def test_set_on_full_emits_level_c8(encoder):
    """set on (no brightness) => level 0xC8 with the verified layout."""
    messages = encoder.encode_entity_command(
        "bedroom_accent_light", ControlCommand(command="set", state="on")
    )
    assert len(messages) == 1
    msg = messages[0]
    assert msg.extended is True
    assert msg.can_id == EXPECTED_CAN_ID
    # bedroom_accent_light is instance 27 (0x1B)
    assert msg.data[0] == 0x1B
    assert msg.data == bytes([0x1B, 0xFF, 0xC8, 0x00, 0xFF, 0x00, 0xFF, 0xFF])


@pytest.mark.unit
def test_set_on_50pct_emits_level_64(encoder):
    """set on brightness=50 => level 0x64 (100 on the 0-200 scale)."""
    messages = encoder.encode_entity_command(
        "bedroom_accent_light", ControlCommand(command="set", state="on", brightness=50)
    )
    assert len(messages) == 1
    assert messages[0].data == bytes([0x1B, 0xFF, 0x64, 0x00, 0xFF, 0x00, 0xFF, 0xFF])


@pytest.mark.unit
def test_set_off_emits_level_00(encoder):
    """set off => level 0x00."""
    messages = encoder.encode_entity_command(
        "bedroom_accent_light", ControlCommand(command="set", state="off")
    )
    assert len(messages) == 1
    assert messages[0].data == bytes([0x1B, 0xFF, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0xFF])


@pytest.mark.unit
def test_multi_instance_fan_out(encoder):
    """bedroom_ceiling_light fans out to instances 0x19 AND 0x1A."""
    messages = encoder.encode_entity_command(
        "bedroom_ceiling_light", ControlCommand(command="set", state="on")
    )
    assert len(messages) == 2

    instances = [msg.data[0] for msg in messages]
    assert instances == [0x19, 0x1A]

    for msg in messages:
        assert msg.can_id == EXPECTED_CAN_ID
        assert msg.extended is True

    # Each frame carries the full verified payload for its own instance.
    assert messages[0].data == bytes([0x19, 0xFF, 0xC8, 0x00, 0xFF, 0x00, 0xFF, 0xFF])
    assert messages[1].data == bytes([0x1A, 0xFF, 0xC8, 0x00, 0xFF, 0x00, 0xFF, 0xFF])


@pytest.mark.unit
def test_multi_instance_off_fan_out(encoder):
    """Off also fans out to both ceiling instances with level 0x00."""
    messages = encoder.encode_entity_command(
        "bedroom_ceiling_light", ControlCommand(command="set", state="off")
    )
    assert len(messages) == 2
    assert messages[0].data == bytes([0x19, 0xFF, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0xFF])
    assert messages[1].data == bytes([0x1A, 0xFF, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0xFF])


@pytest.mark.unit
def test_brightness_clamped_to_200(encoder):
    """Brightness 100% clamps to 0xC8 (200), never overflowing byte2."""
    messages = encoder.encode_entity_command(
        "bedroom_accent_light", ControlCommand(command="set", state="on", brightness=100)
    )
    assert messages[0].data[2] == 0xC8
