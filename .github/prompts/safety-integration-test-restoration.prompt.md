# Subagent task: restore tests/test_safety_integration.py

You are picking up work mid-stream on `fix/test-suite-restoration-2`,
which is branched off the latest `main` of the
[carpenike/coachiq](https://github.com/carpenike/coachiq) repo.

## Read first

These three repo-memory files set the framing — start here, in this
order:

1. `/memories/repo/coachiq-architecture.md` — pins what CoachIQ IS and
   IS NOT. CoachIQ is a CAN-bus orchestration layer that talks to a
   Firefly MIRA panel, **not** a safety-critical system in the
   aerospace / DO-178C sense. The `safety_*` names in this codebase
   are API guardrails, not vehicle safety (Firefly owns that).
2. `/memories/repo/coachiq-state.md` — repo state snapshot.
3. `/memories/repo/handoff-2026-05-11.md` — handoff from PR #89,
   including methodology and house rules.

## The job

Restore `tests/test_safety_integration.py` from
**0 passed / 14 errors / 0 failed** to **14/0/0** without skipping
any tests, and fix any production drift the failures point at.

## Current state (already committed on this branch)

Two commits on `fix/test-suite-restoration-2` already addressed
production gaps surfaced by this cluster's triage; you don't need to
redo them:

- `2510827` — `NotificationAnalyticsService` constructor wiring fix
  (unrelated cluster, but on the same branch).
- `664bac5` — added `ServiceStatus.STOPPED` to the enum, made
  `_shutdown_service` actually update status post-shutdown, and fixed
  a silent bug in `persistence_repository._cleanup_old_backups`
  (offset-naive vs offset-aware datetime comparison).

After those, the cluster still fails 14/14 with a new error:

```
TypeError: EnhancedServiceRegistry.register_service() got an
unexpected keyword argument 'service'
```

## What's broken (the 14 remaining errors)

All 14 errors trace back to the `integrated_system` fixture at
`tests/test_safety_integration.py:235-269`. The fixture calls:

```python
service_registry.register_service(
    name=name,
    service=service,                         # WRONG: kwarg doesn't exist
    dependencies=config.get("depends_on", []),
    is_critical=config.get(...) in [...],    # WRONG: kwarg doesn't exist
)
```

But `EnhancedServiceRegistry.register_service` (in
`backend/core/service_registry.py:316-350`) actually accepts:

```python
def register_service(
    self,
    name: str,
    init_func: Callable[[], Any],          # NOT 'service'
    dependencies: list[str | ServiceDependency] | None = None,
    tags: set[str] | None = None,          # NOT 'is_critical'
    description: str | None = None,
    health_check: Callable[[], bool] | None = None,
) -> None: ...
```

Two more drift points the fixture hits later:

- Tests call `await service_registry.startup()` -- but on
  `EnhancedServiceRegistry`, that hits the base-class method which
  iterates the (empty for ESR) `_startup_stages` list and does
  nothing. The actual startup method on ESR is `startup_all()` (line
  369). The base class's `startup()` is for a different (legacy)
  registration model where you call `register_startup_stage()`
  instead of `register_service()`.
- The fixture builds pre-instantiated `RealWorldService` objects and
  expects the registry to call `service.startup()` on them.
  `EnhancedServiceRegistry._start_service_with_di_and_metrics`
  (line ~485) **does** call `service.startup()` after
  `init_func()` returns -- but only if `init_func` returned a
  fully-built service instance. The fixture currently passes the
  instance directly via `service=`; you need to wrap it in a
  trivial callable.

## Suggested fixture rewrite

```python
@pytest.fixture
def integrated_system(rv_system_config):
    """Create integrated RV system for testing."""
    service_registry = EnhancedServiceRegistry()

    services = {}
    for name, config in rv_system_config.items():
        service = RealWorldService(
            name=name,
            safety_classification=config.get("safety_classification", "operational"),
        )
        service.enabled = config.get("enabled", True)
        services[name] = service

        # `init_func` must be a callable that returns the service
        # instance. Use a default-arg lambda so each iteration captures
        # its own `service` (avoids the classic late-binding closure bug).
        # Use a tag set instead of the legacy `is_critical=` kwarg.
        tags = set()
        if config.get("safety_classification") in ["critical", "safety_related"]:
            tags.add("critical")

        service_registry.register_service(
            name=name,
            init_func=lambda s=service: s,
            dependencies=config.get("depends_on", []),
            tags=tags,
        )

    safety_service = SafetyService(
        service_registry=service_registry,
        health_check_interval=0.1,
        watchdog_timeout=2.0,
    )

    return {
        "service_registry": service_registry,
        "safety_service": safety_service,
        "services": services,
    }
```

Then update every `await service_registry.startup()` in the test
bodies to `await service_registry.startup_all()` (use grep --
there are several occurrences).

## What to expect downstream

After the fixture is fixed, you'll likely surface a second wave of
issues in the test bodies themselves. Audit:

- `service_registry.get_service_status(name)` — verify it exists on
  EnhancedServiceRegistry and returns a `ServiceStatus`.
- `service_registry.check_system_health()` — verify it exists.
- `safety_service.trigger_emergency_stop(reason)` /
  `reset_emergency_stop(authorization)` /
  `_emergency_stop_active` / `get_safety_status()` /
  `get_audit_log()` / `start_monitoring()` — these mostly exist
  per `grep` (see `backend/services/safety_service.py`), but
  signatures may have drifted.

## Methodology

For each failure:

1. Run the test, look at FIRST failure with `--tb=short`.
2. Decide: API drift (test stale), real bug, or fixture issue.
3. If stale: update the test.
4. If real bug: **fix production code** and call it out in the commit
   message. The previous PR #89 found 14 production bugs; commits
   `2510827` and `664bac5` on this branch found 3 more (#15-17). Keep
   counting.
5. Re-run cluster, repeat until clean.
6. **Always run the wider sanity check** before committing:

   ```bash
   nix develop --command bash -c 'poetry run pytest \
     tests/test_rvc_decoder_comprehensive.py \
     tests/integration/test_canbus_decoder_integration.py \
     tests/integrations/rvc/test_phase1_improvements.py \
     backend/integrations/can/tests/test_tx_rate_limiter.py \
     tests/services/test_notification_queue.py \
     tests/services/test_async_notification_dispatcher.py \
     tests/services/test_persistence_service.py \
     tests/services/test_vector_service.py \
     tests/services/test_docs_service.py \
     tests/services/test_config_service.py \
     tests/api/test_safety_pin_endpoints.py \
     tests/test_pin_security.py \
     tests/test_safety_integration.py \
     --no-cov -q --tb=line 2>&1 | tail -5'
   ```

## House rules (non-negotiable)

- Never skip tests — fix them. The user explicitly said "don't be lazy."
- Commit messages explain WHY + HOW, not just WHAT.
- **Production bugs caught by tests are wins** — call them out
  explicitly with a line like "Production bug found and fixed: ...".
- No new `# nosec` / `# noqa` / `# type: ignore` without inline
  rationale.
- Architectural framing: consumer-grade backend, NOT safety-critical.
- The Stage-1 CI gate is line-level diff-aware
  (`scripts/ruff_diff_check.py`), so only NEW issues on lines you
  touch will block. Whole-file pre-commit hooks (ruff-format, bandit)
  still run on the changed file set.
- User's shell is fish — `bash -lc "..."` wrapper for any
  bash arithmetic / heredocs.
- Pre-push hook runs CI locally; use `--no-verify` to bypass it
  during iteration. CI will catch issues anyway.

## Files NOT to touch without asking

- `wip/security-rpi-hardening-2025` branch.
- `config/2021_Entegra_Aspire_44R.yml` (real coach mapping).
- The 3 notification managers (notification_manager.py,
  safe_notification_manager.py, notification_lightweight.py) —
  intentional safety/perf tiers, not duplicates.

## What "done" looks like

- `tests/test_safety_integration.py`: 14/14 passing.
- The wider sanity check shows zero regressions (the
  test_async_notification_dispatcher::test_force_queue_processing
  pollution failure is a known pre-existing issue per handoff
  memory; ignore that one if you see it).
- A focused PR onto `main` with one or more commits whose messages
  explain each design decision and call out every production bug
  found.
- `./scripts/ci-quality-gate.sh` passes locally.

## Branch / PR convention

Either keep working on `fix/test-suite-restoration-2` and add this
work to PR-X (whatever number that branch becomes), or cut a fresh
branch off the latest `main` (after `fix/test-suite-restoration-2`
merges) named something like `fix/safety-integration-test-restoration`.

If you fork a separate branch, reference commits `2510827` and
`664bac5` in your PR description as prerequisites — those will
already be on main by the time you start.
