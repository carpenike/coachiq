# ADR-0005: HTTP error responses include both `detail` (FastAPI-default) and `error.{code,message}` (structured)

## Status

**Accepted**, 2026-05-13. Architectural-audit cycle 2026-05-13, PR A5
(closes #150).

## Context

`backend/core/exception_handlers.py` wraps every HTTP error response in
a custom envelope:

```json
{
  "error": {
    "code": "HTTP_404",
    "message": "Account not found",
    "details": { ... },
    "request_id": "..."
  }
}
```

instead of FastAPI's default `{"detail": "Account not found"}`. The
custom envelope was introduced without an ADR; the audit at the close
of the 2026-05-12 test-restoration cycle flagged it because new tests
discover the contract on contact (see `audit-2026-05-12.md` lesson
"Custom error envelope vs FastAPI default").

The audit then turned up a real production bug. The frontend
(`frontend/src/api/client.ts:118-120`) reads `errorDetails.detail`:

```ts
errorDetails = await response.json() as APIError;
errorMessage = errorDetails.detail || errorMessage;
```

against an `APIError` type whose first field is `detail: string`
(`frontend/src/api/types.ts:307`). But the backend never returns
`detail` -- it returns `error.message`. So `errorDetails.detail` has
always been `undefined`, and every error toast in the React UI has
been a generic `"API Error: <status>"` since the envelope landed,
rather than the actual server message. The frontend silently degrades
because the optional-chain default kicks in.

Eight other frontend sites consume `error.detail` directly (5x in
`MFASetup.tsx`, 1x each in `MFAVerification.tsx`, `MFAManagement.tsx`,
`login-form.tsx`). All of those are also silently broken.

Four backend tests assert against the structured envelope
(`tests/unit/test_database_management_api.py` x2,
`tests/contract/test_domain_api_spec_validation.py` x2). Those pass --
they exercise the wire format the backend actually emits.

## Decision

Error responses MUST include BOTH:

- `detail`: a flat string field at the top level, FastAPI-default
  shape, equal to the human-readable message.
- `error`: the structured object (`{code, message, details?, request_id?}`)
  the codebase already produces.

```json
{
  "detail": "Account not found",
  "error": {
    "code": "HTTP_404",
    "message": "Account not found",
    "details": { ... },
    "request_id": "..."
  }
}
```

Concretely: update `backend.core.exception_handlers.create_error_response`
to write `detail` alongside the existing `error` object. No new code path,
no behavior change beyond the wire-format addition.

## Consequences

### Becomes easier

- Frontend `handleApiResponse` and the eight `error.detail` consumers
  start receiving real server messages without code changes.
- Generated OpenAPI clients that follow the FastAPI default
  (`response.detail`) work out of the box.
- Tests can assert on either shape; the four existing assertions on
  `error.message` / `error.code` keep passing.
- New routes do not need to learn a custom convention; they continue
  using FastAPI's exception machinery and our handler does the right
  thing.

### Becomes harder

- Every error response gains ~30-50 bytes of redundant wire format.
  Acceptable -- error responses are not a hot path.
- New backend code that constructs error responses outside
  `create_error_response()` (currently none, but possible) has to
  remember to populate both fields. Mitigation: keep
  `create_error_response()` as the only sanctioned construction
  site; any future bypass should be PR-rejected.

### Cannot do anymore

- Cannot remove the `error.{code,message}` envelope without breaking
  the four existing test assertions and any external consumer that
  parses it.
- Cannot remove `detail` without re-breaking the React UI.

## Alternatives considered

- **Option A (revert to FastAPI default `{detail}` only)**: smallest
  wire format, fixes the frontend bug. Rejected because it loses the
  structured `error.code` (`HTTP_404`, `VALIDATION_ERROR`,
  `DATABASE_INTEGRITY_ERROR`, ...) that callers can switch on
  programmatically. The four existing test assertions would also need
  rewriting.

- **Option B (keep current envelope, fix frontend `APIError` type +
  client to read `error.message`)**: fixes the frontend bug from the
  other direction. Rejected because it requires updating eight
  frontend sites + the type definition, and offers no benefit over
  Option D for consumers expecting FastAPI defaults (e.g. generated
  OpenAPI clients).

- **Option C (RFC 7807 `application/problem+json`: `type`, `title`,
  `status`, `detail`, `instance`)**: the standard answer for
  structured errors. Rejected because it would break every existing
  consumer (frontend AND tests) for the sake of standards-compliance,
  and CoachIQ has no out-of-tree API consumers that would benefit
  from the standardization (per the threat model in
  `coachiq-architecture.md`, the surface is the React UI behind
  Caddy + occasional integration tests). Reconsider if a third-party
  consumer appears.

- **Option D (this ADR -- include both shapes)**: smallest possible
  change. Backward-compatible with both contracts. Wire format gains
  one field per error response. Picked.

## Revisit conditions

- A third-party API consumer (mobile app, integration partner, public
  API) appears -- the choice between Option C (standards-compliance)
  and the current hybrid should be re-evaluated.
- The structured `error.code` field is no longer used by any caller --
  Option A becomes attractive then.

## See also

- `backend/core/exception_handlers.py` -- the only construction site for
  HTTP error responses.
- `frontend/src/api/client.ts` -- the consumer that this ADR unblocks.
- `audit-2026-05-12.md` -- "Custom error envelope vs FastAPI default"
  lesson that prompted this audit.
- ADR-0003 (api-v2-only-no-legacy) -- companion API-shape decision.
