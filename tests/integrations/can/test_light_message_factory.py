"""The live control path's CAN frame must match the verified Firefly dialect.

These bytes were confirmed on the coach bus: sending 19FEDBF9#19FF6400FF00FFFF
set instance 0x19 to op_status 0x64, and 19FF0000FF00FFFF turned it off, with
DC_DIMMER_STATUS_3 echoing the commanded level (docs/can-re-findings.md).
"""

import pytest

from backend.integrations.can.message_factory import create_light_can_message

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (0xC8, "19FFC800FF00FFFF"),  # on, full
        (0x64, "19FF6400FF00FFFF"),  # 50% — verified on the wire
        (0x00, "19FF0000FF00FFFF"),  # off — verified on the wire
    ],
)
def test_dimmer_command_matches_verified_frame(level: int, expected: str) -> None:
    msg = create_light_can_message(pgn=0x1FEDB, instance=0x19, brightness_can_level=level)
    assert msg.arbitration_id == 0x19FEDBF9  # priority 6, DGN 1FEDB, SA 0xF9
    assert msg.is_extended_id
    assert msg.data.hex().upper() == expected


def test_instance_lands_in_byte0() -> None:
    msg = create_light_can_message(pgn=0x1FEDB, instance=0x1A, brightness_can_level=0x64)
    assert msg.data[0] == 0x1A
    assert msg.data.hex().upper() == "1AFF6400FF00FFFF"
