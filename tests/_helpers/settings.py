"""
Pydantic-Settings test helpers.

CoachIQ's ``backend.core.config.Settings`` is a Pydantic-Settings model
with 19 nested ``BaseSettings`` sections. Three traps bite every test
author who instantiates it (or any of its sub-sections) without help:

1. ``MagicMock(spec=BaseSettings)`` looks like it would yield a typed
   mock, but Pydantic v2 model fields are descriptors that materialize
   on instances, not the class. ``spec=`` walks ``dir(SettingsClass)``
   and finds nothing, so every ``getattr(mock, field)`` raises
   ``AttributeError``. Use a real instance with ``_env_file=None``
   instead -- see ``make_test_settings`` below.

2. ``BaseSettings`` with ``model_config = SettingsConfigDict(env_file=".env")``
   auto-loads the developer's local ``.env`` during tests, leaking real
   config (interfaces, secrets, debug flags) into the test process.
   Pass ``_env_file=None`` to disable that path.

3. ``COACHIQ_*`` env-var pollution leaks across tests because Pydantic
   only reads env on instantiation, and the test process inherits the
   developer's shell. ``patch.dict(os.environ, {"COACHIQ_FOO": "bar"})``
   alone isn't enough -- a leaked ``COACHIQ_LOGGING__LEVEL=DEBUG`` from
   the dev's terminal will still apply. Use ``isolated_env({...})`` to
   build a clean env mapping that strips every pre-existing
   ``COACHIQ_*`` variable.

Lessons canonized in audit-2026-05-12 cycle (PRs #119, #121, #122).
This helper hoists the original ``tests/core/test_config.py`` private
helpers into a shared location so other tests can import them.

Typical use::

    import os
    from unittest.mock import patch

    from tests._helpers.settings import isolated_env, make_test_settings

    def test_default_log_level():
        with patch.dict(os.environ, isolated_env({}), clear=True):
            settings = make_test_settings()
        assert settings.logging.level == "INFO"

    def test_env_override():
        with patch.dict(
            os.environ,
            isolated_env({"COACHIQ_LOGGING__LEVEL": "DEBUG"}),
            clear=True,
        ):
            settings = make_test_settings()
        assert settings.logging.level == "DEBUG"

There is also a ``test_settings`` ``pytest`` fixture in
``tests/conftest.py`` that combines both helpers for the common
"hermetic default settings" case.
"""

from __future__ import annotations

import os
from typing import Any

from backend.core.config import Settings


def isolated_env(env: dict[str, str]) -> dict[str, str]:
    """Build a clean env mapping that strips any pre-existing ``COACHIQ_*`` vars.

    pytest may inherit ``COACHIQ_*`` settings from the developer's shell
    or local ``.env`` file, which would pollute test assertions. This
    helper produces a mapping containing every NON-``COACHIQ_`` env var
    plus exactly the variables the caller wants set, with no leaked
    settings from outside the test.

    Use with ``patch.dict(os.environ, isolated_env({...}), clear=True)``.

    Args:
        env: ``COACHIQ_*`` (or any other) env vars the test wants set.

    Returns:
        A dict suitable for ``patch.dict(os.environ, ..., clear=True)``.
    """
    base = {k: v for k, v in os.environ.items() if not k.startswith("COACHIQ_")}
    base.update(env)
    return base


def make_test_settings(**kwargs: Any) -> Settings:
    """Construct ``Settings`` with ``.env`` file loading disabled.

    The production ``Settings`` class auto-loads values from a ``.env``
    file in the working directory. That's correct for runtime but wrong
    for tests that assert against the documented defaults: a developer's
    local ``.env`` (e.g. ``COACHIQ_CAN__INTERFACES=virtual0``) would
    otherwise override what the test is trying to verify.

    Pydantic-Settings honours the underscore-prefixed ``_env_file=None``
    keyword to disable the env_file path entirely. This helper wraps that
    so test files don't all have to remember the underscore convention.

    Args:
        **kwargs: Forwarded to ``Settings(...)``. Use to set fields
            directly (bypassing env-var parsing).

    Returns:
        A ``Settings`` instance with no ``.env`` file applied.
    """
    return Settings(_env_file=None, **kwargs)


__all__ = ["isolated_env", "make_test_settings"]
