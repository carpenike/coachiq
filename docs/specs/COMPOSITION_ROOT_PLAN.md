# Composition Root Migration Plan

**Status:** approved umbrella architecture, HOF-050
**Author:** Claude (HQ), grounded and graduated by Copilot
**Date:** 2026-06-30
**Component:** backend

This is the durable umbrella plan for replacing CoachIQ's generic
`ServiceRegistry` dependency-injection mechanism with typed composition-root
constructor injection. ADR-0014 records the architectural decision; this plan
captures the current dependency graph and phased migration constraints.

---

## 1. Goal

Construct backend services explicitly in one composition root, using typed object
references and constructor injection. Keep FastAPI `Depends` for request-time
access, but repoint dependency providers to the typed container instead of a
generic string-keyed registry.

Do not change user-visible behavior. The app must boot, shut down, report health,
and coordinate API guardrails as it does today.

## 2. Current Graph Seed

The HOF-050 review ran the current registration setup and resolver:

```python
registry = GuardrailCoordinator()
await _configure_service_startup_stages(registry)
stages = registry._resolver.resolve_dependencies()
```

The result was 68 services across 6 startup stages. This is the seed order for
the migration; do not hand-guess it.

### Stage 0

`app_settings`, `can_anomaly_detector`, `can_bus_recorder`,
`can_interface_service`, `can_message_filter`, `can_message_injector`,
`can_protocol_analyzer`, `can_tracking_repository`, `dashboard_service`,
`database_manager`, `diagnostic_handler`, `diagnostics_repository`,
`edge_proxy_monitor`, `performance_monitor`, `protocol_manager`, `rvc_config`,
`rvc_config_repository`, `system_state_repository`, `websocket_manager`.

### Stage 1

`analytics_dashboard_service`, `analytics_repository`, `auth_event_repository`,
`can_bus_service`, `can_command_repository`, `can_network_telemetry_service`,
`credential_repository`, `database_backup_repository`,
`database_connection_repository`, `database_migration_repository`,
`database_session_repository`, `device_discovery_service`,
`entity_config_repository`, `entity_history_repository`,
`entity_manager_service`, `entity_state_repository`, `mfa_repository`,
`migration_history_repository`, `migration_repository`, `persistence_repository`,
`rvc_config_facade`, `safety_repository`, `security_audit_repository`,
`security_config_repository`, `security_event_repository`,
`security_listener_repository`, `session_repository`, `token_service`.

### Stage 2

`attempt_tracker_service`, `can_facade`, `database_connection_service`,
`entity_initialization_service`, `entity_service`, `mfa_service`,
`migration_safety_validator`, `persistence_service`, `security_config_service`,
`security_event_service`, `session_service`.

### Stage 3

`database_migration_service`, `database_session_service`,
`database_update_service`, `lockout_service`, `pin_manager`,
`security_audit_service`.

### Stage 4

`auth_manager`, `command_guardrail_service`, `security_event_manager`.

### Stage 5

`entity_domain_service`.

## 3. Surface Inventory

Grounding counts from 2026-06-30:

- `register_service(`: 71 sites.
- `register_guardrail_service(`: 10 sites.
- `ServiceDefinition(`: 1 site.
- `create_service_dependency(`: 38 sites.
- `get_service(`: 71 sites.
- Raw `app.state` matches: 8.

The registration surface includes more than the four modules under
`backend/core/registrations/`:

- `backend/core/registrations/core_startup.py`
- `backend/core/registrations/group2_repositories.py`
- `backend/core/registrations/group2_services.py`
- `backend/core/registrations/phase4.py`
- `backend/repositories/service_registration.py`
- `backend/core/service_registration_database_update.py`
- `backend/core/guardrail_coordinator.py`
- `backend/core/service_registry.py`
- `backend/test_service_startup.py`

The last three are registry implementation/tests, but they still matter for the
deletion phase.

## 4. Direct Consumer Inventory

Repointing `dependencies.py` providers is necessary but not sufficient. Direct
registry consumers must also move to the typed composition-root container or
typed constructor arguments.

Known direct-consumer groups:

- `backend/main.py`: lifespan startup/shutdown, health/startup probes, logging
  integration, websocket/security handler setup, protocol manager access.
- Middleware: `backend/middleware/auth.py`, `backend/middleware/secure_auth.py`.
- Websocket code: `backend/websocket/auth_handler.py`,
  `backend/websocket/dashboard_handler.py`, `backend/websocket/handlers.py`, and
  service-backed websocket helpers.
- CAN services/integrations: `CANBusService`, CAN tools registration, anomaly
  detector, multi-network manager.
