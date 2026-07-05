"""
CoachIQ Configuration Management

This module provides centralized configuration management for the CoachIQ application
using Pydantic Settings.

Environment Variable Patterns:
- For top-level settings: `COACHIQ_SETTING` (e.g., `COACHIQ_APP_NAME`)
- For nested settings: `COACHIQ_SECTION__SETTING` (e.g., `COACHIQ_SERVER__HOST`)

The loading order for configuration values is:
1. Default values specified in the Settings classes
2. Values from .env file (if present)
3. Environment variables (which override any previous values)

All settings are strongly typed and validated using Pydantic.

Note: "safety-critical" / "safety" naming in this file is historical and
refers to **API guardrail / command-validation** behavior, NOT vehicle safety.
The OEM Firefly MIRA panel owns the actual vehicle safety case. See
`docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md`.
"""

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_SECURITY_SECRET = "development-only-secret-key-do-not-use-in-production"  # noqa: S105
PLACEHOLDER_SECRET_MARKERS = ("do-not-use-in-production", "change-in-production")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_path(path: Path | str) -> Path:
    """Resolve a path relative to the repository root, not the process cwd."""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


def get_secret_value(secret: SecretStr | str | None) -> str:
    """Return a plain secret value for validation without exposing it in reprs."""
    if secret is None:
        return ""
    if isinstance(secret, SecretStr):
        return secret.get_secret_value()
    return secret


def is_real_secret(secret: SecretStr | str | None) -> bool:
    """Return true when a configured secret is not empty or a known placeholder."""
    candidate = get_secret_value(secret).strip()
    if not candidate:
        return False

    lowered = candidate.lower()
    return not any(marker in lowered for marker in PLACEHOLDER_SECRET_MARKERS)


def read_secret_file(secret_key_file: Path) -> SecretStr:
    """Read a file-backed secret and reject empty files."""
    secret = secret_key_file.read_text(encoding="utf-8").strip()
    if not secret:
        msg = f"Secret file is empty: {secret_key_file}"
        raise ValueError(msg)
    return SecretStr(secret)


def parse_optional_path(value: Any) -> Path | None:
    """Parse optional path settings, treating blank strings as unset."""
    if isinstance(value, str):
        stripped = value.strip()
        return Path(stripped) if stripped else None
    return value


class ServerSettings(BaseSettings):
    """
    Server configuration settings.

    Environment Variables:
        All settings can be configured with the prefix COACHIQ_SERVER__
        For example: COACHIQ_SERVER__HOST=0.0.0.0
    """

    model_config = SettingsConfigDict(env_prefix="COACHIQ_SERVER__", case_sensitive=False)

    host: str = Field(
        default="127.0.0.1",
        description="Server host address. Use '0.0.0.0' only in controlled networks as it binds to all interfaces.",
    )
    port: int = Field(default=8000, description="Server port", ge=1, le=65535)
    reload: bool = Field(default=False, description="Enable auto-reload in development")
    workers: int = Field(default=1, description="Number of worker processes", ge=1, le=32)
    access_log: bool = Field(default=True, description="Enable access logging")
    debug: bool = Field(default=False, description="Enable server debug mode")
    root_path: str = Field(default="", description="Root path for the application")
    public_origin: str = Field(
        default="",
        description="Externally reachable origin for redirect URI generation",
    )

    @field_validator("root_path", mode="before")
    @classmethod
    def parse_root_path(cls, v):
        """Handle None values for root_path."""
        if v is None:
            return ""
        return v

    # Advanced server settings
    keep_alive_timeout: int = Field(default=5, description="Keep-alive timeout in seconds")
    timeout_graceful_shutdown: int = Field(default=30, description="Graceful shutdown timeout")
    limit_concurrency: int | None = Field(
        default=None, description="Maximum number of concurrent connections"
    )
    limit_max_requests: int | None = Field(
        default=None, description="Maximum number of requests before worker restart"
    )
    timeout_notify: int = Field(default=30, description="Timeout for worker startup notification")
    worker_class: str = Field(
        default="uvicorn.workers.UvicornWorker", description="Worker class to use"
    )
    worker_connections: int = Field(
        default=1000, description="Maximum number of simultaneous clients"
    )
    server_header: bool = Field(default=False, description="Include server header in responses")
    date_header: bool = Field(default=True, description="Include date header in responses")

    # SSL/TLS settings
    ssl_keyfile: Path | None = Field(default=None, description="SSL private key file path")
    ssl_certfile: Path | None = Field(default=None, description="SSL certificate file path")
    ssl_ca_certs: Path | None = Field(default=None, description="SSL CA certificates file path")
    ssl_cert_reqs: int = Field(
        default=0,
        description="SSL certificate verification mode (0=CERT_NONE, 1=CERT_OPTIONAL, 2=CERT_REQUIRED)",
    )

    @field_validator("ssl_keyfile", "ssl_certfile", "ssl_ca_certs", mode="before")
    @classmethod
    def parse_ssl_path(cls, v):
        """Parse SSL file paths from strings."""
        if isinstance(v, str) and v.strip():
            return Path(v.strip())
        return v


