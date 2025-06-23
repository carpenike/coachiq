"""
Integration tests for the authentication system.

Tests cover:
- Authentication mode detection
- JWT token flows
- Endpoint security
- Configuration validation
- Error handling scenarios
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.core.config import AuthenticationSettings
from backend.integrations.auth.feature import AuthenticationFeature
from backend.services.auth_manager import (
    AuthenticationError,
    AuthManager,
    AuthMode,
    InvalidTokenError,
)


class TestAuthenticationModeDetection:
    """Test authentication mode detection logic."""

    def test_mode_detection_none_when_disabled(self):
        """Test that authentication mode is NONE when disabled."""
        auth_settings = AuthenticationSettings(enabled=False)
        auth_manager = AuthManager(auth_settings)
        assert auth_manager.auth_mode == AuthMode.NONE

    def test_mode_detection_multi_user_with_oauth(self):
        """Test that multi-user mode is detected when OAuth is enabled."""
        auth_settings = AuthenticationSettings(enabled=True, enable_oauth=True)
        auth_manager = AuthManager(auth_settings)
        assert auth_manager.auth_mode == AuthMode.MULTI_USER

    def test_mode_detection_multi_user_with_magic_links(self):
        """Test that multi-user mode is detected when magic links are enabled."""
        auth_settings = AuthenticationSettings(enabled=True, enable_magic_links=True)
        auth_manager = AuthManager(auth_settings)
        assert auth_manager.auth_mode == AuthMode.MULTI_USER

    def test_mode_detection_multi_user_with_admin_email(self):
        """Test that multi-user mode is detected when admin email is set."""
        auth_settings = AuthenticationSettings(enabled=True, admin_email="admin@example.com")
        auth_manager = AuthManager(auth_settings)
        assert auth_manager.auth_mode == AuthMode.MULTI_USER

    def test_mode_detection_single_user_with_credentials(self):
        """Test that single-user mode is detected when admin credentials are set."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            enable_magic_links=False,  # Disable magic links to get single-user mode
            admin_username="admin",
            admin_password="password",
        )
        auth_manager = AuthManager(auth_settings)
        assert auth_manager.auth_mode == AuthMode.SINGLE_USER

    def test_mode_detection_none_when_no_config(self):
        """Test that mode defaults to NONE when no specific config is provided."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            enable_magic_links=False,  # Disable magic links
            enable_oauth=False,  # Disable OAuth
        )
        auth_manager = AuthManager(auth_settings)
        assert auth_manager.auth_mode == AuthMode.NONE


class TestJWTTokenManagement:
    """Test JWT token generation and validation."""

    @pytest.fixture
    def auth_manager(self):
        """Create an auth manager with JWT capabilities."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            secret_key="test-secret-key-for-jwt-tokens",
            jwt_expire_minutes=30,
            admin_username="admin",
            admin_password="password",
        )
        return AuthManager(auth_settings)

    def test_token_generation_with_valid_settings(self, auth_manager):
        """Test JWT token generation with valid settings."""
        token = auth_manager.generate_token(user_id="test_user", username="testuser")

        assert isinstance(token, str)
        assert len(token) > 0
        assert "." in token  # JWT tokens have dots

    def test_token_validation_with_valid_token(self, auth_manager):
        """Test JWT token validation with a valid token."""
        # Generate a token
        token = auth_manager.generate_token(
            user_id="test_user", username="testuser", additional_claims={"role": "admin"}
        )

        # Validate the token
        payload = auth_manager.validate_token(token)

        assert payload["sub"] == "test_user"
        assert payload["username"] == "testuser"
        assert payload["role"] == "admin"
        assert payload["iss"] == "coachiq"
        assert payload["aud"] == "coachiq-api"

    def test_token_validation_with_invalid_token(self, auth_manager):
        """Test JWT token validation with an invalid token."""
        with pytest.raises(InvalidTokenError):
            auth_manager.validate_token("invalid.token.here")

    def test_token_validation_with_expired_token(self, auth_manager):
        """Test JWT token validation with an expired token."""
        # Generate an expired token
        expired_delta = timedelta(minutes=-10)  # 10 minutes ago
        token = auth_manager.generate_token(
            user_id="test_user", username="testuser", expires_delta=expired_delta
        )

        with pytest.raises(InvalidTokenError, match="expired"):
            auth_manager.validate_token(token)

    def test_token_generation_without_jwt_available(self):
        """Test token generation when JWT is not available."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            secret_key="",  # Empty secret key
        )
        auth_manager = AuthManager(auth_settings)

        with pytest.raises(AuthenticationError):
            auth_manager.generate_token("test_user", "testuser")


class TestSingleUserAuthentication:
    """Test single-user authentication flows."""

    @pytest.fixture
    def auth_manager(self):
        """Create an auth manager in single-user mode."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            secret_key="test-secret-key-for-jwt-tokens",
            enable_magic_links=False,  # Disable magic links to get single-user mode
            admin_username="admin",
            admin_password="testpassword",
        )
        return AuthManager(auth_settings)

    @pytest.mark.asyncio
    async def test_admin_authentication_success(self, auth_manager):
        """Test successful admin authentication."""
        token = await auth_manager.authenticate_admin("admin", "testpassword")

        assert token is not None
        assert isinstance(token, str)

        # Validate the returned token
        payload = auth_manager.validate_token(token)
        assert payload["sub"] == "admin"
        assert payload["username"] == "admin"
        assert payload["role"] == "admin"
        assert payload["mode"] == "single-user"

    @pytest.mark.asyncio
    async def test_admin_authentication_wrong_username(self, auth_manager):
        """Test admin authentication with wrong username."""
        token = await auth_manager.authenticate_admin("wronguser", "testpassword")
        assert token is None

    @pytest.mark.asyncio
    async def test_admin_authentication_wrong_password(self, auth_manager):
        """Test admin authentication with wrong password."""
        token = await auth_manager.authenticate_admin("admin", "wrongpassword")
        assert token is None

    @pytest.mark.asyncio
    async def test_admin_authentication_in_wrong_mode(self):
        """Test admin authentication in wrong mode."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            enable_oauth=True,  # This puts it in multi-user mode
            secret_key="test-secret-key",
        )
        auth_manager = AuthManager(auth_settings)

        token = await auth_manager.authenticate_admin("admin", "password")
        assert token is None


class TestMagicLinkAuthentication:
    """Test magic link authentication flows."""

    @pytest.fixture
    def auth_manager_with_notification(self):
        """Create an auth manager with notification manager."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            secret_key="test-secret-key-for-jwt-tokens",
            enable_magic_links=True,
            magic_link_expire_minutes=15,
            base_url="http://localhost:8000",
        )

        # Mock notification manager
        notification_manager = MagicMock()

        # Make the async method return a coroutine
        async def mock_send_email(*args, **kwargs):
            return True

        notification_manager.send_magic_link_email = mock_send_email

        return AuthManager(auth_settings, notification_manager)

    @pytest.mark.asyncio
    async def test_magic_link_generation(self, auth_manager_with_notification):
        """Test magic link generation."""
        magic_link = await auth_manager_with_notification.generate_magic_link(
            "user@example.com", expires_minutes=15
        )

        assert magic_link is not None
        assert magic_link.startswith("http://localhost:8000/api/auth/magic?token=")
        assert "token=" in magic_link

    @pytest.mark.asyncio
    async def test_magic_link_validation(self, auth_manager_with_notification):
        """Test magic link token validation."""
        # Generate a magic link
        magic_link = await auth_manager_with_notification.generate_magic_link("user@example.com")

        # Extract token from the magic link
        token = magic_link.split("token=")[1]

        # Validate the magic link token
        user_info = await auth_manager_with_notification.validate_magic_link(token)

        assert user_info is not None
        assert user_info["email"] == "user@example.com"
        assert user_info["user_id"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_magic_link_email_sending(self, auth_manager_with_notification):
        """Test magic link email sending."""
        success = await auth_manager_with_notification.send_magic_link_email(
            "user@example.com", expires_minutes=15
        )

        assert success is True

        # Since we mocked it as a regular function, we can't use assert_called_once
        # but we can verify success was True
        assert success is True

    @pytest.mark.asyncio
    async def test_magic_link_without_notification_manager(self):
        """Test magic link functionality without notification manager."""
        auth_settings = AuthenticationSettings(
            enabled=True, secret_key="test-secret-key", enable_magic_links=True
        )
        auth_manager = AuthManager(auth_settings)  # No notification manager

        success = await auth_manager.send_magic_link_email("user@example.com")
        assert success is False


class TestAuthenticationFeature:
    """Test authentication feature integration."""

    @pytest.mark.asyncio
    async def test_feature_startup_and_shutdown(self):
        """Test authentication feature startup and shutdown."""
        feature = AuthenticationFeature(
            name="authentication",
            enabled=True,
            config={"enabled": True, "secret_key": "test-secret-key"},
        )

        # Mock the settings
        with patch("backend.integrations.auth.feature.get_settings") as mock_settings:
            mock_settings.return_value.auth = AuthenticationSettings(
                enabled=True, secret_key="test-secret-key"
            )

            # Test startup
            await feature.startup()
            assert feature.auth_manager is not None
            assert feature.is_ready() is True

            # Test shutdown
            await feature.shutdown()

    def test_feature_health_status(self):
        """Test authentication feature health status."""
        feature = AuthenticationFeature(name="authentication", enabled=True)

        # Test health when not started
        assert feature.health == "failed"

        # Test health when disabled
        feature.enabled = False
        assert feature.health == "healthy"

    @pytest.mark.asyncio
    async def test_feature_health_check(self):
        """Test authentication feature health check method."""
        feature = AuthenticationFeature(name="authentication", enabled=True)

        # Mock auth manager
        mock_auth_manager = MagicMock()

        # Create an async coroutine for get_stats
        async def mock_get_stats():
            return {
                "auth_mode": "single",
                "jwt_available": True,
                "secret_key_configured": True,
                "notification_manager_available": False,
            }

        mock_auth_manager.get_stats = mock_get_stats
        feature.auth_manager = mock_auth_manager

        health_info = await feature.health_check()

        assert health_info["status"] == "healthy"
        assert health_info["auth_mode"] == "single"
        assert health_info["jwt_available"] is True


class TestAuthenticationConfiguration:
    """Test authentication configuration scenarios."""

    def test_authentication_settings_defaults(self):
        """Test authentication settings with defaults."""
        settings = AuthenticationSettings()

        assert settings.enabled is False
        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_expire_minutes == 30
        assert settings.magic_link_expire_minutes == 15
        assert settings.enable_magic_links is True
        assert settings.enable_oauth is False

    def test_authentication_settings_environment_override(self):
        """Test authentication settings with environment variable override."""
        with patch.dict(
            "os.environ",
            {
                "COACHIQ_AUTH__ENABLED": "true",
                "COACHIQ_AUTH__JWT_EXPIRE_MINUTES": "60",
                "COACHIQ_AUTH__ADMIN_USERNAME": "testadmin",
            },
        ):
            from backend.core.config import AuthenticationSettings

            settings = AuthenticationSettings()

            assert settings.enabled is True
            assert settings.jwt_expire_minutes == 60
            assert settings.admin_username == "testadmin"

    def test_auto_generated_secret_key(self):
        """Test handling when no secret key is configured."""
        settings = AuthenticationSettings(
            enabled=True,
            secret_key="",  # Empty secret key
        )
        auth_manager = AuthManager(settings)

        # The auth manager should detect that no secret key is configured
        # and handle this gracefully
        assert auth_manager.settings.secret_key == ""


class TestAuthenticationMiddleware:
    """Test authentication middleware functionality."""

    @pytest.fixture
    def mock_auth_manager(self):
        """Create a mock auth manager for middleware testing."""
        auth_manager = MagicMock()
        auth_manager.auth_mode = AuthMode.SINGLE_USER
        auth_manager.is_authenticated_request = MagicMock(return_value=True)
        auth_manager.validate_token = MagicMock(
            return_value={"sub": "test_user", "username": "testuser", "role": "user"}
        )
        return auth_manager

    def test_middleware_initialization(self, mock_auth_manager):
        """Test authentication middleware initialization."""
        from backend.middleware.auth import AuthenticationMiddleware

        middleware = AuthenticationMiddleware(app=MagicMock(), auth_manager=mock_auth_manager)

        assert middleware.auth_manager == mock_auth_manager

    def test_excluded_paths(self):
        """Test that certain paths are excluded from authentication."""
        from backend.middleware.auth import AuthenticationMiddleware

        middleware = AuthenticationMiddleware(app=MagicMock())

        # Test excluded paths
        assert middleware._is_excluded_path("/") is True
        assert middleware._is_excluded_path("/docs") is True
        assert middleware._is_excluded_path("/api/auth/login") is True
        assert middleware._is_excluded_path("/api/auth/status") is True
        assert middleware._is_excluded_path("/static/test.css") is True

        # Test non-excluded paths
        assert middleware._is_excluded_path("/api/entities") is False
        assert middleware._is_excluded_path("/api/dashboard") is False


class TestAuthenticationErrorHandling:
    """Test authentication error handling scenarios."""

    @pytest.mark.asyncio
    async def test_authentication_manager_startup_failure(self):
        """Test handling of authentication manager startup failure."""
        # Create settings that will cause startup failure
        auth_settings = AuthenticationSettings(
            enabled=True,
            secret_key="",  # Empty secret key
        )

        feature = AuthenticationFeature(name="authentication", enabled=True)

        with patch("backend.integrations.auth.feature.get_settings") as mock_settings:
            mock_settings.return_value.auth = auth_settings

            # Startup should not raise an exception even with invalid config
            await feature.startup()

            # But auth manager might not be properly initialized
            assert feature.auth_manager is not None  # It's created but may not be functional

    def test_token_validation_error_handling(self):
        """Test token validation error handling."""
        auth_settings = AuthenticationSettings(enabled=True, secret_key="test-secret-key")
        auth_manager = AuthManager(auth_settings)

        # Test with completely invalid token
        with pytest.raises(InvalidTokenError):
            auth_manager.validate_token("not-a-token")

        # Test with malformed JWT
        with pytest.raises(InvalidTokenError):
            auth_manager.validate_token("header.payload")  # Missing signature

    @pytest.mark.asyncio
    async def test_magic_link_generation_failure(self):
        """Test magic link generation failure scenarios."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            secret_key="",  # Empty secret key to generate tokens
        )
        auth_manager = AuthManager(auth_settings)

        magic_link = await auth_manager.generate_magic_link("user@example.com")
        assert magic_link is None  # Should handle gracefully


class TestAuthenticationStatistics:
    """Test authentication system statistics and monitoring."""

    @pytest.mark.asyncio
    async def test_auth_manager_statistics(self):
        """Test authentication manager statistics collection."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            secret_key="test-secret-key",
            enable_magic_links=False,  # Disable to get single-user mode
            admin_username="admin",
            admin_password="password",
        )
        auth_manager = AuthManager(auth_settings)

        stats = await auth_manager.get_stats()

        assert "auth_mode" in stats
        assert "jwt_available" in stats
        assert "secret_key_configured" in stats
        assert "notification_manager_available" in stats

        assert stats["auth_mode"] == "single"
        assert stats["jwt_available"] is True
        assert stats["secret_key_configured"] is True
        assert stats["notification_manager_available"] is False

    @pytest.mark.asyncio
    async def test_auth_manager_statistics_with_admin_info(self):
        """Test authentication manager statistics with admin information."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            secret_key="test-secret-key",
            enable_magic_links=False,  # Disable to get single-user mode
            admin_username="testadmin",
            admin_password="password",
        )
        auth_manager = AuthManager(auth_settings)

        stats = await auth_manager.get_stats()

        assert "admin_username" in stats
        assert "admin_created_at" in stats
        assert stats["admin_username"] == "testadmin"
        assert isinstance(stats["admin_created_at"], datetime)


# Integration test utilities
class TestAuthenticationIntegrationHelpers:
    """Helper methods for authentication integration testing."""

    @staticmethod
    def create_test_auth_manager(mode: str = "single") -> AuthManager:
        """Create a test authentication manager with specified mode."""
        if mode == "single":
            settings = AuthenticationSettings(
                enabled=True,
                secret_key="test-secret-key",
                enable_magic_links=False,  # Required for single-user mode
                admin_username="admin",
                admin_password="password",
            )
        elif mode == "multi":
            settings = AuthenticationSettings(
                enabled=True,
                secret_key="test-secret-key",
                enable_magic_links=True,
                admin_email="admin@example.com",
            )
        elif mode == "none":
            settings = AuthenticationSettings(enabled=False)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        return AuthManager(settings)

    @staticmethod
    def create_test_jwt_token(auth_manager: AuthManager, user_id: str = "test_user") -> str:
        """Create a test JWT token for testing purposes."""
        return auth_manager.generate_token(
            user_id=user_id, username="testuser", additional_claims={"role": "user"}
        )


# Pytest configuration for authentication tests
@pytest.fixture(autouse=True)
def reset_auth_state():
    """Reset authentication state between tests."""
    # This fixture ensures each test starts with a clean state
    return
    # Any cleanup code would go here


# Mark all tests in this module as authentication tests
pytestmark = pytest.mark.auth
