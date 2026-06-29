# ADR-0010: Pre-1.0 no backward-compatibility obligation

## Status

**Accepted**, 2026-06-28. Time-boxed: revisit at the 1.0 / first public
release.

## Context

CoachIQ has not shipped a release. The only consumers of its REST/WebSocket
API and frontend interfaces are this repo's own frontend and the maintainer's
`carpenike/nix-config`, both of which change in lockstep with the code.

The conservative ceremony in several earlier ADRs -- deprecation windows,
parallel-maintained legacy surfaces, dual-shape compatibility envelopes, and
convergence ratchets -- was justified by a backward-compatibility obligation
that does not yet exist.

## Decision

Until a 1.0 / first public release creates real external consumers, CoachIQ
carries **no backward-compatibility obligation**. Concretely:

- Legacy surfaces are retired decisively, not incrementally. The gate for
  deleting a legacy interface is: the replacement covers it, our own callers
  still work, and tests pass. It is not: will this break an external consumer.
  Legacy routers with domain API equivalents may be removed in bulk, fixing our
  own callers in the same change.
- Compatibility shims, dual-shape envelopes, deprecation windows, and
  convergence ratchets are not added for external compatibility, and existing
  ones may be removed.
- This relaxes the incremental-retirement framing of
  [ADR-0003](ADR-0003-api-v2-only-no-legacy.md) and supersedes the
  backward-compatibility rationale of
  [ADR-0005](ADR-0005-http-error-response-envelope.md).

## What does not change

The mandatory review gate, the grounding/enumeration discipline (cross-agent
lessons L-01/L-04/L-06), and the test suite stay in force. They catch real bugs
and incomplete scope regardless of compatibility, and have repeatedly done so.
This ADR relaxes only backward-compatibility-driven conservatism.

## Consequences

### Becomes easier

- Deletion-heavy convergence on the domain API surface can proceed without
  compatibility ceremony for consumers that do not exist.
- Error-contract cleanup can be evaluated as an internal repo-wide migration,
  not as a public API break.
- Future hand-offs can focus on replacement coverage, in-repo caller updates,
  and tests rather than deprecation windows.

### Becomes harder

- The cost is deferred to the first public release: at 1.0, CoachIQ must
  reinstate deprecation discipline and freeze public contracts.
- Agents must distinguish backward-compatibility caution from the review,
  grounding, and test disciplines that still apply.

### Cannot do anymore

- Add compatibility shims, parallel-maintained legacy routes, or dual-shape
  contracts solely for hypothetical external consumers before 1.0.
- Treat ADR-0003's incremental retirement pacing or ADR-0005's dual-envelope
  backward-compatibility rationale as permanent.

## Alternatives considered

- **Keep pre-1.0 compatibility ceremony**: rejected because CoachIQ has no
  public release and no external API consumers. The compatibility benefit is
  hypothetical; the maintenance and review cost is real.
- **Delete compatibility surfaces without recording the stance**: rejected
  because ADR-0003 and ADR-0005 are part of the canonical "do not revert" set.
  The relaxed stance needs to live in the ADR set, not only in a hand-off or
  implementation plan.

## Revisit conditions

- CoachIQ reaches a 1.0 / first public release.
- A real external consumer appears before 1.0.
- The maintainer chooses to publish a stable REST/WebSocket API contract.

## See also

- [ADR-0003](ADR-0003-api-v2-only-no-legacy.md) -- API v1 only; legacy
  `/api/*` routes are retired rather than parallel-maintained.
- [ADR-0005](ADR-0005-http-error-response-envelope.md) -- HTTP error response
  envelope whose backward-compatibility rationale is superseded pre-1.0.
- `IMPLEMENTATION_PLAN.md` -- HOF-030 recorded the pre-1.0 compatibility stance
  before this ADR graduated it.
