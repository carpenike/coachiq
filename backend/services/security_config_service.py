"""
Security Configuration Service for RV Safety Operations

Provides centralized security configuration management for:
- PIN security policies
- Rate limiting configurations
- Authentication requirements
- Security audit settings
- Network security policies

Designed for RV-C vehicle control systems with enhanced security requirements.
"""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class PINSecurityPolicy(BaseModel):
    """PIN security policy configuration."""

    # PIN Requirements
    min_pin_length: int = Field(4, ge=4, le=8, description="Minimum PIN length")
    max_pin_length: int = Field(8, ge=4, le=8, description="Maximum PIN length")
    require_numeric_only: bool = Field(True, description="Require numeric PINs only")

    # Session Management
    emergency_session_timeout_minutes: int = Field(
        5, ge=1, le=15, description="Emergency PIN session timeout"
    )
    override_session_timeout_minutes: int = Field(
        15, ge=5, le=60, description="Override PIN session timeout"
    )
    maintenance_session_timeout_minutes: int = Field(
        30, ge=15, le=120, description="Maintenance PIN session timeout"
    )
    max_concurrent_sessions_per_user: int = Field(
        2, ge=1, le=5, description="Max concurrent sessions per user"
    )

    # Lockout Protection
    max_failed_attempts: int = Field(
        3, ge=2, le=10, description="Max failed attempts before lockout"
    )
    lockout_duration_minutes: int = Field(
        15, ge=5, le=60, description="Lockout duration after max failures"
    )
    progressive_lockout_enabled: bool = Field(
        True, description="Enable progressive lockout increases"
    )

    # PIN Rotation
    enable_pin_rotation: bool = Field(True, description="Enable automatic PIN rotation")
    pin_rotation_days: int = Field(30, ge=7, le=90, description="Days between PIN rotation")
    require_pin_confirmation: bool = Field(
        True, description="Require PIN confirmation for critical ops"
    )
    force_rotation_on_breach: bool = Field(True, description="Force rotation on security breach")

    @validator("max_pin_length")
    def validate_pin_length_range(cls, v, values):
        if "min_pin_length" in values and v < values["min_pin_length"]:
            raise ValueError("max_pin_length must be >= min_pin_length")
        return v


class RateLimitingPolicy(BaseModel):
    """Rate limiting policy configuration."""

    # General API Limits
    general_requests_per_minute: int = Field(
        60, ge=10, le=300, description="General requests per minute per IP"
    )
    burst_limit: int = Field(10, ge=5, le=50, description="Burst request limit")

    # Safety-Specific Limits (more restrictive)
    safety_operations_per_minute: int = Field(
        5, ge=1, le=20, description="Safety operations per minute per user"
    )
    emergency_operations_per_hour: int = Field(
        3, ge=1, le=10, description="Emergency operations per hour per user"
    )
    pin_attempts_per_minute: int = Field(
        3, ge=1, le=10, description="PIN attempts per minute per IP"
    )

    # Protection Limits
    max_failed_operations_per_hour: int = Field(
        10, ge=5, le=50, description="Max failed operations before investigation"
    )

    # Network Policies
    trusted_networks: List[str] = Field(
        default_factory=lambda: ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"],
        description="Trusted IP networks (CIDR notation)",
    )
    blocked_networks: List[str] = Field(
        default_factory=list, description="Blocked IP networks (CIDR)"
    )

    # Privilege Escalation
    admin_rate_multiplier: float = Field(
        2.0, ge=1.0, le=5.0, description="Rate limit multiplier for admin users"
    )
    service_account_multiplier: float = Field(
        5.0, ge=1.0, le=10.0, description="Rate limit multiplier for service accounts"
    )


class AuthenticationPolicy(BaseModel):
    """Authentication policy configuration."""

    # Session Management
    session_timeout_minutes: int = Field(
        480, ge=60, le=1440, description="Standard session timeout (8 hours default)"
    )
    admin_session_timeout_minutes: int = Field(
        120, ge=30, le=480, description="Admin session timeout (2 hours default)"
    )
    remember_me_days: int = Field(30, ge=1, le=90, description="Remember me token duration")

    # Security Requirements
    require_mfa_for_admin: bool = Field(False, description="Require MFA for admin operations")
    require_pin_for_safety: bool = Field(True, description="Require PIN for safety operations")
    require_auth_for_read: bool = Field(
        True, description="Require authentication for read operations"
    )

    # Password/Token Policies
    token_rotation_enabled: bool = Field(True, description="Enable automatic token rotation")
    api_key_expiration_days: int = Field(90, ge=30, le=365, description="API key expiration period")

    # Brute Force Protection
    max_login_attempts: int = Field(5, ge=3, le=20, description="Max login attempts before lockout")
    login_lockout_minutes: int = Field(15, ge=5, le=60, description="Login lockout duration")


