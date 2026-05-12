# Subagent task: install a pyright error ratchet

You are working on [carpenike/coachiq](https://github.com/carpenike/coachiq).
This task does NOT fix any pyright errors. It installs a one-way
ratchet so the baseline can only go down, never up.

## Read first

1. `/memories/repo/coachiq-architecture.md` — what CoachIQ is/isn't.
2. `/memories/repo/audit-2026-05-12.md` — current pyright baseline:
   **1488 errors, 1529 warnings** on `pyright basic` over `backend/`.

## Why a ratchet (not a fix)

- 1488 errors won't be fixed in one PR, or even ten.
- Pragmatic pre-commit currently blocks only NEW issues in changed
  files — but pyright doesn't have file-level diff support like ruff
  does, so changes silently introduce new errors elsewhere.
- A ratchet makes the baseline visible and prevents drift in the
  wrong direction. It's the cheapest possible governance.

## The job

1. **Capture the baseline.** Add `scripts/pyright-baseline.txt` with
   a single integer (the current error count, 1488 at audit time).
   Add a comment at the top of the file explaining what it is.

2. **Add a script** `scripts/check-pyright-ratchet.sh`:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   BASELINE=$(grep -E "^[0-9]+$" scripts/pyright-baseline.txt | head -1)
   ACTUAL=$(poetry run pyright backend 2>&1 | \
     grep -E "^[0-9]+ errors?," | awk '{print $1}')
   if [[ -z "$ACTUAL" ]]; then
     echo "ERROR: could not parse pyright output"
     exit 2
   fi
   if (( ACTUAL > BASELINE )); then
     echo "FAIL: pyright errors $ACTUAL > baseline $BASELINE"
     echo "Either fix the regression OR (if intentional) raise the baseline."
     exit 1
   fi
   if (( ACTUAL < BASELINE )); then
     echo "RATCHET: pyright errors dropped from $BASELINE to $ACTUAL"
     echo "Lower the baseline in scripts/pyright-baseline.txt."
     exit 1
   fi
   echo "OK: pyright errors == baseline ($ACTUAL)"
   ```
   The `ACTUAL < BASELINE` failure mode is intentional — it forces
   PRs that improve type safety to also lower the baseline, locking
   in the improvement.

3. **Wire into CI.** Add a step to `scripts/ci-quality-gate.sh` (or
   the relevant workflow) that runs `bash scripts/check-pyright-ratchet.sh`.

4. **Document** in `docs/code-quality-tools.md` (or create a section
   in `CONTRIBUTING.md`):
   - What the ratchet does.
   - How to lower the baseline (run pyright, count errors, edit file).
   - How to raise the baseline (with explicit explanation in the PR
     description — this should be rare).

5. **Optional**: do the same for ruff (`scripts/ruff-baseline.txt`,
   currently ~4624). The same pattern works. Keep it in the same PR
   if straightforward, separate if it grows.

## Acceptance

- [ ] `scripts/pyright-baseline.txt` exists with current count.
- [ ] `scripts/check-pyright-ratchet.sh` exists and is executable.
- [ ] CI runs the ratchet check on every PR.
- [ ] CI fails the PR if the count goes UP.
- [ ] CI fails the PR if the count goes DOWN without baseline update
      (this is what locks in improvements).
- [ ] Documentation explains the rules.

## Out of scope

- Fixing any actual pyright errors. The point is the ratchet, not the
  cleanup. Cleanup happens organically as the baseline ratchets down.
- Switching pyright from `basic` to `strict`. Premature.
- Adding mypy or other type checkers.

## Why this is high-leverage

Once landed, every future PR that touches typed code will either
- leave the baseline alone (no change), or
- improve it (which forces the author to update the baseline number).

The baseline number in git history then becomes a built-in progress
chart. No one has to remember to run pyright manually.