- Guardrails: `CommandGuardrailService` currently receives/uses registry access for
  command-halt coordination.
- Routers: health, protocols, diagnostics helpers, and any router using
  `create_service_dependency` directly.
- Legacy helper modules: `backend/core/service_patterns.py` and
  `backend/core/security_hardening.py` service access helpers.

Each implementation HOF must enumerate the relevant direct consumers with `rg`
before editing. Do not assume the typed FastAPI aliases cover all use sites.

## 5. Optional Dependency Semantics

The current resolver has 33 optional dependency edges and 0 runtime dependency
edges. Composition-root constructors must preserve the optional behavior by
passing either a typed instance or `None`, or by using an explicit deferred
setter where a runtime cycle or late availability is intended.

Important optional edges include:

- `auth_manager`: optional `mfa_repository`, `notification_service`,
  `mfa_service`.
- `security_event_manager`: optional `auth_manager`, `pin_manager`,
  `lockout_service`, `performance_monitor`.
- `database_manager`: optional database connection/session/migration services
  and `performance_monitor`.
- `websocket_manager`: optional CAN tracking and system-state repositories.
- CAN recorder/analyzer/filter/injector services: optional `websocket_manager`
  or security/audit collaborators.
- Dashboard/analytics services: optional repositories, performance monitor, and
  websocket manager.

Optional dependencies are not silently ignored in the new root. The constructor
call must make the optionality visible.

## 6. Guardrail Coordinator

Retire the generic DI role of `GuardrailCoordinator`, but preserve its
guardrail-domain behavior.

The replacement design must include a typed guardrail coordinator or explicit
composition-root/CommandGuardrailService responsibilities for:

- Service guardrail-tier metadata.
- Command-halt participant inventory.
- Command-halt coordination across explicit participants.
- Guardrail metadata reporting.
- Guardrail status summary compatible with current health/diagnostic behavior.

This is not vehicle safety. It is API guardrail behavior under ADR-0004, and it
must not disappear as collateral damage of removing the registry.

## 7. Entity/Websocket Cycle

The current resolved runtime graph is acyclic: `entity_service` depends on
`websocket_manager`, and `entity_domain_service` depends on both. The known cycle
is an import/type-annotation problem: importing the concrete `EntityService` type
from `dependencies.py` triggers websocket imports. The composition root should
not invent a runtime cycle here.

Keep the existing public `EntityService` alias stable until a phase explicitly
fixes the Python import boundary. A lazy import or protocol type may be needed
for typing, but that is separate from construction order.

## 8. Phasing

### Phase A - Introduce And Repoint While Bootable

Build the composition root and typed container. Keep compatibility with the
current registry only as needed during migration. Work by dependency-order
cluster:

1. Settings, performance monitor, database manager, and repositories.
2. Core facades and protocol services.
3. Auth/security services and guardrail coordinator.
4. CAN, websocket, entity, diagnostics, dashboard, and API-facing services.
5. Repoint `backend/core/dependencies.py` providers to the typed container.
6. Migrate direct `get_service()` consumers by cluster.

After each cluster, `backend/test_service_startup.py` must stay green and the
app must still boot.

### Phase B - Delete Registry And Registration Modules

Only after production code no longer references the registry:

- Delete `backend/core/service_registry.py` and dependency resolver code no
  longer needed by tests or tooling.
- Delete registration modules and helper registration files.
- Delete or rewrite registry-specific tests.
- Remove compatibility shims from `dependencies.py`.

Phase B is the deletion phase. Phase A must not claim full deletion success while
compatibility shims are still present.

## 9. Success Criteria For Implementation HOFs

Each implementation HOF must cite the real quality gate:

- `backend/test_service_startup.py` passes after every cluster.
- The app boots, shuts down, and health/startup probes work.
- Existing FastAPI typed dependency aliases remain import-compatible for router
  consumers.
- Direct registry consumers in the edited cluster are gone or explicitly
  deferred with a linked follow-up.
- No new `app.state` or module-level service singletons.
- Guardrail classification/command-halt/status behavior is preserved.
- `pyright backend` is at or below baseline and ratchets down when the migration
  removes `Any` surfaces.
- `scripts/ci-quality-gate.sh` and relevant marker suites pass for each phase.

## 10. Out Of Scope For The Umbrella

- Implementing the composition root under HOF-050 itself.
- Resuming OIDC/MCP work before Phase A establishes the clean construction base.
- Removing FastAPI `Depends` as the request-access mechanism.
- Treating guardrail behavior as a generic DI feature that can be
  discarded.
