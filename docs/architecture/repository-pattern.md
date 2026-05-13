# Repository Pattern

## Status
Implemented and stable as of 2026-05-13. No outstanding migration work.

## Why
Backend state used to live in a monolithic `AppState` object that every
service imported and mutated directly. That made testing painful (you had
to construct a real `AppState` for every unit test), enforced no
boundaries between subsystems, and made dependencies invisible.

The current pattern decomposes that into:

- **Repositories** (`backend/repositories/`): own a single concern's data
  (entity state, RV-C config, CAN tracking, security audit log, etc.).
  Take only what they need at construction time (typically a
  `DatabaseManager` and/or a `PerformanceMonitor`).
- **Services** (`backend/services/`): take repositories as constructor
  arguments. Pure business logic on top of repositories. No global state.
- **Routers** (`backend/api/routers/` and `backend/api/domains/`): use
  FastAPI's `Depends(...)` to receive services. They never touch
  repositories directly.

`AppState` was deleted in PR #109 (2026-05-12); the legacy
`backend/core/state.py` (-609 LOC) and the `dependencies_v2` shim are
both gone.

## How — service development

Use constructor injection. Type-hint everything. Never reach for a
service-locator / global registry from inside a service.

```python
# backend/services/example_service.py
from backend.repositories import EntityStateRepository, SystemStateRepository


class ExampleService:
    def __init__(
        self,
        entity_state_repo: EntityStateRepository,
        system_state_repo: SystemStateRepository,
    ) -> None:
        self._entity_repo = entity_state_repo
        self._system_repo = system_state_repo

    async def do_something(self, entity_id: str) -> dict:
        entity = self._entity_repo.get_entity(entity_id)
        # ...
```

The service is constructed once during startup by
`backend.main._init_*` and registered with the
`EnhancedServiceRegistry` (see `backend/core/service_registry.py`).
Dependency order is declared at registration time and resolved
automatically by the registry's stage planner.

## How — router development

Routers use `Depends(get_*)` from `backend/core/dependencies.py`. The
canonical shape uses `Annotated` for type-checker friendliness:

```python
# backend/api/routers/example.py
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.core.dependencies import get_example_service
from backend.services.example_service import ExampleService

router = APIRouter(prefix="/api/example", tags=["example"])


@router.get("/{entity_id}")
async def get_thing(
    entity_id: str,
    service: Annotated[ExampleService, Depends(get_example_service)],
) -> dict:
    return await service.do_something(entity_id)
```

Each `get_*` helper resolves the named service from the registry. If the
service was never registered (or registry init hasn't run, e.g. in a
test that skips lifespan), the helper raises `RuntimeError` -- catch it
in your test setup by overriding the dependency on the FastAPI app:

```python
app.dependency_overrides[get_example_service] = lambda: my_mock_service
```

See `tests/api/test_safety_pin_endpoints.py` for the canonical
per-router test pattern.

## How — testing

Repositories are easy to mock because they have small, focused
interfaces:

```python
def test_example_service():
    mock_entity_repo = MagicMock()
    mock_system_repo = MagicMock()

    service = ExampleService(
        entity_state_repo=mock_entity_repo,
        system_state_repo=mock_system_repo,
    )
    # ...
```

For service constructor-shape questions, check the real signature in
`backend/services/<service>.py` and pass real repositories where
practical -- that exercises more of the stack than mocks do.

## Repositories that exist today

The full list lives in `backend/repositories/__init__.py`. Notable
ones:

- `EntityStateRepository` -- entity state + last-known-brightness +
  config payloads.
- `RVCConfigRepository` -- parsed `rvc.json` / coach mapping data.
- `CANTrackingRepository` -- in-flight CAN message stats and history.
- `SystemStateRepository` -- system-level state (operational mode,
  emergency-stop status, etc.).
- `DatabaseUpdateRepository`, `DatabaseRepository` -- migration
  history + raw DB session access for service consumers.
- `SecurityAuditRepository`, `SecurityEventRepository`,
  `JournalRepository` -- security and audit logging.
- `PersistenceRepository` -- backup metadata + filesystem operations.

Most repositories take a `database_manager` (for SQL access) and a
`performance_monitor` (for instrumented timings) at construction. A
few are pure in-memory (`SystemStateRepository`) and take no
arguments. Look at the `_init_*_repository` functions in
`backend/main.py` for the canonical construction calls.

## What this is NOT

- It is not a clean-architecture / hexagonal / ports-and-adapters
  scheme. We don't define abstract repository interfaces and bind
  concrete implementations at runtime. Repositories are concrete
  classes; services depend on them directly.
- It is not a mediator / CQRS pattern. Services call repository
  methods directly, not through commands or events.
- It is not feature-flagged. There are no `repository_pattern.enabled`
  toggles, no `migration_mode: gradual`, no `fallback_to_app_state`
  branches. The migration is done.

## See also

- `backend/core/dependencies.py` -- canonical `get_*` injection
  helpers.
- `backend/core/service_registry.py` -- the EnhancedServiceRegistry
  that owns service lifecycle.
- `backend/main.py` -- where every repository and service is
  constructed and registered (search for `_init_*` functions).
- `tests/api/test_safety_pin_endpoints.py` -- canonical per-router
  test pattern with `app.dependency_overrides`.
