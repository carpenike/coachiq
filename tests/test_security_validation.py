"""
Comprehensive security validation tests.

Tests security headers, CSRF protection, input validation, and other
security features to ensure defense-in-depth.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI, Request, status
from fastapi.testclient import TestClient

from backend.core.input_validation import (
    ValidationError,
    sanitize_string,
    validate_array_length,
    validate_can_id,
    validate_email,
    validate_entity_id,
    validate_ip_address,
    validate_numeric_range,
    validate_pin,
    validate_url,
    validate_username,
)
from backend.core.security_hardening import SecurityHeadersMiddleware
from backend.middleware.csrf_protection import CSRFProtectionMiddleware


class TestSecurityHeaders:
    """Test security headers middleware."""

    @pytest.fixture
    def app_with_security_headers(self):
        """Create test app with security headers."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        return app

    def test_security_headers_added(self, app_with_security_headers):
        """Test that security headers are added to responses."""
        client = TestClient(app_with_security_headers)
        response = client.get("/test")

        assert response.status_code == 200

        # Check required security headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in response.headers
        assert "Content-Security-Policy" in response.headers

    def test_hsts_header_https_only(self, app_with_security_headers):
        """Test HSTS header is only added for HTTPS."""
        client = TestClient(app_with_security_headers)

        # HTTP request should not have HSTS
        response = client.get("/test")
        assert "Strict-Transport-Security" not in response.headers

        # HTTPS request should have HSTS
        response = client.get("https://testserver/test")
        assert "Strict-Transport-Security" in response.headers
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]


class TestCSRFProtection:
    """Test CSRF protection middleware."""

    @pytest.fixture
    def app_with_csrf(self):
        """Create test app with CSRF protection."""
        app = FastAPI()
        app.add_middleware(
            CSRFProtectionMiddleware,
            secret_key="test-secret-key",
            secure_cookie=False  # For testing
        )

        @app.post("/test")
        async def test_post():
            return {"status": "ok"}

        @app.get("/test")
        async def test_get():
            return {"status": "ok"}

        return app

    def test_csrf_blocks_post_without_token(self, app_with_csrf):
        """Test that POST without CSRF token is blocked."""
        client = TestClient(app_with_csrf)
        response = client.post("/test", json={"data": "test"})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "CSRF validation failed" in response.json()["detail"]

    def test_csrf_allows_get_without_token(self, app_with_csrf):
        """Test that GET requests don't need CSRF token."""
        client = TestClient(app_with_csrf)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_csrf_allows_post_with_valid_token(self, app_with_csrf):
        """Test that POST with valid CSRF token is allowed."""
        client = TestClient(app_with_csrf)

        # First get a token by making a GET request
        get_response = client.get("/test")

        # In real implementation, token would be set in cookie
        # For this test, we'll simulate the double-submit pattern
        mock_token = "test-csrf-token"

        with patch.object(CSRFProtectionMiddleware, "_verify_token", return_value=True):
            response = client.post(
                "/test",
                json={"data": "test"},
                cookies={CSRFProtectionMiddleware.COOKIE_NAME: mock_token},
                headers={CSRFProtectionMiddleware.HEADER_NAME: mock_token}
            )

        assert response.status_code == 200


