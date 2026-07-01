"""Regression tests for startup security configuration validation."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from backend.core.security_config_validator import SecurityConfigValidator, validate_security_config
from tests._helpers.settings import isolated_env, make_test_settings

if TYPE_CHECKING:
    from backend.core.config import Settings

pytestmark = [pytest.mark.auth, pytest.mark.unit]

SECURITY_SECRET = "security-secret-for-validator-tests-32bytes"  # noqa: S105
AUTH_SECRET = "auth-secret-for-validator-tests-32bytes"  # noqa: S105


def _settings(**kwargs: object) -> Settings:
    """Construct hermetic settings for validator tests."""
    with patch.dict(os.environ, isolated_env({}), clear=True):
        return make_test_settings(**kwargs)


def _production_settings(auth: dict[str, object] | None = None) -> Settings:
    """Build production settings with the required app-level security secret."""
    kwargs: dict[str, object] = {
        "environment": "production",
        "security": {"secret_key": SECURITY_SECRET},
    }
    if auth is not None:
        kwargs["auth"] = auth
    return _settings(**kwargs)


def test_auth_disabled_production_does_not_require_auth_secret() -> None:
    """Auth-disabled production validates without an auth JWT secret."""
    settings = _production_settings()

    assert validate_security_config(settings) is True


def test_auth_enabled_admin_path_uses_current_schema() -> None:
    """Admin credentials validate with admin_password, not removed hash/mode fields."""
    settings = _production_settings(
        {
            "enabled": True,
            "secret_key": AUTH_SECRET,
            "enable_magic_links": False,
            "admin_username": "admin",
            "admin_password": "correct-horse-battery-staple",
        }
    )

    assert validate_security_config(settings) is True


def test_auth_enabled_magic_link_path_requires_current_fields() -> None:
    """Magic-link settings validate with enable_magic_links and base_url."""
    settings = _production_settings(
        {
            "enabled": True,
            "secret_key": AUTH_SECRET,
            "admin_email": "admin@example.com",
            "enable_magic_links": True,
            "base_url": "https://coach.example",
        }
    )

    assert validate_security_config(settings) is True


def test_magic_links_require_base_url_in_production() -> None:
    """Production magic links without base_url fail meaningfully."""
    settings = _production_settings(
        {
            "enabled": True,
            "secret_key": AUTH_SECRET,
            "admin_email": "admin@example.com",
            "enable_magic_links": True,
        }
    )

    validator = SecurityConfigValidator(settings)

    is_valid, errors, _warnings = validator.validate()

    assert is_valid is False
    assert "AUTH: base_url is required when magic links are enabled" in errors


def test_oidc_enabled_while_auth_disabled_warns() -> None:
    """OIDC settings are reported when authentication is disabled."""
    settings = _settings(
        environment="production",
        security={"secret_key": SECURITY_SECRET},
        server={"public_origin": "https://iq.holtel.io"},
        auth={
            "enabled": False,
            "enable_magic_links": False,
            "oidc_enabled": True,
            "oidc_client_id": "coachiq-client",
            "oidc_client_secret": "client-secret",
            "oidc_group_role_map": {"coachiq-users": "user"},
        },
    )

    validator = SecurityConfigValidator(settings)

    is_valid, _errors, warnings = validator.validate()

    assert is_valid is True
    assert "AUTH: Authentication is disabled but OIDC is enabled" in warnings


def test_session_expiry_uses_current_hour_field() -> None:
    """Session validation uses session_expire_hours instead of removed minutes field."""
    settings = _production_settings(
        {
            "enabled": True,
            "secret_key": AUTH_SECRET,
            "enable_magic_links": False,
            "admin_username": "admin",
            "admin_password": "correct-horse-battery-staple",
            "session_expire_hours": 48,
        }
    )
    validator = SecurityConfigValidator(settings)

    is_valid, _errors, warnings = validator.validate()

    assert is_valid is True
    assert "SESSION: Very long session timeout" in warnings
