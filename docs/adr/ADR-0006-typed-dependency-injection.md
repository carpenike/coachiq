# ADR-0006: Type the FastAPI dependency injection layer

## Status

**Accepted**, 2026-05-13. Architectural-audit cycle 2026-05-13, PR A7.0
(starts on #152).

## Context

`backend/core/dependencies.py` exposes every service to FastAPI routers
via type-erased aliases:

```python
CANFacade = Annotated[Any, Depends(get_can_facade)]
EntityService = Annotated[Any, Depends(get_entity_service)]
AuthManager = Annotated[Any, Depends(get_auth_manager)]
# ... 27 of these
```

The accessors (`get_can_facade`, etc.) call
`service_registry.get_service("can_facade")` -- string-keyed lookup
against a runtime `EnhancedServiceRegistry` (collapsed to
`ServiceRegistry` in PR #161 / A3).

Measurements at audit time:

- **27** `Annotated[Any, ...]` aliases in `dependencies.py`.
- **53** `service_registry.get_service("...")` call sites.
- Routers: **73 `Any`** + **47 `Any | None`** = **120 type-erased**
  parameters vs ~150 properly-typed (45% of router DI).

Consequences observed during the audit:

1. **Pyright can't catch misuse.** Routers see `Any.method()` and
   pyright waves it through. The 1452-error baseline (PR #117 / #139)
   is partly self-inflicted: real bugs in router bodies hide behind
   `Any`.
2. **Typos in registry keys are runtime errors, not type errors.**
   `service_registry.get_service("entity_serivce")` (typo) raises
   `RuntimeError` only when a request hits the route.
3. **IDE autocomplete is dead.** `entity_service.<TAB>` produces
   nothing useful in routers; new contributors can't discover the API
   by typing.
4. **Indirection lies in plain sight.** The audit found
   `get_auth_manager()` returns `AuthService`, on which callers must
   then call `.get_auth_manager()` to get the actual `AuthManager`.
   With the type-erased alias the compiler sees nothing wrong with
   `auth_service.get_auth_manager()` (auth_service is `Any`); it would
   loudly catch this if the type were real.

## Decision

Type the dependency-injection aliases in `backend/core/dependencies.py`
with the **concrete service classes**. Keep the runtime mechanism
(string-keyed `ServiceRegistry.get_service`) unchanged.

Pattern:

```python
# Import the real class under an underscore-prefixed name so the
# type alias keeps the public, ergonomic name routers already use.
from backend.services.can.can_facade import CANFacade as _CANFacade

def get_can_facade() -> _CANFacade | None:
    """Get the CANFacade from ServiceRegistry."""
    return create_optional_service_dependency("can_facade")()

CANFacade = Annotated[_CANFacade, Depends(get_verified_can_facade)]
```

Rules:

1. **Each typed alias keeps its existing public name.** Routers do not
   need to change their imports or signatures. The migration is a
   `dependencies.py`-only edit per cluster.
2. **Use underscore-prefixed import aliases when the type alias name
   collides with the real class name** (e.g. `CANFacade` is both an
   alias and a class — import the class as `_CANFacade`).
3. **The runtime ServiceRegistry lookup stays string-keyed.** This is
   Option A from the original prompt; Option B (class-keyed generic
   registry) is deferred until Option A proves insufficient.
4. **One sub-PR per service cluster.** The full DI surface is too
   large to type in one PR; clusters are sized so each sub-PR can
   land independently with a stable pyright baseline.
5. **Pyright baseline movement is allowed.** Real types surface real
   bugs and real fixes. Each sub-PR records the baseline delta in its
   commit message and updates `EXPECTED_PYRIGHT_ERRORS` in
   `scripts/ci-quality-gate.sh` if needed (same recipe as PRs #160 /
   #161 / #139).

Suggested cluster order (low risk → high risk):

| Sub-PR | Cluster | Notes |
|---|---|---|
| A7.0 | CAN services (facade + injector + filter + recorder + analyzer) | This PR. Smallest, well-isolated. |
| A7.1 | Repositories (entity_state, rvc_config, system_state, etc.) | Mechanical -- repositories are simple data-access. |
| A7.2 | Notifications + analytics | Larger surface; touches the 3-tier manager split. |
| A7.3 | Entity + safety | Touches the live entity services + the `CommandGuardrailService` guardrail. |
| A7.4 | Auth + security | **Land AFTER PR A9** (auth namespace consolidation) so typed aliases don't lie about what comes back. |
| A7.5 | Misc cleanup (cleanup of any orphans surfaced by A7.0--A7.4) | Final pass. |

## Consequences

### Becomes easier

- Pyright catches `Any.method()`-style misuse in routers immediately.
- IDE autocomplete in routers works.
- Refactoring service classes (rename a method, change a signature)
  surfaces at the call site.
- Future ADRs (auth namespace, ConfigService rename) get the typed
  call graph for free.
- The `get_auth_manager().get_auth_manager()` anti-pattern (audit
  finding) would have been a type error if the alias had been typed
  -- protects against the next instance.

### Becomes harder

- Sub-PR coordination: changing a service class signature now
  requires the typed alias to absorb the change. Mitigation: the
  alias is intentionally a one-line edit per cluster, kept in a
  single file.
- Circular-import risk: if `dependencies.py` imports a service class
  that itself imports something that transitively imports
  `dependencies.py`, the import chain breaks. Mitigation: use
  `typing.TYPE_CHECKING` guards or `Protocol` types in the rare cases
  where this fires.
- Pyright baseline may move both up (real bugs surface) and down
  (true types reduce some false-positive errors). The hardened
  ratchet handles both.

### Cannot do anymore

- Cannot ship a router that depends on a service that doesn't exist
  in `ServiceRegistry` -- pyright will catch the missing import.
- Cannot ship a typo in a registry key on the `dependencies.py` side
  -- the typed accessor and the type alias have to agree.

## Alternatives considered

- **Option B (class-keyed generic registry)**: replace
  `ServiceRegistry.get_service("can_facade")` with
  `ServiceRegistry.get_service(CANFacade)`. Eliminates the string
  indirection entirely. Rejected for the first pass because it
  requires reworking `EnhancedServiceRegistry` (just collapsed in A3)
  AND every registration site in `main.py` (god module pending A8).
  Reconsider after A7 lands and A8 splits main.py.

- **Status quo (keep `Annotated[Any, ...]`)**: no work, no benefit.
  Rejected -- the audit explicitly flagged this as the highest-leverage
  structural issue.

- **Per-call-site casting** (`cast(CANFacade, can_facade)` at every
  router signature): puts the type-narrowing burden on every router
  author. Rejected because the typed alias is a one-line fix that
  doesn't require any churn outside `dependencies.py`.

## Revisit conditions

- After A8 (main.py split) and A9 (auth namespace) land, the
  string-keyed registry assumption may be revisitable -- a typed
  registry (Option B) might be a clean follow-up.
- If circular-import issues bite more than two sub-PRs, consider
  moving service classes to `Protocol`-based interfaces in a separate
  `backend/core/protocols/` package.

## See also

- `backend/core/dependencies.py` -- the file this ADR governs.
- ADR-0001 (FastAPI Depends over external DI framework) -- this ADR
  is the concrete typing layer on top of that decision.
- ADR-0003 (api v2 only / no legacy) -- the API surface this typing
  benefits most directly.
- `audit-2026-05-12.md` Lesson #3 (PR #111) -- "verify auth deps
  resolve to a real implementation by following imports, not by
  counting occurrences". Typed aliases make this verification a
  compile-time check.
