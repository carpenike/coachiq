# ADR-0003: New endpoints land under `/api/v2/*`; legacy `/api/*` is retired, not parallel-maintained

## Status

**Accepted**, 2026-05-13. Codifies the practice that has governed
several recent PRs (notably #126 retiring `/api/entities`, #124
retiring `/api/missing-dgns`, and the contract-test rewrite in #130).

### Status update (pre-1.0)

[ADR-0010](ADR-0010-pre-1.0-no-backward-compat.md) relaxes this ADR's
incremental-retirement pacing until the 1.0 / first public release. Pre-1.0,
legacy `/api/*` routers with v2 equivalents may be retired decisively and in
bulk once the v2 replacement covers the capability, this repo's own callers are
updated, and tests pass. The original v2-only decision remains in force; only
backward-compatibility-driven caution around retirement pacing is superseded by
ADR-0010.

## Context

The backend has historically grown two API namespaces:

- **Legacy `/api/*`** routers under `backend/api/routers/`: organic
  growth, often with response shapes that match what the original
  caller needed rather than a coherent design.
- **Domain API `/api/v2/*`** under `backend/api/domains/`: built later
  with explicit Pydantic schemas (`EntitySchemaV2`,
  `EntityCollectionV2`, etc.), bulk-operation support, and a
  consistent error envelope.

When v2 was introduced (somewhere around mid-2025) the temptation was
to maintain v1 indefinitely "for backward compatibility". For an
internal-only API on a single-tenant device, that's a very expensive
courtesy.

The 2026-05 audit cycle surfaced multiple test failures that traced
back to v1 endpoints being silently retired without anyone updating
the corresponding tests. The contract tests in
`tests/contract/test_domain_api_spec_validation.py` failed because
they asserted `/api/entities` was reachable; PR #130 had to rewrite
them to assert `/api/v2/entities` instead.

## Decision

**New endpoints land under `/api/v2/*`.** Legacy `/api/*` endpoints
are either:

1. **Kept as-is** if they still have callers and there's no v2
   replacement (auth, health, schemas, CAN tools, etc.).
2. **Retired** if they have a v2 replacement that fully covers them
   (entities, missing-dgns).

We do **not** parallel-maintain v1 + v2 for the same capability. When
v2 is good enough to replace a v1 endpoint, the v1 endpoint is
deleted in the same PR (or the immediately-following one, depending
on coordination cost), not deprecated and left in place.

Domain v2 routers are mounted **unconditionally** by
`register_all_domain_routers` in `backend/api/domains/__init__.py`.
There are no feature flags around v2 endpoints.

## Consequences

### Becomes easier
- **Cognitive load**: one path per capability. No "should I use
  `/api/entities` or `/api/v2/entities`?" judgment call.
- **Test maintenance**: tests assert against one API, not two. The
  PR #130 cleanup removed an entire fallback-and-retry pattern from
  the contract tests.
- **Schema generation**: OpenAPI / Zod export is unambiguous about
  which schemas are current.
- **Audit trail**: when a legacy endpoint is retired, it's a single
  PR with the deletion + the test rewrites visible together.

### Becomes harder
- **Frontend coordination**: any frontend code calling a legacy path
  has to be updated in the same PR or immediately after. So far this
  has been single-developer manageable; with multiple frontend
  contributors this would need a flag-day or a brief deprecation
  window.
- **Out-of-tree consumers**: there aren't any (CoachIQ is a
  single-tenant device), so this isn't actually a cost. If we ever
  publish CoachIQ as a service that other people integrate with,
  this ADR's premise breaks and we'd need a real deprecation policy.

### Cannot do anymore
- Add a new feature to a legacy endpoint. New features go in v2.
- Maintain two parallel implementations for "compatibility" reasons.

## Alternatives considered

### Keep v1 forever, build v2 alongside
Standard "API versioning best practice" for public APIs. Rejected
because:
- CoachIQ is internal to a single device. There are no third-party
  integrators paying the migration cost.
- Maintaining two implementations doubles the testing surface and
  invites them to drift (which is exactly what happened pre-2026-05).
- The "compatibility" benefit is hypothetical; the cost is real.

### Use API gateway / proxy to translate v1 → v2
Considered briefly. Rejected because adding a translation layer
adds a new failure mode (translation bugs) and would require
maintaining mapping rules indefinitely.

### `/api/v2/*` mounted only when a feature flag is set
Was actually how it started. Removed because:
- Every consumer either always wants v2 or never wants v2; there's
  no scenario where you want it sometimes.
- Feature-flagging adds a runtime branch that has to be tested,
  documented, and explained to readers, for zero practical benefit.
- Aligns with [ADR-0001](ADR-0001-fastapi-depends-over-di-framework.md)'s
  preference for "everything is wired explicitly in `main.py` /
  `router_config.py`" over "configuration-driven optionality".

## Revisit conditions

Reconsider this decision if:

- CoachIQ ever ships a public API that third parties consume.
- We adopt a deprecation cycle (e.g. announce-now, remove-in-6-months)
  for any reason.
- Frontend coordination becomes a bottleneck (e.g. team grows enough
  that "delete v1 in the same PR as the v2 frontend update" stops
  scaling).

## See also

- `backend/api/routers/` -- legacy /api/* routers (still active).
- `backend/api/domains/` -- v2 domain routers.
- `backend/api/domains/__init__.py` --
  `register_all_domain_routers`, mounted unconditionally.
- `tests/contract/test_domain_api_spec_validation.py` -- contract
  tests asserting v2-only after PR #130's rewrite.
- PR #126 (legacy /api/entities retirement) and PR #124 (legacy
  /api/missing-dgns retirement) for the canonical "retirement"
  pattern.
