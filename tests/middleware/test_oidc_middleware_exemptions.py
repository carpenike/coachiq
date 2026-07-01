"""Tests for OIDC auth/CSRF middleware exemptions."""

from unittest.mock import Mock

from backend.middleware.auth import AuthenticationMiddleware
from backend.middleware.csrf_protection import CSRFProtectionMiddleware
from backend.middleware.secure_auth import SecureAuthenticationMiddleware


def test_oidc_paths_are_auth_exempt() -> None:
    """OIDC login and callback paths are reachable before local authentication."""
    middleware = AuthenticationMiddleware(app=Mock())

    assert middleware._is_excluded_path("/api/v1/auth/oidc/login") is True
    assert middleware._is_excluded_path("/api/v1/auth/oidc/callback") is True


def test_oidc_paths_are_csrf_exempt() -> None:
    """OIDC callback relies on state/nonce/PKCE, not the CSRF cookie."""
    assert "/api/v1/auth/oidc/login" in CSRFProtectionMiddleware.EXEMPT_PATHS
    assert "/api/v1/auth/oidc/callback" in CSRFProtectionMiddleware.EXEMPT_PATHS


def test_oidc_paths_are_secure_auth_public() -> None:
    """OIDC paths are public in the optional secure-auth middleware surface."""
    assert any(
        "/api/v1/auth/oidc/login".startswith(path)
        for path in SecureAuthenticationMiddleware.PUBLIC_ENDPOINTS
    )
    assert any(
        "/api/v1/auth/oidc/callback".startswith(path)
        for path in SecureAuthenticationMiddleware.PUBLIC_ENDPOINTS
    )
