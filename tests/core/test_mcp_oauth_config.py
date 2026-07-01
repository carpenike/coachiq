"""Tests for MCP OAuth AS configuration and contract constants."""

import pytest
from pydantic import ValidationError

from backend.core.config import McpSettings, ServerSettings, Settings
from backend.services.auth.mcp_contract import (
    MCP_ACCESS_TOKEN_TTL_DAYS,
    MCP_AS_SCOPES_SUPPORTED,
    MCP_AS_TOKEN_AUTH_METHODS,
    MCP_DCR_REDIRECT_URI_PREFIXES,
    MCP_DEFAULT_PATH,
)


def test_mcp_settings_defaults_match_contract() -> None:
    """MCP settings default to the contract-declared path and token TTL."""
    settings = McpSettings()

    assert settings.path == MCP_DEFAULT_PATH
    assert settings.access_token_ttl_days == MCP_ACCESS_TOKEN_TTL_DAYS


def test_mcp_as_requires_pathless_public_origin() -> None:
    """MCP AS enablement requires a byte-match-safe public origin."""
    valid = Settings(
        testing=True,
        mcp=McpSettings(as_enabled=True),
        server=ServerSettings(public_origin="https://iq.holtel.io"),
    )
    assert valid.server.public_origin == "https://iq.holtel.io"

    with pytest.raises(ValidationError, match="PUBLIC_ORIGIN"):
        Settings(
            testing=True,
            mcp=McpSettings(as_enabled=True),
            server=ServerSettings(public_origin="https://iq.holtel.io/api"),
        )


@pytest.mark.parametrize("bad_path", ["api/mcp", "/", "/api/mcp/"])
def test_mcp_path_must_be_non_root_absolute_path_without_trailing_slash(bad_path: str) -> None:
    """MCP path validation prevents resource and well-known URL drift."""
    with pytest.raises(ValidationError, match="COACHIQ_MCP__PATH"):
        Settings(
            testing=True,
            mcp=McpSettings(as_enabled=True, path=bad_path),
            server=ServerSettings(public_origin="https://iq.holtel.io"),
        )


def test_mcp_contract_constants_are_verbatim() -> None:
    """Contract constants preserve load-bearing field values and redirect prefixes."""
    assert MCP_AS_SCOPES_SUPPORTED == ("openid", "email", "profile")
    assert MCP_AS_TOKEN_AUTH_METHODS == ("client_secret_basic", "client_secret_post", "none")
    assert MCP_DCR_REDIRECT_URI_PREFIXES == (
        "https://claude.ai/",
        "https://claude.com/",
        "http://127.0.0.1:",
        "http://127.0.0.1/",
        "http://localhost:",
        "http://localhost/",
        "https://vscode.dev/redirect",
        "https://insiders.vscode.dev/redirect",
    )
