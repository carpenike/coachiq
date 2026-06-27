"""Tests for CSRF secret resolution at the FastAPI middleware boundary."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

import backend.main as backend_main
from backend.main import _DEVELOPMENT_CSRF_SECRET, _resolve_csrf_secret
from tests._helpers.settings import isolated_env, make_test_settings

if TYPE_CHECKING:
    from backend.core.config import Settings

pytestmark = [pytest.mark.auth, pytest.mark.unit]


def _settings(**kwargs) -> Settings:
    """Construct hermetic settings for CSRF secret tests."""
    with patch.dict(os.environ, isolated_env({}), clear=True):
        return make_test_settings(**kwargs)


def test_csrf_secret_prefers_auth_secret() -> None:
    """A configured auth secret is the primary CSRF signing secret."""
    settings = _settings(
        environment="production",
        auth={"enabled": False, "secret_key": "auth-secret-for-csrf-tests"},
    )

    assert _resolve_csrf_secret(settings) == "auth-secret-for-csrf-tests"


def test_csrf_secret_accepts_real_security_secret() -> None:
    """A real security secret is the fallback when auth is intentionally disabled."""
    settings = _settings(
        environment="production",
        auth={"enabled": False, "secret_key": ""},
        security={"secret_key": "security-secret-for-csrf-tests-32bytes"},
    )

    assert _resolve_csrf_secret(settings) == "security-secret-for-csrf-tests-32bytes"


def test_csrf_secret_rejects_dev_placeholder_outside_development() -> None:
    """Non-development CSRF setup fails closed when only the dev placeholder exists."""
    settings = _settings(
        environment="production",
        auth={"enabled": False, "secret_key": ""},
        security={"secret_key": "development-only-secret-key-do-not-use-in-production"},
    )

    with pytest.raises(RuntimeError, match="COACHIQ_AUTH__SECRET_KEY"):
        _resolve_csrf_secret(settings)


def test_csrf_secret_rejects_missing_secret_when_non_development() -> None:
    """Auth-disabled production no longer falls back to a public constant secret."""
    settings = _settings(
        environment="production",
        auth={"enabled": False, "secret_key": ""},
    )

    with pytest.raises(RuntimeError, match="CSRF secret key is required"):
        _resolve_csrf_secret(settings)


def test_create_app_fails_closed_without_non_development_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Application setup fails before adding CSRF middleware with no real secret."""
    settings = _settings(
        environment="production",
        auth={"enabled": False, "secret_key": ""},
    )
    monkeypatch.setattr(backend_main, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="COACHIQ_AUTH__SECRET_KEY"):
        backend_main.create_app()


def test_csrf_secret_keeps_labeled_development_fallback() -> None:
    """Development keeps an explicit dev-only CSRF secret for local convenience."""
    settings = _settings(
        environment="development",
        auth={"enabled": False, "secret_key": ""},
    )

    assert _resolve_csrf_secret(settings) == _DEVELOPMENT_CSRF_SECRET
