"""Integration tests for emergency stop scenarios.

Skip-stubbed 2026-05-12 (Pattern A) after a triage pass found that
the file's assumptions about ``SafetyService`` no longer match
production. The drift is broad rather than narrow:

1. **Attribute rename.** The tests reach into
   ``service._service_registry`` (private, leading underscore) but
   production stores the registry as ``service.service_registry``
   (public). See ``backend/services/safety_service.py:291``.

2. **Iteration semantics.** ``service._interlocks`` is a
   ``dict[str, SafetyInterlock]``; the tests do
   ``for interlock in service._interlocks`` (which yields *keys*),
   then pass each result to ``_check_interlock_conditions`` whose
   first line is ``await interlock.check_conditions(...)``. That
   crashes with ``'str' object has no attribute 'check_conditions'``.
   The fix is ``service._interlocks.values()`` everywhere, but it has
   to be applied per-test alongside the other rewrites.

3. **Sync/async contract change.** Production exposes both
   ``get_safety_status()`` (sync, returns ``dict``, line 1988) and
   ``get_safety_status_async()`` (async, line 1742). The tests
   write ``await service.get_safety_status()`` everywhere, which
   crashes with ``TypeError: object dict can't be used in 'await'
   expression``. Each call site has to be retargeted.

4. **Behavior-assumption drift.** Several tests assert that a
   specific manipulated state should immediately set
   ``_emergency_stop_active = True``, but the current
   ``SafetyService`` state machine does not trigger emergency stop
   from those exact conditions. Distinguishing 'production bug' from
   'test contract is wrong about what triggers emergency stop'
   requires a careful trace through the state machine plus a chat
   with whoever owns the safety semantics.

5. **Mock fixture gaps.** The integration registry mock only
   implements ``check_system_health`` / ``get_service`` /
   ``has_service`` / ``get_service_status``. Production also calls
   ``get_safety_critical_services``, ``get_health_summary``,
   and ``get_safety_status_summary`` -- those need to be added (with
   realistic return types, not bare ``Mock()`` instances which crash
   the production iteration paths).

Items 1, 2, 3, 5 are mechanical; item 4 needs human judgement. Doing
them all together gives an attractive ~10 passing tests but risks
papering over a real safety-state-machine drift if any of the
behavior-assumption failures is actually a production bug. The
audit's stop-and-ask rule applies here:

    > A cluster appears to require an architectural change [or]
    > more than 3 production bugs surface in a single cluster --
    > that's a sign the cluster is guarding a bigger drift than
    > expected, and you want a human to confirm the scope before
    > you change a lot of production code.

Suggested follow-up PR(s):
- Mechanical: rename ``service._service_registry`` ->
  ``service.service_registry``, fix ``.values()`` iteration, drop
  ``await`` from sync ``get_safety_status`` calls, add the missing
  registry-mock methods. Re-run; should leave ~3-5 behavior-driven
  failures.
- Investigative: for each remaining failure, decide test-bug
  vs. prod-bug. The 'emergency during state transition' and
  'critical service failure cascade' tests in particular look
  like they could surface a real safety-state-machine gap.

Refs: PR #109 (state.py removal pattern), PR #111 (entity service
disambiguation), issue #105 (test sweep #2). Architectural framing
in /memories/repo/coachiq-architecture.md (CoachIQ is API guardrails,
not vehicle safety -- Firefly MIRA owns the vehicle safety case).
"""

import pytest

pytest.skip(
    reason=(
        "SafetyService integration tests have multiple drift categories "
        "(attribute renames, sync->async, iteration semantics, mock-fixture "
        "gaps, plus possibly a real safety-state-machine drift). The "
        "mechanical fixes are easy but risk masking a real production bug "
        "in the behavior-assumption tests; restoring this cluster needs a "
        "split investigative+mechanical PR pair, not a one-pass rewrite. "
        "See module docstring."
    ),
    allow_module_level=True,
)
