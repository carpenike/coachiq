# Architecture Decision Records

This directory holds **Architecture Decision Records (ADRs)** for CoachIQ.
An ADR captures *one* meaningful architectural choice along with the
context that led to it, the alternatives considered, and the
consequences of the decision.

## When to write a new ADR

Write an ADR when you are about to commit to a decision that:

- Will be hard to reverse later (database engine, framework, transport,
  auth model).
- Constrains future code (an API contract, a service boundary, a
  threat-model assumption).
- Repeatedly comes up in code review or onboarding ("why don't we do
  X instead?").

You probably **don't** need an ADR for:

- Routine refactors (move a function, rename a class).
- Bug fixes -- those go in commit messages and PR descriptions.
- Implementation details that one well-commented module captures
  better than a separate doc.

## Format

Each ADR is a single markdown file with a numeric prefix:
`ADR-NNNN-short-kebab-case-title.md`. Use the next available number.

Each ADR has these sections:

1. **Status** -- one of `Proposed`, `Accepted`, `Superseded by ADR-NNNN`,
   `Deprecated`. Include a date.
2. **Context** -- what's the situation that forced a decision?
3. **Decision** -- what did we choose? State it as an imperative.
4. **Consequences** -- what becomes easier? Harder? What can we no
   longer do?
5. **Alternatives considered** -- briefly note the options you
   evaluated and why you didn't pick them. Future readers will ask;
   answer up front.

Keep ADRs short -- 50-150 lines is typical. If you find yourself writing
500 lines of architecture, that's a *spec*, not an ADR; put it in
`docs/specs/` and have the ADR link to it.

## Existing ADRs

- [ADR-0001](ADR-0001-fastapi-depends-over-di-framework.md) -- Use
  FastAPI's native `Depends(...)` over an external DI framework.
- [ADR-0002](ADR-0002-can-facade-pattern.md) -- Single `CANFacade` as
  the only entry point for CAN operations.
- [ADR-0003](ADR-0003-api-v2-only-no-legacy.md) -- New endpoints land
  under `/api/v2/*`; legacy `/api/*` routes are retired, not parallel-
  maintained.
- [ADR-0004](ADR-0004-coachiq-is-not-the-safety-system.md) -- CoachIQ
  is API guardrails for an OEM controller, not the vehicle safety
  system itself. **Read this first.**
- [ADR-0005](ADR-0005-http-error-response-envelope.md) -- HTTP error
  responses include both `detail` (FastAPI-default) and `error.{code,
  message}` (structured) for backward-compatibility with both contracts.

## Status

Started 2026-05-13. The first four ADRs canonize decisions that were
already in effect but lived only in commit messages, in-line comments,
or agent memory. They are recorded retroactively.
