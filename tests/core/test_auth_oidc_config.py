"""Tests for typed OIDC authentication configuration."""

import pytest
from pydantic import ValidationError

from backend.core.config import AuthenticationSettings, ServerSettings, Settings


def test_oidc_client_secret_file_and_group_role_map_are_typed(tmp_path) -> None:
    """OIDC client secret supports the _FILE pattern and JSON group-role maps."""
    secret_file = tmp_path / "oidc-client-secret"
    secret_file.write_text("file-backed-client-secret\n", encoding="utf-8")

    settings = AuthenticationSettings(
        oidc_enabled=True,
        oidc_client_id="coachiq-client",
        oidc_client_secret_file=secret_file,
        oidc_group_role_map='{"coachiq-admins": "admin"}',
    )
    expected_secret = secret_file.read_text(encoding="utf-8").strip()

    assert settings.oidc_client_secret == expected_secret
    assert settings.oidc_group_role_map == {"coachiq-admins": "admin"}


def test_oidc_rejects_invalid_group_roles() -> None:
    """OIDC group mapping is limited to admin, user, and readonly roles."""
    with pytest.raises(ValidationError):
        AuthenticationSettings(
            oidc_enabled=True,
            oidc_client_id="coachiq-client",
            oidc_client_secret="client-secret",
            oidc_group_role_map={"coachiq-operators": "operator"},
        )


def test_oidc_requires_pathless_public_origin() -> None:
    """OIDC requires an absolute public origin without a URL path."""
    auth_settings = AuthenticationSettings(
        oidc_enabled=True,
        oidc_client_id="coachiq-client",
        oidc_client_secret="client-secret",
        oidc_group_role_map={"coachiq-users": "user"},
    )

    valid = Settings(
        testing=True,
        auth=auth_settings,
        server=ServerSettings(public_origin="https://iq.holtel.io"),
    )
    assert valid.server.public_origin == "https://iq.holtel.io"

    with pytest.raises(ValidationError):
        Settings(
            testing=True,
            auth=auth_settings,
            server=ServerSettings(public_origin="https://iq.holtel.io/callback"),
        )
