---
mode: "agent"
description: "A1 \u2014 Drop ISO 26262 / safety-critical framing from code docstrings and comments"
---

# A1 \u2014 Drop ISO 26262 / safety-critical framing from code

Audit cycle: 2026-05-13 architectural audit (see
`architectural-audit-2026-05-13-overview.prompt.md`).

## Why

`docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md` and the
`coachiq-architecture.md` memory file both establish that CoachIQ is
**not** a safety-critical system. The OEM Firefly MIRA panel owns the
vehicle safety case. CoachIQ is API guardrails / a smart HMI panel.

The code itself, however, still claims otherwise in many places:

- `backend/services/safety_service.py:1-7` header: *"Implements ISO 26262-inspired safety patterns..."*
- `backend/core/dependencies.py:294` `get_safety_service` docstring: *"This service provides ISO 26262-compliant safety monitoring..."*
- Various `Safety*` enums and `SafetyClassification.CRITICAL` usages
  treat startup-priority as if it were a hazard classification.

New contributors read code before memory files. This is a docstring
sweep to bring the code in line with ADR-0004.

## Scope (PR A1 only)

**In scope** (this PR):

- Replace "ISO 26262", "safety-critical", "ISO 26262-compliant",
  "ISO 26262-inspired", "DO-178C", "MC/DC", "SIL" mentions in
  `backend/**/*.py` docstrings and comments with accurate language.
- Add a one-line link to `docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md`
  in the most prominent docstrings (`safety_service.py`,
  `safety_registry.py`, `safety_interfaces.py`,
  `dependencies.py::get_safety_service`).
- Update the `SafetyClassification` enum docstring to clarify it
  means "startup criticality / restart policy", not "vehicle safety".

**Out of scope** (other PRs handle):

- Renaming files or classes (`SafetyClassification` -> `StartupCriticality`)
  \u2014 see PR A2 / structural follow-ups.
- Deleting dead modules (`brake_safety_monitor.py`) \u2014 PR A2.
- Changing `SafetyServiceRegistry` into a tag on the regular registry \u2014 PR A3 follow-up.

## Concrete substitutions

Replace, with judgement (don't blindly sed):

| Old | New |
|---|---|
| "ISO 26262-compliant safety monitoring" | "command-validation guardrails (see ADR-0004)" |
| "ISO 26262-inspired safety patterns" | "defense-in-depth API guardrail patterns (see ADR-0004)" |
| "safety-critical operations" | "command-validation operations" or "interlock-protected operations" |
| "vehicle safety system" | "API command validator" |
| "emergency stop" | keep \u2014 it's a real feature (refuses to forward commands) |
| "watchdog" | keep \u2014 it's a real feature |

Where docstrings claim emergency-stop or interlock behavior, keep the
description but reframe: it's about **refusing to forward CAN frames
to Firefly**, not about physical safety actuators.

## Files in scope (start here)

```bash
grep -rln "ISO 26262\|ISO-26262\|DO-178\|safety-critical\|MC/DC\|SIL " backend/ --include="*.py"
```

Expect ~10\u201320 files. Edit each one in place. Keep diffs surgical \u2014
don't reflow whole comment blocks.

## Acceptance criteria

- `grep -rn "ISO 26262\|ISO-26262\|DO-178" backend/ --include="*.py"` returns nothing.
- `grep -rn "safety-critical" backend/ --include="*.py"` either returns nothing or
  every remaining hit is followed by a link/comment to ADR-0004 explaining
  the term is being used loosely.
- `nix run .#ci` (or `Dev: Run Tests (Quick)` + `Dev: Lint Backend (Quick)`)
  passes with the existing baselines.
- No behavior change. Test count must not move.

## Stop-and-ask if

- You find a docstring that describes actual physical-safety behavior
  beyond "we refuse to forward this CAN frame". That implies the file
  is doing more than guardrails and the rename isn't safe \u2014 escalate
  before changing.
- You find external API responses (JSON payloads, OpenAPI descriptions)
  that include "ISO 26262". Those are public-facing contracts; rename
  needs an API version bump conversation.
