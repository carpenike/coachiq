"""Frame parsing, J1939/RV-C arbitration-id decomposition, and RV-C naming.

Pure functions only — the unit tests exercise this module directly, and the
capture/census/diff CLIs build on it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# J1939/RV-C arbitration-id field boundaries.
_PDU1_MAX_PF = 0xF0  # PF below this is PDU1 (destination-specific)
_PROPRIETARY_PF_MASK = 0xFF00  # PGN low byte 0xFF__ == proprietary-B
_EXTENDED_ID_MIN = 0x7FF  # ids above the 11-bit range are extended (29-bit)

# candump line, with optional leading "(timestamp)" from `candump -ta`:
#   (1720098123.456789)  can1  19FEDB9C   [8]  B5 FF 00 22 FF 00 FF FF
#   can1  19FEDB9C   [8]  B5 FF 00 22 FF 00 FF FF
_CANDUMP_RE = re.compile(
    r"^\s*(?:\((?P<ts>\d+\.\d+)\)\s+)?"
    r"(?P<iface>\S+)\s+"
    r"(?P<canid>[0-9A-Fa-f]+)\s+"
    r"\[(?P<dlc>\d+)\]\s*"
    r"(?P<data>(?:[0-9A-Fa-f]{2}\s*)*)$"
)


@dataclass(frozen=True)
class Frame:
    """A single observed CAN frame."""

    timestamp: float
    can_id: int
    data: bytes
    interface: str

    # --- derived J1939/RV-C fields -------------------------------------
    @property
    def source_address(self) -> int:
        return self.can_id & 0xFF

    @property
    def pgn(self) -> int:
        return decompose_arbitration_id(self.can_id)[0]

    @property
    def priority(self) -> int:
        return (self.can_id >> 26) & 0x7

    @property
    def instance(self) -> int | None:
        """Byte 0 of the payload — the instance field for dimmer PGNs."""
        return self.data[0] if self.data else None

    def to_record(self) -> dict:
        """Serialize in the app's RecordedMessage field shape (JSONL line)."""
        return {
            "timestamp": self.timestamp,
            "can_id": self.can_id,
            "data": self.data.hex(),
            "interface": self.interface,
            "is_extended": self.can_id > _EXTENDED_ID_MIN,
        }

    @classmethod
    def from_record(cls, rec: dict) -> Frame:
        return cls(
            timestamp=float(rec["timestamp"]),
            can_id=int(rec["can_id"]),
            data=bytes.fromhex(rec["data"]),
            interface=rec.get("interface", ""),
        )


def decompose_arbitration_id(can_id: int) -> tuple[int, int, int]:
    """Return ``(pgn, source_address, pdu_format)`` for a 29-bit CAN id.

    J1939/RV-C: a PDU1 message (PF < 0xF0) is destination-specific and its
    PS byte is an address, not part of the PGN; a PDU2 message (PF >= 0xF0)
    folds PS into the PGN. The Data Page bit is included so RV-C DGNs like
    ``0x1FEDA`` come through intact.
    """
    sa = can_id & 0xFF
    ps = (can_id >> 8) & 0xFF
    pf = (can_id >> 16) & 0xFF
    dp = (can_id >> 24) & 0x1
    pgn = (dp << 16) | (pf << 8) | (ps if pf >= _PDU1_MAX_PF else 0)
    return pgn, sa, pf


def classify_pgn(pgn: int) -> str:
    """``"proprietary"`` for the manufacturer PDU2 range, else ``"standard"``.

    Proprietary-B occupies PF == 0xFF (PGN low byte 0xFF__), i.e. the
    0x_FF00-0x_FFFF band the Firefly system uses for its private channel.
    """
    return "proprietary" if (pgn & _PROPRIETARY_PF_MASK) == _PROPRIETARY_PF_MASK else "standard"


def parse_candump_line(line: str, default_ts: float = 0.0) -> Frame | None:
    """Parse one ``candump`` output line into a :class:`Frame`, or ``None``.

    Accepts both plain ``candump`` and ``candump -ta`` (absolute-timestamp)
    output. Lines that do not match (blank lines, error frames) return None.
    """
    m = _CANDUMP_RE.match(line)
    if not m:
        return None
    ts = float(m.group("ts")) if m.group("ts") else default_ts
    data = bytes.fromhex(m.group("data").replace(" ", "")) if m.group("data").strip() else b""
    return Frame(
        timestamp=ts,
        can_id=int(m.group("canid"), 16),
        data=data,
        interface=m.group("iface"),
    )


class RvcNames:
    """DGN -> human name lookup, loaded from ``config/rvc.json``.

    Falls back gracefully to an empty map (names become ``None``) so the tools
    stay usable off-coach without the spec file.
    """

    def __init__(self, by_pgn: dict[int, str]) -> None:
        self._by_pgn = by_pgn

    def name(self, pgn: int) -> str | None:
        return self._by_pgn.get(pgn)

    @classmethod
    def load(cls, path: str | Path | None = None) -> RvcNames:
        if path is None:
            # dev_tools/can_re/canframe.py -> repo root -> config/rvc.json
            path = Path(__file__).resolve().parents[2] / "config" / "rvc.json"
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return cls({})
        pgns = raw.get("pgns", raw)
        by_pgn: dict[int, str] = {}
        for entry in pgns.values():
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            pgn_hex = entry.get("pgn")
            if name and isinstance(pgn_hex, str):
                try:
                    by_pgn[int(pgn_hex, 16)] = name
                except ValueError:
                    continue
        return cls(by_pgn)
