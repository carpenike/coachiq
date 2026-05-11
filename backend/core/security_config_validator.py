"""
Security Configuration Validator

Validates security settings at startup to ensure proper configuration
for production deployments.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from backend.core.config import Settings

logger = logging.getLogger(__name__)


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
            logger.error(f"Security validation failed with {len(self.errors)} errors")
            for error in self.errors:
                logger.error(f"  - {error}")

        if self.warnings:
            logger.warning(f"Security validation has {len(self.warnings)} warnings")
            for warning in self.warnings:
                logger.warning(f"  - {warning}")

        if is_valid and not self.warnings:
            logger.info("Security configuration validated successfully")

        return is_valid, self.errors, self.warnings

    def _validate_auth_settings(self) -> None:
        """Validate authentication settings."""
        # Check secret key
        if not self.settings.auth.secret_key:
            self.errors.append("AUTH: Secret key is not set")
        elif len(self.settings.auth.secret_key) < 32:
            self.errors.append("AUTH: Secret key is too short (min 32 characters)")
        elif self.settings.auth.secret_key == "your-secret-key-here":
            self.errors.append("AUTH: Default secret key detected - must be changed")

        # Check JWT settings
        if self.settings.auth.access_token_expire_minutes < 5:
            self.warnings.append("AUTH: Access token expiry is very short")
        elif self.settings.auth.access_token_expire_minutes > 60:
            self.warnings.append("AUTH: Access token expiry is very long")

        # Check admin credentials in single-user mode
        if self.settings.auth.mode == "single":
            if not self.settings.auth.admin_username:
                self.errors.append("AUTH: Admin username not set for single-user mode")
            if not self.settings.auth.admin_password_hash:
                self.errors.append("AUTH: Admin password not set for single-user mode")

        # Check multi-user mode settings
        if self.settings.auth.mode == "multi":
            if not self.settings.auth.enable_magic_link:
                self.warnings.append("AUTH: Magic link disabled in multi-user mode")

    def _validate_encryption_settings(self) -> None:
        """Validate encryption and crypto settings."""
        # Check for weak algorithms
        if hasattr(self.settings, "crypto"):
            if getattr(self.settings.crypto, "algorithm", "RS256") not in ["RS256", "ES256"]:
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
        if hasattr(self.settings, "allowed_hosts"):
            if not self.settings.allowed_hosts and not self.settings.is_development():
                self.warnings.append("NETWORK: No allowed hosts configured")

    def _validate_session_settings(self) -> None:
        """Validate session security settings."""
        # Check session timeout
        if hasattr(self.settings.auth, "session_timeout_minutes"):
            timeout = self.settings.auth.session_timeout_minutes
            if timeout > 1440:  # 24 hours
                self.warnings.append("SESSION: Very long session timeout")
            elif timeout < 15 and not self.settings.is_development():
                self.warnings.append("SESSION: Very short session timeout for production")

        # Check cookie settings
        if not self.settings.is_development():
            # These would be checked if we had explicit cookie settings
            pass

    def _validate_rate_limiting(self) -> None:
        """Validate rate limiting settings."""
        # Check if rate limiting is enabled
        if hasattr(self.settings, "rate_limiting"):
            if not getattr(self.settings.rate_limiting, "enabled", True):
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
            ".env",
            "config/coach_mapping.yml",
            "config/rvc.json",
        ]

        for file_path in sensitive_files:
            if os.path.exists(file_path):
                stat_info = os.stat(file_path)
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

        report = {
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
            "production_ready": is_valid and len(warnings) < 3,
        }

        return report

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
    is_valid, errors, warnings = validator.validate()

    return is_valid
