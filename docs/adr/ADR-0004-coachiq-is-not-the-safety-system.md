# ADR-0004: CoachIQ is API guardrails, not the vehicle safety system

## Status

**Accepted**, 2026-05-13. Canonizes the architectural framing that has
governed every PR in the 2026-05 audit cycle (and earlier) but lived
only in `/memories/repo/coachiq-architecture.md` and PR descriptions.

## Context

CoachIQ runs on a Raspberry Pi inside a 2021 Entegra Aspire 44R RV. It
talks to the **Firefly MIRA** multiplex panel over RV-C / J1939 CAN.

It is genuinely tempting to describe CoachIQ as a "vehicle safety
system" because:

- it has files named `safety_service.py`, `brake_safety_monitor.py`,
  `safety_state_engine.py`, `safety_interfaces.py`;
- it sends commands that affect physical hardware (lights, slides,
  awnings, leveling jacks);
- it has emergency-stop endpoints, watchdog timers, and interlock
  checks.

If we accepted that framing, the implication would be that we should
hold the codebase to aerospace / automotive-functional-safety
standards: ISO 26262, DO-178C, MC/DC coverage, formal verification,
SIL ratings, etc. None of that would be insane on its own merits --
but it would be wrong for *this project*.

Three facts make the framing different:

1. **Firefly MIRA is the OEM controller.** It owns physical control
   authority over every device on the bus and enforces the actual
   safety interlocks (slide-with-brake, leveling-while-moving,
   parking-brake-required-for-jacks). Firefly was built and certified
   by an OEM whose business depends on getting that right.

2. **CoachIQ talks *to* Firefly, not around it.** Architecturally
   CoachIQ plays the same role as a wall switch or a touchscreen HMI:
   it emits a well-formed RV-C frame; Firefly decides whether to act
   on it. If CoachIQ asks Firefly to extend the slide while the
   vehicle is moving, Firefly refuses. CoachIQ has no way to bypass
   Firefly because there is no other path to the hardware.

3. **The realistic threat model is API-side, not hardware-side.** An
   attacker who compromises CoachIQ can flood Firefly with valid CAN
   frames, exhaust authentication tokens, or scrape state from the
   web UI. They cannot directly release the parking brake or extend
   slides while moving, because Firefly's interlocks are not in
   CoachIQ's threat surface.

## Decision

CoachIQ is a **good consumer-grade backend** for a CAN-bus orchestration
layer. Calibrate every decision to that level, not to safety-critical
embedded systems.

In particular:

- **In scope** for this codebase:
  - Strict typing (pyright in basic mode is fine; strict eventually).
  - Reasonable test coverage on API guardrail paths (the audit-2026-05
    sweep landed at ~100% pass rate; coverage targets are ~70-80%).
  - JWT + CSRF + RBAC on every mutating endpoint.
  - Token-bucket rate limiting on outbound CAN TX (so a buggy loop
    cannot flood Firefly).
  - Pydantic-validated message factories; never hand-construct CAN
    payloads from user input.
  - Audit logging for every safety-relevant API action.
  - Bandit medium+ blocking on the entire project.

- **Out of scope** for this codebase:
  - DO-178C / IEC 61508 / ISO 26262 compliance.
  - Mutation testing, MC/DC coverage, formal methods.
  - Hardware-fault tolerance assumptions (CoachIQ failing -- crashing,
    losing power, getting unplugged -- is not a vehicle-safety event;
    the vehicle still works without us).
  - Anything that frames CoachIQ as the system of record for vehicle
    safety state.

The naming is unfortunate. Files like `safety_service.py` and
`brake_safety_monitor.py` describe **API guardrails** ("don't let the
API send commands that would be invalid or confusing for Firefly to
process"), not vehicle-safety primitives. The architecture-doc files,
the AGENTS.md / copilot-instructions.md files, and this ADR all repeat
that disclaimer because the names alone will keep tempting readers
toward the wrong framing.

## Consequences

### Becomes easier
- Onboarding humans and AI assistants -- they don't need to ramp on
  ISO 26262 to contribute.
- Saying no to over-engineering proposals (mutation testing,
  proof-carrying code, etc.) without long debate.
- Calibrating code review depth: a 20-line config refactor doesn't
  need the same scrutiny a 5-line CAN-message constructor does.

### Becomes harder
- This ADR has to be cited every time someone reads the safety_*
  filenames and assumes the wrong scope.
- If we ever ship CoachIQ on an RV without a Firefly (or with a
  different OEM controller, or without one at all), this ADR's
  assumptions break and we'd need to write a successor.

### Cannot do anymore
- Claim ISO 26262 / DO-178C compliance. We are not pursuing it.

## Alternatives considered

### Treat CoachIQ as safety-critical
Would require the standards listed above. Rejected because:
- Firefly already owns the safety case; duplicating it inside CoachIQ
  buys no real safety benefit.
- The certification cost (engineering hours, audits, formal-methods
  tooling) is wildly disproportionate to a personal-RV-control project.
- Firefly's certification status would be the binding factor anyway;
  CoachIQ being "more certified" than the device it talks to doesn't
  improve outcomes.

### Treat CoachIQ as a generic web app, drop the safety-* naming entirely
Considered but rejected:
- The naming reflects real intent: the rate-limiting, interlock checks,
  and emergency-stop paths are *defensive* code that exists because
  CAN commands have physical consequences. Removing the safety-*
  prefix would lose that signal.
- A single ADR (this one) clarifying the scope is cheaper than
  renaming dozens of files and re-training every contributor.

## See also

- `/memories/repo/coachiq-architecture.md` -- the agent-memory version
  of this decision (will be kept in sync with this ADR).
- `docs/safety.md` -- operational-safety policy that this ADR
  references.
- `backend/services/safety_service.py` -- the file with the most
  misleading name; read its module docstring for the per-file scope.
