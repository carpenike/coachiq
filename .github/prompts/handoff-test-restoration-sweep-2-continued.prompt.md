# Subagent task: continue test-restoration sweep #2 (#105)

You are picking up a multi-session test-restoration project on
[carpenike/coachiq](https://github.com/carpenike/coachiq). The previous
session merged 11 PRs against the audit-2026-05-12 backlog. This prompt
is the handoff to keep going.

## READ FIRST (in this order)

1. `/memories/repo/coachiq-architecture.md` — what CoachIQ IS and IS NOT
   (CAN-bus orchestration layer, NOT safety-critical; Firefly MIRA owns
   the vehicle-safety case). Calibrates code-quality standards to
   "good consumer-grade backend", not aerospace.
2. `/memories/repo/coachiq-state.md` — repo state snapshot, including
   the canonical map of notification + entity services.
3. `/memories/repo/audit-2026-05-12.md` — the audit and the 11 PRs that
   merged from it, plus the Pydantic-Settings test-fixture lesson
   (see "Reusable insight" below — this is the most important
   lesson from the previous session).
4. `/memories/repo/handoff-2026-05-11.md` — methodology that proved
   itself across 16 PRs total. **THIS IS THE PLAYBOOK.** Don't deviate.

## State of `main` at handoff (2026-05-12 evening)

11 PRs merged this audit cycle (#109, #110, #111, #114, #115, #117,
#118, #119, #120, #121, #122). **−4521+ LOC**, **7 production bugs
caught + fixed**.

**Test suite snapshot on `main`:**

| Metric  | Value | Pass rate |
|---------|-------|-----------|
| Passed  | ~735  | ~89% |
| Failed  | ~58   |  |
| Errors  | ~26   |  |
| Skipped | ~25   |  |

**Quality gate status:**

- ruff: pragmatic-mode + `scripts/ruff_diff_check.py` (line-level)
- pyright: baseline 1455 errors, hardened ratchet (UP=fail, DOWN=fail+update)
- TypeScript: baseline 0 errors, hardened ratchet
- ESLint: pragmatic-mode + `scripts/eslint_diff_check.py` (line-level) +
  whole-project baseline 648 with hardened ratchet
- CI uses `fetch-depth: 0` so diff-checks work correctly (#118 fixed the
  shallow-clone false-positive bug)

## Top remaining clusters (ordered by failure+error count, as of last full-suite run)

These are estimates after the latest merges. Re-measure with the command
in "Useful commands" before you start — the totals shift as PRs land.

| Approx count | Cluster | Likely category |
|-------------|---------|------------------|
| ~10 | `tests/integration/test_safety_emergency_scenarios.py` | integration; might find real safety-validation drift |
| ~9  | `tests/unit/test_database_management_api.py` | constructor / DI drift |
| ~9  | `tests/api/test_entities.py` | API surface drift (entity facade is now the only entity service post-#111) |
| ~6  | `tests/test_api_missing_dgns.py` | downstream of #109's state.py removal |
| ~5  | `tests/services/test_notification_rate_limiting.py` | real bug? AdaptiveRateLimiter assertions failing |
| ~5  | `tests/services/test_core_services.py` | DI drift |
| ~5  | `tests/contract/test_domain_api_spec_validation.py` | slowapi `'State' object has no attribute 'limiter'` setup issue |
| ~3  | `tests/unit/test_performance_monitor.py` | small |
| ~3  | `tests/test_canbus_decoder_safety.py` | small; might be real safety-decoder drift |
| ~3  | `tests/core/test_entity_manager.py` | small |

## The patterns we've established

Every cluster touched in this audit has hit one of three patterns. When
you start a new cluster, your first task is to figure out which one
applies — the response is different for each.

### Pattern A: Tests assert against a designed-but-never-built API

Treatment: **skip-stub** with module-level `pytest.skip(...)` and a
docstring explaining what was being tested + why it's not relevant
anymore. Examples: PRs #109 (`test_state.py`), #111
(`test_entity_service.py`), #115 (notification scaffolding), #120
(v1→v2 migration parity tests).

Honest acceptance: pass count drops. That's correct — fake green from
non-functional coverage is strictly worse than acknowledged red.

### Pattern B: Tests assert against an older API contract

Treatment: **rewrite the tests** to match the current production API.
The production code is fine; the tests are stale. Examples: PRs
#119 (`test_configuration_service.py` — wrong filesystem layout),
#122 (`test_config.py` — pre-`COACHIQ_` env var prefix).

Honest acceptance: real coverage gain, no production bug fix.

### Pattern C: Tests are right, production has drifted

Treatment: **fix the production bug**, update tests if needed.
Examples: PR #121 (`SafeNotificationManager.notify()` was silently
swallowing `ValueError` from invalid `level` strings via too-broad
`except Exception:`).

Honest acceptance: real production bug caught + fixed. Call it out
in the commit message and PR description.

**Most clusters are Pattern A or B (no production bug).** Pattern C
yielded 7 prod bugs across 12 clusters in the audit so far — the
yield is real but lower than the first sweep's (which was running
against a longer-stale baseline).

## Critical Pydantic-Settings test fixture lesson (will save hours)

If a cluster touches `backend.core.config.Settings` or any
`NotificationSettings` / `CANSettings` / etc. subclass, you WILL hit
one or more of these traps. They are NOT obvious; debugging from
"AttributeError: Mock object has no attribute X" or "test fails for
no reason" wastes hours unless you know:

1. **`MagicMock(spec=NotificationSettings)` blocks ALL attribute access**
   on Pydantic v2 BaseSettings models. Field descriptors only materialize
   on instances, not on the class. `spec=` walks `dir(<class>)` and
   finds nothing.
   - Fix: construct a real instance with explicit defaults.
   - Repro: see PR #121 description.

2. **`patch.dict(os.environ, ..., clear=True)` does NOT prevent
   .env-file loading**. Pydantic's `SettingsConfigDict(env_file=".env")`
   reads the file independently. Dev machines with a populated `.env`
   will see different "defaults" than CI.
   - Fix: pass `_env_file=None` to the Settings constructor in tests.
   - Recommended helper:
     ```python
     def _settings_no_env_file(**kwargs) -> Settings:
         return Settings(_env_file=None, **kwargs)
     ```

3. **Pre-existing `COACHIQ_*` env vars pollute "isolated" tests**.
   Even after `patch.dict(..., clear=True)`, your shell may have set
   variables earlier in the pytest run.
   - Fix: a helper that strips `COACHIQ_*` before adding test-specific
     overrides:
     ```python
     def _isolated_env(env: dict[str, str]) -> dict[str, str]:
         base = {k: v for k, v in os.environ.items()
                 if not k.startswith("COACHIQ_")}
         base.update(env)
         return base
     ```

These three pitfalls together account for almost every Settings-related
test failure I've hit. Use the helpers from `tests/core/test_config.py`
(merged via PR #122) as the canonical reference.

## Methodology (proven across 16 PRs)

For each cluster:

1. **Cut a fresh branch off latest `main`**:
   `git checkout main && git pull --ff-only origin main && git checkout -b fix/<short-cluster-name>`

2. **See all failures briefly**:
   `nix develop --command bash -c 'poetry run pytest <path> --no-cov -q --tb=line'`

3. **Look at the FIRST failure with `--tb=short`** to decide the pattern:
   - Pattern A: API doesn't exist in production → skip-stub
   - Pattern B: API exists but shape changed → rewrite tests
   - Pattern C: API matches but behavior is wrong → fix production

4. **For Pattern A (skip stub)**: replace the entire file with a
   `pytest.skip(allow_module_level=True)` stub and a docstring
   explaining what was being tested + why it's gone. Reference the
   removal PR and the issue (#105). Don't keep dead test code "for
   reference" — git history is the reference.

5. **For Pattern B (rewrite)**: rewrite incrementally. Start with the
   fixture (often the source of half the failures). Run tests after
   each change. Don't rewrite tests that already pass — leave them
   alone unless you're changing the fixture they depend on.

6. **For Pattern C (prod bug)**: make the production fix as small as
   possible. Lift one validation. Add one parameter. Don't refactor.
   Then update the test if needed to match the corrected behavior.

7. **Run the cluster** to confirm green.

8. **Run `scripts/ruff_diff_check.py origin/main`** to verify no NEW
   ruff issues. (You'll need to commit your changes first; the diff-
   check operates on commits, not the working tree.)

9. **Commit per cluster** with a detailed message explaining:
   - Which pattern (A, B, or C) and why
   - Production bugs caught (if any) — call them out specifically
   - Test suite delta (before/after pass/fail/error counts)
   - What you DID NOT do (so reviewers can scope follow-up work)

10. **Open a PR** referencing #105 (sweep #2). Use the existing PRs
    as templates for the description.

## When to stop and ask the user

- A cluster appears to require an **architectural change**
  (e.g. a service rewrite, a feature flag system being re-introduced).
- More than **3 production bugs** surface in a single cluster — that's
  a sign the cluster is guarding a bigger drift than expected, and
  you want a human to confirm the scope before you change a lot of
  production code.
- The "fix" requires breaking an established API contract.
- You're tempted to delete production code that has callers (always ask).

## House rules

- **Never skip tests just because they're hard.** Skip-stubbing is for
  tests that genuinely cannot pass because the underlying contract is
  gone (Pattern A). If the contract still exists, rewrite (Pattern B)
  or fix the bug (Pattern C).
- **Commit messages explain WHY + HOW**, not just WHAT.
- **Production bugs caught are wins.** Call them out in commit messages
  and PR descriptions. Track the cumulative count.
- **Architectural framing**: consumer-grade backend, NOT safety-critical.
  See `/memories/repo/coachiq-architecture.md`.
- **CI infra is robust now**. Pre-commit hooks work, diff-checks work,
  baseline ratchets work, no `--admin` overrides needed for routine PRs.
- **User's shell is fish** — bash arithmetic / heredocs need `bash -lc`
  wrapper. Verify with the existing terminal before getting clever.

## Useful commands

```bash
# Re-measure full-suite totals (run this BEFORE picking a cluster)
nix develop --command bash -c 'poetry run pytest --no-cov -q --tb=no --continue-on-collection-errors 2>&1 | tail -3'

# Top failing clusters (re-rank after each merge)
nix develop --command bash -c 'poetry run pytest --no-cov -q --tb=no --continue-on-collection-errors 2>&1 | grep -E "^(FAILED|ERROR)" | awk -F"::" "{print \$1}" | sed "s/^FAILED //; s/^ERROR //" | sort | uniq -c | sort -rn | head -15'

# One cluster, brief failures
nix develop --command bash -c 'poetry run pytest <path> --no-cov -q --tb=line'

# One specific test, full traceback
nix develop --command bash -c 'poetry run pytest <path>::TestClass::test_name --no-cov --tb=long'

# Diff-aware ruff check (BEFORE pushing — this is what CI runs)
nix develop --command bash -c 'poetry run python scripts/ruff_diff_check.py origin/main'

# Lint a specific file end-to-end
nix develop --command bash -c 'poetry run ruff check --fix <path> && poetry run ruff format <path>'
```

## Goal for this session

Drive the full-suite pass rate from **~89% to ~93%+**. That's roughly
35 more tests moved from fail/error to pass, across 5-7 more clusters.
Each cluster is roughly 30 min - 4 hours depending on pattern.

After ~5 more PRs the long tail starts to thin out and the remaining
clusters are likely either:
- Real production bugs that took multiple sweeps to surface (good)
- Tests guarding integration points that need real fixtures (e.g. CAN
  bus, real DB) — those may need to stay marked as integration tests
  and not block the unit-test gate.

Track the cumulative production-bug count in your final summary
message. The audit's running tally is at 7 prod bugs from 12 clusters.

Good luck. Don't be lazy. Fix the tests.
