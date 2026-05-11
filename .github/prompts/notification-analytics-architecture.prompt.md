# Subagent task: restore tests/test_notification_analytics.py

You are picking up work mid-stream on `fix/test-suite-restoration-2`,
which is branched off the latest `main` of the
[carpenike/coachiq](https://github.com/carpenike/coachiq) repo. PR #89
("restore test suite — 8 clusters, +194 passing tests") was merged
recently. This task is the deep architectural work that I peeled out
of that PR because it's much larger than a normal "fix one test
cluster" job.

## Read first

These three repo-memory files set the framing — start here, in this
order. Don't drift from the architectural framing on the first one in
particular:

1. `/memories/repo/coachiq-architecture.md` — pins what CoachIQ IS and
   IS NOT. CoachIQ is a CAN-bus orchestration layer that talks to a
   Firefly MIRA panel, **not** a safety-critical system. Calibrate
   code-quality decisions to "good consumer-grade backend service",
   not aerospace.
2. `/memories/repo/coachiq-state.md` — repo state snapshot.
3. `/memories/repo/handoff-2026-05-11.md` — handoff from the PR #89
   work, including the methodology that worked and house rules.

After you've read those, also skim `.github/copilot-instructions.md`
if you haven't worked in this repo before.

## The job

Restore `tests/test_notification_analytics.py` from
**4 passed / 12 failed / 0 errors** to **16/0/0** without skipping
any tests, and fix the underlying production architecture drift the
test failures are pointing at.

The test file is the spec. Tests describe the contract that production
code should honour. Where tests look stale (poking at private impl
details that have moved), update the tests to assert against the
public API. Where production code is genuinely broken or incomplete,
fix the production code. Per the handoff house rules: **call out every
production bug you find in your commit messages** -- they're real wins.

## Current state (already committed on this branch)

Commit `2510827` on `fix/test-suite-restoration-2` already fixes one
production bug:

- `NotificationAnalyticsService.__init__` was constructing
  `NotificationReportingService` with `(self._repository,
  performance_monitor, database_manager)` (3 args) but the constructor
  only accepts `(database_manager, analytics_service)` (2). Every
  construction of the analytics service was raising `TypeError`,
  which broke every analytics REST endpoint at startup. Fixed.

That fix took the cluster from 16 errors → 12 failures + 4 passes.
The remaining 12 failures expose deeper drift, summarised below.

## What's broken (the 12 remaining failures, grouped)

### Group A: missing query methods on NotificationReportingService

`NotificationAnalyticsService.get_channel_metrics() /
get_aggregated_metrics() / analyze_errors() / get_queue_health()` all
delegate to `self._reporting_service.<same_method>()` -- but those
methods **don't exist** on `NotificationReportingService`. Production
callers blow up with `AttributeError`:

- `backend/api/routers/notification_analytics.py` (the REST endpoints
  for `/api/notifications/analytics/*`) calls all four of these.
- `backend/services/notification_reporting_service_full.py` (a 950-line
  variant that's currently unreferenced -- **decide whether to delete
  it or wire it back in** as part of this work).

The repository layer (`NotificationAnalyticsRepository`) has the right
primitives:

- `get_channel_statistics(channel, start_date, end_date) -> list[dict]`
- `get_metric_aggregates(...) -> ...`
- `get_error_patterns(start_date, end_date, min_occurrences) -> list[dict]`
- `get_queue_statistics(since) -> dict`

What's missing is the **dict→typed-model conversion layer** that
converts those rows into `ChannelMetrics`, `NotificationMetric`,
`NotificationErrorAnalysis`, and `NotificationQueueHealth` (all defined
in `backend/models/notification_analytics.py`).

Decision needed: Do those conversions live on the **reporting service**
(matching what the tests' fixture wires up:
`NotificationReportingService(db_manager, analytics_service)` -- so
the reporting service holds the analytics-service back-reference and
calls the repository directly), or on the **analytics service**
itself (with the reporting service handling only the report-template /
schedule / file-format concerns)?

Both are defensible. Look at the test expectations in
`tests/test_notification_analytics.py::TestNotificationAnalyticsService`
(lines ~170-290) and
`tests/test_notification_analytics.py::TestNotificationReportingService`
(lines ~290-525) and pick whichever placement keeps both classes'
contracts coherent. The test calls `analytics_service.get_*()` and
`reporting_service.generate_report()`, so the public API is clear; the
implementation split is the part that needs your judgement.

### Group B: legacy buffer attribute names

Tests poke at:

- `analytics_service._metric_buffer` (a `list`)
- `analytics_service._buffer_size_limit` (an `int`)
- `analytics_service._flush_buffer()` (a method)

These were on the **old** `NotificationAnalyticsService`. The new
orchestrator moved buffering to `NotificationIngestionService` as an
`asyncio.Queue` (totally different shape: no `len()`, no auto-flush
on size threshold, no public `_metric_buffer` attribute).

Decision needed: either
1. **Restore the legacy attrs** as compatibility shims on the
   orchestrator that proxy to the ingestion service / repository
   buffer (the repository at
   `NotificationAnalyticsRepository` does still have a list-shaped
   `_metric_buffer` with `add_to_buffer` / `flush_buffer` methods --
   these may be the right thing to expose), OR
2. **Rewrite the tests** to match the new ingestion-queue model and
   assert against the queue's behaviour instead.

Option 1 is the smaller change and preserves the tests as the spec.
Option 2 is the cleaner long-term architecture but rewrites the tests
substantially. Use your judgement; document the decision in the
commit message.

### Group C: column name mismatch

Tests construct `NotificationDeliveryLog(metadata={...})` and read
`log.metadata`. The SQLAlchemy model uses **`delivery_metadata`**
(see `backend/models/notification_analytics.py` line 145). Either:

1. Add a property alias `metadata` → `delivery_metadata` on the
   model (cleanest; matches what tests expect; doesn't risk a DB
   migration).
2. Migrate the column to `metadata` (requires Alembic migration;
   `metadata` is a SQLAlchemy reserved attribute name on `Base` so
   you'll likely hit collision warnings -- this is *probably* why
   it was renamed in the first place).

Lean toward option 1. There's the same `metric_metadata` pattern on
`NotificationMetricAggregate`, suggesting deliberate avoidance of
the reserved name.

### Group D: test_dispatcher_analytics_integration & test_end_to_end_analytics_flow

These integration-style tests likely surface as derivative failures of
groups A-C. Re-check them after you've done A-C; they may pass
without further changes, or there may be a small additional fixture
issue.

## The unreferenced file

`backend/services/notification_reporting_service_full.py` (~950 lines,
imports `matplotlib`, `pandas`, `reportlab`) is **not referenced
anywhere in the codebase** (verified via `grep -r`). It looks like an
abandoned variant from a previous refactor. Three options:

1. **Delete it.** Cleanest. If those export formats are wanted
   later, they'll be brought back per a real spec.
2. **Move it to `_deprecated/`.** But `_deprecated/` was already
   purged from the repo on 2026-05-11, so this would re-introduce
   the directory.
3. **Leave it.** Risk: someone confuses it for the real
   reporting service.

Recommend option 1, but flag it in the commit message and let the
human review. Don't surprise the reviewer.

## Methodology (proven on PR #89 — follow this)

For each cluster of failures:

1. Run the cluster, look at the FIRST failure with `--tb=short`
   (or `--tb=long` if cryptic).
2. Decide: API drift (test stale), real bug, or test infra issue.
3. If test stale: update the test to match current API.
4. If real bug: fix production code, then verify the test now passes.
5. If test infra: fix the fixture.
6. Re-run the cluster, repeat until clean.
7. **Always run a wider sanity check** at the end to confirm no
   regressions in earlier-fixed clusters. Use this command:

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
     tests/test_notification_analytics.py \
     --no-cov -q --tb=line 2>&1 | tail -5'
   ```
8. **Commit per logical change** with a detailed message that lists
   production bugs found and design decisions made (especially the
   "decision needed" points above).

## House rules

- Never skip tests — fix them. Per the user: "don't be lazy."
- Commit messages explain WHY + HOW, not just WHAT.
- **Production bugs caught by tests are wins** — call them out
  explicitly in commit messages. The previous PR found 14; the
  orchestrator constructor fix is #15; you may find more.
- Don't add new `# nosec` / `# noqa` / `# type: ignore` without an
  inline rationale comment.
- Architectural framing: **consumer-grade backend, NOT
  safety-critical**. The `safety_*` names in the codebase refer to
  API guardrails, not vehicle safety (Firefly owns that).
- CI is now properly diff-aware (`scripts/ruff_diff_check.py` runs
  ruff lint with line-level filtering); only NEW issues on lines you
  touch will block. Whole-file pre-commit hooks (ruff-format,
  bandit) still run on the changed file set.
- Pre-push hook: use `git push --no-verify` to bypass it during
  iterative work; the gate runs in CI anyway.
- The user's shell is fish — bash arithmetic / heredocs need a
  `bash -lc "..."` wrapper.

## Files NOT to touch without asking

- `wip/security-rpi-hardening-2025` branch (preserved sprint).
- `config/2021_Entegra_Aspire_44R.yml` (real coach mapping).
- The 3 notification managers (`notification_manager.py`,
  `safe_notification_manager.py`, `notification_lightweight.py`) —
  they look like duplicates but are intentional safety/perf tiers.

## What "done" looks like

- `tests/test_notification_analytics.py`: 16/16 passing.
- The wider sanity check above shows zero regressions.
- A focused PR (squash-merge) onto `main` with one or more commits
  whose messages explain:
  - What production bugs were found and how they were fixed
  - Each "decision needed" call you made and why
  - Whether you deleted/kept `notification_reporting_service_full.py`
- `./scripts/ci-quality-gate.sh` passes locally (it's the same gate
  CI runs).

## Branch / PR convention

Work on a fresh branch off the **latest `main`** (NOT off
`fix/test-suite-restoration-2` -- that branch will likely have moved
on with the safety-integration cluster work that's running in
parallel). Name it something like
`fix/notification-analytics-architecture` or similar. Open a PR that
explicitly references this prompt and the orchestrator fix in commit
`2510827` (which will already be on main by the time you start).

Good luck. The codebase rewards careful reading; the test file *is*
the spec for the contract you're trying to honour.
