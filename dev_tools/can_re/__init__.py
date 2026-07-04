"""CAN reverse-engineering toolkit.

Standalone capture / census / diff tools for reverse-engineering the coach's
CAN traffic — in particular the Firefly G6 command dialect that standard
RV-C DC_DIMMER_COMMAND_2 frames do not drive (see docs/can-re-findings.md).

No dependency on the running CoachIQ app or its auth: these run directly
against SocketCAN via ``candump``/``cansend`` so they can be operated from the
coach while pressing physical Vegatouch Mira buttons.

Capture files are JSONL, one frame per line, in the same field shape as the
app's ``RecordedMessage`` (``timestamp``/``can_id``/``data``/``interface``),
so captures interoperate with the in-app CAN recorder.
"""

from dev_tools.can_re.canframe import (
    Frame,
    RvcNames,
    classify_pgn,
    decompose_arbitration_id,
    parse_candump_line,
)

__all__ = [
    "Frame",
    "RvcNames",
    "classify_pgn",
    "decompose_arbitration_id",
    "parse_candump_line",
]
