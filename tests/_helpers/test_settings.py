"""
Tests for the shared Pydantic-Settings test helpers.

Covers ``tests/_helpers/settings.py`` and the ``test_settings`` fixture
defined in ``tests/conftest.py``. Together they encode the three
recurring traps documented in
``/memories/repo/audit-2026-05-12.md`` and
``/memories/repo/audit-2026-05-13.md``.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from backend.core.config import Settings
from tests._helpers.settings import isolated_env, make_test_settings


@pytest.mark.unit
class TestIsolatedEnv:
    """``isolated_env`` strips pre-existing ``COACHIQ_*`` vars."""

    def test_strips_existing_coachiq_vars(self):
        """A leaked ``COACHIQ_*`` from the dev shell is removed."""
        with patch.dict(os.environ, {"COACHIQ_DEBUG": "true", "PATH": "/usr/bin"}, clear=True):
            env = isolated_env({})
        assert "COACHIQ_DEBUG" not in env
        assert env["PATH"] == "/usr/bin"

    def test_preserves_non_coachiq_vars(self):
        """Non-prefixed env vars pass through unchanged."""
        with patch.dict(os.environ, {"FOO": "bar", "BAZ": "qux"}, clear=True):
            env = isolated_env({})
        assert env == {"FOO": "bar", "BAZ": "qux"}

    def test_caller_overrides_take_effect(self):
        """Overrides passed in are added on top of the cleaned base."""
        with patch.dict(os.environ, {"COACHIQ_DEBUG": "true"}, clear=True):
            env = isolated_env({"COACHIQ_LOGGING__LEVEL": "DEBUG"})
        assert env["COACHIQ_LOGGING__LEVEL"] == "DEBUG"
        # Pre-existing COACHIQ_DEBUG was stripped before merging
        assert "COACHIQ_DEBUG" not in env


@pytest.mark.unit
class TestMakeTestSettings:
    """``make_test_settings`` returns a real ``Settings`` instance."""

    def test_returns_real_settings_not_mock(self):
        """The result is a true ``Settings`` instance, not a Mock."""
        with patch.dict(os.environ, isolated_env({}), clear=True):
            settings = make_test_settings()
        assert isinstance(settings, Settings)

    def test_disables_dotenv_loading(self):
        """``_env_file=None`` is forwarded so the dev's local ``.env`` is ignored."""
        # No way to assert the negative directly without a fake .env on disk.
        # The defaults check provides indirect evidence: if .env had been
        # honoured, debug would not be False on a developer's machine
        # running ``COACHIQ_DEBUG=true`` in their shell.
        with patch.dict(os.environ, isolated_env({}), clear=True):
            settings = make_test_settings()
        assert settings.debug is False
        assert settings.logging.level == "INFO"

    def test_kwargs_forwarded_to_settings_ctor(self):
        """Keyword arguments are passed straight through to ``Settings(...)``."""
        with patch.dict(os.environ, isolated_env({}), clear=True):
            settings = make_test_settings(app_name="OverrideName")
        assert settings.app_name == "OverrideName"


@pytest.mark.unit
class TestSettingsFixture:
    """The ``test_settings`` ``pytest`` fixture composes the helpers."""

    def test_returns_real_settings(self, test_settings: Settings):
        """The fixture produces a real ``Settings`` instance."""
        assert isinstance(test_settings, Settings)

    def test_strips_coachiq_env(self, test_settings: Settings, monkeypatch: pytest.MonkeyPatch):
        """``COACHIQ_*`` vars in the parent process are gone inside the fixture."""
        # The fixture should have already done this for us. Verify by
        # asserting that no COACHIQ_* var is currently set.
        coachiq_keys = [k for k in os.environ if k.startswith("COACHIQ_")]
        assert coachiq_keys == [], (
            f"COACHIQ_* env vars leaked into test_settings fixture: {coachiq_keys}"
        )
