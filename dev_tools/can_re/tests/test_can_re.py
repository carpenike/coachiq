"""Unit tests for the CAN reverse-engineering toolkit (pure logic only)."""

from __future__ import annotations

import pytest

from dev_tools.can_re.canframe import (
    Frame,
    RvcNames,
    classify_pgn,
    decompose_arbitration_id,
    parse_candump_line,
)
from dev_tools.can_re.census import census
from dev_tools.can_re.diff import apply_noise_filter, diff

pytestmark = [pytest.mark.unit]


# --- arbitration-id decomposition -------------------------------------------
@pytest.mark.parametrize(
    ("can_id", "pgn", "sa", "kind"),
    [
        (0x19FEDB9C, 0x1FEDB, 0x9C, "standard"),  # DC_DIMMER_COMMAND_2 from G6
        (0x19FEDA8E, 0x1FEDA, 0x8E, "standard"),  # DC_DIMMER_STATUS_3
        (0x0DFFAD4F, 0x1FFAD, 0x4F, "proprietary"),  # Firefly proprietary-B
        (0x18FECA9C, 0x0FECA, 0x9C, "standard"),  # DM_RV (PDU2, DP=0)
    ],
)
def test_decompose_and_classify(can_id: int, pgn: int, sa: int, kind: str) -> None:
    got_pgn, got_sa, _pf = decompose_arbitration_id(can_id)
    assert got_pgn == pgn
    assert got_sa == sa
    assert classify_pgn(got_pgn) == kind


def test_pdu1_ps_is_address_not_pgn() -> None:
    # PF 0xEF (<0xF0) is PDU1: the PS byte is a destination address, not PGN.
    pgn_a, _, _ = decompose_arbitration_id(0x18EF1122)
    pgn_b, _, _ = decompose_arbitration_id(0x18EF9922)
    assert pgn_a == pgn_b == 0x0EF00


# --- candump parsing ---------------------------------------------------------
def test_parse_candump_plain_and_timestamped() -> None:
    plain = parse_candump_line("  can1  19FEDB9C   [8]  B5 FF 00 22 FF 00 FF FF")
    assert plain is not None
    assert plain.can_id == 0x19FEDB9C
    assert plain.data == bytes.fromhex("B5FF0022FF00FFFF")
    assert plain.source_address == 0x9C
    assert plain.pgn == 0x1FEDB
    assert plain.instance == 0xB5

    stamped = parse_candump_line("(1720098123.456789)  can0  18FECAFC   [8]  01 02 03 04 05 06 07 08")
    assert stamped is not None
    assert stamped.timestamp == pytest.approx(1720098123.456789)
    assert stamped.pgn == 0x0FECA


def test_parse_rejects_junk() -> None:
    assert parse_candump_line("") is None
    assert parse_candump_line("  can1  19FEDB9C   [8]") is not None  # zero data bytes ok


def test_record_roundtrip() -> None:
    f = Frame(timestamp=1.5, can_id=0x19FEDB9C, data=b"\x19\xc8", interface="can1")
    assert Frame.from_record(f.to_record()) == f


# --- rvc names ---------------------------------------------------------------
def test_rvc_names_lookup() -> None:
    names = RvcNames({0x1FEDA: "DC_DIMMER_STATUS_3"})
    assert names.name(0x1FEDA) == "DC_DIMMER_STATUS_3"
    assert names.name(0x1FFAD) is None


# --- census ------------------------------------------------------------------
def _frame(can_id: int, data: bytes, ts: float) -> Frame:
    return Frame(timestamp=ts, can_id=can_id, data=data, interface="can1")


def test_census_counts_and_instances() -> None:
    frames = [
        _frame(0x19FEDB9C, b"\x13\xff\x00", 0.0),
        _frame(0x19FEDB9C, b"\x16\xff\x00", 0.5),
        _frame(0x19FEDA8E, b"\x19\x7c\x00", 1.0),
        _frame(0x0DFFAD4F, b"\x01\x02", 1.0),
    ]
    result = census(frames)
    assert result["frames"] == 4
    assert result["distinct_keys"] == 3
    assert result["proprietary_keys"] == 1  # only 1FFAD
    # dimmer command instances captured from byte0
    assert result["instances"][0x1FEDB] == {0x13: 1, 0x16: 1}


# --- diff (the crown jewel) --------------------------------------------------
def test_diff_surfaces_new_key_and_changed_byte() -> None:
    # Idle: a proprietary frame steady at byte2=0x00; a status frame steady off.
    idle = [
        _frame(0x0DFFAD4F, b"\x01\x00\x00", t) for t in (0.0, 0.1, 0.2)
    ] + [_frame(0x19FEDA8E, b"\x19\x7c\x00", t) for t in (0.0, 0.1)]
    # Action ("button pressed"): the proprietary byte2 flips to 0x22 (new value)
    # and a brand-new frame type appears.
    action = (
        [_frame(0x0DFFAD4F, b"\x01\x00\x22", t) for t in (0.0, 0.1, 0.2)]
        + [_frame(0x19FEDA8E, b"\x19\x7c\x00", 0.0)]
        + [_frame(0x19FF859C, b"\xaa\xbb", 0.0)]  # new key
    )
    result = diff(idle, action)

    # the new frame type is reported
    assert (0x1FF85, 0x9C, None) in result.new_keys
    # the proprietary byte-2 change is found and ranked first (proprietary +
    # single specific new value beats everything else)
    top = result.changed[0]
    assert (top.pgn, top.sa) == (0x1FFAD, 0x4F)
    assert top.byte_changes[0].index == 2
    assert top.byte_changes[0].new_values == [0x22]


def test_diff_ignores_unchanged() -> None:
    steady = [_frame(0x19FEDA8E, b"\x19\x7c\x00", t) for t in (0.0, 0.1, 0.2)]
    result = diff(steady, list(steady))
    assert result.new_keys == []
    assert result.gone_keys == []
    assert result.changed == []


def test_noise_filter_cancels_background_churn() -> None:
    # A free-running clock byte changes every capture (idle churn); a real
    # button also flips a dimmer status byte. The noise filter should keep the
    # dimmer signal and drop the clock.
    idle = [_frame(0x19FFFF9C, bytes([0, 0, 0, 0, 0, v]), 0.0) for v in (0x10, 0x11)]
    idle += [_frame(0x19FEDA8E, b"\x19\x7c\x00", 0.0)]
    noise = [_frame(0x19FFFF9C, bytes([0, 0, 0, 0, 0, v]), 0.0) for v in (0x12, 0x13)]
    noise += [_frame(0x19FEDA8E, b"\x19\x7c\x00", 0.0)]
    action = [_frame(0x19FFFF9C, bytes([0, 0, 0, 0, 0, v]), 0.0) for v in (0x14, 0x15)]
    action += [_frame(0x19FEDA8E, b"\x19\x7c\xc8", 0.0)]  # dimmer went on

    raw = diff(idle, action)
    filtered = apply_noise_filter(raw, diff(idle, noise))

    raw_keys = {(c.pgn, c.sa) for c in raw.changed}
    filtered_keys = {(c.pgn, c.sa) for c in filtered.changed}
    assert (0x1FFFF, 0x9C) in raw_keys  # clock flagged in raw
    assert (0x1FFFF, 0x9C) not in filtered_keys  # ...but cancelled as noise
    assert (0x1FEDA, 0x8E) in filtered_keys  # real dimmer change survives
