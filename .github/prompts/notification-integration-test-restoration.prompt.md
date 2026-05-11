# Subagent task: restore tests/integration/test_notification_integration.py

You are picking up work on the test-suite restoration project for
[carpenike/coachiq](https://github.com/carpenike/coachiq), branched
off the latest `main`.

## Read first

1. `/memories/repo/coachiq-architecture.md` — pins what CoachIQ IS
   and IS NOT.
2. `/memories/repo/coachiq-state.md` — repo state snapshot.
3. `/memories/repo/handoff-2026-05-11.md` — methodology + house rules.

## The job

Restore `tests/integration/test_notification_integration.py` from
**3 passed / 5 failed / 1 skipped / 8 errors** to all-green without
skipping any tests, and fix any production drift the failures point
at.

## What's broken (categorised)

### Group A: Pydantic v2 extra-field strictness on routing rules

`TestNotificationRoutingIntegration::test_user_preference_routing` and
`test_custom_routing_rules` fail with errors like:

```
debounce_minutes
  Extra inputs are not permitted [type=extra_forbidden, input_value=1, ...]
```

Either the routing rule model has tightened `model_config = ConfigDict(extra="forbid")`
without adding the fields tests expect, or the tests are passing
fields that genuinely no longer exist. Audit the model in
`backend/services/notification_routing.py` (or similar) against the
test's expectations.

### Group B: TestEmailTemplateIntegration ERRORS

3 tests in `TestEmailTemplateIntegration` error out at setup. Likely
a fixture issue or a template-engine constructor signature drift.
Investigate `--tb=long` on the first error.

### Group C: TestSafeNotificationManagerIntegration ERRORS

3 tests error at setup. `SafeNotificationManager` has its own complex
API surface. Likely fixture drift around the constructor or its
dependencies.

### Group D: Performance test ERRORS

`TestNotificationSystemPerformance::test_high_volume_notification_processing`
and `test_rate_limiting_under_load` error at setup. May be downstream
of B or C, or a separate fixture issue.

### Group E: Queue persistence + retry/DLQ failures

`TestNotificationQueueIntegration::test_queue_persistence_across_restarts`
and `test_queue_retry_and_dlq` fail with `assert 0 == 1`. Tests
expect the queue to recover state across simulated restarts; verify
the persistence layer and DLQ wiring are intact.

### Group F: Mock-based dispatcher test

`TestMockedServiceIntegration::test_dispatcher_processing_with_mocks`
fails with `assert 0 >= 1`. Likely the dispatcher isn't being
triggered, or the mocks don't simulate the right surface.

## Methodology

1. Run cluster with `--tb=line` to get the full failure list
2. For each, run with `--tb=short` or `--tb=long` to get traceback
3. Decide: API drift (test stale), real bug, or fixture issue
4. Fix and re-run
5. Sanity-check across all 14 fixed clusters before each commit

## House rules (same as previous prompts)

- Never skip tests
- Production bugs caught by tests are wins; call them out in commits
- The branch `fix/test-suite-restoration-2` already accumulated 7+
  production-bug fixes via this restoration sweep; keep counting
- No new noqa/nosec/type:ignore without inline rationale
- Architectural framing: consumer-grade backend, NOT safety-critical
- Stage-1 CI gate is line-level diff-aware; only NEW issues block

## Files NOT to touch without asking

- `wip/security-rpi-hardening-2025` branch
- `config/2021_Entegra_Aspire_44R.yml`
- The 3 notification managers (notification_manager.py,
  safe_notification_manager.py, notification_lightweight.py) —
  intentional safety/perf tiers, NOT duplicates. You will likely
  need to MODIFY safe_notification_manager.py for the ERROR tests
  in Group C, but don't attempt to consolidate the three managers.

## Sanity-check command

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
  tests/test_webhook_channel.py \
  tests/integration/test_notification_integration.py \
  --no-cov -q --tb=line 2>&1 | tail -5'
```

The known pre-existing failure
`test_async_notification_dispatcher::test_force_queue_processing`
(passes in isolation, fails in full-suite due to test pollution)
should be ignored.

## Branch / PR convention

Cut a fresh branch off `main` (after PR for `fix/test-suite-restoration-2`
merges). Name something like `fix/notification-integration-test-restoration`.
