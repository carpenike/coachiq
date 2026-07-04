# CAN reverse-engineering toolkit

Standalone capture / census / diff tools for reverse-engineering the coach's
CAN traffic — built to crack the **Firefly G6 command dialect** that standard
RV-C `DC_DIMMER_COMMAND_2` frames do not drive (see
[`docs/can-re-findings.md`](../../docs/can-re-findings.md)).

These talk to SocketCAN directly via `candump`/`cansend`. They need **no**
running CoachIQ app and **no** auth, so you can run them from the coach while
pressing physical Vegatouch Mira buttons. Capture files are JSONL in the same
field shape as the app's in-recorder `RecordedMessage`, so they interoperate.

## Two ways to run

**On the coach (packaged):** the Nix package ships a `coachiq-can-re` command on
the system `PATH`, wrapped with `can-utils` and pointed at the packaged RV-C
spec. Prefer this on the Pi — it is version-matched to the running backend:

```bash
coachiq-can-re capture --iface can1 --seconds 10 --label idle --out idle.jsonl
coachiq-can-re census idle.jsonl
coachiq-can-re diff idle.jsonl action.jsonl --noise idle2.jsonl
```

**From a checkout (dev):** the equivalent `python -m dev_tools.can_re.<tool>`
module CLIs behave identically. The examples below use the module form; swap in
`coachiq-can-re <subcommand>` on the coach.

## The workflow that cracks a control frame

The whole point: **diff what's on the bus when idle vs. while you press a
button.** Whatever a Mira button toggles shows up as the delta.

On the coach (SSH to the Pi, or a terminal in the RV):

```bash
cd <repo>            # wherever the coachiq checkout lives on the Pi
                     # (or copy dev_tools/ + config/rvc.json next to each other)

# 1. Two baselines back-to-back, nothing touched. The second is a "noise
#    floor" that cancels the bus's normal churn (clocks, slow status frames).
python -m dev_tools.can_re.capture --iface can1 --seconds 10 --label idle  --out captures/idle.jsonl
python -m dev_tools.can_re.capture --iface can1 --seconds 10 --label idle2 --out captures/idle2.jsonl

# 2. Action: start this, then press "bedroom ceiling ON" on the Mira panel
#    once, within the 10-second window.
python -m dev_tools.can_re.capture --iface can1 --seconds 10 \
    --label bedroom-ceiling-on --out captures/bedroom-ceiling-on.jsonl

# 3. Diff, with the noise floor subtracted. The ranked "CHANGED payloads" list
#    floats the most likely command frame to the top.
python -m dev_tools.can_re.diff captures/idle.jsonl captures/bedroom-ceiling-on.jsonl \
    --noise captures/idle2.jsonl
```

Reading the output:

- **`CHANGED payloads`** is where the answer usually is — look for a dimmer
  status/command byte or a proprietary `SA 9C` frame that flips with the press.
- **Ignore `NEW frame types` that are `GENERIC_CONFIGURATION_STATUS` or other
  slow status frames** — those are periodics that a short window samples
  unevenly, not your button.
- **Run step 2/3 two or three times.** The change that shows up *every* time you
  press is the signal; one-off flickers are noise. Longer captures (`--seconds
  15`) also help.

Repeat for OFF, dim up/down, and a couple of different lights. The frame + byte
that consistently tracks the action **is** the command the Firefly system uses.
Send me the `captures/*.jsonl` files (or just the diff output) and that's enough
to implement the encoder.

Tip: `can0` and `can1` are bridged on this coach, so either interface sees the
same traffic — `can1` is fine.

## Commands

| Command | What it does |
|---|---|
| `python -m dev_tools.can_re.capture --iface can1 --seconds N --label L --out F.jsonl` | Record N seconds to a labeled JSONL capture. |
| `python -m dev_tools.can_re.census F.jsonl` | Inventory a capture: per-(PGN,SA) counts/rates, standard vs proprietary, RV-C names, dimmer instance breakdown. |
| `python -m dev_tools.can_re.diff idle.jsonl action.jsonl` | Surface NEW / GONE frame types and per-byte payload changes between two captures, ranked by likely control signal. |

`census` and `diff` also read plain `candump -ta` logs, so an ad-hoc
`candump -ta can1 > f.txt` works as input too.

## Layout

- `canframe.py` — frame parsing, J1939/RV-C arbitration-id decomposition, RV-C
  naming from `config/rvc.json`. Pure functions; unit-tested.
- `loader.py` — read capture JSONL (or raw candump logs) into frames.
- `capture.py` / `census.py` / `diff.py` — the three CLIs.
- `tests/` — `pytest -m unit` over the decomposition, parsing, census, and diff.
