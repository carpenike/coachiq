"""Tests for CSRF secret resolution at the FastAPI middleware boundary."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

import backend.main as backend_main
from backend.main import _DEVELOPMENT_CSRF_SECRET, _resolve_csrf_secret

pytestmark = [pytest.mark.auth, pytest.mark.unit]


def _settings(
    *,
    is_development: bool,
    auth_secret: str = "",
    security_secret: str | None = None,
) -> Any:
    """Construct a minimal settings double for CSRF middleware-boundary tests."""
    return SimpleNamespace(
        auth=SimpleNamespace(secret_key=auth_secret),
        security=SimpleNamespace(
            secret_key=SecretStr(security_secret) if security_secret is not None else None,
            tls_termination_is_external=False,
        ),
        is_development=lambda: is_development,
    )


def test_csrf_secret_prefers_auth_secret() -> None:
    """A configured auth secret is the primary CSRF signing secret."""
    settings = _settings(
        is_development=False,
        auth_secret="auth-secret-for-csrf-tests",
    )

    assert _resolve_csrf_secret(settings) == "auth-secret-for-csrf-tests"


def test_csrf_secret_accepts_real_security_secret() -> None:
    """A real security secret is the fallback when auth is intentionally disabled."""
    settings = _settings(
        is_development=False,
        security_secret="security-secret-for-csrf-tests-32bytes",
    )

    assert _resolve_csrf_secret(settings) == "security-secret-for-csrf-tests-32bytes"


def test_csrf_secret_rejects_dev_placeholder_outside_development() -> None:
    """Non-development CSRF setup fails closed when only the dev placeholder exists."""
    settings = _settings(
        is_development=False,
        security_secret="development-only-secret-key-do-not-use-in-production",
    )

    with pytest.raises(RuntimeError, match="COACHIQ_AUTH__SECRET_KEY"):
        _resolve_csrf_secret(settings)


def test_csrf_secret_rejects_missing_secret_when_non_development() -> None:
    """Auth-disabled production no longer falls back to a public constant secret."""
    settings = _settings(is_development=False)

    with pytest.raises(RuntimeError, match="CSRF secret key is required"):
        _resolve_csrf_secret(settings)


def test_create_app_fails_closed_without_non_development_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Application setup fails before adding CSRF middleware with no real secret."""
    settings = _settings(is_development=False)
    monkeypatch.setattr(backend_main, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="COACHIQ_AUTH__SECRET_KEY"):
        backend_main.create_app()


def test_csrf_secret_keeps_labeled_development_fallback() -> None:
    """Development keeps an explicit dev-only CSRF secret for local convenience."""
    settings = _settings(is_development=True)

    assert _resolve_csrf_secret(settings) == _DEVELOPMENT_CSRF_SECRET
