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
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, validator

from backend.core.performance import PerformanceMonitor
from backend.repositories.security_config_repository import SecurityConfigRepository

logger = logging.getLogger(__name__)


class RateLimitRule(BaseModel):
    """Rate limit configuration for an endpoint."""

    requests: int = Field(..., description="Number of requests allowed")
    window: int = Field(..., description="Time window in seconds")


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
    trusted_networks: list[str] = Field(
        default_factory=lambda: ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"],
        description="Trusted IP networks (CIDR notation)",
    )
    blocked_networks: list[str] = Field(
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
    login_attempt_window_minutes: int = Field(
        15, ge=5, le=60, description="Time window for counting failed login attempts"
    )

    # JWT Configuration
    jwt_algorithm: str = Field("HS256", description="JWT algorithm to use (e.g., HS256, RS256)")
    access_token_expire_minutes: int = Field(
        60, ge=1, le=1440, description="Access token expiration time in minutes"
    )
    magic_link_expire_minutes: int = Field(
        15, ge=1, le=60, description="Magic link token expiration time in minutes"
    )
    refresh_token_expire_days: int = Field(
        7, ge=1, le=365, description="Refresh token expiration time in days"
    )

    # Feature Flags
    enable_magic_links: bool = Field(True, description="Enable magic link authentication")
    enable_oauth: bool = Field(False, description="Enable OAuth authentication")
    enable_mfa: bool = Field(False, description="Enable multi-factor authentication")


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
    whitelist_networks: list[str] = Field(
        default_factory=list, description="Whitelisted IP networks"
    )
    enable_geoip_blocking: bool = Field(False, description="Enable GeoIP-based blocking")
    blocked_countries: list[str] = Field(default_factory=list, description="Blocked country codes")

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

    def __init__(
        self,
        security_config_repository: SecurityConfigRepository,
        performance_monitor: PerformanceMonitor,
        config_path: Path | None = None,
    ):
        """
        Initialize security configuration service.

        Args:
            security_config_repository: Repository for security configuration data
            performance_monitor: Performance monitoring instance
            config_path: Path to security configuration file
        """
        self._repository = security_config_repository
        self._monitor = performance_monitor
        self.config_path = config_path or Path("config/security.yml")
        self._config: SecurityConfiguration | None = None
        self._last_reload = 0.0
        self._reload_interval = 300  # 5 minutes
        self._init_rate_limit_config()

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("Security Configuration Service initialized")

    async def get_config(self, force_reload: bool = False) -> SecurityConfiguration:
        """
        Get current security configuration.

        Args:
            force_reload: Force reload from disk

        Returns:
            SecurityConfiguration: Current security config
        """
        now = time.time()

        if self._config is None or force_reload or now - self._last_reload > self._reload_interval:
            await self._load_config()
            self._last_reload = now

        # Ensure we have a valid config
        if self._config is None:
            self._config = SecurityConfiguration()

        return self._config

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.get_config = self._monitor.monitor_service_method(
            "SecurityConfigService", "get_config"
        )(self.get_config)

        self.save_config = self._monitor.monitor_service_method(
            "SecurityConfigService", "save_config"
        )(self.save_config)

        self.validate_configuration = self._monitor.monitor_service_method(
            "SecurityConfigService", "validate_configuration"
        )(self.validate_configuration)

    async def _load_config(self) -> None:
        """Load configuration from repository or create defaults."""
        try:
            # Try to get cached config first
            cached_config = await self._repository.get_cached_config()
            if cached_config:
                self._config = SecurityConfiguration(**cached_config)
                return

            # Load from file via repository
            config_data = await self._repository.load_config(self.config_path)
            if config_data:
                self._config = SecurityConfiguration(**config_data)
                logger.info(f"Loaded security configuration from {self.config_path}")
            else:
                # Get default config from repository
                default_config = await self._repository.get_default_config()
                self._config = SecurityConfiguration(**default_config)
                logger.info("Using default security configuration")

        except Exception as e:
            logger.error(f"Error loading security configuration: {e}")
            # Fallback to basic defaults
            default_config = await self._repository.get_default_config()
            self._config = SecurityConfiguration(**default_config)

    async def save_config(self, config: SecurityConfiguration, updated_by: str = "system") -> bool:
        """
        Save security configuration via repository.

        Args:
            config: Security configuration to save
            updated_by: Who is updating the configuration

        Returns:
            bool: True if saved successfully
        """
        try:
            # Convert to dict for repository
            config_data = config.model_dump()

            # Save via repository
            success = await self._repository.save_config(self.config_path, config_data, updated_by)

            if success:
                # Update cached config
                self._config = config
                self._last_reload = time.time()
                logger.info(f"Security configuration saved by {updated_by}")

            return success

        except Exception as e:
            logger.error(f"Error saving security configuration: {e}")
            return False

    async def get_pin_config(self) -> dict[str, Any]:
        """Get PIN manager configuration."""
        config = await self.get_config()

        # Convert to dict and use repository method for consistency
        config_data = config.model_dump()
        return await self._repository.get_pin_config(config_data)

    async def get_rate_limit_config(self) -> dict[str, Any]:
        """Get rate limiting configuration."""
        config = await self.get_config()

        # Convert to dict and use repository method for consistency
        config_data = config.model_dump()
        return await self._repository.get_rate_limit_config(config_data)

    async def get_auth_config(self) -> dict[str, Any]:
        """Get authentication configuration with secure JWT secret handling."""
        config = await self.get_config()

        # Convert to dict and use repository method for consistency
        config_data = config.model_dump()
        auth_config = await self._repository.get_auth_config(config_data)

        # Securely inject JWT secret from environment variable
        # This overrides any value from YAML for security reasons
        jwt_secret = os.environ.get("COACHIQ_AUTH__SECRET_KEY")
        if jwt_secret:
            auth_config["jwt_secret"] = jwt_secret
        else:
            # No fallback - JWT secret MUST be provided via environment variable
            logger.error(
                "CRITICAL: JWT secret not found in environment variable COACHIQ_AUTH__SECRET_KEY. "
                "This is required for secure authentication. "
                "Please set COACHIQ_AUTH__SECRET_KEY to a secure random value."
            )
            raise ValueError(
                "JWT secret must be provided via COACHIQ_AUTH__SECRET_KEY environment variable. "
                "Generate a secure secret with: openssl rand -hex 32"
            )

        return auth_config

    async def update_security_mode(self, mode: str, updated_by: str = "admin") -> bool:
        """
        Update security mode and apply corresponding policies.

        Args:
            mode: Security mode (minimal, standard, strict, paranoid)
            updated_by: Who is updating the mode

        Returns:
            bool: True if updated successfully
        """
        try:
            config = await self.get_config()

            # Convert to dict for repository processing
            config_data = config.model_dump()

            # Apply security mode via repository
            updated_config_data = await self._repository.apply_security_mode(config_data, mode)

            # Create new config object from updated data
            updated_config = SecurityConfiguration(**updated_config_data)

            # Save the updated configuration
            return await self.save_config(updated_config, updated_by)

        except Exception as e:
            logger.error(f"Error updating security mode: {e}")
            return False

    async def validate_configuration(self) -> dict[str, Any]:
        """
        Validate current security configuration.

        Returns:
            dict: Validation results with issues and recommendations
        """
        config = await self.get_config()

        # Convert to dict for repository validation
        config_data = config.model_dump()

        # Use repository validation method
        return await self._repository.validate_config(config_data)

    async def get_security_summary(self) -> dict[str, Any]:
        """
        Get security configuration summary for monitoring.

        Returns:
            dict: Security configuration summary
        """
        config = await self.get_config()
        validation = await self.validate_configuration()

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

    async def get_config_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get configuration history.

        Args:
            limit: Maximum entries to return

        Returns:
            List of historical configurations
        """
        return await self._repository.get_config_history(limit)

    def _init_rate_limit_config(self):
        """Initialize rate limiting configuration placeholder.

        Note: Actual configuration comes from SecurityConfiguration.rate_limiting
        This is kept for backward compatibility during initialization.
        """
        # Will be populated from SecurityConfiguration
        self._rate_limit_config = None

    async def get_rate_limit_for_endpoint(
        self, endpoint: str, category: str = "api"
    ) -> dict[str, int]:
        """
        Get rate limit configuration for an endpoint.

        Args:
            endpoint: The endpoint path
            category: The endpoint category (auth, api, safety)

        Returns:
            Rate limit configuration with requests and window
        """
        # Get configuration from SecurityConfiguration
        config = await self.get_config()
        rate_policy = config.rate_limiting

        # Determine appropriate limits based on endpoint
        if "/auth/login" in endpoint or "/auth/signin" in endpoint:
            # Use PIN attempts limit for login (more restrictive)
            return {"requests": rate_policy.pin_attempts_per_minute, "window": 60}
        if "/auth/reset-password" in endpoint:
            # Password reset - very restrictive
            return {"requests": 3, "window": 3600}  # 3 per hour
        if "/auth/register" in endpoint:
            # Registration - restrictive
            return {"requests": 3, "window": 3600}  # 3 per hour
        if "/auth/refresh" in endpoint or "/token" in endpoint:
            # Token operations - moderate
            return {"requests": 10, "window": 300}  # 10 per 5 minutes
        if "/emergency" in endpoint:
            # Emergency operations - use configured limit
            return {"requests": rate_policy.emergency_operations_per_hour, "window": 3600}
        if "/pin" in endpoint:
            # PIN operations - use configured limit
            return {"requests": rate_policy.pin_attempts_per_minute, "window": 60}
        if "/safety" in endpoint:
            # Safety operations - use configured limit
            return {"requests": rate_policy.safety_operations_per_minute, "window": 60}
        if "/export" in endpoint:
            # Export operations - restrictive
            return {"requests": 5, "window": 300}  # 5 per 5 minutes
        if "/search" in endpoint:
            # Search operations - moderate
            return {"requests": 30, "window": 60}  # 30 per minute
        # Default API rate limit
        return {"requests": rate_policy.general_requests_per_minute, "window": 60}

    async def get_rate_limit_config(self) -> dict[str, Any]:
        """
        Get the complete rate limiting configuration.

        Returns:
            Complete rate limit configuration
        """
        # Get configuration from SecurityConfiguration
        config = await self.get_config()
        rate_policy = config.rate_limiting

        # Build rate limit configuration from policy
        return {
            "auth": {
                "login": {"requests": rate_policy.pin_attempts_per_minute, "window": 60},
                "password_reset": {"requests": 3, "window": 3600},
                "register": {"requests": 3, "window": 3600},
                "token_refresh": {"requests": 10, "window": 300},
            },
            "api": {
                "default": {"requests": rate_policy.general_requests_per_minute, "window": 60},
                "search": {"requests": 30, "window": 60},
                "export": {"requests": 5, "window": 300},
            },
            "safety": {
                "default": {"requests": rate_policy.safety_operations_per_minute, "window": 60},
                "emergency": {
                    "requests": rate_policy.emergency_operations_per_hour,
                    "window": 3600,
                },
                "pin_validation": {"requests": rate_policy.pin_attempts_per_minute, "window": 60},
            },
        }
