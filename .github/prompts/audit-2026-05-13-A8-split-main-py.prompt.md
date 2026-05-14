---
mode: "agent"
description: "A8 \u2014 Split backend/main.py (2562 LOC) into per-domain registration modules"
---

# A8 \u2014 Split `backend/main.py` into per-domain registration modules

Audit cycle: 2026-05-13 architectural audit. **Structural \u2014 expect 1
or 2 sub-PRs.**

## Why

`backend/main.py` is 2562 lines:

- ~1500 LOC of `service_registry.register_service(...)` calls.
- TODOs that have lived through every Phase since 2025:
  - `# TODO(Phase 3): These services need to be updated for constructor injection` (~line 1578)
  - `# TODO: Migrate these services to ServiceRegistry` (~line 1585)
- Special post-startup mutation patches (e.g. injecting
  `service_registry` into `safety_service` after the fact at
  ~line 1505\u20131518) that leak across module boundaries because
  there's no obvious place for them.

Every PR contends for the same file. Touching one service's
dependencies forces editing main.py.

## The job

1. Create `backend/core/registrations/` (or `backend/core/bootstrap/`).
2. Per domain, extract `register(registry: ServiceRegistry) -> None`:
   - `auth.py` (auth_manager, auth_services, security_audit_service, etc.)
   - `can.py` (can_facade, can_recorder, message_injector, can_filter, analyzer, bus_service, interface_service)
   - `safety.py` (safety_service + the safety_registry registrations)
   - `notifications.py` (the 3 manager tiers + the supporting services)
   - `persistence.py` (database_manager, persistence_service, repositories)
   - `entity.py` (entity_service, entity_domain_service, entity_manager_service, etc.)
   - `security.py` (security_event_manager, security_config_service, pin_manager, security_websocket_handler)
   - `analytics.py` (performance_monitor, analytics_dashboard_service, etc.)
   - `protocols.py` (rvc_service, j1939, firefly, spartan_k2 \u2014 if they have register hooks)
3. main.py becomes ~200\u2013300 LOC: build app, call each `register(...)`,
   set up middleware, lifespan glue, uvicorn launch.
4. **The post-startup mutation patches get a home**: a `post_startup`
   hook on each registration module, called by `lifespan` after
   `service_registry.startup_all()`.

## Suggested two-stage rollout

- **A8.1** (mechanical extraction): create `registrations/` package,
  move blocks of code one domain at a time. No behavior changes.
  Each domain extraction is its own commit so reviewers can follow.
- **A8.2** (structural cleanup): finally close the Phase 3 TODOs by
  giving each `_init_X` function its proper signature and registering
  via constructor injection.

A8.1 alone is the win. A8.2 is gravy that will be much easier afterward.

## Verification

```bash
# main.py LOC dropped substantially
wc -l backend/main.py
# Expect ~250-400 after A8.1

# Each registration module is small
wc -l backend/core/registrations/*.py | sort -n

# Same number of services registered
grep -rn "register_service\|register_safety_service" backend/core/registrations backend/main.py | wc -l
# Should match the pre-PR count from main.py

# All tests pass
nix run .#ci
```

## Acceptance criteria

- main.py reduced by at least 1500 LOC.
- Each registration module is <500 LOC.
- Service startup order, dependencies, and lifecycle are bit-identical
  to pre-PR (verify via `service_registry.export_dependency_diagram()`
  output if possible).
- The "Phase 3" TODOs in main.py either resolved or migrated to issue.
- ADR? **Optional** \u2014 this is structural cleanup, not a new pattern.
  A short note in `docs/architecture/backend.md` is enough.

## Stop-and-ask if

- An extraction reveals that two domains share state via a hidden
  global. That's a deeper coupling problem; document and proceed
  carefully \u2014 don't paper over it with a circular import.
- A `_init_X` function depends on app-construction-time state
  (e.g. `app.state.something`) that isn't yet set. The boundary
  between "registration time" and "lifespan time" needs to be clear.

## Risk

High volume but mechanically simple. The risk is mis-ordering startup
stages. Mitigation: run the app after each domain extraction and check
the dependency-diagram log line in startup output matches the
pre-extraction snapshot.