class SecuritySettings(BaseSettings):
    """Security configuration settings."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_SECURITY__", case_sensitive=False)

    secret_key: SecretStr | None = Field(
        default=None,
        description="Secret key for session management (required in production, set via COACHIQ_SECURITY__SECRET_KEY)",
    )
    secret_key_file: Path | None = Field(
        default=None,
        description="Path to a file containing the security secret key",
    )
    api_key: SecretStr | None = Field(default=None, description="API key for authentication")
    allowed_ips: list[str] = Field(default=[], description="Allowed IP addresses")
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Rate limit requests per minute")

    # TLS/HTTPS Configuration
    tls_termination_is_external: bool = Field(
        default=False,
        description=(
            "When True, the application assumes it's behind a TLS-terminating reverse proxy. "
            "The proxy is responsible for HTTP->HTTPS redirection and HSTS headers. "
            "The application MUST be run with --proxy-headers for this to be secure."
        ),
    )

    @field_validator("allowed_ips", mode="before")
    @classmethod
    def parse_ips(cls, v):
        """Parse comma-separated IP addresses from environment variable."""
        if isinstance(v, str):
            return [ip.strip() for ip in v.split(",") if ip.strip()]
        return v

    @field_validator("secret_key_file", mode="before")
    @classmethod
    def parse_secret_key_file(cls, v):
        """Parse optional secret key file path from environment variables."""
        return parse_optional_path(v)

    @model_validator(mode="after")
    def resolve_secret_key(self) -> "SecuritySettings":
        """Resolve direct or file-backed security secrets."""
        if not get_secret_value(self.secret_key) and self.secret_key_file:
            self.secret_key = read_secret_file(self.secret_key_file)

        if not get_secret_value(self.secret_key):
            self.secret_key = SecretStr(DEVELOPMENT_SECURITY_SECRET)

        return self


class LoggingSettings(BaseSettings):
    """Logging configuration settings."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_LOGGING__", case_sensitive=False)

    level: str = Field(default="INFO", description="Logging level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string",
    )
    file: Path | None = Field(default=None, description="Log file path")
    log_to_file: bool = Field(default=False, description="Enable logging to file")
    log_file: Path | None = Field(default=None, description="Log file path (alias for file)")
    colorize: bool = Field(default=True, description="Enable colored logging output")
    max_bytes: int = Field(default=10485760, description="Maximum log file size in bytes")
    backup_count: int = Field(default=5, description="Number of backup log files")

    @field_validator("level", mode="before")
    @classmethod
    def validate_level(cls, v):
        """Validate logging level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if isinstance(v, str):
            v = v.upper()
            if v not in valid_levels:
                msg = f"Invalid logging level: {v}. Must be one of {valid_levels}"
                raise ValueError(msg)
        return v

    @field_validator("file", mode="before")
    @classmethod
    def parse_file_path(cls, v):
        """Parse file path from string."""
        if isinstance(v, str) and v.strip():
            return Path(v.strip())
        return v


class CANSettings(BaseSettings):
    """CAN bus configuration settings with interface mapping."""

    model_config = SettingsConfigDict(
        env_prefix="COACHIQ_CAN__", case_sensitive=False, env_parse_none_str=""
    )

    interface: str = Field(
        default="can0", description="CAN interface name (deprecated, use interfaces)"
    )
    interfaces: Any = Field(default=["can0"], description="CAN interface names")
    bustype: str = Field(default="socketcan", description="CAN bus type")
    bitrate: int = Field(default=500000, description="CAN bus bitrate")
    timeout: float = Field(default=1.0, description="CAN timeout in seconds", gt=0)
    buffer_size: int = Field(default=1000, description="Message buffer size", ge=1)
    auto_reconnect: bool = Field(default=True, description="Auto-reconnect on CAN failure")
    filters: Any = Field(default=[], description="CAN message filters")

    # New interface mapping - stored as Any to avoid auto-JSON parsing, validated to dict
    interface_mappings: Any = Field(
        default={"house": "can0", "chassis": "can1"},
        description="Logical to physical interface mapping",
        json_schema_extra={
            "examples": [
                {"house": "can0", "chassis": "can1"},
                "house:can0,chassis:can1",
                "house=can0,chassis=can1",
            ]
        },
    )

    @field_validator("interfaces", mode="before")
    @classmethod
    def parse_interfaces(cls, v) -> list[str]:
        """Parse comma-separated interfaces from environment variable."""
        if isinstance(v, str):
            return [f.strip() for f in v.split(",") if f.strip()]
        if isinstance(v, list):
            return v
        # Return default if unable to parse
        return ["can0"]

    @field_validator("filters", mode="before")
    @classmethod
    def parse_filters(cls, v) -> list[str]:
        """Parse comma-separated filters from environment variable."""
        if isinstance(v, str):
            return [f.strip() for f in v.split(",") if f.strip()]
        if isinstance(v, list):
            return v
        # Return default if unable to parse
        return []

    @field_validator("interface_mappings", mode="before")
    @classmethod
    def parse_interface_mappings(cls, v) -> dict[str, str]:
        """
        Parse interface mappings from environment variable or dict.

        Supports multiple formats:
        - Dictionary: {"house": "can0", "chassis": "can1"} (primary format)
        - JSON string: '{"house": "can0", "chassis": "can1"}' (from NixOS)
        - Colon-separated: "house:can0,chassis:can1" (fallback)
        - Equals-separated: "house=can0,chassis=can1" (fallback)

        Examples:
            COACHIQ_CAN__INTERFACE_MAPPINGS='{"house": "can0", "chassis": "can1"}'
            COACHIQ_CAN__INTERFACE_MAPPINGS="house:can0,chassis:can1"
            COACHIQ_CAN__INTERFACE_MAPPINGS="house=can0,chassis=can1"
        """
        if isinstance(v, str):
            # First try to parse as JSON (primary format from NixOS)
            import json

            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

            # Fallback to string parsing for manual configuration
            mappings = {}
            # Support both : and = as separators
            for pair in v.split(","):
                pair = pair.strip()
                if ":" in pair:
                    logical, physical = pair.split(":", 1)
                elif "=" in pair:
                    logical, physical = pair.split("=", 1)
                else:
                    continue  # Skip invalid pairs

                logical = logical.strip()
                physical = physical.strip()

                if logical and physical:
                    mappings[logical] = physical

            return mappings
        if isinstance(v, dict):
            return v
        # Return default value if unable to parse
        return {"house": "can0", "chassis": "can1"}

    @property
    def all_interfaces(self) -> list[str]:
        """Get all CAN interfaces, supporting both old and new configuration."""
        # If interfaces is explicitly set to non-default, use it
        if self.interfaces != ["can0"]:
            return self.interfaces
        # Otherwise, if interface (singular) is set to non-default, use it
        if self.interface != "can0":
            return [self.interface]
        # Use interfaces default
        return self.interfaces


class RVCSettings(BaseSettings):
    """RV-C configuration settings."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_RVC__", case_sensitive=False)

    config_dir: Path | None = Field(
        default=None, description="RVC configuration directory override"
    )
    spec_path: Path | None = Field(default=None, description="Path to RVC spec JSON file override")
    coach_mapping_path: Path | None = Field(
        default=None, description="Path to RVC coach mapping YAML file override"
    )
    coach_model: str | None = Field(
        default=None, description="Coach model to use for mapping selection"
    )

    @field_validator("config_dir", "spec_path", "coach_mapping_path", mode="before")
    @classmethod
    def parse_path(cls, v):
        """Parse path from string."""
        if isinstance(v, str) and v.strip():
            return Path(v.strip())
        return v

    def get_config_dir(self) -> Path:
        """Get the RVC configuration directory."""
        if self.config_dir:
            return self.config_dir

        # Search paths in order of preference
        search_paths = [
            # 1. Top-level config directory (for development)
            Path.cwd() / "config",
            # 2. Try to find bundled config files using importlib.resources
            self._get_bundled_config_dir(),
            # 3. Production: Look in /var/lib/coachiq/reference
            # This directory contains read-only reference data (RV-C specs, coach mappings)
            # managed by Nix with restrictive permissions
            Path("/var/lib/coachiq/reference"),
        ]

        for path in search_paths:
            if path and path.exists() and path.is_dir():
                return path

        # Default to top-level config
        return Path.cwd() / "config"

    def _get_bundled_config_dir(self) -> Path | None:
        """Try to locate bundled config files using importlib.resources."""
        try:
            # Try to find config files relative to the backend package
            import backend

            backend_pkg = resources.files(backend)
            backend_path = Path(str(backend_pkg))

            # Check if config directory exists relative to backend package
            config_candidates = [
                backend_path.parent / "config",  # ../config from backend/
                backend_path / "config",  # backend/config/
            ]

            for candidate in config_candidates:
                try:
                    if candidate.is_dir() and candidate.joinpath("rvc.json").is_file():
                        return Path(str(candidate))
                except (AttributeError, OSError):
                    continue

        except Exception:
            pass
        return None

    def get_spec_path(self) -> Path:
        """Get the RVC spec JSON file path."""
        if self.spec_path:
            return self.spec_path

        # Try bundled resources first for Nix compatibility
        bundled_path = self._get_bundled_file("rvc.json")
        if bundled_path and bundled_path.exists():
            return bundled_path

        # Fall back to config directory
        config_dir = self.get_config_dir()
        return config_dir / "rvc.json"

    def get_coach_mapping_path(self) -> Path:
        """Get the coach mapping YAML file path."""
        if self.coach_mapping_path:
            return self.coach_mapping_path

        # If coach_model is specified, try to find that specific mapping first in bundled resources
        if self.coach_model:
            bundled_model_path = self._get_bundled_file(f"{self.coach_model}.yml")
            if bundled_model_path and bundled_model_path.exists():
                return bundled_model_path

            # Then try in config directory
            config_dir = self.get_config_dir()
            coach_file = config_dir / f"{self.coach_model}.yml"
            if coach_file.exists():
                return coach_file

        # Try bundled default mapping first for Nix compatibility
        bundled_path = self._get_bundled_file("coach_mapping.default.yml")
        if bundled_path and bundled_path.exists():
            return bundled_path

        # Fall back to config directory
        config_dir = self.get_config_dir()
        return config_dir / "coach_mapping.default.yml"

    def _get_bundled_file(self, filename: str) -> Path | None:
        """Try to locate a specific bundled config file using importlib.resources."""
        try:
            # First try to find config files relative to the backend package
            import backend

            backend_pkg = resources.files(backend)
            backend_path = Path(str(backend_pkg))

            # Check if file exists relative to backend package
            file_candidates = [
                backend_path.parent / "config" / filename,  # ../config/filename from backend/
                backend_path / "config" / filename,  # backend/config/filename
            ]

            for candidate in file_candidates:
                try:
                    if candidate.is_file():
                        return Path(str(candidate))
                except (AttributeError, OSError):
                    continue

            # If not found, try using importlib.resources directly for bundled resources
            # This works better in packaged environments like Nix
            try:
                # Try to access as a direct package resource
                config_resource = resources.files("config")
                if config_resource:
                    config_file = config_resource / filename
                    if config_file.is_file():
                        return Path(str(config_file))
            except (ImportError, FileNotFoundError, AttributeError):
                pass

        except Exception:
            pass
        return None


