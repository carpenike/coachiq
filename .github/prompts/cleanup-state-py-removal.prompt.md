# Subagent task: delete `backend/core/state.py` (dead code, 609 LOC)

You are working on [carpenike/coachiq](https://github.com/carpenike/coachiq).
This task closes the dead-code half of the post-test-restoration cleanup.

## Read first

1. `/memories/repo/coachiq-architecture.md` — what CoachIQ is/isn't.
2. `/memories/repo/coachiq-state.md` — repo state snapshot.
3. `/memories/repo/audit-2026-05-12.md` — the audit that found this.

## The job

`backend/core/state.py` (609 LOC) is documented as "removed and
decomposed into repositories" in `copilot-instructions.md` and
`coachiq-state.md`. The file is still on disk. As of the 2026-05-12
audit, the only import path into `core.state` is a self-import inside
the file itself (`backend/core/state.py:517` does
`from backend.core.state import CANSniffer`).

Your job:

1. **Verify** the file is genuinely dead. Run from repo root:
   ```bash
   grep -rn "from backend.core.state\|import backend.core.state\|backend\.core\.state" backend/ tests/ --include="*.py"
   ```
   Expected: only the one self-import inside `state.py` itself, plus
   any test files that should also be deleted.
2. If anything else imports from it, **stop and ask the user** —
   the audit may have missed something.
3. If truly dead:
   - Delete `backend/core/state.py`.
   - Delete any `tests/core/test_state.py` cases that test the dead
     file (the audit shows `tests/core/test_state.py` has 6 failures —
     some or all may be testing the dead file).
   - Search for stale "AppState" docstring references in
     `backend/repositories/` (e.g. "Part of Phase 2R: AppState
     Repository Migration") and either delete the comment or rephrase
     to past tense ("Replaced the monolithic AppState class").
4. Run the full test suite. Pass count should not drop. Failure count
   may go DOWN (the 6 test_state.py failures should go to 0).
5. Run `poetry run ruff check backend/core/` and `poetry run pyright
   backend/core/` — neither should regress.

## Acceptance

- [ ] `backend/core/state.py` deleted.
- [ ] No grep hits for `backend.core.state` outside test files that
      were also deleted.
- [ ] Stale AppState docstrings in `backend/repositories/` updated.
- [ ] Test suite passing count stable or higher.
- [ ] PR description summarises the audit + verification grep output.

## Why this matters

The file's continued existence makes the agent guidance docs lie. Every
new agent reads "AppState was removed" and then trips over a 609-line
file claiming to be `AppState`. Documentation drift is the most
expensive bug class on a multi-agent project.

## Out of scope

Don't touch the `entity_service.py` vs `entity_services.py`
disambiguation — that's a separate issue/PR.
Don't refactor the repositories — they're working fine.
