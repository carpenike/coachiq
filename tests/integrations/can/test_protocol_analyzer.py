"""Protocol analyzer performance regressions."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.integrations.can.protocol_analyzer import ProtocolAnalyzer

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_pattern_detection_cadence_survives_full_buffer() -> None:
    """A full bounded buffer must not trigger pattern analysis on every message."""
    analyzer = ProtocolAnalyzer(buffer_size=100)
    await analyzer.start()

    with patch.object(analyzer, "_detect_patterns", new_callable=AsyncMock) as detect_patterns:
        for _ in range(100):
            await analyzer.analyze_message(
                can_id=0x19FEDA8E,
                data=b"\x19\x7c\x00\xfc\xff\x05\x00\xff",
                interface="can1",
            )

        assert len(analyzer.message_buffer) == 100
        detect_patterns.assert_awaited_once()

        await analyzer.analyze_message(
            can_id=0x19FEDA8E,
            data=b"\x19\x7c\x00\xfc\xff\x05\x00\xff",
            interface="can1",
        )

        assert len(analyzer.message_buffer) == 100
        assert len(analyzer.sequence_tracker[0x19FEDA8E]) == 100
        detect_patterns.assert_awaited_once()
