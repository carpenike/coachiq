---
mode: "agent"
description: "A2 \u2014 Delete dead brake_safety_monitor.py and audit safety_state_engine.py"
---

# A2 \u2014 Delete dead `brake_safety_monitor.py`, audit `safety_state_engine.py`

Audit cycle: 2026-05-13 architectural audit (see overview prompt).

## Why

The audit (2026-05-13) measured zero in-repo consumers for
`backend/services/brake_safety_monitor.py` (311 LOC) and a single
consumer for `backend/core/safety_state_engine.py` (299 LOC) \u2014
`backend/integrations/can/protocol_router.py`.

This is the same pattern as PR #109 (`backend/core/state.py`) and
PR #139 (`backend/core/services.py` + `core_services_removal.py`):
WIP scaffolding that never landed in a live code path. Memory file
[audit-2026-05-12.md](../../memories/repo/audit-2026-05-12.md) has
the cleanup recipe under "PR #139 capstone cleanup".

## The job

1. **Delete `backend/services/brake_safety_monitor.py` outright** if
   the consumer audit is still clean.
2. **Audit `backend/core/safety_state_engine.py`**: read the one
   call site (`protocol_router.py`) end-to-end. Decide between:
   - **Keep** \u2014 it's actually wired and the audit miscounted; document
     in `coachiq-state.md` that this is live.
   - **Delete + rip out the protocol_router call** \u2014 if the call site
     is itself unreachable or stub-grade.
3. Delete any tests that exclusively exercise the deleted modules
   (apply the PR #109 lesson: a passing test on dead code is fake green).

## Verification commands

```bash
# Should return only the file itself
grep -rln "brake_safety_monitor\|BrakeSafetyMonitor" backend/ --include="*.py" | grep -v __pycache__

# Should show 1 consumer + the file itself
grep -rln "safety_state_engine\|SafetyStateEngine" backend/ --include="*.py" | grep -v __pycache__

# Read the consumer end-to-end before deciding
sed -n '1,200p' backend/integrations/can/protocol_router.py
```

## Acceptance criteria

- `brake_safety_monitor.py` is deleted (or the PR explains why
  `git log` since the audit revealed live consumers).
- `safety_state_engine.py` either deleted or explicitly classified
  as live with a docstring update + memory-file note.
- Test count change is **non-positive** (some dead-code tests may go;
  the PR description must enumerate any drops, per the PR #109 lesson).
- Pyright baseline (`EXPECTED_PYRIGHT_ERRORS` in
  `scripts/ci-quality-gate.sh`) ratcheted DOWN if the deletion shed
  errors. CI's hardened ratchet (PR #117) will force this.
- LOC delta is recorded in the PR description.

## Stop-and-ask if

- The single consumer of `safety_state_engine.py` is on a code path
  that *should* be reachable but isn't because of a registration bug.
  That's a real-bug discovery and deserves its own PR (deferred-work
  pattern from PR #129 \u2192 PR #140).
- You find that `brake_safety_monitor.py` is referenced from a
  string lookup (e.g. `service_registry.get_service("brake_safety_monitor")`).
  String references don't show up in the symbol grep. Search for the
  string literal too, before deleting.

## Memory updates

After landing, update `/memories/repo/audit-2026-05-12.md` (or the new
`audit-2026-05-13.md` if started by then) with:

- Files deleted, LOC delta.
- Whether the safety_state_engine investigation found a real bug
  (deferred-work item) or just dead code.
