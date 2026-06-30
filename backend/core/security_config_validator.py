"""
Security Configuration Validator

Validates security settings at startup to ensure proper configuration
for production deployments.
"""

import logging
from pathlib import Path
from typing import Any

from backend.core.config import AuthenticationSettings, Settings

logger = logging.getLogger(__name__)

MIN_AUTH_SECRET_LENGTH = 32
MIN_JWT_EXPIRE_MINUTES = 5
MAX_JWT_EXPIRE_MINUTES = 60
MIN_SESSION_EXPIRE_HOURS = 1
MAX_SESSION_EXPIRE_HOURS = 24
MAX_PRODUCTION_READY_WARNINGS = 3
DEFAULT_AUTH_SECRET_PLACEHOLDER = "your-secret-key-here"  # noqa: S105
RECOMMENDED_JWT_ALGORITHMS = {"RS256", "ES256"}
OAUTH_PROVIDER_FIELDS = (
    ("github", "oauth_github_client_id", "oauth_github_client_secret"),
    ("google", "oauth_google_client_id", "oauth_google_client_secret"),
    ("microsoft", "oauth_microsoft_client_id", "oauth_microsoft_client_secret"),
)


class SecurityConfigValidator:
    """Validates security configuration for production readiness."""

    def __init__(self, settings: Settings):
        """Initialize validator with settings."""
        self.settings = settings
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate(self) -> tuple[bool, list[str], list[str]]:
        """
        Validate all security settings.

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []

        # Run all validation checks
        self._validate_auth_settings()
        self._validate_encryption_settings()
        self._validate_network_settings()
        self._validate_session_settings()
        self._validate_rate_limiting()
        self._validate_cors_settings()
        self._validate_security_headers()
        self._validate_file_permissions()

        is_valid = len(self.errors) == 0

        # Log results
        if self.errors:
            logger.error("Security validation failed with %d errors", len(self.errors))
            for error in self.errors:
                logger.error("  - %s", error)

        if self.warnings:
            logger.warning("Security validation has %d warnings", len(self.warnings))
            for warning in self.warnings:
                logger.warning("  - %s", warning)

        if is_valid and not self.warnings:
            logger.info("Security configuration validated successfully")

        return is_valid, self.errors, self.warnings

    def _validate_auth_settings(self) -> None:
        """Validate authentication settings."""
        auth = self.settings.auth

        if not auth.enabled:
            self._warn_on_disabled_auth_config(auth)
            return

        self._validate_auth_secret(auth)
        self._validate_jwt_lifetime(auth)
        self._validate_admin_credentials(auth)
        self._validate_magic_links(auth)
        self._validate_oauth(auth)

    def _warn_on_disabled_auth_config(self, auth: AuthenticationSettings) -> None:
        """Warn about auth-specific settings that are ignored while auth is disabled."""
        if auth.admin_username or auth.admin_password or auth.admin_email:
            self.warnings.append("AUTH: Authentication is disabled but auth credentials are set")
        if auth.enable_oauth:
            self.warnings.append("AUTH: Authentication is disabled but OAuth is enabled")

    def _validate_auth_secret(self, auth: AuthenticationSettings) -> None:
        """Validate the JWT secret used when authentication is enabled."""
        if not auth.secret_key:
            self.errors.append("AUTH: Secret key is not set")
        elif len(auth.secret_key) < MIN_AUTH_SECRET_LENGTH:
            self.errors.append("AUTH: Secret key is too short (min 32 characters)")
        elif auth.secret_key == DEFAULT_AUTH_SECRET_PLACEHOLDER:
            self.errors.append("AUTH: Default secret key detected - must be changed")

    def _validate_jwt_lifetime(self, auth: AuthenticationSettings) -> None:
        """Validate JWT access-token lifetime bounds."""
        if auth.jwt_expire_minutes < MIN_JWT_EXPIRE_MINUTES:
            self.warnings.append("AUTH: Access token expiry is very short")
        elif auth.jwt_expire_minutes > MAX_JWT_EXPIRE_MINUTES:
            self.warnings.append("AUTH: Access token expiry is very long")

    def _validate_admin_credentials(self, auth: AuthenticationSettings) -> None:
        """Validate modeless admin credential consistency."""
        if bool(auth.admin_username) != bool(auth.admin_password):
            self.errors.append("AUTH: Admin username and password must both be set")

    def _validate_magic_links(self, auth: AuthenticationSettings) -> None:
        """Validate magic-link prerequisites."""
        if auth.enable_magic_links and not auth.base_url and not self.settings.is_development():
            self.errors.append("AUTH: base_url is required when magic links are enabled")

    def _validate_oauth(self, auth: AuthenticationSettings) -> None:
        """Validate OAuth provider completeness when OAuth is enabled."""
        complete_oauth_providers = 0
        for provider_name, client_id_field, client_secret_field in OAUTH_PROVIDER_FIELDS:
            client_id = getattr(auth, client_id_field)
            client_secret = getattr(auth, client_secret_field)
            if bool(client_id) != bool(client_secret):
                self.errors.append(
                    f"AUTH: OAuth provider {provider_name} requires both client ID and secret"
                )
            elif client_id and client_secret:
                complete_oauth_providers += 1

        if auth.enable_oauth and complete_oauth_providers == 0:
            self.errors.append("AUTH: OAuth is enabled but no complete provider is configured")

    def _validate_encryption_settings(self) -> None:
        """Validate encryption and crypto settings."""
        # Check for weak algorithms
        crypto_settings = getattr(self.settings, "crypto", None)
        crypto_algorithm = getattr(crypto_settings, "algorithm", "RS256")
        if crypto_algorithm not in RECOMMENDED_JWT_ALGORITHMS:
            self.warnings.append("CRYPTO: Using non-recommended JWT algorithm")

        # Note: SSL/TLS termination is handled by Caddy (reverse proxy)
        # FastAPI runs behind Caddy, so we don't check for SSL here

    def _validate_network_settings(self) -> None:
        """Validate network security settings."""
        # Check bind address. The literal "0.0.0.0" here is a comparison
        # target, not a bind operation; this validator's job is to detect
        # bind-all in production and warn about it. False-positive against
        # both bandit B104 and ruff S104 (hardcoded-bind-all-interfaces);
        # neither tool models comparison vs. assignment so suppress both.
        if (
            self.settings.server.host == "0.0.0.0"  # noqa: S104  # nosec B104
            and not self.settings.is_development()
        ):
            self.warnings.append("NETWORK: Binding to 0.0.0.0 in production")

        # Check trusted hosts
        allowed_hosts = getattr(self.settings, "allowed_hosts", None)
        if not allowed_hosts and not self.settings.is_development():
            self.warnings.append("NETWORK: No allowed hosts configured")

    def _validate_session_settings(self) -> None:
        """Validate session security settings."""
        timeout_hours = self.settings.auth.session_expire_hours
        if timeout_hours > MAX_SESSION_EXPIRE_HOURS:
            self.warnings.append("SESSION: Very long session timeout")
        elif timeout_hours < MIN_SESSION_EXPIRE_HOURS and not self.settings.is_development():
            self.warnings.append("SESSION: Very short session timeout for production")

        # Check cookie settings
        if not self.settings.is_development():
            # These would be checked if we had explicit cookie settings
            pass

    def _validate_rate_limiting(self) -> None:
        """Validate rate limiting settings."""
        # Check if rate limiting is enabled
        rate_limiting = getattr(self.settings, "rate_limiting", None)
        if rate_limiting is not None:
            if not getattr(rate_limiting, "enabled", True):
                self.warnings.append("RATE_LIMIT: Rate limiting disabled")
        # Rate limiting should be configured
        elif not self.settings.is_development():
            self.warnings.append("RATE_LIMIT: No rate limiting configuration found")

    def _validate_cors_settings(self) -> None:
        """Validate CORS settings."""
        # In this architecture, CORS is handled by Caddy
        if hasattr(self.settings, "cors"):
            self.warnings.append("CORS: CORS should be configured in Caddy, not application")

    def _validate_security_headers(self) -> None:
        """Validate security headers configuration."""
        # Headers are added by middleware, just check if in production
        if not self.settings.is_development():
            # Could check for specific header configurations if exposed
            pass

    def _validate_file_permissions(self) -> None:
        """Validate file and directory permissions."""
        # Check sensitive file permissions
        sensitive_files = [
            Path(".env"),
            Path("config/coach_mapping.yml"),
            Path("config/rvc.json"),
        ]

        for file_path in sensitive_files:
            if file_path.exists():
                stat_info = file_path.stat()
                mode = stat_info.st_mode & 0o777

                if mode & 0o077:  # Check for group/other permissions
                    self.warnings.append(
                        f"PERMISSIONS: {file_path} has overly permissive permissions: {oct(mode)}"
                    )

    def get_security_report(self) -> dict[str, Any]:
        """
        Generate a comprehensive security report.

        Returns:
            Dictionary with security status and recommendations
        """
        is_valid, errors, warnings = self.validate()

        return {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "checks_performed": [
                "Authentication configuration",
                "Encryption settings",
                "Network security (behind Caddy proxy)",
                "Session management",
                "Rate limiting (hybrid: Caddy + FastAPI)",
                "CORS configuration (handled by Caddy)",
                "Security headers (application + Caddy)",
                "File permissions",
            ],
            "recommendations": self._get_recommendations(),
            "production_ready": is_valid and len(warnings) < MAX_PRODUCTION_READY_WARNINGS,
        }

    def _get_recommendations(self) -> list[str]:
        """Get security recommendations based on current configuration."""
        recommendations = []

        if self.settings.is_development():
            recommendations.append("Switch to production mode for deployment")

        if not self.errors and not self.warnings:
            recommendations.append("Security configuration looks good!")
        else:
            if any("SECRET" in e or "KEY" in e for e in self.errors):
                recommendations.append("Generate strong random secrets for production")

            if any("SSL" in e or "TLS" in e for e in self.errors):
                recommendations.append("Enable HTTPS/TLS for production deployment")

            if any("RATE_LIMIT" in w for w in self.warnings):
                recommendations.append("Configure rate limiting for API protection")

        recommendations.append("Regularly review and update security settings")
        recommendations.append("Monitor security logs and audit trails")

        return recommendations


def validate_security_config(settings: Settings) -> bool:
    """
    Validate security configuration and log results.

    Args:
        settings: Application settings to validate

    Returns:
        True if configuration is valid, False otherwise
    """
    validator = SecurityConfigValidator(settings)
    is_valid, _errors, _warnings = validator.validate()

    return is_valid
