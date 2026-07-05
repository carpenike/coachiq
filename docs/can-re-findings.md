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

## Climate (heating / cooling) — survey 2026-07-04

A 15 s census while diagnosing nothing in particular (idle bus, July
afternoon) showed the climate system talks **standard RV-C thermostat DGNs**,
all broadcast by the G6 (SA `0x9C`):

| DGN | Name | What we saw |
|---|---|---|
| `1FFE2` | THERMOSTAT_STATUS_1 | **7 instances (0–6)**, each ~every 5 s. Instances 0–2: mode=Cool, fan on 50%, heat/cool setpoints in lockstep (69.5 / 68.5 / 100.5 °F). Instances 3–6: mode=Off, fan 0 (heat-only zones: bay + floor loops). Setpoints are uint16 LE 1/32 K — the spec JSON's `big_endian` annotation was wrong (decoder ignores it; fixed anyway). |
| `1FF9C` | THERMOSTAT_AMBIENT_STATUS | Per-zone ambient, bytes 1–2 LE (spec JSON had a fabricated layout — fixed). Observed 78.7 / 101.8 / 86.9 / (−88 = sensor absent) / 72.8 / 74.8 °F for instances 0–5; instance 6 silent. |
| `1FFE1` | AIR_CONDITIONER_STATUS | Rooftop ACs report from their own SAs `0x96/0x97/0x98` as instances 3/2/1. A fourth node `0x99` broadcasts instance `0x51` with an odd payload — unidentified, left unmapped. |
| `1FFE0` | AIR_CONDITIONER_COMMAND | Re-broadcast by the G6 at ~1 Hz per unit — same continuous-master pattern as the dimmers, so **command the thermostat, not the AC units**. |
| `1FFF7`/`1FE99` | WATERHEATER_STATUS(_2) | Aqua-Hot on SA `0x9E`, instance 1: mode 3 (gas/electric), loop temp ~92 °C / 198 °F. |

Control: `THERMOSTAT_COMMAND_1` (DGN `1FEF9`, sent as `0x19FEF9F9`) with the
payload mirroring the STATUS_1 layout: `[instance, mode|fan<<4|sched<<6,
fan_speed(0-200), heat_lo, heat_hi, cool_lo, cool_hi, FF]`. The spec JSON had
the wrong PGN (`FEF6`) and a "tenths of °C" layout — both corrected.

**Wire-verified 2026-07-04 (evening):** unlike the dimmers, the G6 accepts the
standard command from SA `0xF9` as-is — an app-driven setpoint change on
instance 0 was echoed in the very next `1FFE2` broadcast, and the G6 then
cascaded it into the linked heat instance. No Firefly dialect needed.

Zone mapping, confirmed live (pressing + on each Mira zone in display order
stepped these instances in order):

- 0 = Front, 1 = Mid, 2 = Rear (cool-capable; the G6 re-syncs heat==cool a few
  seconds after a cool-side change — the Mira's + steps cool only, in 0.5 °F
  raw steps).
- 3 tracks zone 0's setpoint and 4 tracks zone 2's — per-zone Aqua-Hot heat
  counterparts, not independent zones.
- 5 = **Bay**, 6 = **Floor** — identified live 2026-07-05: the Mira's Bay
  setpoint button stepped zone 5, the Floor button stepped zone 6.

**`1FF9C` ambient instances are SENSOR CHANNELS, not zone instances** —
discovered when the UI showed the rear temperature on the Mid card
(2026-07-05). Verified against the Mira display plus a thumb-on-sensor test
(channel 5 rose 70.3→77.5 °F while warming the Mid wall sensor):

| channel | sensor | reading at test |
|---|---|---|
| 0 | Front zone air | 69.8 (Mira Front 69) |
| 1 | **Rear** zone air | 96.8 (Mira Rear 97) |
| 2 | Bay | 81.5 (Mira Bay 81) |
| 3 | disconnected | −88 °C |
| 4 | Floor | 70.2 (Mira Floor 70) |
| 5 | **Mid** zone air | thumb test |

The coach mapping joins channels 0/1/5 to the Front/Rear/Mid zones and 2/4 to
the Bay/Floor heat zones (status instances 5/6). A separate node at SA `0x75`
also broadcasts `1FF9C` instance 0x13 (~82 °F, tracks bay/outdoor-ish —
unidentified).

## Guardrail

Per ADR-0004, CoachIQ is API guardrails only; Firefly owns physical safety.
Lighting control is in scope; slides and locks are not.
