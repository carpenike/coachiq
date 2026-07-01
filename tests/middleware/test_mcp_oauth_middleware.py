"""Tests for MCP OAuth middleware exemptions."""

from unittest.mock import Mock

from backend.middleware.auth import AuthenticationMiddleware
from backend.middleware.csrf_protection import CSRFProtectionMiddleware
from backend.middleware.secure_auth import SecureAuthenticationMiddleware


def test_mcp_oauth_well_known_and_protocol_paths_are_auth_exempt() -> None:
    """OAuth discovery and protocol endpoints are reachable before auth."""
    middleware = AuthenticationMiddleware(app=Mock())

    assert middleware._is_excluded_path("/.well-known/oauth-authorization-server") is True
    assert middleware._is_excluded_path("/.well-known/oauth-protected-resource/api/mcp") is True
    assert middleware._is_excluded_path("/oauth/register") is True
    assert middleware._is_excluded_path("/oauth/token") is True


def test_mcp_oauth_paths_are_csrf_exempt() -> None:
    """OAuth protocol endpoints are CSRF-exempt for non-browser MCP clients."""
    middleware = CSRFProtectionMiddleware(app=Mock(), secret_key="test-secret")

    assert middleware._is_exempt(Mock(url=Mock(path="/.well-known/oauth-authorization-server")))
    assert middleware._is_exempt(Mock(url=Mock(path="/oauth/register")))
    assert middleware._is_exempt(Mock(url=Mock(path="/oauth/token")))


def test_mcp_oauth_paths_are_secure_auth_public() -> None:
    """OAuth paths are public in the optional secure-auth middleware surface."""
    assert any(
        "/.well-known/oauth-authorization-server".startswith(path)
        for path in SecureAuthenticationMiddleware.PUBLIC_ENDPOINTS
    )
    assert any(
        "/oauth/register".startswith(path)
        for path in SecureAuthenticationMiddleware.PUBLIC_ENDPOINTS
    )
