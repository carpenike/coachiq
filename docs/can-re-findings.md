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

## Light command and status mapping (PARTIALLY RESOLVED)

**Evidence policy:** prose and commit messages are leads, not ground truth. A
coach-specific mapping is considered verified only when a retained raw capture
or a repeatable live test ties a named action to its command and status frames.
The standard RV-C specification establishes field meaning, but not which
instance belongs to which physical light on this coach.

Early standard-frame attempts failed and pointed at a proprietary dialect;
the real causes turned out to be mundane (full chain in the PR #185–#188
history): the payload byte layout was wrong, and — the biggest single cause —
**the CAN TX writer was never started** after the service-layer rebuild, so
commands built frames that nothing transmitted.

The implemented CoachIQ encoder uses this dialect:

- Frame `0x19FEDBF9` (DC_DIMMER_COMMAND_2, prio 6, SA `0xF9`), payload
  `[instance, 0xFF group, level 0-200, 0x00 set-level, 0xFF duration, 0x00,
  `0xFF, 0xFF]`. Unit tests pin this frame shape. The July 4 captures did not
  contain source `0xF9`, but live acceptance was subsequently wire-verified on
  July 15 as described below.
- The bedroom ceiling is wire-verified as multi-channel instances 25 (`0x19`)
  **and** 26 (`0x1A`). The command fans out to each (`command.instances` in the
  coach mapping).
- Bedroom Accent 27 (`0x1B`), Vanity 28 (`0x1C`), Mira `Bed OVHD` 29 (`0x1D`,
  represented as `bedroom_reading_light`), and Courtesy 38 (`0x26`) were each
  wire-verified on July 15. Non-bedroom light assignments remain provisional;
  they were carried forward from the June 2025 coach mapping and do not yet
  have retained per-light action captures.

### Live bedroom control acceptance — 2026-07-15

Dual-interface captures on the deployed coach established the sender and
acknowledgement chain:

- The Mira panel commands from source `0x95`; the physical bedroom wall panel
  commands from source `0x9A`; output status comes from module `0x8E`.
- CoachIQ source `0xF9` successfully commanded both bedroom-ceiling channels.
  Full On used raw level `0xC8` (200), 25% used `0x32` (50), and Off used
  `0x00`. Module `0x8E` acknowledged the same level for both instances.
- Canonical captures are under
  `/home/ryan/canre-captures/audit-2026-07-15/`:
  `bedroom-ceiling-coachiq-on-50-dedup-fix.candump`,
  `bedroom-ceiling-coachiq-slider-25-dedup-fix.candump`, and
  `bedroom-ceiling-coachiq-off-dedup-fix.candump`.
- A wall-panel Off capture exposed asynchronous bridged-interface ordering:
  dequeue-time timestamps could let an older On status overwrite a newer Off.
  The RX pipeline now preserves python-can receive timestamps and applies
  newest-wins ordering per entity, source DGN, and instance.

### Retained light evidence replay — 2026-07-10

The original JSONL captures remain on `nixpi` under
`/home/ryan/canre-captures/`. Replaying them through the current
`coachiq-can-re diff` tool established:

- `ceiling-on.jsonl` and the independent `ceiling-on2.jsonl` both show source
  `0xFC` send `DC_DIMMER_COMMAND_2` to instances `0x19` and `0x1A`; source
  `0x8E` reports `DC_DIMMER_STATUS_3` for the same instance within 1–2 ms and
  continues broadcasting the resulting nonzero levels.
- `ceiling-off.jsonl` shows the same two commands followed by status level 0
  for both channels.
- `ceiling-dim.jsonl` shows both status channels tracking changing levels,
  including the RV-C ramping sentinel `0xFB`.
- The idle captures show the G6's unrelated periodic instance set
  (`0x13`, `0x16`, `0x32`, `0xB5`–`0xBC`). Its presence does not invalidate
  event-driven status instances `0x19`/`0x1A`.

A live idle audit on 2026-07-10 found all 27 light entities still at their
startup seed timestamp while the periodic instance set continued on the bus.
That does not disprove the bedroom mapping, because its status is action-driven,
but it does mean CoachIQ has no authoritative state for a named light until a
mapped status frame appears. Every remaining light needs an individual
Off/On/dim capture before its mapping can be treated as fact.

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

**Heat modes (mapped live 2026-07-05 by cycling the Mira mode buttons):**
`operating_mode` (low nibble of byte 1): 0=off, 1=cool, **2=heat (drives the
rooftop HEAT PUMP on the main zones)**, 3=auto (a *setting* — the status
reports the resolved mode, so a heating zone still shows 2). fan_mode nibble:
0=auto, 1=on.

The coach has two independent heat sources per zone, and they can run
together:
- **Heat Pump** = the main zone's own instance in mode 2. All three main
  zones (Front/Mid/Rear) have a heat pump.
- **Aqua-Hot heat** = the counterpart zone in mode 2 — **inst 3 = Front,
  inst 4 = Rear** (Mid has no Aqua-Hot), plus inst 5 = Bay, 6 = Floor. These
  are the `climate_*_heat` entities. Pressing "Aqua-Hot" for Front lit inst 3
  while Front's own inst 0 stayed in heat-pump mode 2 — confirming they're
  separate, stackable sources.

So heat-pump control needs no new code (the "heat" command already sends
mode 2, the exact frame the Mira emits), and Aqua-Hot heat is the existing
counterpart-zone cards.

**Mode-selector mechanics confirmed live (2026-07-05, watching inst 0 + 3 on
Front while cycling the Mira).** The Mira's per-zone selector is really *two*
independent controls, which is why the UI now folds them into one card:
- The **rooftop unit** has one **exclusive** mode on the zone's own instance —
  Off (0) / Cool (1) / Heat Pump (2) / Auto (3). Cool and Heat Pump are
  mutually exclusive (same compressor).
- **Aqua-Hot** is an **independent toggle** on the counterpart instance (Front
  inst 3 / Rear inst 4), mode 2 on / 0 off. It stayed at mode 2 while inst 0
  was cycled Cool→Heat Pump→Auto — it does *not* follow the rooftop mode. Both
  share the zone's single setpoint (the G6 keeps the counterpart's heat
  setpoint synced to the main zone).
- The captured baseline (Front reading `00 10 …` / `03 02 …`) was the exact
  "No Aqua-Hot Source!" state from the owner screenshot: rooftop **off**,
  Aqua-Hot loop calling (inst 3 mode 2) but **neither** burner nor electric
  element energized. The Mira shows that warning whenever a loop is in Aqua-Hot
  heat with no source on; CoachIQ reproduces it per zone.

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

## Aqua-Hot electric/burner = energy-managed AC loads — 2026-07-05

The Aqua-Hot's electric element and diesel burner are **not** controlled by
`WATERHEATER_COMMAND` (`1FFF6`) — a spec-correct `1FFF6` frame from CoachIQ
transmitted and was ignored (`operating_mode` stayed put). An idle-vs-toggle
diff of a Mira press showed they're **generic AC loads** the G6 manages:

- `AC_LOAD_COMMAND` (`1FFBE`) drives them, byte 2 = level (`0xC8` on, `0x00`
  off). Instances: **`0xD4` (212) = electric element**, **`0xD2` (210) =
  burner** (confirmed by toggling each on the Mira and watching that
  instance flip + `WATERHEATER_STATUS.operating_mode` bit 0x2 electric /
  0x1 burner).
- Honored from our SA `0xF9` and it **latches** (a single OFF stayed off 10 s
  untouched). No impersonation, no continuous-master fight for OFF.

**Load shed.** These are *deferrable* loads. Turning one ON is a **request**;
the energy manager grants it only when the power budget allows and sheds it
under AC load (the Mira shows "Aqua-Hot Electric: Shed"). Shed is broadcast:
`AC_LOAD_STATUS` (`1FFBF`) byte 2 (operating level) reads **`0xC8` energized /
`0x00` off / `0xFD` shed** (`0xFC` = "load delay active", the transient
variant) — verified against the Mira's shed display. So the UI shows the
requested state on the toggle plus a "Shed" badge when byte 2 is a shed
sentinel, exactly like the Mira.

Modeled as a reusable **`ac_load`** device type (control `1FFBE`, status
`1FFBF` → on/off/shed).

**The rooftop AC compressors shed the same way** (2026-07-05). Under forced
demand (all zones commanded to 60 °F + Aqua-Hot loaded) the Front and Mid
compressors appear as AC loads and one was caught at `FD`. Mapped by
disabling each zone and watching which AC unit + load dropped (turning a load
off is immediate; forcing one ON hits the compressors' ~3 min anti-short-cycle
lockout, so only the disable direction is reliable):

- **Front (zone 0) = AC unit inst1 (SA98) = load `D5` (213)**
- **Mid (zone 1) = AC unit inst2 (SA97) = load `D0` (208)**
- **Rear (zone 2) = AC unit inst3 (SA96) = NOT load-managed** — never appears
  as a managed AC load across any capture (bedroom, ambient ~97 °F, always
  demanding, never a shed candidate).

The Front/Mid climate zones source `1FFBF` D5/D0 so the zone card shows "Shed"
(status `0xFD`) exactly like the Mira. Zone → unit mapping is via the AC
*load*, not a fixed zone↔unit binding; the manager pools compressors, so map
by the disable test, not by assuming zone N = unit N. (Front & Rear have heat
pumps, Mid does not — per the owner.)

### Climate/Victron consistency audit — 2026-07-10

A live audit was triggered when Victron showed about 1.6 kW of AC output while
the Climate page labeled all rooftop zones Off. The coach mapping and deployed
Nix package were byte-for-byte identical. The wire showed the mapping itself
was correct:

- `THERMOSTAT_STATUS_1` instance 1 (Mid) reported mode 1 (Cool), 100% fan, and
  a 69.5 °F setpoint.
- `AIR_CONDITIONER_STATUS` instance 2 from SA `0x97` reported 100% fan and 100%
  compressor output.
- `AC_LOAD_STATUS` instance `D0` reported `0xC8` (energized).
- Victron reported 1,625 W AC output (1,462 W L1 + 163 W L2).

The display bug was a composite-state field collision. `climate_mid` merges
thermostat status, ambient channel 5, and AC load `D0`; both thermostat status
and AC load status define a generic `operating_mode` field. The later load
frame's value 0 (Automatic load management) overwrote thermostat mode 1
(Cool). Auxiliary source `instance` fields similarly replaced the canonical
thermostat instance.

The RX merge now keeps thermostat fields canonical, exposes the sensor source
as `ambient_instance`, namespaces AC-load fields as `load_*`, and derives
`shed` from `load_operating_status`. A running compressor therefore remains
Cool while retaining the independent energy-management status.

## Guardrail

Per ADR-0004, CoachIQ is API guardrails only; Firefly owns physical safety.
Lighting and climate control are in scope; slides and locks are not. The
Aqua-Hot burner is a diesel flame the Aqua-Hot's own controller supervises —
CoachIQ only requests the load; the UI gates lighting it behind a confirm.
