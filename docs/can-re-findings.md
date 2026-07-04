# CAN reverse-engineering findings (2021 Entegra Aspire 44R)

Passive-sniff observations from the coach bus, gathered while diagnosing why
CoachIQ can receive live state but cannot command lights. Tooling to reproduce
and extend this lives in [`dev_tools/can_re/`](../dev_tools/can_re/README.md).

**Status:** receive path proven end to end; **transmit/control is blocked** on
learning the Firefly command dialect. This document is the map for that work.

## Bus topology

- Two SocketCAN interfaces, `can0` and `can1`, are **bridged** — both carry the
  same ~250 frames/s (they showed identical PGN/SA distributions in a 20 s
  census). This is the known nixpi bridge; it is why the app runs a message
  deduplicator. Capture from either; `can1` is fine.
- ~62–77 distinct `(PGN, source-address)` pairs are live at idle.

## Who's talking

| Source | Role (inferred) | Notable PGNs |
|---|---|---|
| `0x9C` | **Firefly G6 controller** (the master) | `15F00`, `1FEDB` DC_DIMMER_COMMAND_2, `1FACE`, many `1FFxx` |
| `0x8E`, `0x8F` | Dimmer/output modules (status reporters) | `1FEDA` DC_DIMMER_STATUS_3, `E800` |
| `0x4F` | **Energy / ATS node** (not lighting) | `1FFAB/1FFAC/1FFAD/1FF85` = `ATS_AC_STATUS_1..4`, `1FFBF` = `AC_LOAD_STATUS` |
| `0xFC` | Chassis diagnostics | `FECA` DM_RV / DM1 |

The RV-C name lookup resolving the `0x4F` proprietary frames to `ATS_AC_STATUS_*`
means a large slice of the "proprietary" traffic is **AC power management, not
lighting** — it can be set aside when hunting the light-command frame.

## Why standard commands don't work

1. **The G6 is a continuous master.** It re-broadcasts `DC_DIMMER_COMMAND_2`
   (`1FEDB`, from SA `0x9C`) at ~2 Hz per output, cycling byte-0 (instance)
   through `{0x13, 0x16, 0x32, 0xB5..0xBC}` — ~11 outputs. A single competing
   command from CoachIQ (SA `0xF9`) is overwritten within ~90 ms. Verified: a
   30-command burst of standard `DC_DIMMER_COMMAND_2` produced **no change** in
   the target's `DC_DIMMER_STATUS_3` broadcast.

2. **Instance numbering doesn't match.** The coach mapping calls the bedroom
   ceiling light instance **25 (`0x19`)**, but the G6 never commands `0x19` on
   the wire — its instance set is `{0x13, 0x16, 0x32, 0xB5..0xBC}`. So either
   the mapping's instances are wrong, or Firefly addresses outputs by a
   different scheme (zone/group) in a proprietary frame. **This is the open
   question a button-press capture resolves.**

## The open question → how to answer it

Whatever a Vegatouch Mira button toggles is, by definition, the command the
Firefly system honors. Capture idle vs. a button press and diff:

```
python -m dev_tools.can_re.capture --iface can1 --seconds 6 --label idle       --out captures/idle.jsonl
python -m dev_tools.can_re.capture --iface can1 --seconds 6 --label ceiling-on  --out captures/ceiling-on.jsonl   # press the button now
python -m dev_tools.can_re.diff captures/idle.jsonl captures/ceiling-on.jsonl --noise captures/idle2.jsonl
```

The surviving ranked change is the control frame. Likely outcomes, in order of
prior probability:

1. A **proprietary `0x1FFxx` frame from SA `0x9C`** carries the real command
   (Firefly's private channel). Decode it, emit it as `0x9C`/that PGN.
2. It **is** `DC_DIMMER_COMMAND_2` but with a different instance/group byte than
   our mapping assumes — fix the mapping, keep the standard encoder.
3. The module only accepts commands from the master's SA `0x9C` — we'd emit as
   `0x9C` (impersonation) rather than `0xF9`.

Once known, implement in `backend/integrations/rvc/encoder.py` behind the
existing command path, then the acknowledgment matcher in
`entity_domain_service._wait_for_acknowledgment` starts confirming.

## Guardrail

Per ADR-0004, CoachIQ is API guardrails only; Firefly owns physical safety.
Lighting control is in scope; slides and locks are not.
