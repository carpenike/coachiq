"""
Per-domain ServiceRegistry registration modules.

Extracted from `backend/main.py` in audit cycle 2026-05-13 PR A8.

The registrations were originally one ~1500-LOC block in `main.py`.
Splitting into per-domain modules:
- Reduces PR contention on a single file.
- Closes the long-standing "Phase 3 -- needs constructor injection"
  TODOs by giving the work an obvious home.
- Makes the call graph visible: each module's `register(...)` function
  declares exactly which `ServiceRegistry.register_service` calls it
  contributes.

Convention: each module exports a `register(service_registry: GuardrailCoordinator) -> None`
function that `main.py.lifespan()` calls in dependency order.
"""