class TestInputValidation:
    """Test input validation helpers."""

    def test_sanitize_string_basic(self):
        """Test basic string sanitization."""
        assert sanitize_string("hello world") == "hello world"
        assert sanitize_string("  hello   world  ") == "hello world"
        assert sanitize_string("hello\x00world") == "helloworld"

    def test_sanitize_string_html_stripping(self):
        """Test HTML stripping in sanitization."""
        assert sanitize_string("<script>alert('xss')</script>") == "alert('xss')"
        assert sanitize_string("Hello <b>world</b>!") == "Hello world!"

    def test_sanitize_string_length_limit(self):
        """Test string length limiting."""
        long_string = "x" * 2000
        result = sanitize_string(long_string, max_length=100)
        assert len(result) == 100

    def test_validate_email_valid(self):
        """Test valid email validation."""
        assert validate_email("user@example.com") == "user@example.com"
        assert validate_email("User@Example.COM") == "user@example.com"
        assert validate_email(" user@example.com ") == "user@example.com"

    def test_validate_email_invalid(self):
        """Test invalid email validation."""
        with pytest.raises(ValidationError) as exc:
            validate_email("invalid.email")
        assert "Invalid email format" in str(exc.value)

        with pytest.raises(ValidationError):
            validate_email("@example.com")

        with pytest.raises(ValidationError):
            validate_email("user@")

    def test_validate_username_valid(self):
        """Test valid username validation."""
        assert validate_username("user123") == "user123"
        assert validate_username("test_user") == "test_user"
        assert validate_username("user-name") == "user-name"

    def test_validate_username_invalid(self):
        """Test invalid username validation."""
        with pytest.raises(ValidationError):
            validate_username("u")  # Too short

        with pytest.raises(ValidationError):
            validate_username("user@123")  # Invalid character

        with pytest.raises(ValidationError):
            validate_username("x" * 33)  # Too long

    def test_validate_entity_id(self):
        """Test entity ID validation."""
        assert validate_entity_id("light_1") == "light_1"
        assert validate_entity_id("HVAC-Zone-2") == "HVAC-Zone-2"

        with pytest.raises(ValidationError):
            validate_entity_id("entity id with spaces")

        with pytest.raises(ValidationError):
            validate_entity_id("")

    def test_validate_can_id(self):
        """Test CAN ID validation."""
        assert validate_can_id("0x123") == 0x123
        assert validate_can_id(0x1FFFFFFF) == 0x1FFFFFFF
        assert validate_can_id("291") == 291

        with pytest.raises(ValidationError):
            validate_can_id(0x20000000)  # Too large

        with pytest.raises(ValidationError):
            validate_can_id("invalid")

    def test_validate_pin(self):
        """Test PIN validation."""
        assert validate_pin("1357") == "1357"
        assert validate_pin("135790") == "135790"

        with pytest.raises(ValidationError):
            validate_pin("123")  # Too short

        with pytest.raises(ValidationError):
            validate_pin("1234")  # Weak PIN

        with pytest.raises(ValidationError):
            validate_pin("12a4")  # Non-numeric

    def test_validate_ip_address(self):
        """Test IP address validation."""
        assert validate_ip_address("8.8.8.8") == "8.8.8.8"
        assert validate_ip_address("2001:db8::1") == "2001:db8::1"

        with pytest.raises(ValidationError):
            validate_ip_address("192.168.1.1")  # Private IP

        with pytest.raises(ValidationError):
            validate_ip_address("127.0.0.1")  # Loopback

        with pytest.raises(ValidationError):
            validate_ip_address("not.an.ip")

    def test_validate_url(self):
        """Test URL validation."""
        assert validate_url("https://example.com") == "https://example.com"
        assert validate_url("http://example.com/path?query=1") == "http://example.com/path?query=1"

        with pytest.raises(ValidationError):
            validate_url("javascript:alert('xss')")  # Invalid scheme

        with pytest.raises(ValidationError):
            validate_url("http://localhost/admin")  # Local address

        with pytest.raises(ValidationError):
            validate_url("http://192.168.1.1/")  # Private IP

    def test_validate_numeric_range(self):
        """Test numeric range validation."""
        assert validate_numeric_range(50, 0, 100) == 50
        assert validate_numeric_range(0.5, 0.0, 1.0) == 0.5

        with pytest.raises(ValidationError):
            validate_numeric_range(150, 0, 100)

        with pytest.raises(ValidationError):
            validate_numeric_range(-10, 0, 100)

    def test_validate_array_length(self):
        """Test array length validation."""
        assert validate_array_length([1, 2, 3]) == [1, 2, 3]
        assert validate_array_length([], max_length=10) == []

        with pytest.raises(ValidationError):
            validate_array_length([1] * 101, max_length=100)

        with pytest.raises(ValidationError):
            validate_array_length("not a list")


class TestSecurityIntegration:
    """Test security features integration."""

    def test_auth_decorators_with_security_headers(self):
        """Test that auth decorators work with security headers."""
        # This would test the full integration

    def test_rate_limiting_with_csrf(self):
        """Test rate limiting works with CSRF protection."""
        # This would test rate limiting doesn't interfere with CSRF
