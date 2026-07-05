# CAN reverse-engineering findings (2021 Entegra Aspire 44R)

The living map of this coach's CAN bus: who talks, which DGNs carry what, and
which command dialects the Firefly system honors — all verified on the wire.
Tooling to reproduce and extend this lives in
[`dev_tools/can_re/`](../dev_tools/can_re/README.md).

**Status (2026-07-05):** RX and TX both proven end to end. CoachIQ controls
**lights** (DC_DIMMER_COMMAND_2 with the payload dialect below) and **climate**
(standard THERMOSTAT_COMMAND_1) from SA `0xF9`, with the G6 echoing commanded
state in its next status broadcast. The idle-vs-action capture diff remains
the method for mapping anything new (awnings, generator, Aqua-Hot commands).

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

## The light command dialect (RESOLVED 2026-07-04)

Early standard-frame attempts failed and pointed at a proprietary dialect;
the real causes turned out to be mundane (full chain in the PR #185–#188
history): the payload byte layout was wrong, and — the biggest single cause —
**the CAN TX writer was never started** after the service-layer rebuild, so
commands built frames that nothing transmitted.

The working dialect, verified by DC_DIMMER_STATUS_3 echoing commanded levels:

- Frame `0x19FEDBF9` (DC_DIMMER_COMMAND_2, prio 6, SA `0xF9`), payload
  `[instance, 0xFF group, level 0-200, 0x00 set-level, 0xFF duration, 0x00,
  0xFF, 0xFF]`.
- The mapping's instances (25/`0x19` etc.) were CORRECT; the instance set the
  G6 cycles in its own ~2 Hz re-broadcasts is unrelated to what the modules
  accept from other senders.
- Some lights are multi-channel (bedroom ceiling = instances 25 **and** 26);
  the command fans out to each (`command.instances` in the coach mapping).

## The method: idle vs. action capture diffs

Whatever a Vegatouch Mira button toggles is, by definition, the command the
Firefly system honors — and whatever changes on the panel shows up as a
status delta. This cracked both lights and climate, and is the template for
anything new (awnings, generator, Aqua-Hot burner/electric):

```
coachiq-can-re capture --iface can1 --seconds 10 --label idle   --out captures/idle.jsonl
coachiq-can-re capture --iface can1 --seconds 10 --label action --out captures/action.jsonl   # press the button now
coachiq-can-re diff captures/idle.jsonl captures/action.jsonl --noise captures/idle2.jsonl
```

A live `candump -ta can1,<id>:<mask>` watch during single presses is even
better for instance identification — that is how the thermostat zone order,
the ambient sensor channels, and the Bay/Floor zones were pinned.

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

## rvc.json spec audit — 2026-07-05

Historic trust level: parts of the file were generated rather than
transcribed, so unverified entries were **claims, not facts** — that is what
produced the THERMOSTAT_AMBIENT_STATUS fabricated layout, the wrong
THERMOSTAT_COMMAND_1 PGN, and the `UNKNOWN_*` shadowing that blanked every
climate temperature in production. The debt is now paid down:

`config/rvc.json` had systematically unreliable, LLM-fabricated entries (the
root cause of the THERMOSTAT_AMBIENT_STATUS and THERMOSTAT_COMMAND_1 bugs in
PRs #190/#191). Every entry was audited against the official RV-C 2023-11 spec
(`resources/rvc-2023-11_chunks.json`) and a 20 s live census on nixpi `can1`.
Invariants are now pinned by `tests/integrations/rvc/test_rvc_spec_config.py`,
and the loader warns on duplicate DGN keys instead of silently shadowing.

Key findings, wire-confirmed by the census:

- **Two diagnostic dialects coexist.** J1939 DM1 (PGN `FECA`) heartbeats come
  from a dozen-plus nodes (SAs `0x8E–0x9F`, `0xAF`, `0xFC`); RV-C DM_RV
  (DGN `1FECA`) comes from the ATS (`0x4F`) and `0x9F`. The spec file now has
  separate `J1939_DM1` / `DM_RV` entries and `_process_diagnostic_frame`
  accepts both PGNs. Both dialects put FMI in byte 4 bits 0–4 and the SPN top
  bits in 5–7 — the old entry had them swapped, so real fault SPNs decoded
  wrong (the all-FF "clear" heartbeat masked the bug).
- **SA `0x9F` is a J1939 chassis gateway.** Its `FECA`/`FEFC`/`FEF5` frames
  had been dressed up as RV-C `DM_RV`/`FLOOR_HEAT_STATUS`/
  `THERMOSTAT_SCHEDULE_COMMAND_1`. They are DM1, Dash Display, and Ambient
  Conditions; now quarantined as `UNKNOWN_18xxxx9F` entries.
- **`1D7EFExx` (SAs `0x96–0x9E`) is the RV-C Virtual TERMINAL** (DGN
  `17E00` + destination, Sec. 6.2.3) — the three "PRODUCT_ID /
  FIRMWARE_VERSION / TERMINAL" entries were all this one PGN. Real RV-C
  PRODUCT_ID is `FEEB` (Sec. 3.2.8), same DGN and payload as the J1939
  Component ID the BAM handler already records.
- **`19FFFF9C` is DATE_TIME_STATUS (`1FFFF`), `19FFFE75` is
  SET_DATE_TIME_COMMAND (`1FFFE`)** — both were misnamed; the fabricated
  duplicates at `18CFC`/`1F33D` are gone.
- **Generator DGNs corrected before start/stop lands:** command `1FFDA`
  (single command byte: 0 stop / 1 start / 2 prime — the old entry had an
  invented leading instance byte), status2 `1FFDB` (layout rebuilt from Table
  6.18.24b), demand command `1FEFF`. GENERATOR_STATUS_1 (`1FFDC`, live from
  `0x9C`) gained its Table 5.3 scales.
- **`1FACE`, `1FACF`, `15FCE`, `1AAFD`, `1FED9`, `1FBDA` are not in RV-C
  2023-11** — proprietary Firefly-range traffic from the G6, quarantined as
  `UNKNOWN_*`. `WEATHER_WIND_STATUS` (`1F65B`) never existed anywhere and was
  deleted.
- Table 5.3 scales added to the 16-bit temperatures in `FLOOR_HEAT_STATUS`
  (rebuilt at its real DGN `1FEFC`) and `DC_SOURCE_STATUS_2` (real DGN
  `1FFFC`, was garbage `21604`).

Convention going forward: entries not yet seen on the wire carry a
`Spec-canonical entry; not observed …` note and a placeholder source address
`0xFE` in their `id`; quarantined mystery frames are named
`UNKNOWN_<captured arbitration id>` with raw byte signals. Before building on
a `not observed` entry, verify it against the official RV-C PDF or a live
capture.

## Guardrail

Per ADR-0004, CoachIQ is API guardrails only; Firefly owns physical safety.
Lighting control is in scope; slides and locks are not.