class PersistenceSettings(BaseSettings):
    """Data persistence configuration settings - MANDATORY in new architecture."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_PERSISTENCE__", case_sensitive=False)

    # NOTE: enabled field removed - persistence is now mandatory
    data_dir: Path = Field(
        default=Path("/var/lib/coachiq"),
        description="Base directory for persistent data storage (REQUIRED)",
    )
    create_dirs: bool = Field(
        default=True,
        description="Automatically create data directories if they don't exist",
    )
    backup_enabled: bool = Field(default=True, description="Enable automatic backups")
    backup_retention_days: int = Field(
        default=30, description="Number of days to retain backups", ge=1, le=365
    )
    max_backup_size_mb: int = Field(
        default=500, description="Maximum backup size in MB", ge=1, le=10000
    )

    @field_validator("data_dir", mode="before")
    @classmethod
    def parse_data_dir(cls, v: Any) -> Any:
        """Parse and absolutize data directory paths."""
        if isinstance(v, str) and v.strip():
            return resolve_project_path(v.strip())
        if isinstance(v, Path):
            return resolve_project_path(v)
        return v

    def get_database_dir(self) -> Path:
        """Get the database storage directory."""
        # Note: subdirectory is plural ('databases') to match the layout
        # produced by PersistenceRepository._ensure_directories(). These two
        # have to agree or backup/list_backups assertions break.
        return self.data_dir / "databases"

    def get_backup_dir(self) -> Path:
        """Get the backup storage directory."""
        return self.data_dir / "backups"

    def get_config_dir(self) -> Path:
        """Get the user configuration directory."""
        return self.data_dir / "config"

    def get_themes_dir(self) -> Path:
        """Get the custom themes directory."""
        return self.data_dir / "themes"

    def get_dashboards_dir(self) -> Path:
        """Get the custom dashboards directory."""
        return self.data_dir / "dashboards"

    def get_logs_dir(self) -> Path:
        """Get the persistent logs directory."""
        return self.data_dir / "logs"

    def get_recordings_dir(self) -> Path:
        """Get the CAN recording storage directory."""
        return self.data_dir / "recordings"

    def get_reports_dir(self) -> Path:
        """Get the generated reports storage directory."""
        return self.data_dir / "reports"

    def get_notification_queue_db_path(self) -> Path:
        """Get the persistent notification queue database path."""
        return self.get_database_dir() / "notifications.db"

    def ensure_directories(self) -> list[Path]:
        """
        Ensure all required directories exist.

        Returns:
            List of directories that were created
        """
        if not self.create_dirs:
            return []

        directories = [
            self.data_dir,
            self.get_database_dir(),
            self.get_backup_dir(),
            self.get_config_dir(),
            self.get_themes_dir(),
            self.get_dashboards_dir(),
            self.get_logs_dir(),
            self.get_recordings_dir(),
            self.get_reports_dir(),
        ]

        created = []
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                created.append(directory)
            except (OSError, PermissionError) as e:
                # Log warning but don't fail startup
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to create directory {directory}: {e}")

        return created


class CANRecorderSettings(BaseSettings):
    """CAN bus recorder storage configuration."""

    model_config = SettingsConfigDict(
        env_prefix="COACHIQ_CAN_RECORDER__", case_sensitive=False, env_parse_none_str=""
    )

    storage_path: Path | None = Field(
        default=None,
        description=(
            "CAN recording storage directory. Relative values are anchored under "
            "COACHIQ_PERSISTENCE__DATA_DIR."
        ),
    )

    @field_validator("storage_path", mode="before")
    @classmethod
    def parse_storage_path(cls, v: Any) -> Path | None:
        """Parse optional recorder storage path settings."""
        return parse_optional_path(v)


class SMTPChannelConfig(BaseSettings):
    """SMTP channel configuration for notification system."""

    model_config = SettingsConfigDict(
        env_prefix="COACHIQ_NOTIFICATIONS__SMTP__", case_sensitive=False
    )

    enabled: bool = Field(default=False, description="Enable SMTP notifications")
    host: str = Field(default="localhost", description="SMTP server hostname")
    port: int = Field(default=587, description="SMTP server port", ge=1, le=65535)
    username: str = Field(default="", description="SMTP authentication username")
    password: SecretStr = Field(
        default_factory=lambda: SecretStr(""), description="SMTP authentication password"
    )
    from_email: str = Field(default="", description="From email address")
    from_name: str = Field(default="CoachIQ", description="From display name")
    use_tls: bool = Field(default=True, description="Use TLS/STARTTLS encryption")
    use_ssl: bool = Field(default=False, description="Use SSL encryption")
    timeout: int = Field(default=30, description="Connection timeout in seconds", ge=1, le=300)

    def to_apprise_url(self, to_email: str) -> str:
        """Generate Apprise SMTP URL for specific recipient."""
        protocol = "mailtos" if self.use_tls else "mailtos" if self.use_ssl else "mailto"
        auth_part = f"{self.username}:{self.password.get_secret_value()}" if self.username else ""
        host_part = f"{self.host}:{self.port}"

        # Build query parameters
        params = []
        if self.from_email:
            params.append(f"from={self.from_email}")
        if self.from_name != "CoachIQ":
            params.append(f"name={self.from_name}")
        params.append(f"to={to_email}")

        query_string = "&".join(params)

        if auth_part:
            return f"{protocol}://{auth_part}@{host_part}?{query_string}"
        return f"{protocol}://{host_part}?{query_string}"


class SlackChannelConfig(BaseSettings):
    """Slack channel configuration for notification system."""

    model_config = SettingsConfigDict(
        env_prefix="COACHIQ_NOTIFICATIONS__SLACK__", case_sensitive=False
    )

    enabled: bool = Field(default=False, description="Enable Slack notifications")
    webhook_url: str = Field(default="", description="Slack webhook URL")

    def to_apprise_url(self) -> str:
        """Generate Apprise Slack URL."""
        if not self.webhook_url.startswith("https://hooks.slack.com/services/"):
            return self.webhook_url
        return self.webhook_url.replace("https://hooks.slack.com/services/", "slack://")


class DiscordChannelConfig(BaseSettings):
    """Discord channel configuration for notification system."""

    model_config = SettingsConfigDict(
        env_prefix="COACHIQ_NOTIFICATIONS__DISCORD__", case_sensitive=False
    )

    enabled: bool = Field(default=False, description="Enable Discord notifications")
    webhook_url: str = Field(default="", description="Discord webhook URL")

    def to_apprise_url(self) -> str:
        """Generate Apprise Discord URL."""
        if not self.webhook_url.startswith("https://discord.com/api/webhooks/"):
            return self.webhook_url
        return self.webhook_url.replace("https://discord.com/api/webhooks/", "discord://")


class PushoverChannelConfig(BaseSettings):
    """Pushover channel configuration for notification system."""

    model_config = SettingsConfigDict(
        env_prefix="COACHIQ_NOTIFICATIONS__PUSHOVER__", case_sensitive=False
    )

    enabled: bool = Field(default=False, description="Enable Pushover notifications")
    user_key: str = Field(default="", description="Pushover user key")
    token: str = Field(default="", description="Pushover application token")
    device: str = Field(default="", description="Pushover device name (optional)")

    def to_apprise_url(self) -> str:
        """Convert to Apprise URL format."""
        if not self.enabled or not self.user_key or not self.token:
            return ""

        url = f"pover://{self.user_key}@{self.token}"
        if self.device:
            url += f"/{self.device}"

        return url


class WebhookChannelConfig(BaseSettings):
    """Webhook channel configuration for notification system."""

    model_config = SettingsConfigDict(
        env_prefix="COACHIQ_NOTIFICATIONS__WEBHOOK__", case_sensitive=False
    )

    enabled: bool = Field(default=False, description="Enable webhook notifications")
    default_timeout: int = Field(
        default=30, description="Default request timeout in seconds", ge=1, le=300
    )
    max_retries: int = Field(default=3, description="Default maximum retry attempts", ge=0, le=10)
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates by default")
    rate_limit_requests: int = Field(
        default=100, description="Rate limit requests per window", ge=1
    )
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds", ge=1)

    # Webhook targets configuration (simplified for environment variables)
    targets: dict[str, Any] = Field(
        default_factory=dict, description="Webhook target configurations"
    )


class NotificationSettings(BaseSettings):
    """Unified notification system configuration using Apprise."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_NOTIFICATIONS__", case_sensitive=False)

    enabled: bool = Field(default=False, description="Enable notification system")
    default_title: str = Field(
        default="CoachIQ Notification", description="Default notification title"
    )
    app_name: str = Field(
        default="CoachIQ",
        description="Application name used in notification templates and headers",
    )
    template_path: str = Field(
        default="backend/templates/email",
        description=(
            "Directory containing email notification templates. Earlier "
            "revisions used a root-level notification template directory, but the "
            "shipped templates actually live at ``backend/templates/email`` "
            "and ``EmailTemplateManager`` ignored this field anyway. "
            "Default updated to match what's actually on disk and the "
            "field is now honoured by the manager."
        ),
    )
    log_notifications: bool = Field(
        default=True, description="Log notification attempts and results"
    )

    # SafeNotificationManager / NotificationQueue knobs.
    # Production previously read these via ``getattr(self.config, ..., default)``
    # because they weren't defined here, which meant operators couldn't
    # actually tune them via env vars -- the ``getattr`` default was the
    # only path. Defining them as proper fields restores the config
    # surface and matches what the integration test fixture has expected
    # for a long time.
    queue_db_path: str = Field(
        default="data/notifications.db",
        description="SQLite path for the persistent notification queue (':memory:' for tests)",
    )
    rate_limit_max_tokens: int = Field(
        default=100,
        description="Token-bucket capacity for outbound notification rate limiting",
    )
    rate_limit_per_minute: int = Field(
        default=60,
        description="Token-bucket refill rate (tokens per minute) for outbound notifications",
    )
    debounce_minutes: int = Field(
        default=15,
        description="Suppression window for duplicate notifications (minutes)",
    )

    # Channel configurations
    smtp: SMTPChannelConfig = Field(default_factory=SMTPChannelConfig)
    slack: SlackChannelConfig = Field(default_factory=SlackChannelConfig)
    discord: DiscordChannelConfig = Field(default_factory=DiscordChannelConfig)
    pushover: PushoverChannelConfig = Field(default_factory=PushoverChannelConfig)
    webhook: WebhookChannelConfig = Field(default_factory=WebhookChannelConfig)

    def resolve_queue_db_path(self, persistence: PersistenceSettings | None = None) -> str:
        """Resolve the notification queue DB path without depending on process cwd."""
        if self.queue_db_path == ":memory:":
            return self.queue_db_path

        candidate = Path(self.queue_db_path).expanduser()
        if candidate.is_absolute():
            return str(candidate)

        persistence_settings = persistence or PersistenceSettings()
        if candidate == Path("data/notifications.db"):
            return str(persistence_settings.get_notification_queue_db_path())

        return str((persistence_settings.data_dir / candidate).resolve())

    def get_enabled_channels(self) -> list[tuple[str, str]]:
        """Get list of enabled notification channels with their Apprise URLs."""
        channels = []

        if self.smtp.enabled and self.smtp.host and self.smtp.from_email:
            # SMTP requires dynamic URL generation per recipient
            channels.append(("smtp", "dynamic"))

        if self.slack.enabled and self.slack.webhook_url:
            channels.append(("slack", self.slack.to_apprise_url()))

        if self.discord.enabled and self.discord.webhook_url:
            channels.append(("discord", self.discord.to_apprise_url()))

        if self.pushover.enabled and self.pushover.user_key and self.pushover.token:
            channels.append(("pushover", self.pushover.to_apprise_url()))

        if self.webhook.enabled and self.webhook.targets:
            # Webhook uses custom delivery mechanism
            channels.append(("webhook", "custom"))

        return channels


