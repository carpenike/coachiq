# ADR-0001: Use FastAPI's `Depends(...)` over an external DI framework

## Status

**Accepted**, 2026-05-13. Compresses the 2025-06 evaluation in
`docs/development/di-framework-evaluation.md` (368 lines) into a single
record. The artifacts that evaluation cited as evidence (`dependencies_v2`,
`ServiceProxy`, "Migration Adapters") are gone; the underlying decision
holds.

## Context

The backend has ~60 services and growing. They have a clear dependency
graph (e.g. `EntityService` depends on `EntityStateRepository`, which
depends on `DatabaseManager`). At some point during the 2025 sprint
the question came up: should we adopt a real DI framework
(`dependency-injector`, `punq`, `pinject`, `lagom`) instead of relying
on FastAPI's built-in `Depends(...)` machinery plus our own
`EnhancedServiceRegistry`?

The cost of "yes" is: adopt a non-standard dep, learn its DSL, retrain
contributors, deal with its corner cases (provider scopes, container
nesting, async ergonomics). The benefit is supposed to be more
declarative wiring and better separation of concerns.

## Decision

Stay with FastAPI's `Depends(...)` plus our own
`EnhancedServiceRegistry`. Do not adopt a third-party DI framework.

The actual pattern in production:

1. **Construction**: every service is built in a `_init_*` function in
   `backend/main.py`, with its dependencies passed as constructor
   arguments. No global state, no service locator inside services.
2. **Registration**: each constructed service is handed to
   `EnhancedServiceRegistry.register_service(name, init_func,
   dependencies)`. The registry's `ServiceDependencyResolver` builds
   a topological order at startup.
3. **Injection**: routers receive services via
   `Annotated[Type, Depends(get_x)]`. The `get_x` helpers in
   `backend/core/dependencies.py` resolve the named service from the
   registry.

That is the entire wiring story. There is no DSL, no decorator
machinery, no separate config file describing service shapes.

## Consequences

### Becomes easier
- **Type checking**: pyright sees through every `Depends(get_x)` call.
- **Onboarding**: anyone who knows FastAPI knows our DI. No second
  framework to learn.
- **Testing**: `app.dependency_overrides[get_x] = lambda: mock`
  replaces a service for one test. Standard FastAPI; no container
  rewiring.
- **Stack traces**: a missing dependency raises `RuntimeError` from
  `get_service_registry()` with the requested service name in the
  message. There's no DI-framework layer to peer through.

### Becomes harder
- **Lifecycle features that DI frameworks ship for free** -- scoped
  providers, lazy resolution, cyclic-dependency detection -- we have
  to build ourselves. We have done the ones we needed
  (`ServiceDependencyResolver` does cycle detection and stage planning;
  PR #135 fixed a fallback-handling bug in stage optimization), and
  the gaps that remain (e.g. per-request scopes) we don't actually
  need.
- **No declarative service config**. Adding a service requires editing
  `main.py`. That's a maintenance cost but also a forcing function:
  every service registration is visible in one place.

### Cannot do anymore
- Adopt a DI framework cleanly later. We could do it as a refactor,
  but `main.py`'s explicit-registration pattern would have to be
  reworked. Worth the effort only if we ever feel real pain from the
  current pattern, which we don't.

## Alternatives considered

### `dependency-injector` (most popular Python DI framework)
- Strong feature set: scopes, async, providers, configuration
  binding.
- Cost: introduces a non-trivial DSL. Containers are themselves
  Python classes with a particular shape; all wiring goes through
  `Provide[Container.thing]` markers in function signatures.
- Rejected because the marker approach interacts awkwardly with
  FastAPI's own `Depends(...)` (you end up with two layers of DI),
  and because the benefits (configurability, scopes) don't apply to
  our use case where every service is a singleton with one
  construction site.

### `punq`, `lagom`, `pinject`
- Smaller / lighter than `dependency-injector`. Mostly favor
  constructor-injection-by-type-hint.
- Rejected because the constructor-injection-by-type-hint approach
  presumes you want runtime resolution of types, which we don't.
  Our service registration is explicit by name; type-based
  resolution would just add ambiguity (e.g. "which `Repository`
  should I inject here?").

### Our own decorator + YAML config (proposed in
`di-framework-evaluation.md` "Recommended Minor Enhancements")
- The 2025 evaluation suggested a `@service_dependency` decorator
  and a `services.yaml` config to describe service wiring
  declaratively.
- **Push back**: not needed. The current state -- explicit
  registration in `main.py`, type-checkable injection at call sites
  -- is simple, type-checkable, and you've shown across 17 PRs that
  it scales fine for ~60 services. Don't introduce a config DSL on
  top of working code without a concrete pain point that the DSL
  would relieve.

## Revisit conditions

Reconsider this decision if any of these become true:

- Service count grows past ~150 (current ~60).
- We grow a team large enough that "edit main.py" becomes a bottleneck.
- We decide to break the monolith into multiple processes
  (microservices), where independent service containers would
  matter.
- A specific pain point emerges that a DI framework would relieve
  (e.g. per-request scoping for multi-tenant deployments).

Until then, the answer is "FastAPI's `Depends(...)` is enough".

## See also

- `backend/core/service_registry.py` -- the registry implementation.
- `backend/core/service_dependency_resolver.py` -- topological
  ordering + cycle detection (with the PR #135 fallback fix).
- `backend/core/dependencies.py` -- the `get_*` injection helpers.
- `backend/main.py` -- the single source of truth for what is wired
  to what.
- `docs/architecture/repository-pattern.md` -- describes the same
  pattern from the data-access angle.
