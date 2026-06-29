# ADR-0008: Rename `ConfigService` and `ConfigurationService` to clarify the three-tier config layering

## Status

**Accepted**, 2026-05-14. Architectural-audit cycle 2026-05-13, PR A10
(closes #155).

## Context

Before this ADR, the codebase had three different things all called
"configuration", and the names hid which one was which:

| Class | File | What it actually did |
|---|---|---|
| `Settings` | `backend/core/config.py` | Pydantic-validated app configuration (server port, feature flags, persistence mode, etc.) |
| `ConfigService` | `backend/services/config_service.py` | Thin facade over `RVCConfigRepository` for PGN names and coach info |
| `ConfigurationService` | `backend/core/configuration_service.py` | TTL-cached YAML/JSON loader for RV-C spec and mapping files on disk |

Two specific bits of wreckage flowed from this naming:

1. **`copilot-instructions.md` told contributors "ConfigService: ALWAYS
   use for configuration access."** That was wrong. `Settings` is the
   canonical app-configuration object, and most code already read
   `Settings` directly via `get_settings()`. `ConfigService` only knows
   about RV-C metadata; using it for a general app setting would
   crash. The instruction was steering humans and Copilot toward the
   wrong abstraction.
2. **`ConfigService` vs `ConfigurationService` were undistinguishable
   by name.** One was a request-time read API for parsed RV-C data;
   the other was a file-system spec loader with a TTL cache. Both
   answered to "the config service" in code review.

This was a maintenance hazard, not a runtime bug: the wiring was
correct, only the names were lying.

## Decision

1. **Three tiers, three distinct names**:

   | Tier | Class | New module | Role |
   |---|---|---|---|
   | App config | `Settings` | `backend.core.config` | Canonical app configuration, read via `get_settings()`. **No rename** -- this layer was already right. |
   | RV-C metadata facade | `RVCConfigFacade` (was `ConfigService`) | `backend.services.rvc.rvc_config_facade` | Thin request-time read API over `RVCConfigRepository` for PGN names and coach info. |
   | Spec-file loader | `RVCSpecLoader` (was `ConfigurationService`) | `backend.integrations.rvc.spec_loader` | TTL-cached loader for `rvc.json` / `coach_mapping.yml` / DGN spec files. Internal to the RV-C decoder; not a public service. |

2. **Renames are mechanical**: every call site moved from
   `ConfigService` -> `RVCConfigFacade` and from `ConfigurationService`
   -> `RVCSpecLoader`. The `ConfigurationLoadError` exception was
   renamed to `RVCSpecLoadError` for symmetry. The `ServiceRegistry`
   key `"config_service"` became `"rvc_config_facade"`.

3. **Public DI exports follow the rename**: `get_config_service` ->
   `get_rvc_config_facade`, and the typed alias `ConfigService` (which
   was actually `Annotated[ConfigService, Depends(...)]`) was replaced
   with `RVCConfigFacade`. There is no back-compat alias.

4. **`copilot-instructions.md` was rewritten** to drop the misleading
   "ALWAYS use ConfigService" guidance and to document the three
   tiers explicitly.

## Out of scope (deferred)

- `RVCSpecLoader` was, in production code, only imported by tests at
  the time of this rename -- it had been replaced earlier by a
  repository-backed path. Auditing whether `RVCSpecLoader` is dead
  code worth deleting is a separate cleanup; this ADR only handles
  the rename.
- The `CONFIGURATION_SERVICE = "configuration_service"` enum value in
  `backend/integrations/can/performance_monitor.py` is a string
  category label, not a service-registry key, and is left as-is.
- The environment variable
  `COACHIQ_CANBUS_DECODER_V2__ENABLE_CONFIGURATION_SERVICE` is a
  feature-flag name distinct from a class name. It is left as-is to
  avoid breaking external NixOS deployments.
- A handful of cosmetic strings in tests (test class names like
  `TestConfigServiceConstruction`, docstring labels) still mention the
  old names. These were intentionally not renamed: they are local
  test labels, not API surface.

## Consequences

- **Positive**: The three "configuration" concepts now have distinct
  names that match their roles. Reading `Settings` directly is the
  obvious path for app config, and `RVCConfigFacade` cannot be
  mistaken for the canonical config object.
- **Positive**: The docs no longer steer contributors at the wrong
  abstraction.
- **Cost**: ~10 backend call sites + 3 test files were updated. All
  changes were mechanical; no behavior changed.

## References

- Issue #155: A10 -- Rename `ConfigService` and `ConfigurationService`
- Audit prompt:
  `.github/prompts/audit-2026-05-13-A10-config-service-rename.prompt.md`
- ADR-0006: Typed dependency injection (the tier-distinguishing
  pattern this rename reinforces)
- ADR-0007: Auth service namespace (sibling rename in the same audit
  cycle)
