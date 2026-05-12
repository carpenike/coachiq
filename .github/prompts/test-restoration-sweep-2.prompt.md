# Subagent task: test-restoration sweep #2

You are continuing the test-suite restoration project on
[carpenike/coachiq](https://github.com/carpenike/coachiq). PRs #89,
#90, #97, #98, #99, #100 (the first sweep) restored 12 clusters and
caught 39 production bugs. 149 failures+errors remain.

## Read first

1. `/memories/repo/coachiq-architecture.md` — what CoachIQ is/isn't.
2. `/memories/repo/coachiq-state.md` — repo state snapshot.
3. `/memories/repo/handoff-2026-05-11.md` — methodology that worked
   for the first sweep. **THIS IS THE PLAYBOOK.** Don't deviate.
4. `/memories/repo/audit-2026-05-12.md` — current state, including the
   ranked top-cluster table.

## Target clusters (ordered by failure+error count)

Pick clusters in this order. Each is roughly an independent PR.

| Count | Cluster | Likely category |
|-------|---------|------------------|
| 12 | `tests/services/test_safe_notification_manager.py` | service drift |
| 12 | `tests/contract/test_feature_parity_validation.py` | contract drift |
| 11 | `tests/unit/test_configuration_service.py` | constructor drift |
| 11 | `tests/services/test_entity_service.py` | **see note below** |
| 10 | `tests/integration/test_safety_emergency_scenarios.py` | integration |
| 10 | `tests/core/test_config.py` | Pydantic v2 / settings |
| 10 | `tests/contract/test_domain_api_contract.py` | contract drift |
|  9 | `tests/unit/test_database_management_api.py` | constructor drift |
|  9 | `tests/api/test_entities.py` | API surface drift |

### `test_entity_service.py` blocker

Don't touch `tests/services/test_entity_service.py` until the
`entity_service.py` vs `entity_services.py` disambiguation PR
(see `cleanup-entity-service-disambiguation.prompt.md`) merges.
Some or all of these failures will resolve as a side effect.

### `tests/core/test_state.py` (6 failures)

These may all disappear when `backend/core/state.py` is deleted (see
`cleanup-state-py-removal.prompt.md`). Skip until that lands.

## Methodology — copy verbatim from prior PRs

For each cluster:

1. Run with `--tb=line` to see all failures briefly:
   ```bash
   nix develop --command bash -c 'poetry run pytest <path> --no-cov -q --tb=line'
   ```
2. Look at the FIRST failure with `--tb=short`. Decide:
   - **API drift** (test stale) → update test to match current API.
   - **Real bug** → fix production, verify test passes.
   - **Test infra** → fix fixture.
3. Re-run, repeat until cluster is clean.
4. Run a wider sanity check (a few adjacent clusters) to confirm no
   regressions.
5. Commit with a detailed message: WHY + HOW, including a list of any
   production bugs caught. The first-sweep PRs (#89, #90, #97-100)
   are the format reference.

## Pacing

- One cluster per PR is ideal. The first-sweep PRs averaged ~3-5h per
  cluster including bug investigation.
- Don't open more than two PRs in flight — the user is reviewing.
- After each PR merges, update `audit-2026-05-12.md` with the new
  totals (run `pytest --no-cov -q --tb=no --continue-on-collection-errors
  | tail -3`).

## Stop and ask the user when

- A cluster appears to require an architectural change (e.g. a
  service rewrite).
- More than 5 production bugs surface in a single cluster — that's
  a sign the cluster is guarding a bigger drift than expected.
- The "fix" requires breaking an established API contract.

## House rules (from prior sweep)

- Never skip tests — fix them.
- Commit messages explain WHY + HOW.
- Production bugs caught are wins; call them out.
- Architectural framing: consumer-grade backend, NOT safety-critical.
- Use `--no-verify` for pre-push if Cachix is broken.
- User's shell is fish — bash arithmetic / heredocs need `bash -lc`.

## Useful commands

```bash
# Full suite totals
nix develop --command bash -c 'poetry run pytest --no-cov -q --tb=no --continue-on-collection-errors 2>&1 | tail -3'

# Top failing clusters
nix develop --command bash -c 'poetry run pytest --no-cov -q --tb=no --continue-on-collection-errors 2>&1 | grep -E "^(FAILED|ERROR)" | awk -F"::" "{print \$1}" | sed "s/^FAILED //; s/^ERROR //" | sort | uniq -c | sort -rn | head -20'

# Single cluster, brief failures
nix develop --command bash -c 'poetry run pytest <path> --no-cov -q --tb=line'

# Single test, full traceback
nix develop --command bash -c 'poetry run pytest <path>::TestClass::test_name --no-cov --tb=long'
```

## Goal

Get from 750/91/58 → 850+/<30/<20 over the course of this sweep.
That gets the suite to ~93%+ pass rate, which is good-enough to start
treating green CI as a real signal again.
