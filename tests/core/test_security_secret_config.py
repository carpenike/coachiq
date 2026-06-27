"""Tests for security secret configuration fail-closed behavior."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.core.config import DEVELOPMENT_SECURITY_SECRET, Settings
from tests._helpers.settings import isolated_env, make_test_settings

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.auth, pytest.mark.unit]


def _settings(**kwargs) -> Settings:
    """Construct hermetic settings for security secret validation tests."""
    with patch.dict(os.environ, isolated_env({}), clear=True):
        return make_test_settings(**kwargs)


def _secret_file(tmp_path: Path, value: str = "real-security-secret-for-tests-32bytes") -> Path:
    """Write a temporary secret file and return its path."""
    path = tmp_path / "coachiq-secret"
    path.write_text(value, encoding="utf-8")
    return path


def test_production_requires_real_security_secret() -> None:
    """Production settings fail closed instead of using the dev placeholder."""
    with pytest.raises(ValidationError, match="COACHIQ_SECURITY__SECRET_KEY"):
        _settings(environment="production")


def test_staging_rejects_env_example_placeholder() -> None:
    """Production-like environments reject documented placeholder values."""
    with pytest.raises(ValidationError, match="production and staging"):
        _settings(
            environment="staging",
            security={"secret_key": "your-secret-key-change-in-production"},
        )


def test_development_and_testing_keep_labeled_fallback() -> None:
    """Development and testing keep the explicit non-production fallback."""
    development = _settings(environment="development")
    testing = _settings(environment="testing")

    assert development.security.secret_key is not None
    assert testing.security.secret_key is not None
    assert development.security.secret_key.get_secret_value() == DEVELOPMENT_SECURITY_SECRET
    assert testing.security.secret_key.get_secret_value() == DEVELOPMENT_SECURITY_SECRET


def test_production_accepts_security_secret_file(tmp_path: Path) -> None:
    """Production accepts a real file-backed security secret."""
    path = _secret_file(tmp_path)

    settings = _settings(
        environment="production",
        security={"secret_key_file": path},
    )

    assert settings.security.secret_key is not None
    assert (
        settings.security.secret_key.get_secret_value() == "real-security-secret-for-tests-32bytes"
    )


def test_security_secret_file_env_var(tmp_path: Path) -> None:
    """COACHIQ_SECURITY__SECRET_KEY_FILE loads a file-backed security secret."""
    path = _secret_file(tmp_path, "env-security-secret-for-tests-32bytes")
    with patch.dict(
        os.environ,
        isolated_env({"COACHIQ_SECURITY__SECRET_KEY_FILE": str(path)}),
        clear=True,
    ):
        settings = make_test_settings(environment="production")

    assert settings.security.secret_key is not None
    assert (
        settings.security.secret_key.get_secret_value() == "env-security-secret-for-tests-32bytes"
    )


def test_blank_secret_file_env_vars_are_unset() -> None:
    """Blank *_SECRET_KEY_FILE env vars behave like unset values."""
    with patch.dict(
        os.environ,
        isolated_env(
            {
                "COACHIQ_SECURITY__SECRET_KEY_FILE": "",
                "COACHIQ_AUTH__SECRET_KEY_FILE": "",
            }
        ),
        clear=True,
    ):
        settings = make_test_settings(environment="development")

    assert settings.security.secret_key_file is None
    assert settings.auth.secret_key_file is None


def test_auth_secret_file_satisfies_enabled_auth(tmp_path: Path) -> None:
    """COACHIQ_AUTH__SECRET_KEY_FILE can satisfy enabled auth secret validation."""
    expected = "auth-secret-for-tests-32bytes"
    path = _secret_file(tmp_path, expected)

    settings = _settings(
        auth={"enabled": True, "secret_key_file": path},
    )

    assert settings.auth.secret_key == expected


def test_empty_secret_file_is_rejected(tmp_path: Path) -> None:
    """Empty secret files fail during settings construction."""
    path = _secret_file(tmp_path, "")

    with pytest.raises(ValidationError, match="Secret file is empty"):
        _settings(environment="production", security={"secret_key_file": path})
