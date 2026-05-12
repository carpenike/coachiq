# Subagent task: audit `backend/services/notification_*` (13 files)

You are working on [carpenike/coachiq](https://github.com/carpenike/coachiq).
This task is the third leg of the post-test-restoration cleanup.

## Read first

1. `/memories/repo/coachiq-architecture.md` — system framing.
2. `/memories/repo/coachiq-state.md` — note the "Notification services
   — three intentional variants" section. Three of the 13 files are
   intentional and should NOT be merged or deleted.
3. `/memories/repo/audit-2026-05-12.md` — current state.

## The 13 files

```
backend/services/notification_analytics_service.py
backend/services/notification_batching.py
backend/services/notification_ingestion_service.py
backend/services/notification_lightweight.py        ← intentional tier
backend/services/notification_manager.py            ← intentional tier
backend/services/notification_performance.py
backend/services/notification_processing_service.py
backend/services/notification_queue.py
backend/services/notification_rate_limiting.py
backend/services/notification_reporting_service.py
backend/services/notification_routing.py
backend/services/safe_notification_manager.py       ← intentional tier
```

The three marked tiers are documented as deliberate (Apprise generic /
RV-C-safety-hardened / RPi-optimized). The other ten need
classification.

## The job

For EACH of the ten unclassified files:

1. **Find imports.** From repo root:
   ```bash
   grep -rn "from backend.services.notification_<name>" backend/ tests/ --include="*.py"
   ```
2. **Classify** as one of:
   - **LIVE** — imported and exercised by production code (main.py,
     a router, or one of the three notification managers).
   - **TEST-ONLY** — only imported by tests. May be valid
     infrastructure or may be dead.
   - **DEAD** — no imports anywhere, or only imported by other dead
     files.
   - **WIP** — imported, but the importer is itself unused (e.g.
     scaffolding from the shelved security-rpi sprint).

3. **For LIVE files**: add a 1-line comment at the top of each file
   explaining its role (e.g. "Persistent SQLite queue used by
   SafeNotificationManager for retry-on-failure"). This single
   sentence is what's missing right now.

4. **For DEAD/WIP files**: delete them. Remove their imports from
   `__init__.py` if any. Delete their tests if dead.

5. **For TEST-ONLY files**: investigate — usually means a service
   was scaffolded but never wired up. Either wire it up or delete it.
   If unclear, leave the file but add a `# TODO(audit-2026-05-12):
   classify — currently test-only` comment and document in the PR.

6. **Update `coachiq-state.md`** to add a new subsection under
   "Notification services" listing each LIVE file with its one-line
   role. This becomes the canonical map.

## Expected outcome

The `tests/services/test_safe_notification_manager.py` (12 failures)
and `tests/services/test_notification_rate_limiting.py` (5 failures)
clusters may drop after dead-code removal exposes which fixtures point
at nonexistent constructors. Don't try to FIX those test clusters in
this PR — that's the test-restoration sweep. Just note in the PR if
their counts changed.

## Acceptance

- [ ] All 10 unclassified files classified in the PR description.
- [ ] LIVE files have a one-line top-of-file role comment.
- [ ] DEAD/WIP files deleted.
- [ ] `__init__.py` cleaned up.
- [ ] `coachiq-state.md` updated with the LIVE-file map.
- [ ] Test suite pass count stable or higher.

## Out of scope

- Don't merge or refactor the three intentional tiers.
- Don't fix the notification test failures (separate sweep).
- Don't touch `core/state.py` or entity services.