class AuthenticationSettings(BaseSettings):
    """Authentication system configuration."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_AUTH__", case_sensitive=False)

    # Core authentication settings
    enabled: bool = Field(default=False, description="Enable authentication system")
    secret_key: str = Field(
        default="",
        description="Secret key for JWT tokens - MUST be set via COACHIQ_AUTH__SECRET_KEY env var",
    )
    secret_key_file: Path | None = Field(
        default=None,
        description="Path to a file containing the JWT secret key",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expire_minutes: int = Field(
        default=15, description="JWT access token expiration in minutes"
    )

    # Refresh token settings
    refresh_token_expire_days: int = Field(
        default=7, description="Refresh token expiration in days"
    )
    refresh_token_secret: str = Field(
        default="",
        description="Separate secret key for refresh tokens - defaults to secret_key if not set",
    )
    enable_refresh_tokens: bool = Field(
        default=True, description="Enable refresh token functionality"
    )

    # Base URL for magic links
    base_url: str = Field(default="", description="Base URL for magic link generation")

    # Single-user mode settings
    admin_username: str = Field(default="", description="Admin username for single-user mode")
    admin_password: str = Field(default="", description="Admin password for single-user mode")

    # Multi-user mode settings
    admin_email: str = Field(default="", description="Admin email for multi-user mode")
    enable_magic_links: bool = Field(default=True, description="Enable magic link authentication")

    # PocketID OIDC settings
    oidc_enabled: bool = Field(default=False, description="Enable PocketID OIDC login")
    oidc_issuer: str = Field(default="https://id.holthome.net", description="PocketID issuer")
    oidc_client_id: str = Field(default="", description="PocketID OIDC client ID")
    oidc_client_secret: str = Field(default="", description="PocketID OIDC client secret")
    oidc_client_secret_file: Path | None = Field(
        default=None,
        description="Path to a file containing the PocketID OIDC client secret",
    )
    oidc_scopes: list[str] = Field(
        default_factory=lambda: ["openid", "profile", "email", "groups"],
        description="OIDC scopes requested from PocketID",
    )
    oidc_group_role_map: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of PocketID group names to CoachIQ roles",
    )
    oidc_discovery_ttl_seconds: int = Field(
        default=300, description="OIDC discovery cache TTL in seconds", ge=30
    )
    oidc_jwks_ttl_seconds: int = Field(
        default=300, description="OIDC JWKS cache TTL in seconds", ge=30
    )
    oidc_request_timeout_seconds: float = Field(
        default=3.0, description="OIDC HTTP request timeout in seconds", gt=0, le=30
    )
    oidc_state_ttl_seconds: int = Field(
        default=300, description="OIDC login state TTL in seconds", ge=60
    )
    oidc_session_code_ttl_seconds: int = Field(
        default=60, description="OIDC local session handoff code TTL in seconds", ge=15
    )
    oidc_frontend_callback_path: str = Field(
        default="/auth/oidc/callback",
        description="Frontend route that completes OIDC local token handoff",
    )
    oidc_failure_redirect_path: str = Field(
        default="/login?oidc_error=sso_unavailable",
        description="Frontend route for graceful OIDC failure redirects",
    )

    # Magic link settings
    magic_link_expire_minutes: int = Field(
        default=15, description="Magic link expiration in minutes"
    )

    # Session settings
    session_expire_hours: int = Field(default=24, description="Session expiration in hours")
    max_sessions_per_user: int = Field(default=5, description="Maximum sessions per user")

    # Security settings
    require_secure_cookies: bool = Field(
        default=True, description="Require secure cookies in production"
    )
    rate_limit_auth_attempts: int = Field(
        default=5, description="Rate limit for authentication attempts"
    )
    rate_limit_window_minutes: int = Field(default=15, description="Rate limit window in minutes")

    # Account lockout settings
    enable_account_lockout: bool = Field(
        default=True, description="Enable account lockout after failed attempts"
    )
    max_failed_attempts: int = Field(
        default=5, description="Maximum failed login attempts before lockout"
    )
    lockout_duration_minutes: int = Field(
        default=30, description="Initial lockout duration in minutes"
    )
    lockout_escalation_factor: float = Field(
        default=2.0, description="Escalation factor for subsequent lockouts"
    )
    max_lockout_duration_hours: int = Field(
        default=24, description="Maximum lockout duration in hours"
    )
    lockout_reset_success_count: int = Field(
        default=3, description="Successful logins needed to reset lockout escalation"
    )

    # Multi-Factor Authentication (MFA) settings
    enable_mfa: bool = Field(default=False, description="Enable multi-factor authentication")
    mfa_totp_issuer: str = Field(default="CoachIQ", description="TOTP issuer name")
    mfa_totp_digits: int = Field(default=6, description="Number of TOTP digits", ge=6, le=8)
    mfa_totp_window: int = Field(default=1, description="TOTP validation window", ge=0, le=5)
    mfa_backup_codes_count: int = Field(
        default=10, description="Number of backup codes to generate", ge=5, le=20
    )
    mfa_backup_code_length: int = Field(
        default=8, description="Length of backup codes", ge=6, le=16
    )

    @model_validator(mode="after")
    def validate_jwt_secret(self) -> "AuthenticationSettings":
        """Ensure JWT secret is provided when authentication is enabled."""
        if not self.secret_key and self.secret_key_file:
            self.secret_key = read_secret_file(self.secret_key_file).get_secret_value()

        if not self.oidc_client_secret and self.oidc_client_secret_file:
            self.oidc_client_secret = read_secret_file(
                self.oidc_client_secret_file
            ).get_secret_value()

        if self.enabled and not self.secret_key:
            msg = (
                "JWT secret key is required when authentication is enabled. "
                "Please set COACHIQ_AUTH__SECRET_KEY environment variable with a secure random value. "
                "Generate one with: openssl rand -hex 32"
            )
            raise ValueError(msg)

        # Set refresh token secret to main secret if not provided
        if self.enabled and self.enable_refresh_tokens and not self.refresh_token_secret:
            self.refresh_token_secret = self.secret_key

        if self.oidc_enabled:
            if not self.oidc_client_id:
                msg = "OIDC client ID is required when OIDC is enabled"
                raise ValueError(msg)
            if not self.oidc_client_secret:
                msg = "OIDC client secret is required when OIDC is enabled"
                raise ValueError(msg)
            valid_roles = {"admin", "user", "readonly"}
            invalid_roles = set(self.oidc_group_role_map.values()) - valid_roles
            if invalid_roles:
                msg = f"OIDC group role map contains invalid roles: {sorted(invalid_roles)}"
                raise ValueError(msg)

        return self

    @field_validator("secret_key_file", "oidc_client_secret_file", mode="before")
    @classmethod
    def parse_secret_key_file(cls, v):
        """Parse optional secret file paths from environment variables."""
        return parse_optional_path(v)

    @field_validator("oidc_scopes", mode="before")
    @classmethod
    def parse_oidc_scopes(cls, value):
        """Parse OIDC scopes from comma- or space-separated text."""
        if isinstance(value, str):
            normalized = value.replace(",", " ")
            return [scope.strip() for scope in normalized.split() if scope.strip()]
        return value

    @field_validator("oidc_group_role_map", mode="before")
    @classmethod
    def parse_oidc_group_role_map(cls, value):
        """Parse OIDC group role map from JSON text."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return {}
            parsed = json.loads(stripped)
            if not isinstance(parsed, dict):
                msg = "OIDC group role map must be a JSON object"
                raise ValueError(msg)
            return parsed
        return value

    require_mfa_for_admin: bool = Field(default=False, description="Require MFA for admin users")
    allow_mfa_bypass: bool = Field(default=True, description="Allow MFA bypass during grace period")
    mfa_setup_grace_period_hours: int = Field(
        default=24, description="Grace period for MFA setup in hours", ge=1, le=168
    )
    mfa_backup_code_regeneration_threshold: int = Field(
        default=3, description="Remaining backup codes threshold for regeneration", ge=1, le=10
    )

    # NOTE: refresh_token_secret intentionally has no "before" field_validator to
    # auto-generate a random value. Doing so would produce a NEW secret on every
    # process boot (invalidating all legacy-mode refresh tokens on restart) and would
    # pre-empt the validate_jwt_secret model-validator fallback below, which derives a
    # stable secret from the persisted secret_key. Leave the default empty so that
    # fallback applies.


class FeaturesSettings(BaseSettings):
    """Feature flags configuration."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_FEATURES__", case_sensitive=False)

    enable_maintenance_tracking: bool = Field(
        default=False, description="Enable maintenance tracking"
    )
    enable_notifications: bool = Field(default=False, description="Enable notifications")
    enable_vector_search: bool = Field(default=True, description="Enable vector search feature")
    enable_uptimerobot: bool = Field(default=False, description="Enable UptimeRobot integration")
    enable_pushover: bool = Field(default=False, description="Enable Pushover notifications")
    enable_api_docs: bool = Field(default=True, description="Enable API documentation")
    enable_metrics: bool = Field(default=True, description="Enable metrics collection")
    message_queue_size: int = Field(default=1000, description="Message queue size", ge=1)

    # Enhanced frontend features
    enable_dashboard_aggregation: bool = Field(
        default=True, description="Enable aggregated dashboard endpoints"
    )
    enable_bulk_operations: bool = Field(default=True, description="Enable bulk entity operations")
    enable_system_analytics: bool = Field(
        default=True, description="Enable system analytics and alerting"
    )
    enable_activity_tracking: bool = Field(
        default=True, description="Enable activity feed tracking"
    )

    # Domain API v1 features
    domain_api_v2: bool = Field(default=True, description="Enable domain API v1")
    entities_api_v2: bool = Field(default=True, description="Enable entities API v1")
    diagnostics_api_v2: bool = Field(default=True, description="Enable diagnostics API v1")
    analytics_api_v2: bool = Field(default=True, description="Enable analytics API v1")
    networks_api_v2: bool = Field(default=True, description="Enable networks API v1")
    system_api_v2: bool = Field(default=True, description="Enable system API v1")

    # Performance and optimization settings
    dashboard_cache_ttl: int = Field(
        default=30, description="Dashboard data cache TTL in seconds", ge=1
    )
    bulk_operation_limit: int = Field(
        default=50, description="Maximum entities per bulk operation", ge=1, le=200
    )
    activity_feed_limit: int = Field(
        default=100, description="Maximum activity feed entries", ge=10, le=1000
    )

    # Domain API Features - Migration Complete
    # Note: V2 flags removed per pre-release development policy
    diagnostics_api: bool = Field(
        default=False, description="Domain-specific diagnostics API with enhanced fault correlation"
    )
    analytics_api: bool = Field(
        default=False, description="Domain-specific analytics API with advanced telemetry"
    )
    networks_api: bool = Field(
        default=False,
        description="Domain-specific networks API with CAN bus monitoring and interface management",
    )
    system_api: bool = Field(
        default=False,
        description="Domain-specific system API with configuration management and service monitoring",
    )


class MultiNetworkSettings(BaseSettings):
    """Multi-network CAN management configuration settings."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_MULTI_NETWORK__", case_sensitive=False)

    enabled: bool = Field(default=False, description="Enable multi-network CAN management")

    # Network definitions
    default_networks: dict[str, dict[str, Any]] = Field(
        default={
            "house": {
                "interface": "can0",
                "protocol": "rvc",
                "priority": "high",
                "isolation": True,
                "description": "RV coach/house systems network",
            },
            "chassis": {
                "interface": "can1",
                "protocol": "j1939",
                "priority": "critical",
                "isolation": True,
                "description": "Vehicle chassis and engine systems network",
            },
        },
        description="Default network definitions with protocol mapping",
    )

    # Fault tolerance and health monitoring
    enable_fault_isolation: bool = Field(
        default=True, description="Enable automatic network fault isolation"
    )
    enable_health_monitoring: bool = Field(
        default=True, description="Enable continuous network health monitoring"
    )
    health_check_interval: int = Field(
        default=5, description="Health check interval in seconds", ge=1, le=60
    )

    # Cross-network communication policies
    enable_cross_network_routing: bool = Field(
        default=False, description="Enable controlled cross-network message routing"
    )
    cross_network_whitelist: list[str] = Field(
        default=[], description="Whitelisted message types for cross-network routing"
    )

    # Security and filtering
    enable_network_security: bool = Field(
        default=True, description="Enable network-level security filtering"
    )
    max_networks: int = Field(
        default=8, description="Maximum number of concurrent networks", ge=1, le=16
    )

    # Performance optimization
    message_routing_timeout: float = Field(
        default=0.1, description="Message routing timeout in seconds", gt=0
    )
    network_priority_scheduling: bool = Field(
        default=True, description="Enable priority-based network scheduling"
    )

    @field_validator("cross_network_whitelist", mode="before")
    @classmethod
    def parse_whitelist(cls, v):
        """Parse comma-separated whitelist from environment variable."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return v
        return []


class VictronSettings(BaseSettings):
    """Victron Cerbo GX (Venus OS) MQTT integration settings."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_VICTRON__", case_sensitive=False)

    enabled: bool = Field(default=False, description="Enable the Victron MQTT integration")
    host: str = Field(default="", description="Cerbo GX hostname or IP address")
    port: int = Field(default=1883, description="MQTT broker port on the Cerbo GX", ge=1, le=65535)
    username: str | None = Field(default=None, description="MQTT username (usually unset)")
    password: str | None = Field(default=None, description="MQTT password (usually unset)")
    portal_id: str | None = Field(
        default=None,
        description="VRM portal id; auto-discovered from broker traffic when unset",
    )
    keepalive_interval_seconds: float = Field(
        default=30.0,
        description="Interval for Venus OS keepalive publishes (broker stops after 60s without)",
        gt=0,
        lt=60,
    )
    broadcast_interval_seconds: float = Field(
        default=1.0,
        description="Minimum interval between entity state broadcasts per entity",
        gt=0,
    )


