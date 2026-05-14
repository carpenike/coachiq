---
mode: "agent"
description: "A7 \u2014 Type the FastAPI DI layer (eliminate Annotated[Any, ...] aliases)"
---

# A7 \u2014 Type the FastAPI dependency injection layer

Audit cycle: 2026-05-13 architectural audit. **High-leverage structural
PR \u2014 expect to land in 4\u20136 incremental sub-PRs, one service-cluster
at a time.**

## Why

`backend/core/dependencies.py` exposes every service as
`Annotated[Any, Depends(get_X)]`. Measurements at audit time:

- 27 `Annotated[Any, ...]` aliases in `dependencies.py`.
- 53 `service_registry.get_service("...")` callsites.
- Routers: **73 `Any` + 47 `Any | None` = 120 type-erased deps**
  vs ~150 properly-typed (45% of router DI is `Any`).

The result: pyright sees `Any.control_light(...)` and waves it through.
A typo in `get_service("entity_service")` is a runtime `RuntimeError`,
not a type error. Real types are fed into an `Any` blender at the
boundary. The 1452-error pyright baseline is partly self-inflicted.

The reductio: `auth_service = get_service("auth_manager")` \u2192
`auth_service.get_auth_manager()` \u2014 registry name \u2260 class name \u2260
what callers want, with no type system protection.

## The decision: ADR first

Before code, write `docs/adr/ADR-0006-typed-dependency-injection.md`
weighing two approaches:

- **Option A** (smaller change): replace each `Annotated[Any, ...]`
  alias with `Annotated[<RealClass>, Depends(get_X)]`. Keep the
  string-keyed registry as the lifecycle owner. The accessors
  `get_X()` still call `service_registry.get_service("x")` at runtime
  but their *return type* is `RealClass`. **Pyright and IDEs win;
  runtime model unchanged.**
- **Option B** (bigger change): make `get_service` generic
  (`get_service(EntityService) -> EntityService`) using a class-keyed
  registry. Eliminates the string indirection entirely.

Recommendation: **Option A**. Lower risk, captures most of the
benefit, doesn't require restructuring the registry. Option B is a
candidate for a future ADR if Option A proves insufficient.

## The job (after ADR)

Per service cluster (one PR each):

1. Add real types to the relevant `dependencies.py` accessors and
   aliases.
2. Update routers in that domain to use the new typed alias.
3. Run pyright \u2014 expect 50\u2013200 NEW errors as `Any` evaporates.
   Triage them: most are real bugs or missing type stubs.
4. Either fix in this PR (preferred) or add a focused TODO with
   an issue link.
5. Ratchet the pyright baseline UP if real fixes lower it, or
   accept the increase if it represents previously-hidden
   real-type-flow problems (this is fine \u2014 the gate is
   "shouldn't grow without acknowledgement", not "always go down").

Suggested cluster order (low-risk \u2192 high-risk):

| Sub-PR | Cluster | Likely error count |
|---|---|---|
| A7.1 | CAN services (`get_can_facade`, recorder, injector, filter, analyzer) | ~30 |
| A7.2 | Repositories (entity_state, rvc_config, system_state) | ~20 |
| A7.3 | Notification + analytics | ~50 |
| A7.4 | Auth + security | ~100 (touches the auth triumvirate \u2014 coordinate with A9) |
| A7.5 | Entity services + safety_service | ~80 |
| A7.6 | Misc cleanup | residual |

## Verification

```bash
# Per sub-PR
poetry run pyright backend/api/routers/<cluster>* backend/core/dependencies.py
poetry run pytest tests/api/<cluster>* tests/services/<cluster>* -q

# Final
nix run .#ci
```

## Acceptance criteria (per sub-PR)

- The cluster's `Annotated[Any, ...]` aliases are gone.
- Pyright baseline updated (UP or DOWN, with rationale in PR description).
- Tests still pass.
- ADR-0006 updated with each sub-PR's "real bugs surfaced" list.

## Stop-and-ask if

- A real type for a service produces 50+ pyright errors that all look
  like genuine API misuse. That's a PR-A7-pause moment: the cluster
  may need an API rationalization first.
- Adding a real type creates a circular import. Move the type to a
  Protocol in `backend/core/protocols/<service>.py`.
- The service has multiple "incarnations" (cf. auth) where the typed
  alias would lie about what comes back. Pause and finish A9 first.

## Risk

High volume of changes per sub-PR but each is mechanical. The risk is
discovering bugs that were previously hidden by `Any` \u2014 those are wins,
not failures. Cap each sub-PR at one cluster.

## Long-term win

When this is done, `dependencies.py` becomes a typed DI catalog.
`@vscode/copilot` autocompletion in routers improves dramatically.
Misnamed registry keys become type errors at edit time, not runtime
errors at request time.