class AuditPolicy(BaseModel):
    """Security audit policy configuration."""

    # Event Logging
    log_all_authentication: bool = Field(True, description="Log all authentication attempts")
    log_safety_operations: bool = Field(True, description="Log all safety-critical operations")
    log_admin_operations: bool = Field(True, description="Log all admin operations")
    log_failed_operations: bool = Field(True, description="Log failed operations")

    # Event Retention
    audit_retention_days: int = Field(
        365, ge=90, le=2555, description="Audit log retention period (1 year default)"
    )
    compliance_retention_days: int = Field(
        2555, ge=365, le=3650, description="Compliance log retention (7 years default)"
    )

    # Alert Thresholds
    suspicious_activity_threshold: int = Field(
        5, ge=3, le=20, description="Events before suspicious activity alert"
    )
    brute_force_threshold: int = Field(
        5, ge=3, le=20, description="Failed attempts before brute force alert"
    )

    # Monitoring
    real_time_monitoring_enabled: bool = Field(
        True, description="Enable real-time security monitoring"
    )
    threat_detection_enabled: bool = Field(True, description="Enable automated threat detection")


class NetworkSecurityPolicy(BaseModel):
    """Network security policy configuration."""

    # SSL/TLS Requirements
    require_https: bool = Field(True, description="Require HTTPS for all connections")
    min_tls_version: str = Field("1.2", description="Minimum TLS version (1.2 or 1.3)")

    # IP Filtering
    enable_ip_whitelist: bool = Field(False, description="Enable IP whitelist mode")
    whitelist_networks: List[str] = Field(
        default_factory=list, description="Whitelisted IP networks"
    )
    enable_geoip_blocking: bool = Field(False, description="Enable GeoIP-based blocking")
    blocked_countries: List[str] = Field(default_factory=list, description="Blocked country codes")

    # DDoS Protection
    enable_ddos_protection: bool = Field(True, description="Enable DDoS protection")
    connection_limit_per_ip: int = Field(10, ge=1, le=100, description="Max connections per IP")
    request_size_limit_mb: int = Field(10, ge=1, le=100, description="Max request size in MB")

    # Security Headers
    enable_security_headers: bool = Field(True, description="Enable security headers")
    enable_csp: bool = Field(True, description="Enable Content Security Policy")
    enable_hsts: bool = Field(True, description="Enable HTTP Strict Transport Security")


class SecurityConfiguration(BaseModel):
    """Complete security configuration for RV-C systems."""

    # Policy Sections
    pin_policy: PINSecurityPolicy = Field(default_factory=PINSecurityPolicy)
    rate_limiting: RateLimitingPolicy = Field(default_factory=RateLimitingPolicy)
    authentication: AuthenticationPolicy = Field(default_factory=AuthenticationPolicy)
    audit: AuditPolicy = Field(default_factory=AuditPolicy)
    network: NetworkSecurityPolicy = Field(default_factory=NetworkSecurityPolicy)

    # Metadata
    config_version: str = Field("1.0", description="Configuration version")
    last_updated: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_by: str = Field("system", description="Who last updated the configuration")

    # Security Modes
    security_mode: str = Field("standard", description="Overall security mode")
    rv_deployment_mode: bool = Field(True, description="Optimize for RV deployment scenarios")

    @validator("security_mode")
    def apply_security_mode_defaults(cls, v, values):
        """Apply security mode-specific defaults."""
        if v == "minimal":
            # Minimal security for testing/development
            if "rate_limiting" in values:
                values["rate_limiting"].general_requests_per_minute = 120
                values["rate_limiting"].safety_operations_per_minute = 10
        elif v == "strict":
            # Strict security for production
            if "pin_policy" in values:
                values["pin_policy"].max_failed_attempts = 2
                values["pin_policy"].lockout_duration_minutes = 30
        elif v == "paranoid":
            # Maximum security for high-risk deployments
            if "pin_policy" in values:
                values["pin_policy"].max_failed_attempts = 1
                values["pin_policy"].lockout_duration_minutes = 60
            if "rate_limiting" in values:
                values["rate_limiting"].safety_operations_per_minute = 2
                values["rate_limiting"].emergency_operations_per_hour = 1
        return v


