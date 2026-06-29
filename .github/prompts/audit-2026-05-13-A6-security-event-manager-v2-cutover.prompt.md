---
mode: "agent"
description: "A6 \u2014 Finish the security_event_manager v1 \u2192 v2 cutover"
---

# A6 \u2014 security_event_manager v1 \u2192 v2 cutover

Audit cycle: 2026-05-13 architectural audit.

## Why

`backend/services/security_event_manager.py` (v1) is imported by
`backend/websocket/security_handler.py`.
`backend/services/security_event_manager_v2.py` (`EnhancedSecurityEventManager`)
is imported by `backend/main.py`.

Half-finished migrations on `main` are how three-version-deep "v3"
files start to appear. Audit memo
`/memories/repo/audit-2026-05-12.md` flagged this as
"### Security event manager \u2014 mid-migration"; nothing has changed.

Same playbook as PR #111 (entity_service vs entity_services).

## The job

1. **Read both implementations end-to-end** before deciding direction.
   Confirm v2 is genuinely a superset of v1 \u2014 do NOT assume.
2. **Migrate `backend/websocket/security_handler.py`** (and any other
   v1 consumers found) to `EnhancedSecurityEventManager`.
3. **Delete `backend/services/security_event_manager.py`** (v1).
4. **Optionally rename** `security_event_manager_v2.py` \u2192
   `security_event_manager.py` and `EnhancedSecurityEventManager` \u2192
   `SecurityEventManager`. Drop the v2 / Enhanced affix.
5. Update tests.

## Verification commands

```bash
# All v1 consumers
grep -rln "from backend.services.security.security_event_manager import\|from backend\\.services\\.security_event_manager " backend/ --include="*.py" | grep -v __pycache__

# All v2 consumers
grep -rln "security_event_manager_v2\|EnhancedSecurityEventManager" backend/ --include="*.py" | grep -v __pycache__

# After the migration, both should resolve to the new file
```

## Acceptance criteria

- One file: `backend/services/security_event_manager.py`.
- One class: `SecurityEventManager`.
- All tests pass; no behavior regression.
- Pyright + eslint baselines either flat or ratcheted DOWN.
- LOC delta recorded.

## Stop-and-ask if

- v2 is missing functionality that v1 has and that
  `security_handler.py` actually uses (e.g. a method, an event type).
  Don't paper over the gap; document and either port the missing
  functionality or pause the migration.
- The `WebSocket` event broadcast path differs between v1 and v2 in
  a way that would change the wire protocol. That requires a
  paired frontend PR.

## Lesson reminder (from PR #111)

The audit memo's "Lesson learned #2" applies: the prompt's binary
"pick v1 or v2" framing may be wrong. The right answer might be
"keep v2's class, harvest the listener-registration pattern from v1,
delete v1". Read both before deciding.

## Risk

Medium. Touches a security code path. Run integration tests
(`tests/integration/test_security_*.py` if any) before merging.