class TripLogSettings(BaseSettings):
    """GPS trip log (breadcrumb) settings.

    Reads position from the local gpsd (the same daemon the router sidecar
    uses) and records distance-sampled breadcrumbs segmented into trips.
    """

    model_config = SettingsConfigDict(env_prefix="COACHIQ_TRIP_LOG__", case_sensitive=False)

    enabled: bool = Field(default=False, description="Enable GPS trip logging")
    gpsd_host: str = Field(default="127.0.0.1", description="gpsd host")
    gpsd_port: int = Field(default=2947, description="gpsd JSON port", ge=1, le=65535)
    min_distance_m: float = Field(
        default=50.0,
        description="Minimum distance between recorded breadcrumbs in meters",
        gt=0,
    )
    min_interval_seconds: float = Field(
        default=15.0,
        description="Minimum time between recorded breadcrumbs while moving (0 disables)",
        ge=0,
    )
    stationary_speed_mps: float = Field(
        default=1.0,
        description="Below this speed the RV is considered stationary",
        ge=0,
    )
    trip_gap_minutes: float = Field(
        default=20.0,
        description="Stationary time that closes the current trip",
        gt=0,
    )
    retention_days: int = Field(
        default=0,
        description="Days of breadcrumbs to keep; 0 keeps everything",
        ge=0,
    )


class J1939Settings(BaseSettings):
    """J1939 protocol configuration settings."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_J1939__", case_sensitive=False)

    enabled: bool = Field(default=False, description="Enable J1939 protocol support")

    # J1939 specification file paths
    spec_path: Path | None = Field(
        default=None, description="Path to J1939 spec JSON file override"
    )
    standard_pgns_path: Path | None = Field(
        default=None, description="Path to standard J1939 PGNs definition file"
    )

    # Engine and transmission manufacturer support
    enable_cummins_extensions: bool = Field(
        default=True, description="Enable Cummins engine-specific PGNs and extensions"
    )
    enable_allison_extensions: bool = Field(
        default=True, description="Enable Allison transmission-specific PGNs and extensions"
    )
    enable_chassis_extensions: bool = Field(
        default=True, description="Enable chassis-specific PGNs (Spartan K2, etc.)"
    )

    # Network configuration
    default_interface: str = Field(
        default="chassis",
        description="Default logical interface for J1939 (maps to physical CAN interface)",
    )
    address_range_start: int = Field(
        default=128, description="Start of J1939 address range for this ECU", ge=128, le=247
    )
    address_range_end: int = Field(
        default=247, description="End of J1939 address range for this ECU", ge=128, le=247
    )

    # Message filtering and priorities
    priority_critical_pgns: list[int] = Field(
        default=[61444, 65262, 65265], description="PGNs treated as critical priority"
    )
    priority_high_pgns: list[int] = Field(
        default=[65266, 65272, 61443], description="PGNs treated as high priority"
    )

    # Security and validation
    enable_address_validation: bool = Field(
        default=True, description="Enable J1939 source address validation"
    )
    enable_pgn_validation: bool = Field(
        default=True, description="Enable PGN structure and range validation"
    )
    rate_limit_enabled: bool = Field(
        default=True, description="Enable rate limiting for J1939 messages"
    )
    max_messages_per_second: int = Field(
        default=500, description="Maximum J1939 messages per second per source", ge=1
    )

    # Protocol bridge settings
    enable_rvc_bridge: bool = Field(
        default=True, description="Enable automatic translation between J1939 and RV-C"
    )
    bridge_engine_data: bool = Field(
        default=True, description="Bridge engine data from J1939 to RV-C format"
    )
    bridge_transmission_data: bool = Field(
        default=True, description="Bridge transmission data from J1939 to RV-C format"
    )

    @field_validator("spec_path", "standard_pgns_path", mode="before")
    @classmethod
    def parse_path(cls, v):
        """Parse path from string."""
        if isinstance(v, str) and v.strip():
            return Path(v.strip())
        return v

    @field_validator("priority_critical_pgns", "priority_high_pgns", mode="before")
    @classmethod
    def parse_pgn_list(cls, v):
        """Parse comma-separated PGN list from environment variable."""
        if isinstance(v, str):
            return [int(pgn.strip()) for pgn in v.split(",") if pgn.strip().isdigit()]
        if isinstance(v, list):
            return [int(pgn) for pgn in v if isinstance(pgn, int | str) and str(pgn).isdigit()]
        return v

    def get_spec_path(self) -> Path:
        """Get the J1939 spec JSON file path."""
        if self.spec_path:
            return self.spec_path

        # Try bundled resources first for Nix compatibility
        bundled_path = self._get_bundled_file("j1939.json")
        if bundled_path and bundled_path.exists():
            return bundled_path

        # Fall back to config directory
        from backend.core.config_utils import get_config_dir

        config_dir = get_config_dir()
        return config_dir / "j1939.json"

    def get_standard_pgns_path(self) -> Path:
        """Get the standard J1939 PGNs definition file path."""
        if self.standard_pgns_path:
            return self.standard_pgns_path

        # Try bundled resources first
        bundled_path = self._get_bundled_file("j1939_standard_pgns.json")
        if bundled_path and bundled_path.exists():
            return bundled_path

        # Fall back to config directory
        from backend.core.config_utils import get_config_dir

        config_dir = get_config_dir()
        return config_dir / "j1939_standard_pgns.json"

    def _get_bundled_file(self, filename: str) -> Path | None:
        """Try to locate a specific bundled config file using importlib.resources."""
        try:
            # First try to find config files relative to the backend package
            from importlib import resources

            import backend

            backend_pkg = resources.files(backend)
            backend_path = Path(str(backend_pkg))

            # Check if file exists relative to backend package
            file_candidates = [
                backend_path.parent / "config" / filename,  # ../config/filename from backend/
                backend_path / "config" / filename,  # backend/config/filename
            ]

            for candidate in file_candidates:
                try:
                    if candidate.is_file():
                        return Path(str(candidate))
                except (AttributeError, OSError):
                    continue

        except Exception:
            pass
        return None


class FireflySettings(BaseSettings):
    """Firefly RV systems configuration settings."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_FIREFLY__", case_sensitive=False)

    enabled: bool = Field(default=False, description="Enable Firefly RV systems support")

    # Firefly-specific configuration
    enable_multiplexing: bool = Field(
        default=True, description="Enable Firefly message multiplexing support"
    )
    enable_custom_dgns: bool = Field(
        default=True, description="Enable Firefly proprietary DGN support"
    )
    enable_state_interlocks: bool = Field(
        default=True, description="Enable Firefly safety interlock monitoring"
    )
    enable_can_detective_integration: bool = Field(
        default=False, description="Enable integration with Firefly CAN Detective tool"
    )

    # Network and interface configuration
    default_interface: str = Field(
        default="house", description="Default logical interface for Firefly systems"
    )

    # Firefly-specific DGN ranges (based on research findings)
    custom_dgn_range_start: int = Field(
        default=0x1F000, description="Start of Firefly custom DGN range", ge=0x1F000
    )
    custom_dgn_range_end: int = Field(
        default=0x1FFFF, description="End of Firefly custom DGN range", le=0x1FFFF
    )

    # Message handling configuration
    multiplex_buffer_size: int = Field(
        default=100, description="Buffer size for multiplexed message assembly", ge=10
    )
    multiplex_timeout_ms: int = Field(
        default=1000, description="Timeout for multiplexed message assembly in milliseconds", ge=100
    )

    # Component management
    supported_components: list[str] = Field(
        default=[
            "lighting",
            "climate",
            "slides",
            "awnings",
            "tanks",
            "inverters",
            "generators",
            "transfer_switches",
            "pumps",
        ],
        description="List of Firefly components to support",
    )

    # Safety and interlock configuration
    safety_interlock_components: list[str] = Field(
        default=["slides", "awnings", "leveling_jacks"],
        description="Components that require safety interlock checks",
    )
    required_interlocks: dict[str, list[str]] = Field(
        default={
            "slides": ["park_brake", "engine_off"],
            "awnings": ["wind_speed", "vehicle_level"],
            "leveling_jacks": ["park_brake", "engine_off"],
        },
        description="Required safety conditions for each component",
    )

    # Message validation and security
    enable_message_validation: bool = Field(
        default=True, description="Enable Firefly-specific message validation"
    )
    enable_sequence_validation: bool = Field(
        default=True, description="Enable message sequence validation for multiplexed data"
    )

    # Performance settings
    priority_dgns: list[int] = Field(
        default=[0x1FECA, 0x1FEDB, 0x1FEDA], description="Firefly DGNs treated as high priority"
    )
    background_dgns: list[int] = Field(
        default=[0x1FFB7, 0x1FFB6],
        description="Firefly DGNs treated as background priority (tank levels, sensors)",
    )

    # CAN Detective integration (if enabled)
    can_detective_path: Path | None = Field(
        default=None, description="Path to CAN Detective tool executable"
    )
    can_detective_config_path: Path | None = Field(
        default=None, description="Path to CAN Detective configuration file"
    )

    @field_validator("can_detective_path", "can_detective_config_path", mode="before")
    @classmethod
    def parse_path(cls, v):
        """Parse path from string."""
        if isinstance(v, str) and v.strip():
            return Path(v.strip())
        return v

    @field_validator("supported_components", "safety_interlock_components", mode="before")
    @classmethod
    def parse_component_list(cls, v):
        """Parse comma-separated component list from environment variable."""
        if isinstance(v, str):
            return [comp.strip() for comp in v.split(",") if comp.strip()]
        return v

    @field_validator("priority_dgns", "background_dgns", mode="before")
    @classmethod
    def parse_dgn_list(cls, v):
        """Parse comma-separated DGN list from environment variable."""
        if isinstance(v, str):
            # Handle both hex (0x1FECA) and decimal formats
            dgns = []
            for dgn_str in v.split(","):
                dgn_str = dgn_str.strip()
                if dgn_str.startswith(("0x", "0X")):
                    dgns.append(int(dgn_str, 16))
                elif dgn_str.isdigit():
                    dgns.append(int(dgn_str))
            return dgns
        if isinstance(v, list):
            return [int(dgn) if isinstance(dgn, str) and dgn.isdigit() else dgn for dgn in v]
        return v


