# Backend Architecture

The CoachIQ backend is a Python 3.12 + FastAPI service that talks to
the OEM Firefly MIRA panel over RV-C / J1939 CAN. Architecturally it
plays the same role as a smart wall-switch or HMI: it emits well-formed
CAN frames; the OEM controller decides whether to act on them.

For the architectural framing (what CoachIQ is and is not, the realistic
threat model, why we calibrate code quality to "good consumer-grade
backend" rather than aerospace), see
[`/memories/repo/coachiq-architecture.md`](../../memories/repo/coachiq-architecture.md)
or, once it lands, `docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md`.

## Top-level layout

```text
backend/
├── main.py               # ASGI app construction + service registration
├── api/
│   ├── routers/          # Legacy /api/* endpoints (incl. events.py, the /api/events SSE stream)
│   ├── domains/          # Domain API v1 (/api/v1/*)
│   └── router_config.py  # Mounts every router on the app
├── core/
│   ├── config.py         # Pydantic Settings (COACHIQ_* env vars)
│   ├── dependencies.py   # FastAPI Depends(get_*) helpers
│   ├── service_registry.py  # EnhancedServiceRegistry
│   ├── safety_state_engine.py
│   ├── service_dependency_resolver.py
│   ├── exception_handlers.py
│   └── exceptions.py
├── services/             # Business logic; constructor-injected
├── repositories/         # Data access; see repository-pattern.md
├── integrations/
│   ├── can/              # CAN bus + multi-network manager
│   ├── rvc/              # RV-C decoder, Firefly extensions
│   ├── j1939/            # J1939 decoder, Spartan K2 extensions
│   ├── analytics/        # PerformanceAnalyticsFeature
│   └── diagnostics/      # Cross-protocol diagnostics
├── middleware/           # Auth, CSRF, structured logging, etc.
├── models/               # Pydantic request/response models
├── schemas/              # Zod-exportable schemas for the frontend
├── websocket/            # Diagnostic WebSocket routes (logs, CAN tools) + auth handler
└── alembic/              # SQLite migrations
```

## Component flow

```mermaid
flowchart LR
    Client[Client / Browser] <--> FastAPI[FastAPI App]

    subgraph Backend
        FastAPI --> Routers[Routers /api/* + /api/v1/*]
        FastAPI --> SSE[SSE stream GET /api/events]
        FastAPI --> WS[Diagnostic WebSockets /ws/*]

        Routers -->|Depends| Services[Services]
        SSE --> Broker[EventBroker]
        Services -->|publish| Broker
        WS -->|Depends| Services

        Services --> Repos[Repositories]
        Services --> CAN[CAN Facade + Integrations]

        Repos --> DB[(SQLite via DatabaseManager)]
        Repos -.in-memory.-> Memory[Bounded in-memory state]
    end

    CAN <--> CANBus[CAN Bus]

    classDef client fill:#E1F5FE,stroke:#0288D1
    classDef api fill:#E8F5E9,stroke:#4CAF50
    classDef logic fill:#FFF3E0,stroke:#FF9800
    classDef data fill:#F3E5F5,stroke:#7B1FA2
    classDef hw fill:#FFEBEE,stroke:#F44336

    class Client client
    class FastAPI,Routers,SSE,WS api
    class Services,CAN,Broker logic
    class Repos,DB,Memory data
    class CANBus hw
```

The arrow from Routers to Services goes through FastAPI's `Depends(...)`
machinery (see [`repository-pattern.md`](repository-pattern.md) for the
canonical injection pattern). Services never reach back up to routers,
and they never reach across to other services without the registry
making the dependency explicit.

## Service lifecycle

1. **Construction** (in `backend/main.py`'s `_init_*` functions):
   each service is built with its dependencies passed as constructor
   arguments. This is also where dependency edges get declared
   (e.g. `EntityService` depends on `entity_state_repository`).

2. **Registration** (still in `main.py`): each constructed service is
   handed to `EnhancedServiceRegistry.register_service(name, init_func,
   dependencies)`.

3. **Stage planning**: at startup the registry's
   `ServiceDependencyResolver` builds a topological order of services
   and groups them into stages that can run concurrently. The startup
   log prints the stage plan.

4. **Startup**: `service_registry.startup_all()` runs each stage in
   order, awaiting all services in a stage in parallel.

5. **Lifespan**: services live for the duration of the FastAPI
   lifespan context. `service_registry.shutdown_all()` runs on
   shutdown in reverse stage order.

The registry has hardened semantics for missing-dependency detection,
circular-dependency detection, and a `fallback=` mechanism where a
service can declare an alternative dependency if the primary isn't
registered (see PR #135 for the bug fix that made `fallback=` actually
work in stage planning).

## API surface

Two API namespaces coexist:

- **`/api/*`** -- legacy routers under `backend/api/routers/`. Most of
  these are still active (auth, health, CAN tools, schemas, victron,
  location, etc.), and the realtime SSE endpoint (`/api/events`) also
  lives here. Legacy endpoints are retired endpoint-by-endpoint once a
  domain replacement covers them (notably `/api/entities` and
  `/api/missing-dgns`, both removed during the 2026-05 refactor); see
  [ADR-0003](../adr/ADR-0003-api-v2-only-no-legacy.md).

- **`/api/v1/*`** -- domain API under `backend/api/domains/` (auth,
  diagnostics, entities, networks, system). Mounted unconditionally by
  `register_all_domain_routers` in `backend/api/domains/__init__.py`.
  There are no feature flags around domain routes; they are always on.
  The public naming settled on `/api/v1` per
  [ADR-0011](../adr/ADR-0011-public-api-v1-naming.md) (the earlier
  v2 prefix was an internal migration label).

The legacy `/api/entities` -> `/api/v1/entities` transition is documented
in PR #126's docstring (and tested by
`tests/contract/test_domain_api_spec_validation.py`).

## State and data

- **SQL state** lives in SQLite via `DatabaseManager`. Migrations are
  managed by Alembic (`backend/alembic/`) and are applied at startup
  by `DatabaseUpdateService`.
- **In-memory state** (e.g. last-known entity values, CAN message
  history, system-state snapshots) lives in repositories with bounded
  collections to prevent memory growth. The
  `SystemStateRepository` is intentionally pure-in-memory.
- **Configuration** comes from Pydantic `Settings` driven by
  `COACHIQ_*` env vars. See `backend/core/config.py` and
  `docs/architecture/configuration-loading.md`.

## Real-time updates

App-wide realtime state rides one authenticated Server-Sent Events
stream: `GET /api/events` (`backend/api/routers/events.py`). The
endpoint sits behind the standard `AuthenticationMiddleware`
(`Authorization: Bearer` header — it is *not* an excluded path), sends
a `retry: 3000` reconnect hint, heartbeats every 15 s with an SSE
comment, and replays missed events when a reconnecting client sends
`Last-Event-ID`.

Behind it sits the `EventBroker`
(`backend/services/system/event_broker.py`): an in-process fan-out hub
with monotonic event ids, a 1000-event replay ring buffer, and bounded
per-client queues that drop the oldest event rather than stall the CAN
RX path. It is wired in the composition root
(`backend/core/composition_root.py`) and injected via `EventBrokerDep`
(`backend/core/dependencies.py`). Producers are `EntityService`,
`EntityDomainService`, `VictronService`, and `CANBusService`.

When a CAN message decodes into an entity-state change:

1. The decoder writes the new state into `EntityStateRepository`.
2. The owning service publishes an `entity_update` event
   (`{entity_id, entity_data}`) to the `EventBroker`.
3. Connected SSE clients see the update in <100ms typical; commands
   flow the other way over plain REST.

WebSockets remain only for page-scoped CAN diagnostic streams
(`backend/websocket/routes.py`): `/ws/can-sniffer`, `/ws/can-recorder`,
`/ws/can-analyzer`, and `/ws/can-filter`. Live logs stream over SSE at
`GET /api/logs/stream` (admin-only). The old `/ws` entity-data socket
(and `/ws/logs`, `/ws/network-map`, `/ws/features`, `/ws/security`)
were removed when the SSE streams landed.

## See also

- [Repository Pattern](repository-pattern.md) -- the data-access
  layer.
- [Configuration Loading](configuration-loading.md) -- how
  `rvc.json`, coach mappings, and `COACHIQ_*` env vars resolve.
- [Overview](overview.md) -- top-level system diagram.
- `backend/main.py` -- the source of truth for every service
  registration.
- `backend/core/service_registry.py` -- the registry implementation.
