"""Security Config Repository

Handles data access for security configuration including:
- Security policy storage and retrieval
- Configuration versioning
- Policy validation and caching
- Default policy management
"""

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class SecurityConfigRepository(MonitoredRepository):
    """Repository for security configuration management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # Configuration storage
        self._current_config: dict[str, Any] | None = None
        self._config_history: list[dict[str, Any]] = []
        self._max_history_entries = 100

        # Caching
        self._cache_ttl = 300  # 5 minutes
        self._last_load_time = 0.0

        # Default configurations by security mode
        self._security_mode_defaults = {
            "minimal": {
                "rate_limiting": {
                    "general_requests_per_minute": 120,
                    "safety_operations_per_minute": 10,
                },
                "pin_policy": {"max_failed_attempts": 5, "lockout_duration_minutes": 10},
            },
            "standard": {
                "rate_limiting": {
                    "general_requests_per_minute": 60,
                    "safety_operations_per_minute": 5,
                },
                "pin_policy": {"max_failed_attempts": 3, "lockout_duration_minutes": 15},
            },
            "strict": {
                "rate_limiting": {
                    "general_requests_per_minute": 30,
                    "safety_operations_per_minute": 3,
                },
                "pin_policy": {"max_failed_attempts": 2, "lockout_duration_minutes": 30},
            },
            "paranoid": {
                "rate_limiting": {
                    "general_requests_per_minute": 20,
                    "safety_operations_per_minute": 2,
                    "emergency_operations_per_hour": 1,
                },
                "pin_policy": {"max_failed_attempts": 1, "lockout_duration_minutes": 60},
                "network": {"enable_ip_whitelist": True},
            },
        }

    @MonitoredRepository._monitored_operation("load_config")
    async def load_config(self, config_path: Path) -> dict[str, Any] | None:
        """Load configuration from file.

        Args:
            config_path: Path to configuration file

        Returns:
            Configuration dictionary or None if not found
        """
        try:
            if config_path.exists():
                import yaml

                with open(config_path) as f:
                    config_data = yaml.safe_load(f)

                self._current_config = config_data
                self._last_load_time = time.time()

                logger.info(f"Loaded security configuration from {config_path}")
                return config_data
            logger.info("Configuration file not found, using defaults")
            return None

        except Exception as e:
            logger.error(f"Error loading security configuration: {e}")
            return None

    @MonitoredRepository._monitored_operation("save_config")
    async def save_config(
        self, config_path: Path, config_data: dict[str, Any], updated_by: str = "system"
    ) -> bool:
        """Save configuration to file.

        Args:
            config_path: Path to save configuration
            config_data: Configuration data
            updated_by: Who is updating the configuration

        Returns:
            True if saved successfully
        """
        try:
            # Update metadata
            config_data["last_updated"] = datetime.now(UTC).isoformat()
            config_data["updated_by"] = updated_by

            # Add to history
            self._add_to_history(config_data)

            # Ensure config directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)

            # Save to YAML
            import yaml

            with open(config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, indent=2)

            # Update cache
            self._current_config = config_data
            self._last_load_time = time.time()

            logger.info(f"Security configuration saved by {updated_by}")
            return True

        except Exception as e:
            logger.error(f"Error saving security configuration: {e}")
            return False

    @MonitoredRepository._monitored_operation("get_cached_config")
    async def get_cached_config(self) -> dict[str, Any] | None:
        """Get cached configuration if still valid.

        Returns:
            Cached configuration or None if expired
        """
        if self._current_config and (time.time() - self._last_load_time) < self._cache_ttl:
            return self._current_config
        return None

    @MonitoredRepository._monitored_operation("get_default_config")
    async def get_default_config(self) -> dict[str, Any]:
        """Get default security configuration.

        Returns:
            Default configuration dictionary
        """
        return {
            "pin_policy": {
                "min_pin_length": 4,
                "max_pin_length": 8,
                "require_numeric_only": True,
                "emergency_session_timeout_minutes": 5,
                "override_session_timeout_minutes": 15,
                "maintenance_session_timeout_minutes": 30,
                "max_concurrent_sessions_per_user": 2,
                "max_failed_attempts": 3,
                "lockout_duration_minutes": 15,
                "progressive_lockout_enabled": True,
                "enable_pin_rotation": True,
                "pin_rotation_days": 30,
                "require_pin_confirmation": True,
                "force_rotation_on_breach": True,
            },
            "rate_limiting": {
                "general_requests_per_minute": 60,
                "burst_limit": 10,
                "safety_operations_per_minute": 5,
                "emergency_operations_per_hour": 3,
                "pin_attempts_per_minute": 3,
                "max_failed_operations_per_hour": 10,
                "trusted_networks": ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"],
                "blocked_networks": [],
                "admin_rate_multiplier": 2.0,
                "service_account_multiplier": 5.0,
            },
            "authentication": {
                "session_timeout_minutes": 480,
                "admin_session_timeout_minutes": 120,
                "remember_me_days": 30,
                "require_mfa_for_admin": False,
                "require_pin_for_safety": True,
                "require_auth_for_read": True,
                "token_rotation_enabled": True,
                "api_key_expiration_days": 90,
                "max_login_attempts": 5,
                "login_lockout_minutes": 15,
            },
            "audit": {
                "log_all_authentication": True,
                "log_safety_operations": True,
                "log_admin_operations": True,
                "log_failed_operations": True,
                "audit_retention_days": 365,
                "compliance_retention_days": 2555,
                "suspicious_activity_threshold": 5,
                "brute_force_threshold": 5,
                "real_time_monitoring_enabled": True,
                "threat_detection_enabled": True,
            },
            "network": {
                "require_https": True,
                "min_tls_version": "1.2",
                "enable_ip_whitelist": False,
                "whitelist_networks": [],
                "enable_geoip_blocking": False,
                "blocked_countries": [],
                "enable_ddos_protection": True,
                "connection_limit_per_ip": 10,
                "request_size_limit_mb": 10,
                "enable_security_headers": True,
                "enable_csp": True,
                "enable_hsts": True,
            },
            "config_version": "1.0",
            "last_updated": datetime.now(UTC).isoformat(),
            "updated_by": "system",
            "security_mode": "standard",
            "rv_deployment_mode": True,
        }

    @MonitoredRepository._monitored_operation("apply_security_mode")
    async def apply_security_mode(
        self, config_data: dict[str, Any], security_mode: str
    ) -> dict[str, Any]:
        """Apply security mode-specific settings to configuration.

        Args:
            config_data: Base configuration
            security_mode: Security mode to apply

        Returns:
            Updated configuration
        """
        if security_mode not in self._security_mode_defaults:
            logger.warning(f"Unknown security mode: {security_mode}")
            return config_data

        # Deep merge mode-specific settings
        mode_settings = self._security_mode_defaults[security_mode]

        for section, settings in mode_settings.items():
            if section not in config_data:
                config_data[section] = {}
            config_data[section].update(settings)

        config_data["security_mode"] = security_mode

        return config_data

    @MonitoredRepository._monitored_operation("validate_config")
    async def validate_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """Validate security configuration.

        Args:
            config_data: Configuration to validate

        Returns:
            Validation results
        """
        issues = []
        recommendations = []

        # Validate PIN policy
        pin_policy = config_data.get("pin_policy", {})
        if pin_policy.get("max_failed_attempts", 3) > 5:
            recommendations.append("Consider reducing max_failed_attempts for better security")

        if pin_policy.get("lockout_duration_minutes", 15) < 10:
            recommendations.append("Consider increasing lockout duration for better protection")

        if pin_policy.get("min_pin_length", 4) < 4:
            issues.append("PIN length should be at least 4 digits")

        # Validate rate limiting
        rate_limiting = config_data.get("rate_limiting", {})
        if rate_limiting.get("safety_operations_per_minute", 5) > 10:
            issues.append("Safety operations rate limit is too high for RV deployment")

        # Validate network security
        network = config_data.get("network", {})
        rv_mode = config_data.get("rv_deployment_mode", True)

        if not network.get("require_https", True) and rv_mode:
            issues.append("HTTPS should be required for RV deployments")

        # Check for RV-specific configurations
        if rv_mode:
            auth = config_data.get("authentication", {})
            if not auth.get("require_pin_for_safety", True):
                issues.append("PIN should be required for safety operations in RV mode")

            if len(rate_limiting.get("trusted_networks", [])) == 0:
                recommendations.append(
                    "Consider adding trusted RV networks to rate limiting policy"
                )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations,
            "last_validated": datetime.now(UTC).isoformat(),
            "config_version": config_data.get("config_version", "unknown"),
            "security_mode": config_data.get("security_mode", "unknown"),
        }

    def _add_to_history(self, config_data: dict[str, Any]) -> None:
        """Add configuration to history.

        Args:
            config_data: Configuration to add
        """
        # Create history entry
        history_entry = {
            "config": config_data.copy(),
            "timestamp": datetime.now(UTC).isoformat(),
            "updated_by": config_data.get("updated_by", "unknown"),
        }

        self._config_history.append(history_entry)

        # Trim history if needed
        if len(self._config_history) > self._max_history_entries:
            self._config_history = self._config_history[-self._max_history_entries :]

    @MonitoredRepository._monitored_operation("get_config_history")
    async def get_config_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get configuration history.

        Args:
            limit: Maximum entries to return

        Returns:
            List of historical configurations
        """
        return self._config_history[-limit:]

    @MonitoredRepository._monitored_operation("get_pin_config")
    async def get_pin_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """Extract PIN manager configuration.

        Args:
            config_data: Full configuration

        Returns:
            PIN configuration for PIN manager
        """
        pin_policy = config_data.get("pin_policy", {})

        return {
            "min_pin_length": pin_policy.get("min_pin_length", 4),
            "max_pin_length": pin_policy.get("max_pin_length", 8),
            "require_numeric_only": pin_policy.get("require_numeric_only", True),
            "emergency_pin_expires_minutes": pin_policy.get("emergency_session_timeout_minutes", 5),
            "max_failed_attempts": pin_policy.get("max_failed_attempts", 3),
            "lockout_duration_minutes": pin_policy.get("lockout_duration_minutes", 15),
            "session_timeout_minutes": pin_policy.get("override_session_timeout_minutes", 15),
            "max_concurrent_sessions": pin_policy.get("max_concurrent_sessions_per_user", 2),
            "enable_pin_rotation": pin_policy.get("enable_pin_rotation", True),
            "pin_rotation_days": pin_policy.get("pin_rotation_days", 30),
            "require_pin_confirmation": pin_policy.get("require_pin_confirmation", True),
        }

    @MonitoredRepository._monitored_operation("get_rate_limit_config")
    async def get_rate_limit_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """Extract rate limiting configuration.

        Args:
            config_data: Full configuration

        Returns:
            Rate limiting configuration
        """
        rate_limiting = config_data.get("rate_limiting", {})

        return {
            "requests_per_minute": rate_limiting.get("general_requests_per_minute", 60),
            "burst_limit": rate_limiting.get("burst_limit", 10),
            "safety_operations_per_minute": rate_limiting.get("safety_operations_per_minute", 5),
            "emergency_operations_per_hour": rate_limiting.get("emergency_operations_per_hour", 3),
            "pin_attempts_per_minute": rate_limiting.get("pin_attempts_per_minute", 3),
            "max_failed_operations_per_hour": rate_limiting.get(
                "max_failed_operations_per_hour", 10
            ),
            "trusted_networks": rate_limiting.get("trusted_networks", []),
            "admin_multiplier": rate_limiting.get("admin_rate_multiplier", 2.0),
        }

    @MonitoredRepository._monitored_operation("get_auth_config")
    async def get_auth_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """Extract authentication configuration.

        Args:
            config_data: Full configuration

        Returns:
            Authentication configuration
        """
        auth = config_data.get("authentication", {})

        return {
            "session_timeout_minutes": auth.get("session_timeout_minutes", 480),
            "admin_session_timeout_minutes": auth.get("admin_session_timeout_minutes", 120),
            "require_pin_for_safety": auth.get("require_pin_for_safety", True),
            "require_auth_for_read": auth.get("require_auth_for_read", True),
            "max_login_attempts": auth.get("max_login_attempts", 5),
            "login_lockout_minutes": auth.get("login_lockout_minutes", 15),
        }
