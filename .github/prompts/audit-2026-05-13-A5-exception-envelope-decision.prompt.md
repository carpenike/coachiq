---
mode: "agent"
description: "A5 \u2014 ADR + decision on the custom HTTP exception envelope"
---

# A5 \u2014 Custom exception envelope: keep, revert, or migrate to RFC 7807?

Audit cycle: 2026-05-13 architectural audit.

## Why

`backend/core/exception_handlers.py:176` wraps every HTTP error as:

```json
{"error": {"code": "HTTP_<status>", "message": "..."}}
```

instead of FastAPI's default `{"detail": "..."}`. There is **no rationale**
documented anywhere in the file or in `docs/`. New tests learn this on
contact (see `audit-2026-05-12.md` lesson "Custom error envelope vs
FastAPI default"), the frontend has to special-case it, and OpenAPI
clients generated from `openapi.json` may not reflect it.

This PR is decision-first, code-second.

## The job

1. **Write `docs/adr/ADR-0005-http-error-response-envelope.md`** using
   the `docs/adr/TEMPLATE.md` form. The ADR must enumerate:
   - **Option A**: revert to FastAPI default (`{"detail": "..."}`)
     \u2014 simplest; breaks any existing client that expects the custom
     envelope.
   - **Option B**: keep the custom envelope, document it, codify it
     into the OpenAPI schema with `responses=...` on every router \u2014
     status quo + bookkeeping cost forever.
   - **Option C**: migrate to RFC 7807 `application/problem+json`
     (`type`, `title`, `status`, `detail`, `instance`) \u2014 standard,
     well-supported in FastAPI via `fastapi-problem` or hand-rolled,
     breaks current clients but only once.

2. **Pick one** based on:
   - Is the frontend the only consumer? (Easier to migrate.)
   - Are there mobile/3rd-party clients? (Constrains breakage.)
   - Audit the React frontend for `response.error.message` patterns
     before deciding.

3. **Implement** the chosen option:
   - If A or C: update the exception handlers + every router test that
     asserts on `response.json()["error"]["message"]`.
   - If B: extend exception_handlers docstring with the rationale,
     audit OpenAPI schema export to ensure all error responses are
     advertised.

## Verification

```bash
# Find every test that asserts on the custom envelope
grep -rn "response.json().*\\[\"error\"\\]\|json()\\[.error.\\]" tests/ --include="*.py"

# Find frontend consumers
grep -rn "error.message\|error.code\|HTTP_" frontend/src --include="*.ts" --include="*.tsx" | head -20
```

## Acceptance criteria

- ADR-0005 exists, status **Accepted**.
- The chosen option is implemented and tested.
- All test assertions migrated.
- Frontend (if affected) updated in the same PR or in a paired
  follow-up referenced from the ADR.
- Memory file updated.

## Stop-and-ask if

- The frontend has 50+ call sites that assert on the custom envelope.
  At that scale the migration deserves its own paired frontend PR;
  the backend PR should land behind a feature flag or be coordinated.
- You discover a 3rd-party API consumer (mobile, integration partner)
  not visible in the repo. That blocks Option A/C; default to Option B.

## Risk

Medium. Public-API contract change. Only do this when all consumers
are accounted for.

## Default recommendation

Lean Option C (RFC 7807) only if the frontend audit shows <10 affected
files. Otherwise lean Option B + document. Option A (revert) is rarely
the right call once an envelope is shipped.
