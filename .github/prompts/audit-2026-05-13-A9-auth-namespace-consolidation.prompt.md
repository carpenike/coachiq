---
mode: "agent"
description: "A9 \u2014 Consolidate auth_service.py / auth_services.py / auth_manager.py into backend/services/auth/"
---

# A9 \u2014 Auth namespace consolidation

Audit cycle: 2026-05-13 architectural audit. **High-leverage structural PR.**

## Why

Three files, all live, all imported from main.py:

- `backend/services/auth_service.py` (272 LOC) \u2014 `class AuthService`
- `backend/services/auth_services.py` (680 LOC) \u2014 `class TokenService, SessionService, MfaService, LockoutService`
- `backend/services/auth_manager.py` (1794 LOC) \u2014 `class AuthManager`

Runtime story: `_init_auth_service(...)` in main.py constructs an
`AuthService` and registers it under the registry name `"auth_manager"`.
Routers call `get_auth_manager()`, which looks up `"auth_manager"`
(returns `AuthService`), and calls `.get_auth_manager()` on it
(returns the underlying `AuthManager`).

Three layers of name confusion. The names aren't wrong individually \u2014
together they're cognitive load tax for every reader.

## The job

1. **Create `backend/services/auth/` package**:
   - `__init__.py` \u2014 exports `AuthService` (the public facade).
   - `tokens.py` \u2014 `TokenService` (extracted from `auth_services.py`).
   - `sessions.py` \u2014 `SessionService`.
   - `mfa.py` \u2014 `MfaService`.
   - `lockout.py` \u2014 `LockoutService`.
   - `manager.py` \u2014 `AuthManager` (the underlying state holder if it's
     genuinely needed; otherwise inline into `AuthService`).
   - `repository.py` \u2014 `AuthRepository` (currently legacy; either keep
     under that name for compat or move and delete the original).

2. **Delete the three top-level files** after migration.

3. **Rename the registry key** `"auth_manager"` \u2192 `"auth"` (or
   keep `"auth_service"` for clarity \u2014 author's choice).

4. **Eliminate the `get_auth_manager().get_auth_manager()` charade**:
   either expose `AuthManager` directly under its own registry key
   (`"auth_manager"` for real this time) and have callers depend on
   the right one, or fold `AuthManager`'s state into `AuthService`
   if the split is no longer meaningful.

5. **Update routers and dependency aliases**: every
   `Annotated[AuthManager, Depends(get_auth_manager)]` needs to become
   either `Annotated[AuthManager, Depends(get_auth_manager)]` (real)
   or `Annotated[AuthService, Depends(get_auth_service)]`, depending
   on what the call site actually needs.

## Coordination with A7 (typed DI)

A9 and A7 overlap heavily. Suggested order:

- A7.1 (CAN), A7.2 (repos), A7.3 (notifications) first \u2014 small wins.
- A9 next \u2014 cleans up the auth files.
- A7.4 (auth + security typed DI) immediately after A9 \u2014 then the
  typed aliases land cleanly without lying about the return type.

## Verification

```bash
# After consolidation
ls backend/services/auth/
# tokens.py sessions.py mfa.py lockout.py manager.py __init__.py

# Old files gone
ls backend/services/auth_service.py backend/services/auth_services.py backend/services/auth_manager.py 2>&1
# Should be "No such file or directory"

# Tests pass
poetry run pytest tests/services/test_auth* tests/services/test_pin_manager* tests/api/test_auth* -q
nix run .#ci
```

## Acceptance criteria

- `backend/services/auth/` package exists with the listed modules.
- The three top-level files are gone.
- Registry key clarity: no `get_X_manager().get_X_manager()` patterns.
- Routers use the typed aliases that resolve to the right class.
- Auth tests pass (PIN manager, JWT validation, MFA, sessions).
- ADR? Yes \u2014 short `docs/adr/ADR-0007-auth-service-namespace.md` codifying
  the package layout decision so future contributors don't undo it.

## Stop-and-ask if

- `AuthManager` and `AuthService` turn out to encapsulate genuinely
  different responsibilities (one is the policy engine, one is the
  request-time facade). Don't merge \u2014 document the distinction
  clearly in `__init__.py` and keep both, but inside the package.
- The 1794 LOC `auth_manager.py` contains feature-flagged code paths
  (single-user vs multi-user vs none). Each path must be tested
  through the new layout.

## Risk

High. Auth code is the realistic threat-model surface (per
`coachiq-architecture.md`). Run the security integration tests and
do a manual login flow in dev before merging.
