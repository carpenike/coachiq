---
mode: "static"
description: "Index of the 2026-05-13 architectural-audit cleanup cycle (12 PRs)"
---

# Architectural audit 2026-05-13 — overview

Companion to the 12 child prompt files under `.github/prompts/audit-2026-05-13-*.prompt.md`.

## Read first (every session)

1. `/memories/repo/coachiq-architecture.md` — what CoachIQ IS / IS NOT.
2. `docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md` — same, canonized.
3. `/memories/repo/coachiq-state.md` — running state (notification tiers, entity tiers, security migration status).
4. `/memories/repo/audit-2026-05-12.md` — last cycle's results, methodology, "stop-and-ask" rule.

## Origin

This cycle was opened in response to a comprehensive architectural audit
performed on `main` at the close of the 2026-05-12 test-restoration sweep
(see issue tracker for the audit summary comment). The audit found that
the codebase has been re-baselined to "consumer-grade backend" in the
*memory files and ADRs*, but the *code itself* still reflects the older
"vehicle safety system" framing in many places — type-erased DI, ISO
26262 docstrings, dead safety-state machines, three-named auth files,
mid-migrations on `main`, etc.

The 12 child issues cover the full backlog. Priority order (mechanical
→ structural):

| # | Slug | Risk | Touches |
|---|---|---|---|
| A1 | `audit-2026-05-13-safety-naming-cleanup` | very low | docstrings only |
| A2 | `audit-2026-05-13-delete-dead-safety-modules` | low | `brake_safety_monitor.py`, `safety_state_engine.py` |
| A3 | `audit-2026-05-13-collapse-service-registry-inheritance` | low | `core/service_registry.py` |
| A4 | `audit-2026-05-13-settings-test-fixture-helper` | low | `tests/conftest.py` |
| A5 | `audit-2026-05-13-exception-envelope-decision` | medium | ADR + `core/exception_handlers.py` |
| A6 | `audit-2026-05-13-security-event-manager-v2-cutover` | medium | `services/security_event_manager*.py`, `websocket/security_handler.py` |
| A7 | `audit-2026-05-13-type-the-di-layer` | high | `core/dependencies.py` + every router |
| A8 | `audit-2026-05-13-split-main-py` | high | `backend/main.py` |
| A9 | `audit-2026-05-13-auth-namespace-consolidation` | high | `services/auth_*.py` |
| A10 | `audit-2026-05-13-config-service-rename` | medium | `services/config_service.py`, `core/configuration_service.py` |
| A11 | `audit-2026-05-13-domain-v2-decision` | high | `api/domains/`, `api/routers/` |
| A12 | `audit-2026-05-13-frontend-router-idiom` | medium | `frontend/src/{app,pages}/` |

## House rules

Same as the 2026-05-12 cycle:

- **Don't skip tests** — fix or properly skip-stub with a follow-up issue.
- **Production bugs caught by these PRs are wins** — call them out.
- **Stop-and-ask** when an issue surfaces a >1-PR problem (e.g. an
  ambiguous safety-state-machine change, a security regression).
- **Architectural framing** is consumer-grade backend, NOT safety-critical.
- ADRs land in the same PR as the structural change they document.

## Methodology per PR

1. Cut a branch from latest `main`: `chore/audit-A<N>-<slug>`.
2. Read the prompt file end-to-end.
3. Read the code area end-to-end before changing anything.
4. Make the smallest correct change. Add or update tests.
5. Run `nix run .#ci` (or the equivalent staged commands) before pushing.
6. Open the PR with: problem, change, evidence (commands), risk note.
7. Update the relevant memory file(s) with what was learned.

## Cumulative tracker

Each PR appends a row to `/memories/repo/audit-2026-05-13.md` (created
in the bootstrap PR). Track:

- Tests Δ
- LOC Δ
- Pyright/eslint baseline Δ
- Production bugs caught
- Surprises / lessons