class SecurityConfigService:
    """
    Security configuration management service.

    Provides centralized management of security policies and configurations
    for RV-C vehicle control systems.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize security configuration service.

        Args:
            config_path: Path to security configuration file
        """
        self.config_path = config_path or Path("config/security.yml")
        self._config: Optional[SecurityConfiguration] = None
        self._last_reload = 0.0
        self._reload_interval = 300  # 5 minutes

        logger.info("Security Configuration Service initialized")

    def get_config(self, force_reload: bool = False) -> SecurityConfiguration:
        """
        Get current security configuration.

        Args:
            force_reload: Force reload from disk

        Returns:
            SecurityConfiguration: Current security config
        """
        now = time.time()

        if self._config is None or force_reload or now - self._last_reload > self._reload_interval:
            self._load_config()
            self._last_reload = now

        # Ensure we have a valid config
        if self._config is None:
            self._config = SecurityConfiguration()

        return self._config

    def _load_config(self) -> None:
        """Load configuration from file or create defaults."""
        try:
            if self.config_path.exists():
                import yaml

                with open(self.config_path, "r") as f:
                    config_data = yaml.safe_load(f)
                self._config = SecurityConfiguration(**config_data)
                logger.info(f"Loaded security configuration from {self.config_path}")
            else:
                self._config = SecurityConfiguration()
                logger.info("Using default security configuration")

        except Exception as e:
            logger.error(f"Error loading security configuration: {e}")
            self._config = SecurityConfiguration()

    def save_config(self, config: SecurityConfiguration, updated_by: str = "system") -> bool:
        """
        Save security configuration to file.

        Args:
            config: Security configuration to save
            updated_by: Who is updating the configuration

        Returns:
            bool: True if saved successfully
        """
        try:
            # Update metadata
            config.last_updated = datetime.now(UTC).isoformat()
            config.updated_by = updated_by

            # Ensure config directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Save to YAML
            import yaml

            with open(self.config_path, "w") as f:
                yaml.dump(config.model_dump(), f, default_flow_style=False, indent=2)

            # Update cached config
            self._config = config
            self._last_reload = time.time()

            logger.info(f"Security configuration saved by {updated_by}")
            return True

        except Exception as e:
            logger.error(f"Error saving security configuration: {e}")
            return False

    def get_pin_config(self) -> Dict[str, Any]:
        """Get PIN manager configuration."""
        config = self.get_config()
        return {
            "min_pin_length": config.pin_policy.min_pin_length,
            "max_pin_length": config.pin_policy.max_pin_length,
            "require_numeric_only": config.pin_policy.require_numeric_only,
            "emergency_pin_expires_minutes": config.pin_policy.emergency_session_timeout_minutes,
            "max_failed_attempts": config.pin_policy.max_failed_attempts,
            "lockout_duration_minutes": config.pin_policy.lockout_duration_minutes,
            "session_timeout_minutes": config.pin_policy.override_session_timeout_minutes,
            "max_concurrent_sessions": config.pin_policy.max_concurrent_sessions_per_user,
            "enable_pin_rotation": config.pin_policy.enable_pin_rotation,
            "pin_rotation_days": config.pin_policy.pin_rotation_days,
            "require_pin_confirmation": config.pin_policy.require_pin_confirmation,
        }

    def get_rate_limit_config(self) -> Dict[str, Any]:
        """Get rate limiting configuration."""
        config = self.get_config()
        return {
            "requests_per_minute": config.rate_limiting.general_requests_per_minute,
            "burst_limit": config.rate_limiting.burst_limit,
            "safety_operations_per_minute": config.rate_limiting.safety_operations_per_minute,
            "emergency_operations_per_hour": config.rate_limiting.emergency_operations_per_hour,
            "pin_attempts_per_minute": config.rate_limiting.pin_attempts_per_minute,
            "max_failed_operations_per_hour": config.rate_limiting.max_failed_operations_per_hour,
            "trusted_networks": config.rate_limiting.trusted_networks,
            "admin_multiplier": config.rate_limiting.admin_rate_multiplier,
        }

    def get_auth_config(self) -> Dict[str, Any]:
        """Get authentication configuration."""
        config = self.get_config()
        return {
            "session_timeout_minutes": config.authentication.session_timeout_minutes,
            "admin_session_timeout_minutes": config.authentication.admin_session_timeout_minutes,
            "require_pin_for_safety": config.authentication.require_pin_for_safety,
            "require_auth_for_read": config.authentication.require_auth_for_read,
            "max_login_attempts": config.authentication.max_login_attempts,
            "login_lockout_minutes": config.authentication.login_lockout_minutes,
        }

    def update_security_mode(self, mode: str, updated_by: str = "admin") -> bool:
        """
        Update security mode and apply corresponding policies.

        Args:
            mode: Security mode (minimal, standard, strict, paranoid)
            updated_by: Who is updating the mode

        Returns:
            bool: True if updated successfully
        """
        try:
            config = self.get_config()
            config.security_mode = mode

            # Apply mode-specific adjustments
            if mode == "minimal":
                config.rate_limiting.general_requests_per_minute = 120
                config.rate_limiting.safety_operations_per_minute = 10
                config.pin_policy.max_failed_attempts = 5
            elif mode == "strict":
                config.rate_limiting.safety_operations_per_minute = 3
                config.pin_policy.max_failed_attempts = 2
                config.pin_policy.lockout_duration_minutes = 30
            elif mode == "paranoid":
                config.rate_limiting.safety_operations_per_minute = 2
                config.rate_limiting.emergency_operations_per_hour = 1
                config.pin_policy.max_failed_attempts = 1
                config.pin_policy.lockout_duration_minutes = 60
                config.network.enable_ip_whitelist = True

            return self.save_config(config, updated_by)

        except Exception as e:
            logger.error(f"Error updating security mode: {e}")
            return False

    def validate_configuration(self) -> Dict[str, Any]:
        """
        Validate current security configuration.

        Returns:
            dict: Validation results with issues and recommendations
        """
        config = self.get_config()
        issues = []
        recommendations = []

        # Validate PIN policy
        if config.pin_policy.max_failed_attempts > 5:
            recommendations.append("Consider reducing max_failed_attempts for better security")

        if config.pin_policy.lockout_duration_minutes < 10:
            recommendations.append("Consider increasing lockout duration for better protection")

        # Validate rate limiting
        if config.rate_limiting.safety_operations_per_minute > 10:
            issues.append("Safety operations rate limit is too high for RV deployment")

        # Validate network security
        if not config.network.require_https and config.rv_deployment_mode:
            issues.append("HTTPS should be required for RV deployments")

        # Check for RV-specific configurations
        if config.rv_deployment_mode:
            if not config.authentication.require_pin_for_safety:
                issues.append("PIN should be required for safety operations in RV mode")

            if len(config.rate_limiting.trusted_networks) == 0:
                recommendations.append(
                    "Consider adding trusted RV networks to rate limiting policy"
                )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations,
            "last_validated": datetime.now(UTC).isoformat(),
            "config_version": config.config_version,
            "security_mode": config.security_mode,
        }

    def get_security_summary(self) -> Dict[str, Any]:
        """
        Get security configuration summary for monitoring.

        Returns:
            dict: Security configuration summary
        """
        config = self.get_config()
        validation = self.validate_configuration()

        return {
            "security_mode": config.security_mode,
            "rv_deployment_mode": config.rv_deployment_mode,
            "config_version": config.config_version,
            "last_updated": config.last_updated,
            "updated_by": config.updated_by,
            "validation": validation,
            "policies": {
                "pin_enabled": True,
                "rate_limiting_enabled": True,
                "audit_enabled": config.audit.real_time_monitoring_enabled,
                "network_security_enabled": config.network.require_https,
                "mfa_required": config.authentication.require_mfa_for_admin,
            },
            "key_settings": {
                "pin_max_attempts": config.pin_policy.max_failed_attempts,
                "pin_lockout_minutes": config.pin_policy.lockout_duration_minutes,
                "safety_ops_per_minute": config.rate_limiting.safety_operations_per_minute,
                "emergency_ops_per_hour": config.rate_limiting.emergency_operations_per_hour,
                "session_timeout_minutes": config.authentication.session_timeout_minutes,
            },
        }
