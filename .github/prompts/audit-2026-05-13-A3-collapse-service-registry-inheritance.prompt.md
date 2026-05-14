---
mode: "agent"
description: "A3 \u2014 Collapse EnhancedServiceRegistry inheritance into a single ServiceRegistry"
---

# A3 \u2014 Collapse `EnhancedServiceRegistry(ServiceRegistry)` inheritance

Audit cycle: 2026-05-13 architectural audit.

## Why

`backend/core/service_registry.py` defines two registry classes:

- `ServiceRegistry` (lines ~56\u2013265): old `register_startup_stage` API,
  `_startup_stages` model. **No live instantiation in the repo.**
- `EnhancedServiceRegistry(ServiceRegistry)` (line ~295 onward):
  `register_service` / `_service_definitions` model with on-demand
  stage resolution. **The only registry actually used in `main.py`.**

The base's startup methods are inert when the subclass takes over \u2014
the file's own block comments admit this. The "Enhanced" prefix is a
refactoring leftover.

This is the classic v1+v2 mid-migration smell. Same pattern as the
audit's #103 (entity_service vs entity_services), #104 (notification
sprawl), and the upcoming A6 (security_event_manager v1+v2).

## The job

1. Inline the still-used base methods into `EnhancedServiceRegistry`.
2. Delete the base class.
3. Rename `EnhancedServiceRegistry` \u2192 `ServiceRegistry`.
4. Update imports across the codebase.
5. Delete `register_startup_stage` and `_startup_stages` if unused
   after the inline (they should be \u2014 main.py uses `register_service`).

## Verification commands

```bash
# Confirm nothing instantiates the base
grep -rn "ServiceRegistry()" backend/ --include="*.py" | grep -v EnhancedServiceRegistry | grep -v __pycache__

# Confirm register_startup_stage isn't used
grep -rn "register_startup_stage" backend/ --include="*.py" | grep -v __pycache__
# (If non-empty, those callers must be migrated to register_service first.)

# After rename, confirm no dangling EnhancedServiceRegistry references
grep -rn "EnhancedServiceRegistry" backend/ --include="*.py" | grep -v __pycache__
```

## Acceptance criteria

- One `class ServiceRegistry` in `backend/core/service_registry.py`.
- ~200 LOC removed (the dead base methods).
- All `from backend.core.service_registry import EnhancedServiceRegistry`
  rewritten to `import ServiceRegistry`.
- `nix run .#ci` passes.
- Pyright baseline ratcheted DOWN if applicable.

## Stop-and-ask if

- A test or a non-`main.py` consumer is found instantiating the bare
  `ServiceRegistry()` class. Migrate it first or document why it
  needs the simpler API.
- Removing the base class changes runtime behavior in a way that
  isn't a no-op (e.g. an MRO subtlety). If so, document and proceed
  carefully.

## Risk

Low. This is a structural rename + dead-method delete. No business
logic touched.
