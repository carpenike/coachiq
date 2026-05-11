# Subagent task: restore tests/services/test_pin_manager_db.py

You are picking up work on the test-suite restoration project for
[carpenike/coachiq](https://github.com/carpenike/coachiq). This task
follows commit `0474815` on `fix/test-suite-restoration-2`, which
added three missing public-API methods (`create_pin`, `rotate_pin`,
`deactivate_pin`) to `PINManager`.

## Read first

These three repo-memory files set the framing — read in order:

1. `/memories/repo/coachiq-architecture.md` — pins what CoachIQ IS
   and IS NOT (CAN-bus orchestration layer, NOT safety-critical).
   Realistic threats are API-side (auth bypass, session leak, etc.).
   PIN management directly serves the auth threat model.
2. `/memories/repo/coachiq-state.md` — repo state snapshot.
3. `/memories/repo/handoff-2026-05-11.md` — handoff from PR #89,
   methodology, house rules.

## The job

Restore `tests/services/test_pin_manager_db.py` from
**5 passed / 7 failed / 1 error** to **12+/0/0** without skipping
any tests, and fix any production drift the failures point at.

## Current state (already on the branch)

Commit `0474815` added three operator-facing methods to PINManager:

- `create_pin(user_id, pin, pin_type, description=None)` — wrapper
  over `set_pin` with arg order matching `validate_pin` and a clearer
  verb name. The method works; 5 tests now pass (PIN creation /
  duplicate / multiple types).
- `rotate_pin(user_id, pin_type, old_pin, new_pin)` — verifies old
  PIN, revokes the verification session, sets new PIN.
- `deactivate_pin(user_id, pin_type)` — soft-deletes via
  `is_active = False`.

The tests for `rotate_pin` and `deactivate_pin` themselves still
fail because they're downstream of the `validate_pin` API drift
described below.

## The remaining 7 failures + 1 error: validate_pin return-type drift

Every remaining failure traces to one root cause: `PINManager.validate_pin`
returns a **`PINValidationResult` Pydantic model** (defined in
`backend/services/pin_manager.py:81`) with these fields:

```python
class PINValidationResult(BaseModel):
    success: bool
    session_id: str | None = None      # populated only when success=True
    error_message: str | None = None
    lockout_until: datetime | None = None
```

The tests treat the return value as a **bare `session_id: str | None`**:

```python
session_id = await pin_manager_with_db.validate_pin(...)
assert session_id is not None        # success case
assert session_id is None            # failure case (wrong PIN, lockout, etc.)
```

There are 12 sites in `tests/services/test_pin_manager_db.py` that
need this pattern updated. The minimal-change rewrite is:

```python
result = await pin_manager_with_db.validate_pin(...)
session_id = result.session_id  # already None on failure (line 442/453/476/489 in pin_manager.py)
assert session_id is not None  # or `is None`
```

OR equivalently:

```python
result = await pin_manager_with_db.validate_pin(...)
assert result.success            # success case
assert not result.success        # failure case
```

The latter is more readable but requires fixing more lines in each
test. Use your judgement; document the convention you pick in a
brief module-level comment.

The 12 call sites are at lines: 150, 201, 233, 296, 304, 351, 374
(closure return -> needs different handling), 408, 455, 472, 480,
504. (Run `grep -n "validate_pin" tests/services/test_pin_manager_db.py`
to confirm if drift since.)

The closure case at line 374 (`return await pin_manager_with_db.validate_pin(...)`)
returns a list of `PINValidationResult` objects; the assertion below
is `assert all(sid is not None for sid in session_ids)` which needs
to become `assert all(r.success for r in results)`.

## The 1 ERROR (TestConcurrentOperations::test_concurrent_session_creation)

The pytest output shows this is an ERROR, not just a FAILED, which
usually means it failed during setup or teardown rather than during
the test body. Diagnose with `--tb=long` first; it may be related to
the SAWarning seen in the output (`Session.add() within flush
process`) which suggests a real concurrency issue in `_create_session`.
If it IS a real concurrency bug, fix it -- this is exactly the kind
of API guardrail issue the project's threat model cares about.

## Other failures to investigate

After fixing the validate_pin return-type drift, re-run the cluster.
If `test_lockout_after_failed_attempts` or other tests still fail,
check the `lockout_until` field handling — the production code
likely returns success=False with lockout_until set, but the tests
may be expecting an exception or a different shape.

Also `test_rotate_pin` and `test_deactivate_pin` -- these will
exercise the new methods I added in `0474815`. Verify the implementations
work correctly end-to-end (the methods compiled fine but I didn't
test them past unit construction; the `rotate_pin` validate-then-
revoke flow especially should be verified against the test
expectations).

## Methodology

For each test:

1. Run with `--tb=short`, identify root cause.
2. Decide: API drift (test stale), real bug, or fixture issue.
3. If stale: update the test.
4. If real bug: **fix production code** and call it out in the
   commit message.
5. Re-run, repeat until clean.
6. **Sanity check** before each commit:

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
     tests/services/test_pin_manager_db.py \
     --no-cov -q --tb=line 2>&1 | tail -5'
   ```

## House rules

- Never skip tests — fix them. User: "don't be lazy."
- Commit messages explain WHY + HOW.
- **Production bugs caught by tests are wins** -- call them out
  explicitly. PR #89 found 14, this branch has added 7+ more so far
  (NotificationReportingService constructor wiring; ServiceStatus.STOPPED
  + _shutdown_service status update; persistence backup cleanup
  datetime tz; webhook retry_delay int->float; webhook per-attempt
  vs per-notification stat semantics; webhook 4xx no-retry; webhook
  partial-success counter logic). Keep counting.
- No new `# nosec` / `# noqa` / `# type: ignore` without inline
  rationale.
- Architectural framing: consumer-grade backend, NOT safety-critical.
- The CI gate's Stage-1 ruff check is line-level diff-aware
  (`scripts/ruff_diff_check.py`); only NEW issues on changed lines
  block. Whole-file pre-commit hooks (ruff-format, bandit) still
  run on the changed file set.
- Pre-push hook runs the gate locally; use `--no-verify` to bypass
  during iteration.
- User's shell is fish — wrap heredocs in `bash -lc "..."`.

## Files NOT to touch without asking

- `wip/security-rpi-hardening-2025` branch.
- `config/2021_Entegra_Aspire_44R.yml` (real coach mapping).
- The 3 notification managers — intentional safety/perf tiers.

## What "done" looks like

- `tests/services/test_pin_manager_db.py`: all 12 tests passing
  (12+/0/0).
- The wider sanity check shows zero regressions (the
  `test_async_notification_dispatcher::test_force_queue_processing`
  pollution failure is a known pre-existing issue per handoff memory;
  ignore it).
- `./scripts/ci-quality-gate.sh` passes locally.
- A focused PR commit with a message that explains the validate_pin
  return-type drift decision, calls out any production bugs found
  in the rotate_pin / deactivate_pin verification, and addresses
  the concurrency error.

## Branch / PR convention

Either keep working on `fix/test-suite-restoration-2` (where the
0474815 PINManager work already lives), or wait until that branch
merges to main and cut a fresh branch. Reference commit `0474815`
in your PR description as the prerequisite.