class SpartanK2Settings(BaseSettings):
    """Spartan K2 chassis configuration settings."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_SPARTAN_K2__", case_sensitive=False)

    enabled: bool = Field(default=False, description="Enable Spartan K2 chassis support")

    # Spartan K2-specific configuration
    enable_safety_interlocks: bool = Field(
        default=True, description="Enable Spartan K2 safety interlock monitoring and validation"
    )
    enable_advanced_diagnostics: bool = Field(
        default=True, description="Enable Spartan K2 advanced diagnostic capabilities"
    )
    enable_brake_monitoring: bool = Field(
        default=True, description="Enable comprehensive brake system monitoring"
    )
    enable_suspension_control: bool = Field(
        default=True, description="Enable suspension and leveling system control"
    )
    enable_steering_monitoring: bool = Field(
        default=True, description="Enable power steering system monitoring"
    )

    # Network and interface configuration
    chassis_interface: str = Field(
        default="chassis", description="Default logical interface for Spartan K2 chassis systems"
    )

    # Spartan K2-specific PGN ranges
    custom_pgn_range_start: int = Field(
        default=65280, description="Start of Spartan K2 custom PGN range", ge=65280
    )
    custom_pgn_range_end: int = Field(
        default=65300, description="End of Spartan K2 custom PGN range", le=65300
    )

    # Message handling configuration
    message_buffer_size: int = Field(
        default=100, description="Buffer size for Spartan K2 message handling", ge=10
    )
    diagnostic_cache_size: int = Field(
        default=500, description="Cache size for diagnostic trouble codes", ge=50
    )

    # Safety interlock configuration
    brake_pressure_threshold: float = Field(
        default=80.0, description="Minimum brake pressure for safety validation (psi)", ge=0
    )
    level_differential_threshold: float = Field(
        default=15.0, description="Maximum chassis level differential (percentage)", ge=0, le=50
    )
    steering_pressure_threshold: float = Field(
        default=1000.0, description="Minimum power steering pressure (psi)", ge=0
    )
    max_steering_angle: float = Field(
        default=720.0, description="Maximum allowed steering angle (degrees)", ge=0
    )

    # Diagnostic and maintenance settings
    enable_predictive_maintenance: bool = Field(
        default=False, description="Enable predictive maintenance based on system data"
    )
    maintenance_alert_threshold: int = Field(
        default=30, description="Days ahead to alert for maintenance", ge=1, le=365
    )
    system_health_check_interval: int = Field(
        default=60, description="System health check interval in seconds", ge=10, le=3600
    )

    # Advanced chassis features
    supported_systems: list[str] = Field(
        default=[
            "brakes",
            "suspension",
            "steering",
            "electrical",
            "diagnostics",
            "safety",
            "leveling",
        ],
        description="List of Spartan K2 systems to support",
    )

    # Safety-critical component monitoring
    safety_critical_components: list[str] = Field(
        default=["brakes", "steering", "suspension"],
        description="Components requiring continuous safety monitoring",
    )
    safety_check_frequency: int = Field(
        default=5, description="Safety check frequency in seconds", ge=1, le=60
    )

    # Message validation and security
    enable_message_validation: bool = Field(
        default=True, description="Enable Spartan K2-specific message validation"
    )
    enable_source_validation: bool = Field(
        default=True, description="Enable J1939 source address validation for chassis messages"
    )

    # Performance settings
    priority_pgns: list[int] = Field(
        default=[65280, 65281, 65282], description="Spartan K2 PGNs treated as high priority"
    )
    critical_pgns: list[int] = Field(
        default=[65280],  # Brake system controller
        description="Spartan K2 PGNs treated as critical priority",
    )

    @field_validator("supported_systems", "safety_critical_components", mode="before")
    @classmethod
    def parse_component_list(cls, v):
        """Parse comma-separated component list from environment variable."""
        if isinstance(v, str):
            return [comp.strip() for comp in v.split(",") if comp.strip()]
        return v

    @field_validator("priority_pgns", "critical_pgns", mode="before")
    @classmethod
    def parse_pgn_list(cls, v):
        """Parse comma-separated PGN list from environment variable."""
        if isinstance(v, str):
            # Handle both hex (0xFF00) and decimal formats
            pgns = []
            for pgn_str in v.split(","):
                pgn_str = pgn_str.strip()
                if pgn_str.startswith(("0x", "0X")):
                    pgns.append(int(pgn_str, 16))
                elif pgn_str.isdigit():
                    pgns.append(int(pgn_str))
            return pgns
        if isinstance(v, list):
            return [int(pgn) if isinstance(pgn, str) and pgn.isdigit() else pgn for pgn in v]
        return v


class APIDomainSettings(BaseSettings):
    """API Domain configuration settings for safety-critical operations."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_API_DOMAINS__", case_sensitive=False)

    # Core domain API settings
    enabled: bool = Field(default=False, description="Enable Domain API v1 architecture")
    safety_mode: str = Field(
        default="strict", description="Safety mode: strict, permissive, halt_command_emission"
    )

    # Validation and schema settings
    enable_runtime_validation: bool = Field(
        default=True, description="Enable runtime schema validation for all operations"
    )
    enable_schema_export: bool = Field(
        default=True, description="Enable Pydantic to TypeScript schema export"
    )
    validation_mode: str = Field(
        default="strict", description="Validation mode: strict, lenient, development"
    )

    # Command execution and safety settings
    command_timeout_seconds: float = Field(
        default=5.0, ge=0.1, le=30.0, description="Default command timeout in seconds"
    )
    max_pending_commands: int = Field(
        default=10, ge=1, le=100, description="Maximum pending commands per session"
    )
    enable_command_acknowledgment: bool = Field(
        default=True, description="Enable command/acknowledgment patterns for safety"
    )
    enable_state_reconciliation: bool = Field(
        default=True, description="Enable state reconciliation with RV-C bus"
    )
    state_sync_interval_seconds: float = Field(
        default=2.0, ge=0.5, le=30.0, description="State synchronization interval"
    )

    # Emergency and safety controls
    enable_halt_command_emission: bool = Field(
        default=True, description="Enable emergency stop capability"
    )
    enable_safety_interlocks: bool = Field(
        default=True, description="Enable safety interlocks for vehicle operations"
    )
    require_explicit_confirmation: bool = Field(
        default=True, description="Require explicit safety confirmation for critical operations"
    )

    # Operation limits and performance
    max_bulk_operation_size: int = Field(
        default=50, ge=1, le=200, description="Maximum entities per bulk operation"
    )
    bulk_operation_timeout_seconds: float = Field(
        default=30.0, ge=5.0, le=300.0, description="Bulk operation timeout"
    )
    max_concurrent_operations: int = Field(
        default=10, ge=1, le=50, description="Maximum concurrent operations"
    )

    # Audit and logging settings
    enable_audit_logging: bool = Field(
        default=True, description="Enable comprehensive audit logging for all operations"
    )
    audit_log_retention_days: int = Field(
        default=90, ge=1, le=365, description="Audit log retention period in days"
    )
    log_sensitive_data: bool = Field(
        default=False, description="Include sensitive data in audit logs (dev only)"
    )

    # Authentication and authorization
    enable_device_validation: bool = Field(
        default=True, description="Enable device-level validation before operations"
    )
    enable_state_verification: bool = Field(
        default=True, description="Enable post-operation state verification"
    )
    authentication_timeout_seconds: float = Field(
        default=300.0, ge=60.0, le=3600.0, description="Authentication session timeout"
    )

    @field_validator("safety_mode", mode="before")
    @classmethod
    def validate_safety_mode(cls, v):
        """Validate safety mode setting."""
        valid_modes = {"strict", "permissive", "halt_command_emission"}
        if isinstance(v, str) and v.lower() not in valid_modes:
            msg = f"Invalid safety mode: {v}. Must be one of {valid_modes}"
            raise ValueError(msg)
        return v.lower() if isinstance(v, str) else v

    @field_validator("validation_mode", mode="before")
    @classmethod
    def validate_validation_mode(cls, v):
        """Validate validation mode setting."""
        valid_modes = {"strict", "lenient", "development"}
        if isinstance(v, str) and v.lower() not in valid_modes:
            msg = f"Invalid validation mode: {v}. Must be one of {valid_modes}"
            raise ValueError(msg)
        return v.lower() if isinstance(v, str) else v


