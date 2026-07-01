"""Tests for MCP OAuth endpoint security helpers."""

from backend.services.auth.mcp_oauth_security import McpOAuthRateLimiter, audit_mcp_oauth_event


def test_rate_limiter_enforces_per_key_window() -> None:
    """Rate limiter blocks requests after the configured per-key limit."""
    limiter = McpOAuthRateLimiter(limit=2, window_seconds=3600)

    assert limiter.allow("ip:127.0.0.1") is True
    assert limiter.allow("ip:127.0.0.1") is True
    assert limiter.allow("ip:127.0.0.1") is False
    assert limiter.allow("ip:127.0.0.2") is True


def test_audit_helper_redacts_secret_token_and_code_fields(caplog) -> None:
    """Audit helper logs protocol events without exposing secret material."""
    with caplog.at_level("INFO"):
        audit_mcp_oauth_event(
            "token_issued",
            client_id="client-1",
            client_secret="secret-value",
            access_token="ciqpat_value",
            authorization_code="code-value",
        )

    assert "token_issued" in caplog.text
    assert "secret-value" not in caplog.text
    assert "ciqpat_value" not in caplog.text
    assert "code-value" not in caplog.text
