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
  under `/api/v1/*`; legacy `/api/*` routes are retired, not parallel-
  maintained.
- [ADR-0004](ADR-0004-coachiq-is-not-the-safety-system.md) -- CoachIQ
  is API guardrails for an OEM controller, not the vehicle safety
  system itself. **Read this first.**
- [ADR-0005](ADR-0005-http-error-response-envelope.md) -- HTTP error
  responses include both `detail` (FastAPI-default) and `error.{code,
  message}` (structured) for backward-compatibility with both contracts.
- [ADR-0006](ADR-0006-typed-dependency-injection.md) -- Type the
  FastAPI dependency-injection aliases in `backend/core/dependencies.py`
  with concrete service classes; keep the string-keyed runtime
  registry. Migration is incremental, one service cluster per sub-PR.
- [ADR-0007](ADR-0007-auth-service-namespace.md) -- Consolidate the
  four `backend/services/auth_*.py` files into a single
  `backend/services/auth/` package, split `auth_services.py` per
  class, and keep `AuthManager` (policy engine) and `AuthService`
  (request-time facade) intentionally separate.
- [ADR-0008](ADR-0008-rvc-config-facade-naming.md) -- Rename
  `ConfigService` -> `RVCConfigFacade` and `ConfigurationService` ->
  `RVCSpecLoader` so the three "configuration" tiers (Pydantic
  `Settings`, RV-C metadata facade, RV-C spec-file loader) have
  distinct names.
- [ADR-0009](ADR-0009-nix-module-hybrid-options.md) -- Keep the
  `services.coachiq` NixOS module surface small and typed, with
  long-tail configuration passed through environment variables.
- [ADR-0010](ADR-0010-pre-1.0-no-backward-compat.md) -- Carry no
  backward-compatibility obligation before 1.0; retire legacy surfaces
  decisively once replacements, in-repo callers, and tests are covered.
- [ADR-0011](ADR-0011-public-api-v1-naming.md) -- Launch the public
  Domain API at `/api/v1/*`; retire the internal v2 migration label
  before 1.0 while keeping URL versioning.
- [ADR-0012](ADR-0012-knowledge-maintenance-subsystem-boundary.md) -- Keep
  Knowledge & Maintenance as a separate offline-first bounded context and
  use sqlite-vec as its proven local vector substrate.
- [ADR-0013](ADR-0013-auth-oidc-mcp-as-architecture.md) -- Add PocketID OIDC
  login as an additive local-session path and embed a conformant MCP OAuth AS
  for `/api/mcp`.

## Status

Started 2026-05-13. The first four ADRs canonize decisions that were
already in effect but lived only in commit messages, in-line comments,
or agent memory. They are recorded retroactively.
