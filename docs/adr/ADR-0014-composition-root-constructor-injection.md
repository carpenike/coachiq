# ADR-0014: Replace ServiceRegistry with composition-root constructor injection

## Status

**Accepted**, 2026-06-30. Graduates the HOF-050 composition-root umbrella.

## Context

CoachIQ currently starts backend services through a bespoke `ServiceRegistry` and
`SafetyServiceRegistry`. The registry is a hand-rolled dependency-injection
container: service names are strings, dependencies are declared by string, the
resolver uses a custom topological sort, startup uses dynamic keyword injection,
and request-time dependencies look typed only because `backend/core/dependencies.py`
wraps registry lookups in `Annotated[..., Depends(...)]` aliases.

The HOF-050 grounding pass showed the current registry graph contains 68
services across 6 resolved startup stages. It also showed the replacement is not
only a `dependencies.py` provider rewrite. There are direct `get_service()` users
in `main.py`, middleware, websocket handlers, CAN services, `SafetyService`,
routers, integrations, and service internals; there are 33 optional dependency
edges; and the `SafetyServiceRegistry` carries real guardrail behavior such as
service classification, emergency-stop coordination, metadata, and safety status
summary.

Pre-1.0 is the right window to replace this foundation decisively before OIDC,
MCP, and knowledge features add more surface to the stringly-typed pattern.

## Decision

Replace the generic service-registry dependency-injection mechanism with an
explicit composition root that constructs services through typed constructor
injection.

The composition root will own startup construction order, reverse-order
shutdown, and health aggregation. It will hold typed service instances in a
typed container/dataclass. It must not regress to `app.state`, module-level
singletons, or a generic string-keyed service locator.

Keep FastAPI `Depends` as the request-time access mechanism. The existing typed
aliases in `backend/core/dependencies.py` remain the public router contract, but
their internals will be repointed to the typed composition-root container instead
of `ServiceRegistry.get_service()`.

Separate generic DI from guardrail-domain behavior. The generic registry,
resolver, and registration modules are retired. The safety classification,
emergency-stop coordination, safety metadata, and safety status summary behavior
from `SafetyServiceRegistry` remains, either as a small typed safety coordinator
or as explicit responsibilities in `SafetyService` and the composition root.

Migrate in phases, not as a big-bang cutover:

- **Phase A** introduces the composition root, repoints providers, and migrates
  direct service-locator consumers while keeping the app bootable.
- **Phase B** deletes the registry, resolver, and registration modules only
  after no production code references them.

Use the resolver-derived 68-service, 6-stage startup order as the migration seed
rather than hand-guessing construction order.

## Consequences

### Becomes easier

- Constructor signatures and object references become the dependency graph.
- Pyright can see service types without bolting annotations onto an untyped
  string lookup layer.
- Startup order, optional dependencies, and lifecycle hooks become explicit code
  instead of metadata interpreted by a custom resolver.
- Future auth/OIDC/MCP/knowledge work builds on typed composition rather than a
  container scheduled for removal.

### Becomes harder

- Direct registry consumers outside `dependencies.py` must be migrated.
- Optional dependency behavior must be represented explicitly as object-or-None
  constructor arguments or deferred wiring.
- The safety-classification behavior must be preserved deliberately; it cannot
  be treated as generic health aggregation.
- During Phase A, compatibility shims may temporarily coexist with the new root,
  so the migration needs strict boundaries and boot tests after each cluster.

### Cannot do anymore

- Add new long-lived services to `ServiceRegistry` as the primary DI mechanism.
- Treat `SafetyServiceRegistry` as disposable generic DI; its guardrail behavior
  must be preserved in typed code.
- Hide service dependencies behind `Any` string lookups when constructors can
  accept typed objects.
- Use `app.state` or new module-level singletons as the replacement container.

## Alternatives considered

- **Keep ServiceRegistry and add more typed aliases**: rejected. HOF-049 proved
  this pattern can hide real runtime config-delivery bugs. More aliases do not
  fix the stringly-typed runtime graph.
- **Use an external DI framework**: rejected for the same reason ADR-0001
  rejected it. CoachIQ does not need a container; it needs one explicit
  composition root.
- **Big-bang cutover**: rejected because startup order and optional edges are
  load-bearing. Phase A/Phase B keeps the app bootable while each cluster moves.
- **Delete all safety-registry behavior with the DI registry**: rejected.
  Classification, emergency stop, and safety-status coordination are API
  guardrail behavior under ADR-0004, not DI mechanics.

## Revisit conditions

- A future public 1.0 plugin API requires dynamic service registration.
- The composition root grows a generic string lookup interface, recreating the
  registry under another name.
- Safety classification semantics move into a separate formally specified
  guardrail subsystem.

## See also

- `docs/specs/COMPOSITION_ROOT_PLAN.md`
- [ADR-0001](ADR-0001-fastapi-depends-over-di-framework.md) -- superseded for
  the internal service-construction mechanism; FastAPI `Depends` still remains
  for request access.
- [ADR-0006](ADR-0006-typed-dependency-injection.md) -- superseded for the
  registry-backed provider internals; typed aliases remain.
- [ADR-0010](ADR-0010-pre-1.0-no-backward-compat.md) -- decisive cleanup before
  public release.
- HOF-050 in the CoachIQ handoff channel.
