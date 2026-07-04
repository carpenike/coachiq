"""Tests for CANBusRecorder buffer queries used by the CAN facade."""

from pathlib import Path

import pytest

from backend.integrations.can.can_bus_recorder import CANBusRecorder, RecordedMessage

pytestmark = pytest.mark.can


def _message(index: int) -> RecordedMessage:
    return RecordedMessage(
        timestamp=1000.0 + index,
        can_id=0x18FEF100 + index,
        data=bytes([index & 0xFF] * 8),
        interface="can0",
    )


@pytest.fixture
def recorder(tmp_path: Path) -> CANBusRecorder:
    return CANBusRecorder(buffer_size=10, storage_path=tmp_path)


@pytest.mark.asyncio
async def test_get_recent_messages_returns_newest_slice_as_dicts(
    recorder: CANBusRecorder,
) -> None:
    """The facade's /api/can/recent path reads dict-shaped messages from the buffer.

    Regression: CANFacade.get_recent_messages delegated to a recorder method
    that did not exist, 500ing /api/can/recent on any live app.
    """
    for index in range(5):
        recorder.message_buffer.append(_message(index))

    recent = await recorder.get_recent_messages(limit=3)

    assert [message["can_id"] for message in recent] == [
        0x18FEF102,
        0x18FEF103,
        0x18FEF104,
    ]
    assert recent[-1] == _message(4).to_dict()


@pytest.mark.asyncio
async def test_get_recent_messages_handles_empty_buffer_and_bad_limits(
    recorder: CANBusRecorder,
) -> None:
    assert await recorder.get_recent_messages() == []

    recorder.message_buffer.append(_message(0))
    assert await recorder.get_recent_messages(limit=0) == []
    assert len(await recorder.get_recent_messages(limit=100)) == 1
