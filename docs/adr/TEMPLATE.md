# ADR-NNNN: <imperative title>

## Status

**Proposed** | **Accepted** | **Superseded by ADR-NNNN** | **Deprecated**, <YYYY-MM-DD>

(Pick one. Include a date. If superseding an earlier ADR, link it.)

## Context

What's the situation that forced a decision?

- Concrete facts about the codebase, the deployment, the team, the
  threat model, etc. State only what's relevant to the decision.
- If the context has a history (e.g. "we tried X first and it
  didn't work"), summarize it in one paragraph.
- Avoid prescribing the answer here; that's the next section.

## Decision

What did we choose? State it as an imperative:

> Use FastAPI's `Depends(...)` over an external DI framework.

> All CAN operations go through a single `CANFacade` service.

Spell out the rule in enough detail that a reviewer can flag a PR
that violates it. Include the smallest example of the pattern in
action if it helps.

## Consequences

### Becomes easier
- ...
- ...

### Becomes harder
- ...
- ...

### Cannot do anymore
- ...

## Alternatives considered

For each alternative you seriously considered:

- **<name>**: 1-2 sentences on what it is, then why you didn't pick
  it. Future readers will ask; answer up front.

## Revisit conditions (optional)

If there are specific futures in which this decision should be
re-opened, list them here. Examples:

- Service count grows past N.
- We start serving an out-of-tree consumer.
- A specific pain point emerges.

## See also

- Code paths that embody this decision (file references with line
  numbers if useful).
- Related ADRs.
- External references (RFCs, papers, blog posts, vendor docs).
