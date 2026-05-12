# Subagent task: resolve `entity_service.py` vs `entity_services.py` ambiguity

You are working on [carpenike/coachiq](https://github.com/carpenike/coachiq).
This task closes the most consequential half of the post-test-restoration
cleanup.

## Read first

1. `/memories/repo/coachiq-architecture.md` — what CoachIQ is/isn't.
2. `/memories/repo/coachiq-state.md` — note the "Entity services —
   three concerns" section. There are intentionally THREE classes here.
3. `/memories/repo/wip-branch-analysis.md` — original analysis of the
   `wip/security-rpi-hardening-2025` sprint that introduced the
   half-merged duplicate. Read this carefully — it lays out
   Options A/B/C and explains why the right answer is "pick one,
   delete the loser".
4. `/memories/repo/audit-2026-05-12.md` — current state.

## Current situation

Three entity service files coexist, two with confusingly similar names:

```
backend/services/entity_service.py       630 LOC
backend/services/entity_services.py      650 LOC
backend/services/entity_domain_service.py 582 LOC
```

`backend/main.py` imports BOTH top-level files:

```python
backend/main.py:103: from backend.services.entity_service import EntityService
backend/main.py:104: from backend.services.entity_services import (
```

`backend/services/__init__.py:11` re-exports `EntityService` from the
*singular* file. The 11 failures in `tests/services/test_entity_service.py`
likely surface this disambiguation.

Per `wip-branch-analysis.md`:

> `backend/services/entity_service.py` was rewritten as a thin DB-only
> reader. The INTENT was sound: build a fast cached persistence-layer
> primitive over the EntityState SQLAlchemy table. The PROBLEM: it kept
> the same class name and DI key, but other callers still expect the
> old monolithic API. The migration was 50% done.

The wip-branch-analysis flagged the singular file
(`entity_service.py`) as the broken WIP rewrite. **However**, it's the
one currently imported in `main.py:103`, so verify before deleting.

## The job

1. **Map the call graph.** For each of the three files, run:
   ```bash
   grep -rn "from backend.services.entity_service " backend/ tests/ --include="*.py"
   grep -rn "from backend.services.entity_services" backend/ tests/ --include="*.py"
   grep -rn "from backend.services.entity_domain_service" backend/ tests/ --include="*.py"
   ```
   Document which files import which.

2. **Identify the live one.** Trace through `main.py` and
   `backend/api/routers/entities*.py` and `backend/api/domains/entities.py`
   to figure out which class actually services API requests at runtime.
   The dependencies in `backend/core/dependencies.py` (look for
   `get_entity_service`) are the single source of truth — whatever
   that returns is the live one.

3. **Decision point.** Three possible outcomes:
   - **A.** `entity_services.py` (plural, layered) is live, `entity_service.py`
     (singular) is the dead WIP rewrite → delete `entity_service.py`,
     remove the `main.py:103` import, delete the `__init__.py:11`
     re-export, fix `entity_domain_service.py:24` import.
   - **B.** `entity_service.py` (singular) is live → confirm it's the
     monolithic version (not the WIP rewrite), delete `entity_services.py`
     (plural), remove the `main.py:104` import block, migrate any
     callers of `EntityQueryService`/`EntityControlService`/
     `EntityManagementService` back to the monolith methods.
   - **C.** Both are partially live (different routes use different
     services) → STOP and ask the user. This is a design decision,
     not a cleanup.

4. **Make the change.** Delete the loser. Update imports. Run the test
   suite — `tests/services/test_entity_service.py` should improve
   noticeably.

5. **Update memory.** Edit `/memories/repo/coachiq-state.md` to remove
   the duplicated entry from the "Entity services — three concerns"
   section. Keep `entity_domain_service.py` as the still-distinct
   third file (it adds command/ack pattern on top).

## Acceptance

- [ ] Exactly one of `entity_service.py` / `entity_services.py` remains.
- [ ] `main.py` imports from one file, not two.
- [ ] `tests/services/test_entity_service.py` failure count drops.
- [ ] Pyright/ruff baseline doesn't regress.
- [ ] Memory file updated.
- [ ] PR description includes the call-graph mapping and which option
      (A/B/C) was taken.

## House rules

- Never skip tests — if a test fails after the deletion, decide
  whether it was guarding the dead file (delete it) or the live one
  (fix the test or fix production).
- Commit messages explain WHY + HOW, not just WHAT.
- Don't touch `entity_domain_service.py` — it's the separately-purposed
  third tier (bulk operations + command/ack).

## Out of scope

- Don't fix `core/state.py` — separate issue.
- Don't audit the notification services — separate issue.
- Don't fix frontend typecheck — separate issue.