class McpSettings(BaseSettings):
    """MCP OAuth Authorization Server configuration."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_MCP__", case_sensitive=False)

    as_enabled: bool = Field(default=False, description="Enable embedded MCP OAuth AS")
    path: str = Field(default="/api/mcp", description="MCP resource path")
    access_token_ttl_days: int = Field(
        default=90,
        description="MCP OAuth opaque access token TTL in days",
        ge=1,
        le=365,
    )

    @field_validator("path", mode="before")
    @classmethod
    def parse_path(cls, value):
        """Normalize blank MCP path values to the default."""
        if value is None:
            return "/api/mcp"
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or "/api/mcp"
        return value


class RouterSidecarSettings(BaseSettings):
    """RouterOS sidecar listener and poller configuration."""

    model_config = SettingsConfigDict(env_prefix="COACHIQ_ROUTER_SIDECAR__", case_sensitive=False)

    enabled: bool = Field(default=False, description="Enable the RouterOS sidecar API")
    host: str = Field(default="0.0.0.0", description="Sidecar bind host")  # noqa: S104  # nosec B104
    port: int = Field(default=8100, description="Sidecar bind port", ge=1, le=65535)
    access_log: bool = Field(default=False, description="Enable sidecar access logs")

    home_latitude: float | None = Field(default=None, description="Home geofence latitude")
    home_longitude: float | None = Field(default=None, description="Home geofence longitude")
    geofence_radius_m: float = Field(default=200.0, description="Home geofence radius", gt=0)
    location_hysteresis_count: int = Field(
        default=3, description="Consecutive location reads before state flips", ge=1
    )

    gpsd_host: str = Field(default="127.0.0.1", description="gpsd host")
    gpsd_port: int = Field(default=2947, description="gpsd TCP port", ge=1, le=65535)
    gps_fix_staleness_seconds: float = Field(
        default=120.0, description="Seconds before a GPS fix is stale", gt=0
    )
    gps_poll_interval_seconds: float = Field(
        default=2.0, description="Delay after gpsd reconnect attempts", gt=0
    )

    dish_host: str = Field(default="192.168.100.1", description="Starlink dish gRPC host")
    dish_port: int = Field(default=9200, description="Starlink dish gRPC port", ge=1, le=65535)
    starlink_poll_interval_seconds: float = Field(
        default=5.0, description="Starlink status poll interval", gt=0
    )
    starlink_degraded_debounce_seconds: float = Field(
        default=75.0, description="Sustained degradation interval before degraded", gt=0
    )
    starlink_obstruction_fraction_degraded: float = Field(
        default=0.03, description="Obstruction fraction threshold for degraded", ge=0
    )
    starlink_obstruction_fraction_recovery: float = Field(
        default=0.02, description="Obstruction fraction threshold for recovery", ge=0
    )
    starlink_pop_ping_drop_rate_degraded: float = Field(
        default=0.05, description="PoP ping drop-rate threshold for degraded", ge=0
    )
    starlink_pop_ping_drop_rate_recovery: float = Field(
        default=0.02, description="PoP ping drop-rate threshold for recovery", ge=0
    )
    starlink_pop_ping_latency_ms_degraded: float = Field(
        default=100.0, description="PoP ping latency threshold for degraded", gt=0
    )
    starlink_pop_ping_latency_ms_recovery: float = Field(
        default=60.0, description="PoP ping latency threshold for recovery", gt=0
    )
    starlink_recent_outage_count_degraded: int = Field(
        default=3, description="Recent outage count threshold for degraded", ge=1
    )
    starlink_history_sample_window: int = Field(
        default=60, description="History samples used for Starlink rolling averages", ge=1
    )
    starlink_telemetry_staleness_seconds: float = Field(
        default=15.0, description="Seconds before Starlink telemetry is stale", gt=0
    )
    starlink_down_recovery_dwell_seconds: float = Field(
        default=75.0, description="Sustained recovery interval before leaving down", gt=0
    )

    nighthawk_base_url: str = Field(
        default="http://192.168.12.1", description="Nighthawk M6 Pro base URL"
    )
    nighthawk_poll_interval_seconds: float = Field(
        default=5.0, description="Nighthawk model.json poll interval", gt=0
    )
    nighthawk_request_timeout_seconds: float = Field(
        default=5.0, description="Nighthawk HTTP request timeout", gt=0
    )
    nighthawk_telemetry_staleness_seconds: float = Field(
        default=15.0, description="Seconds before Nighthawk telemetry is stale", gt=0
    )
    nighthawk_signal_window_seconds: float = Field(
        default=45.0, description="Rolling signal average window", gt=0
    )
    nighthawk_verdict_dwell_seconds: float = Field(
        default=75.0, description="Sustained 5G verdict interval before publishing", gt=0
    )
    nighthawk_rsrp_degraded: float = Field(default=-105.0, description="RSRP degraded threshold")
    nighthawk_rsrp_recovery: float = Field(default=-100.0, description="RSRP recovery threshold")
    nighthawk_rsrq_degraded: float = Field(default=-18.0, description="RSRQ degraded threshold")
    nighthawk_rsrq_recovery: float = Field(default=-15.0, description="RSRQ recovery threshold")
    nighthawk_sinr_degraded: float = Field(default=5.0, description="SINR degraded threshold")
    nighthawk_sinr_recovery: float = Field(default=8.0, description="SINR recovery threshold")
    nighthawk_radio_quality_degraded: float = Field(
        default=30.0, description="Radio quality degraded threshold"
    )
    nighthawk_radio_quality_recovery: float = Field(
        default=40.0, description="Radio quality recovery threshold"
    )


class Settings(BaseSettings):
    """
    Main application settings.

    Environment Variable Patterns:
        - Top-level settings: COACHIQ_SETTING (e.g., `COACHIQ_APP_NAME`)
        - Nested settings: COACHIQ_SECTION__SETTING (e.g., `COACHIQ_SERVER__HOST`)

    Configuration Loading Order:
        1. Default values specified in this class
        2. Values from .env file (if present)
        3. Environment variables (which override any previous values)
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="COACHIQ_",
        case_sensitive=False,
        env_nested_delimiter="__",
        env_parse_none_str="",
        extra="ignore",
    )

    # Application info
    app_name: str = Field(default="CoachIQ", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    app_description: str = Field(
        default="API for RV-C CANbus", description="Application description"
    )
    app_title: str = Field(default="RV-C API", description="API title for documentation")

    # Environment and deployment
    environment: str = Field(default="development", description="Application environment")
    debug: bool = Field(default=False, description="Enable debug mode")
    testing: bool = Field(default=False, description="Enable testing mode")

    # File paths and directories
    static_dir: str = Field(default="static", description="Static files directory")

    # RVC-specific paths
    rvc_spec_path: Path | None = Field(default=None, description="Path to RVC spec JSON file")
    rvc_coach_mapping_path: Path | None = Field(
        default=None, description="Path to RVC coach mapping YAML file"
    )

    # External integrations
    github_update_repo: str | None = Field(
        default=None, description="GitHub repository for update checks (owner/repo)"
    )
    controller_source_addr: str = Field(default="0xF9", description="Controller source address")

    # Protocol enablement settings
    # These control whether protocols are enabled, separate from their configuration
    rvc_enabled: bool = Field(default=True, description="Enable RV-C protocol (always true)")
    j1939_enabled: bool = Field(default=False, description="Enable J1939 protocol")
    firefly_enabled: bool = Field(default=False, description="Enable Firefly protocol")

    # Nested settings
    server: ServerSettings = Field(default_factory=ServerSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    can: CANSettings = Field(default_factory=CANSettings)
    can_recorder: CANRecorderSettings = Field(default_factory=CANRecorderSettings)
    rvc: RVCSettings = Field(default_factory=RVCSettings)
    j1939: J1939Settings = Field(default_factory=J1939Settings)
    firefly: FireflySettings = Field(default_factory=FireflySettings)
    victron: VictronSettings = Field(default_factory=VictronSettings)
    trip_log: TripLogSettings = Field(default_factory=TripLogSettings)
    spartan_k2: SpartanK2Settings = Field(default_factory=SpartanK2Settings)
    multi_network: MultiNetworkSettings = Field(default_factory=MultiNetworkSettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)
    features: FeaturesSettings = Field(default_factory=FeaturesSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    auth: AuthenticationSettings = Field(default_factory=AuthenticationSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    router_sidecar: RouterSidecarSettings = Field(default_factory=RouterSidecarSettings)
    api_domains: APIDomainSettings = Field(default_factory=APIDomainSettings)

    def __init__(self, **data):
        # Import here to avoid circular dependency and initialize advanced_diagnostics field
        try:
            from backend.integrations.diagnostics.config import AdvancedDiagnosticsSettings

            if "advanced_diagnostics" not in data:
                data["advanced_diagnostics"] = AdvancedDiagnosticsSettings()
        except ImportError:
            # Diagnostics module not available - set None to avoid field errors
            if "advanced_diagnostics" not in data:
                data["advanced_diagnostics"] = None

        # Import here to avoid circular dependency and initialize performance_analytics field
        try:
            from backend.integrations.analytics.config import PerformanceAnalyticsSettings

            if "performance_analytics" not in data:
                data["performance_analytics"] = PerformanceAnalyticsSettings()
        except ImportError:
            # Analytics module not available - set None to avoid field errors
            if "performance_analytics" not in data:
                data["performance_analytics"] = None

        # Import here to avoid circular dependency and initialize database field
        try:
            from backend.services.database.database_engine import DatabaseSettings

            if "database" not in data:
                data["database"] = DatabaseSettings()
        except ImportError:
            # Database module not available - use default DatabaseSettings
            # Create a minimal class if needed
            class MinimalDatabaseSettings:
                def get_database_url(self):
                    return f"sqlite:///{self.get_database_path()}"

                def get_database_path(self):
                    return str(resolve_project_path("backend/data/databases/coachiq.db"))

            if "database" not in data:
                data["database"] = MinimalDatabaseSettings()

        super().__init__(**data)
        self._anchor_runtime_write_paths()

    # Add the fields with defaults
    advanced_diagnostics: Any = Field(
        default=None, exclude=True, description="Advanced diagnostics settings"
    )
    performance_analytics: Any = Field(
        default=None, exclude=True, description="Performance analytics settings"
    )
    database: Any = Field(default=None, exclude=True, description="Database configuration settings")

    @property
    def data_dir(self) -> Path:
        """Convenience property to access persistence.data_dir."""
        return self.persistence.data_dir

    def _resolve_runtime_write_path(self, configured_path: Path | None, default_path: Path) -> Path:
        """Resolve runtime write paths under the data root unless explicitly absolute."""
        if configured_path is None:
            return default_path

        candidate = configured_path.expanduser()
        if candidate.is_absolute():
            return candidate

        return (self.persistence.data_dir / candidate).resolve()

    def _anchor_runtime_write_paths(self) -> None:
        """Anchor runtime write paths so service startup is independent of cwd."""
        object.__setattr__(
            self.can_recorder,
            "storage_path",
            self._resolve_runtime_write_path(
                self.can_recorder.storage_path, self.persistence.get_recordings_dir()
            ),
        )
        object.__setattr__(
            self.notifications,
            "queue_db_path",
            self.notifications.resolve_queue_db_path(self.persistence),
        )

    def get_can_recorder_storage_path(self) -> Path:
        """Get the anchored CAN recorder storage path."""
        return self.can_recorder.storage_path or self.persistence.get_recordings_dir()

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, v):
        """Validate environment name."""
        valid_envs = {"development", "testing", "staging", "production"}
        if isinstance(v, str) and v.lower() not in valid_envs:
            msg = f"Invalid environment: {v}. Must be one of {valid_envs}"
            raise ValueError(msg)
        return v.lower() if isinstance(v, str) else v

    @field_validator("rvc_spec_path", "rvc_coach_mapping_path", mode="before")
    @classmethod
    def parse_path(cls, v):
        """Parse path from string."""
        if isinstance(v, str) and v.strip():
            return Path(v.strip())
        return v

    @model_validator(mode="after")
    def validate_non_development_security_secret(self) -> "Settings":
        """Validate cross-section security settings."""
        if self.auth.oidc_enabled or self.mcp.as_enabled:
            parsed_origin = urlparse(self.server.public_origin)
            if not parsed_origin.scheme or not parsed_origin.netloc or parsed_origin.path:
                msg = (
                    "COACHIQ_SERVER__PUBLIC_ORIGIN must be an absolute origin without a path "
                    "when OIDC or MCP AS is enabled"
                )
                raise ValueError(msg)
            if self.server.public_origin.endswith("/"):
                msg = "COACHIQ_SERVER__PUBLIC_ORIGIN must not have a trailing slash"
                raise ValueError(msg)

        if self.mcp.as_enabled:
            if self.mcp.path != "/api/mcp":
                msg = "COACHIQ_MCP__PATH must be /api/mcp while the MCP route is mounted literally"
                raise ValueError(msg)
            if not self.mcp.path.startswith("/"):
                msg = "COACHIQ_MCP__PATH must be an absolute path"
                raise ValueError(msg)
            if self.mcp.path == "/":
                msg = "COACHIQ_MCP__PATH must not be the root path"
                raise ValueError(msg)
            if self.mcp.path.endswith("/"):
                msg = "COACHIQ_MCP__PATH must not have a trailing slash"
                raise ValueError(msg)

        if self.is_development() or self.is_testing():
            return self

        if not is_real_secret(self.security.secret_key):
            msg = (
                "Security secret key is required in production and staging environments. "
                "Set COACHIQ_SECURITY__SECRET_KEY or COACHIQ_SECURITY__SECRET_KEY_FILE "
                "to a secure random value. Generate one with: openssl rand -hex 32"
            )
            raise ValueError(msg)

        return self

    def get_config_dict(self, hide_secrets: bool = True) -> dict[str, Any]:
        """
        Get configuration as dictionary with optional secret hiding.

        Args:
            hide_secrets: If True, replace sensitive values with '***'

        Returns:
            Dictionary representation of configuration
        """
        config = self.model_dump()

        if hide_secrets and "security" in config:
            # Hide sensitive values
            for key in ["secret_key", "api_key"]:
                if key in config["security"] and config["security"][key]:
                    config["security"][key] = "***"

        return config

    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"

    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.testing or self.environment == "testing"

    def get_uvicorn_config(self) -> dict[str, Any]:
        """Get configuration dict for Uvicorn server."""
        # Only allow reload in explicit development mode to prevent file watchers in production
        allow_reload = self.server.reload and self.is_development() and not self.is_production()

        config = {
            "host": self.server.host,
            "port": self.server.port,
            "reload": allow_reload,
            "workers": 1 if allow_reload else self.server.workers,
            "access_log": self.server.access_log,
            "log_level": self.logging.level.lower(),
        }

        # Automatically enable proxy headers when external TLS termination is configured
        # This ensures proper handling of X-Forwarded-Proto, X-Forwarded-For, etc.
        if self.security.tls_termination_is_external:
            config["proxy_headers"] = True

        # Add reload directories to prevent PermissionError on protected directories
        if allow_reload:
            # Use absolute path to backend directory to handle cases where working directory is /
            import os

            backend_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            config["reload_dirs"] = [os.path.join(backend_dir, "backend")]

        # Ensure reload is disabled in any non-development environment
        if not self.is_development() or self.is_production():
            config["reload"] = False

        return config

    @property
    def data_dir(self) -> Path:
        """Convenience property to access persistence.data_dir directly."""
        return self.persistence.data_dir

    def get_uvicorn_ssl_config(self) -> dict[str, Any]:
        """
        Get SSL/TLS configuration dict for Uvicorn server.

        Returns SSL configuration if SSL certificates are provided,
        otherwise returns empty dict for HTTP mode.
        """
        ssl_config = {}

        # Only add SSL config if both keyfile and certfile are provided
        if self.server.ssl_keyfile and self.server.ssl_certfile:
            ssl_config["ssl_keyfile"] = str(self.server.ssl_keyfile)
            ssl_config["ssl_certfile"] = str(self.server.ssl_certfile)

            # Optional SSL settings
            if self.server.ssl_ca_certs:
                ssl_config["ssl_ca_certs"] = str(self.server.ssl_ca_certs)

            # SSL certificate verification mode
            # 0 = CERT_NONE, 1 = CERT_OPTIONAL, 2 = CERT_REQUIRED
            ssl_config["ssl_cert_reqs"] = self.server.ssl_cert_reqs

        return ssl_config


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance. Uses lru_cache to ensure settings are only loaded once.

    For development or testing scenarios where you need to reload settings,
    you can access the uncached settings with `Settings()` directly.

    Returns:
        Settings instance
    """
    return Settings()


def get_hierarchical_settings() -> Settings:
    """
    Get settings instance using the new hierarchical configuration loader.

    This function implements the 8-layer configuration hierarchy:
    1. Core Protocol Specification (JSON)
    2. Coach Model Base Definition (YAML)
    3. User Structural Customizations (JSON Patch)
    4. System Settings (TOML)
    5. User Config Overrides (TOML)
    6. User Model Selection & System State (SQLite)
    7. User Preferences (SQLite)
    8. Secrets & Runtime Overrides (Environment Variables)

    Returns:
        Settings instance with hierarchical configuration loaded
    """
    try:
        from backend.core.config_loader import create_configuration_loader

        # Create and run the configuration loader
        loader = create_configuration_loader()
        config_dict = loader.load()

        # Initialize Pydantic settings from the merged config
        # Pydantic will still apply environment variable loading (Layer 8)
        return Settings(**config_dict)

    except ImportError:
        # Fallback to standard loading if config_loader not available
        import logging

        logging.getLogger(__name__).warning(
            "Hierarchical config loader not available, falling back to environment-only config"
        )
        return Settings()
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Hierarchical config loading failed: {e}")
        # Fallback to standard loading
        return Settings()


# Convenience functions for getting specific setting sections
def get_server_settings() -> ServerSettings:
    """Get server settings."""
    return get_settings().server


def get_security_settings() -> SecuritySettings:
    """Get security settings."""
    return get_settings().security


def get_logging_settings() -> LoggingSettings:
    """Get logging settings."""
    return get_settings().logging


def get_can_settings() -> CANSettings:
    """Get CAN settings."""
    return get_settings().can


def get_rvc_settings() -> RVCSettings:
    """Get RVC settings."""
    return get_settings().rvc


def get_persistence_settings() -> PersistenceSettings:
    """Get persistence settings."""
    return get_settings().persistence


def get_features_settings() -> FeaturesSettings:
    """Get features settings."""
    return get_settings().features


def get_multi_network_settings() -> MultiNetworkSettings:
    """Get multi-network settings."""
    return get_settings().multi_network


def get_firefly_settings() -> FireflySettings:
    """Get Firefly settings."""
    return get_settings().firefly


def get_notification_settings() -> NotificationSettings:
    """Get notification settings."""
    return get_settings().notifications


def get_api_domain_settings() -> APIDomainSettings:
    """Get API domain settings."""
    return get_settings().api_domains


# Note: Use get_settings() function instead of a global instance
# to ensure environment variables are read correctly


def validate_config_cli():
    """CLI entry point for validating configuration."""
    import sys

    try:
        settings = get_settings()
        print("Configuration is valid.")
        print(f"Server will start on {settings.server.host}:{settings.server.port}")
        sys.exit(0)
    except Exception as e:
        print(f"Configuration validation failed: {e}", file=sys.stderr)
        sys.exit(1)
