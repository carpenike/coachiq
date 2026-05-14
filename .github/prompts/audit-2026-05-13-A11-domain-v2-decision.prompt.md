---
mode: "agent"
description: "A11 \u2014 Pick a fate for backend/api/domains/ (v2) vs backend/api/routers/ (legacy)"
---

# A11 \u2014 Domain API v2 vs legacy routers \u2014 pick one

Audit cycle: 2026-05-13 architectural audit. **Strategic decision PR.**

## Why

Two parallel API surfaces:

- `backend/api/routers/` \u2014 34 files, the original /api/* surface.
- `backend/api/domains/` \u2014 5 files (entities, system, networks,
  diagnostics, plus shared domain helpers), the /api/v2/* surface.

`copilot-instructions.md` describes the v2 layer as having
"bulk operations and richer schemas". `docs/adr/ADR-0003-api-v2-only-no-legacy.md`
has a strong stance \u2014 read it first.

But on the ground, both surfaces are live, and PR #111 already
discovered a security bug exactly here (placeholder-lambda auth in
`api/domains/entities.py`). Mid-migrations on `main` are how silently
deprecated APIs become indefinitely supported.

## The job

This PR is decision-first, code-second. Read ADR-0003 carefully,
then either:

### Path 1: Honor ADR-0003 (kill the legacy)

If ADR-0003 truly says "v2 only", then:

1. Audit every legacy router: which are covered by a v2 equivalent?
2. For each that IS covered: redirect (HTTP 308 + Location header) to
   the v2 endpoint, with a deprecation `Sunset` header per RFC 8594.
3. For each that is NOT covered: either build the v2 equivalent in
   this PR (if small) or open a child issue and keep the legacy
   route alive behind an explicit `legacy_*` tag.
4. Update OpenAPI tags to mark deprecated routes.
5. Update the React frontend to consume v2 only \u2014 paired PR.
6. Set a removal deadline in the deprecation headers.

### Path 2: Update ADR-0003 to reflect reality

If both surfaces are intentional and v2 is the "rich" interface
while v1 is the "simple" one, then:

1. Supersede ADR-0003 with `ADR-0003a-api-surfaces-coexistence.md`
   (or amend ADR-0003 in place).
2. Document which router belongs to which surface.
3. Codify the auth pattern \u2014 PR #111 found that domain v2 had a
   placeholder-lambda auth bypass. Make it impossible to land a
   v2 route without a real auth dependency by adding a CI check.

## Verification

```bash
# Per-domain coverage matrix
ls backend/api/routers/*.py
ls backend/api/domains/*.py

# Auth dependency audit on v2
grep -n "Depends(get_authenticated_user\|Depends(get_authenticated_admin" backend/api/domains/*.py

# Find any remaining placeholder-lambda dependencies (PR #111 lesson)
grep -n "= lambda: None\|= lambda:.*None" backend/api/domains/*.py backend/api/routers/*.py
```

## Acceptance criteria

- ADR-0003 status is updated (stays Accepted, or Superseded).
- A coverage matrix lives in `docs/architecture/api-surfaces.md`
  showing which legacy routes have v2 equivalents.
- Deprecation headers in place (Path 1) OR documented coexistence
  rules (Path 2).
- No placeholder-lambda auth deps anywhere (the PR #111 lesson \u2014
  add a grep-based pre-commit check if not already present).

## Stop-and-ask if

- The frontend depends heavily on legacy routes that have no v2
  equivalent. Path 1 then requires a substantial frontend PR;
  pause and decide scope.
- Some legacy routes are public-facing (3rd party) and the
  Sunset/deprecation timeline isn't acceptable.

## Risk

High. Public-API contract change. Coordinate with frontend team
(or A12 prompt if you're the frontend team).

## Default recommendation

**Path 2** (coexistence) is the realistic answer in the short term.
Codify it, fix the bypass risk, and only then attempt Path 1.
