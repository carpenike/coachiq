# ADR-0007: Consolidate auth subsystem under `backend/services/auth/`

## Status

**Accepted**, 2026-05-14. Architectural-audit cycle 2026-05-13, PR A9
(closes #154).

## Context

Before this ADR, the auth subsystem lived in four files at the top
level of `backend/services/`:

```
backend/services/auth_manager.py     1794 LOC  AuthManager (policy/state engine)
backend/services/auth_service.py      272 LOC  AuthService (request-time facade)
backend/services/auth_services.py     680 LOC  TokenService + SessionService
                                                + MfaService + LockoutService
backend/services/auth_repository.py  1087 LOC  AuthRepository (legacy DB layer)
```

The naming-by-counting-`s` pattern (`auth_service.py` vs
`auth_services.py`) was a constant source of confusion. Worse, the
runtime call chain compounded it: `main.py` constructed an
`AuthService`, registered it under the `ServiceRegistry` key
`"auth_manager"`, and every router that needed the underlying engine
called `get_auth_manager().get_auth_manager()` to unwrap it. A
deliberate audit walkthrough flagged this as the single highest
cognitive-load tax in the backend.

The audit prompt
(`.github/prompts/audit-2026-05-13-A9-auth-namespace-consolidation.prompt.md`)
proposed two changes:

1. Move all four files into a single `backend/services/auth/` package
   and split `auth_services.py` into one file per service class.
2. Eliminate the registry-key/getter-of-getter charade by renaming
   the key and merging or clearly delineating `AuthManager` vs
   `AuthService`.

## Decision

### 1. Package layout (this PR)

Adopt the following package structure under
`backend/services/auth/`:

```
backend/services/auth/
    __init__.py        -- public re-exports + design documentation
    manager.py         -- AuthManager       (was auth_manager.py)
    service.py         -- AuthService       (was auth_service.py)
    repository.py      -- AuthRepository    (was auth_repository.py)
    tokens.py          -- TokenService      (split from auth_services.py)
    sessions.py        -- SessionService    (split from auth_services.py)
    mfa.py             -- MfaService        (split from auth_services.py)
    lockout.py         -- LockoutService    (split from auth_services.py)
```

The three single-class files were moved with `git mv` so blame is
preserved. The four split files are verbatim copies of the original
class bodies; only the imports and module docstrings are new.

The four top-level files are deleted -- no compatibility shims. All
in-tree call sites (14 import statements across `backend/` and
`tests/`) are updated in the same commit.

### 2. `AuthManager` and `AuthService` stay separate

Per the audit prompt's stop-and-ask, the two classes are **not**
merged. They encapsulate genuinely different responsibilities:

- **`AuthManager`** (`auth/manager.py`) is the policy / state engine.
  It owns the auth-mode decision (none / single-user / multi-user),
  user lookup, password validation, magic-link issuance, MFA
  challenge orchestration, and the in-process state machine. It is
  testable in isolation without spinning up FastAPI.

- **`AuthService`** (`auth/service.py`) is the request-time facade
  that the rest of the application talks to via dependency injection.
  Its job is constructor wiring: it builds the four sub-services
  (`TokenService` / `SessionService` / `MfaService` /
  `LockoutService`), instantiates the legacy `AuthRepository`, and
  passes them all into the `AuthManager` at startup. It exposes
  `.get_auth_manager()` so consumers can reach the policy engine.

Merging them would either bloat `AuthService` into a 2000+ LOC class
or push request-time concerns down into `AuthManager`, hurting
testability either way. The split is intentional and documented in
the package `__init__.py`.

### 3. Out of scope (deferred follow-ups)

The audit prompt also calls for:

- Renaming the `ServiceRegistry` key `"auth_manager"` -> `"auth"` or
  `"auth_service"`.
- Eliminating the `get_auth_manager().get_auth_manager()` getter-of-
  getter pattern by exposing `AuthManager` under its own key (real
  this time) and updating every consumer.

Both touch every auth router (~6 routers, ~30 endpoints) and every
middleware that pulls auth from DI (~4 middlewares). Doing them in
the same PR as the file relocation would make the diff
unreviewable. They are intentionally deferred to a follow-up.

The follow-up sequence is:

1. **A7.4** (typed DI for auth + security cluster, the next typed-DI
   wave) -- introduces real types on `Annotated[AuthManager, ...]`
   etc. After A9 the type targets are stable.
2. A subsequent PR (not yet numbered) to rename the registry key and
   collapse the getter-of-getter.

## Consequences

### Positive

- Single discoverable location for everything auth.
- Per-class files make blame / git log / pyright errors easier to
  read.
- Future structural changes (e.g. swapping `AuthManager` for a
  different policy engine) are localised to the package.
- Type-aware DI (A7.4) lands on a stable namespace.

### Negative

- One round of cosmetic churn for git blame on the four split
  classes (the move was `git mv` for the three single-class files but
  the four split files are necessarily new from git's POV).
- Two getter-of-getter call sites still exist in routers / middleware
  until the follow-up PR.

### Neutral

- `AuthRepository` lives at `backend.services.auth.repository`, not
  `backend.repositories.auth_repository`. The new package is
  *services*, not *repositories*, because `AuthRepository` is the
  **legacy** persistence layer that pre-dates the
  `backend/repositories/` pattern. Moving it to
  `backend/repositories/` would shadow the new-style
  `auth_repository.py` already there and create more confusion than
  it resolves. Keep it under auth/ until the legacy class is
  decommissioned.

## References

- Architectural audit cycle 2026-05-13 (`#145` epic).
- PR A9 (`#154` child).
- Audit prompt:
  `.github/prompts/audit-2026-05-13-A9-auth-namespace-consolidation.prompt.md`.
- ADR-0006: typed DI (the work that comes after this in A7.4).
