# ADR-0011: Public API launches at `/api/v1`

## Status

**Accepted**, 2026-06-29. Applies before the 1.0 / first public release.

## Context

CoachIQ historically used a v2-prefixed path for the Domain API to distinguish
the new domain routers from the older unversioned `/api/*` routers. That label was an
internal migration marker, not a public version contract: CoachIQ has not shipped
a public release, and no external consumer has seen a `/api/v1/*` contract.

Launching the public API with the old v2 migration label would make the first
public version look like a second public contract.
[ADR-0010](ADR-0010-pre-1.0-no-backward-compat.md) is the zero-coordination
window to correct that naming before external consumers exist.

## Decision

The public Domain API launches under `/api/v1/*`.

The old v2 migration label is retired from the served API surface and current
public documentation. Domain routers keep URL versioning; they do not collapse
to unversioned `/api/*` routes. Legacy unversioned routers remain on their own
retirement track under [ADR-0003](ADR-0003-api-v2-only-no-legacy.md) and related
handoffs.

This ADR supersedes ADR-0003's naming only. ADR-0003's architectural decision
still holds: new development uses the domain API surface, and legacy `/api/*`
routes are retired rather than parallel-maintained once their replacements,
in-repo callers, and tests are covered.

## Consequences

### Becomes easier

- The first public API version has the expected `/api/v1/*` shape.
- OpenAPI paths, frontend clients, tests, deployment examples, and current docs
  describe one coherent launch namespace.
- Future deprecation policy can start from a real public v1 contract at 1.0.

### Becomes harder

- Historical references to the internal v2 migration label must be read with
  the ADR-0011 status note in mind.
- Any in-repo path literal, generated type, or deployment rule that referenced
  the old v2-prefixed path must be updated in the same change.

### Cannot do anymore

- Present the old v2-prefixed path as the current public Domain API namespace.
- Add new public API documentation or generated clients that point at the old
  v2-prefixed path.
- Collapse domain routes to unversioned `/api/*` as part of this naming change.

## Alternatives considered

- **Keep the old v2-prefixed path for launch**: rejected because the label only
  represented an internal migration from legacy routers. It would be confusing
  for the first public contract to launch as v2.
- **Collapse to unversioned `/api/*`**: rejected because URL versioning is still
  useful once CoachIQ has external consumers. The fix is the version number, not
  the presence of a version segment.
- **Maintain both v1 and old-v2 aliases**: rejected under ADR-0010. There is no
  backward-compatibility obligation before 1.0, and aliases would recreate the
  parallel-maintenance problem ADR-0003 avoids.

## Revisit conditions

- CoachIQ reaches a 1.0 / first public release and freezes public API contracts.
- A real external consumer appears before 1.0.
- The project adopts a formal API deprecation/versioning policy.

## See also

- [ADR-0003](ADR-0003-api-v2-only-no-legacy.md) -- Domain API over legacy
  unversioned routers; naming superseded by this ADR only.
- [ADR-0010](ADR-0010-pre-1.0-no-backward-compat.md) -- pre-1.0 no
  backward-compatibility obligation.
