---
mode: "agent"
description: "A10 \u2014 Rename ConfigService and ConfigurationService to reflect what they actually do"
---

# A10 \u2014 Rename `ConfigService` and `ConfigurationService`

Audit cycle: 2026-05-13 architectural audit.

## Why

Three things have "config" in the name and do different jobs:

| Class | Location | What it does |
|---|---|---|
| `Settings` | `backend/core/config.py` (1933 LOC) | Pydantic env-driven app config (canonical) |
| `ConfigService` | `backend/services/config_service.py` (100 LOC) | Wrapper over `RVCConfigRepository` for PGN/coach lookups |
| `ConfigurationService` | `backend/core/configuration_service.py` (356 LOC) | TTL-cached YAML/JSON loader for DGN/mapping/spec files |

`copilot-instructions.md` says *"ConfigService: ALWAYS use for
configuration access"*. Reality: 49 modules import `get_settings`
directly; 48 use `ConfigService`. They are not interchangeable; the
docs are wrong.

## The job

1. **Rename `backend/services/config_service.py::ConfigService`** \u2192
   `RVCConfigFacade` (or `RVCConfigService` if you want to keep the
   `*Service` convention). It's an RVC-config facade, period.
2. **Rename `backend/core/configuration_service.py::ConfigurationService`** \u2192
   `RVCSpecLoader`. It loads spec files; the name should say so.
3. **Move both files** if the rename makes the location obvious:
   - `backend/services/rvc_config_facade.py`
   - `backend/integrations/rvc/spec_loader.py` (if there's nothing
     else in `core/` that would orphan it)
4. **Drop the misleading copilot-instructions.md claim** that
   `ConfigService` is the canonical config interface. `Settings` IS
   the canonical app config; that's idiomatic Pydantic-Settings.
5. Update the registry key (`"config_service"` \u2192 `"rvc_config_facade"`).
6. Update routers + their typed aliases (coordinate with A7).

## Verification

```bash
# Confirm no lingering references
grep -rn "ConfigService\|configuration_service\|ConfigurationService" backend/ tests/ --include="*.py" | grep -v __pycache__ | grep -v "rvc_config\|RVCConfig\|RVCSpec"

# Should be empty after the rename
```

## Acceptance criteria

- New names land; old names are gone.
- `copilot-instructions.md` updated to remove the misleading claim.
- A short note in `docs/architecture/configuration-loading.md`
  explaining the three-layer split (`Settings` for app config,
  `RVCConfigFacade` for runtime PGN/coach queries, `RVCSpecLoader`
  for loading the spec files from disk).
- All tests pass.

## Stop-and-ask if

- A consumer is using `ConfigService` for something OTHER than RVC
  PGN/coach lookups. That's a signal the file accreted responsibility
  and the rename + extract is bigger than expected.
- The `ConfigurationService` cache TTL behavior is depended on by
  hot-reload code paths. The rename shouldn't change behavior, but
  flag any subtleties.

## Risk

Low\u2013medium. Mostly mechanical rename + import updates. Coordinate
with A7 if it's already in flight (typed DI for the renamed classes
needs the new types).

## Optional: ADR-0008-rvc-config-facade-naming.md

Short ADR (~one page) explaining the three-tier config layering
(Settings vs RVCConfigFacade vs RVCSpecLoader) so future contributors
don't re-merge them.
