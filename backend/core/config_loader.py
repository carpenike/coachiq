"""
CoachIQ Hierarchical Configuration Loader

This module implements the 8-layer configuration hierarchy for the persistence migration:

1. Core Protocol Specification (JSON) - RV-C protocol definitions
2. Coach Model Base Definition (YAML) - Coach-specific mappings
3. User Structural Customizations (JSON Patch) - User modifications via UI
4. System Settings (TOML) - System deployment configuration
5. User Config Overrides (TOML) - User configuration overrides
6. User Model Selection & System State (SQLite) - Mutable system state
7. User Preferences (SQLite) - User cosmetic preferences
8. Secrets & Runtime Overrides (Environment Variables) - Handled by Pydantic

The loader provides a single, merged configuration dictionary that can be used
to initialize Pydantic Settings classes.
"""

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Fallback for older Python versions

import jsonpatch
import yaml
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Base exception for configuration loading errors."""


class ConfigParseError(ConfigurationError):
    """For errors parsing a specific config file."""


class ConfigPatchError(ConfigurationError):
    """For errors applying a JSON patch."""


class ConfigVersionError(ConfigurationError):
    """For schema version mismatches."""


class ConfigPermissionError(ConfigurationError):
    """For file permission issues."""


def deep_merge(source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merges source dict into destination dict.

    User overrides take precedence over system settings.
    Supports deep merging for nested dictionaries.

    Args:
        source: The source dictionary (user overrides)
        destination: The destination dictionary (system defaults)

    Returns:
        Merged dictionary with source values taking precedence
    """
    result = destination.copy()

    for key, value in source.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = deep_merge(value, result[key])
        else:
            # Override the value
            result[key] = value
            logger.debug(f"Configuration override applied: {key} = {value}")

    return result


class ConfigurationLoader:
    """
    Hierarchical configuration loader implementing 8-layer config system.

    This loader reads configuration from multiple sources in a specific order,
    with later layers taking precedence over earlier ones.
    """

    SUPPORTED_PROTOCOL_VERSION = "2.0"
    SUPPORTED_MODEL_VERSION = "1.0"

    def __init__(
        self,
        system_root: Path = Path("/var/lib/coachiq"),
        user_root: Path = Path("/var/lib/coachiq/user"),
        db_path: Path | None = None,
    ):
        """
        Initialize the configuration loader.

        Args:
            system_root: Root directory for system configuration files
            user_root: Root directory for user configuration files
            db_path: Path to SQLite database (defaults to user_root/coachiq.db)
        """
        self.system_root = system_root
        self.user_root = user_root
        self.db_path = db_path or (user_root / "coachiq.db")
        self.config: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        """
        Execute the full 8-layer loading process.

        Returns:
            Merged configuration dictionary

        Raises:
            ConfigurationError: For any configuration loading errors
        """
        try:
            logger.info("Starting hierarchical configuration loading")

            # Layer 6 (Partial): Load model selection first, needed for Layer 2
            model_selection = self._load_model_selection_from_db()
            logger.debug(f"Active coach model: {model_selection}")

            # Layer 1: Core Protocol Specification (JSON)
            self.config = self._load_layer1_core_spec()
            logger.debug("Loaded Layer 1: Core Protocol Specification")

            # Layer 2: Coach Model Base Definition (YAML)
            model_config = self._load_layer2_model_base(model_selection)
            self.config = self._merge_protocol_extensions(self.config, model_config)
            logger.debug("Loaded Layer 2: Coach Model Base Definition")

            # Layer 3: User Structural Customizations (JSON Patch)
            self.config = self._apply_layer3_user_patches()
            logger.debug("Applied Layer 3: User Structural Customizations")

            # Layer 4: System Settings (TOML)
            system_settings = self._load_layer4_system_settings()
            self.config = deep_merge(system_settings, self.config)
            logger.debug("Loaded Layer 4: System Settings")

            # Layer 5: User Config Overrides (TOML)
            user_overrides = self._load_layer5_user_overrides()
            self.config = deep_merge(user_overrides, self.config)
            logger.debug("Applied Layer 5: User Config Overrides")

            # Layers 6 & 7: Remaining DB State & Preferences
            db_config = self._load_layers_6_7_from_db()
            self.config = deep_merge(db_config, self.config)
            logger.debug("Loaded Layers 6-7: Database State & Preferences")

            # Layer 8 (Secrets/Runtime) handled by Pydantic environment loading

            logger.info("Configuration loading completed successfully")
            return self.config

        except Exception as e:
            logger.error(f"Configuration loading failed: {e}")
            if not isinstance(e, ConfigurationError):
                # Wrap unexpected errors
                msg = f"Unexpected error during configuration loading: {e}"
                raise ConfigurationError(msg) from e
            raise

    def _load_layer1_core_spec(self) -> dict[str, Any]:
        """Load Layer 1: Core Protocol Specification from rvc.json."""
        path = self.system_root / "config" / "rvc.json"

        try:
            self._verify_read_only_protection(path)

            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate schema version
            self._validate_schema_version(
                data, self.SUPPORTED_PROTOCOL_VERSION, "protocol specification"
            )

            return {"protocol": data}

        except FileNotFoundError:
            msg = f"Core protocol specification not found: {path}"
            raise ConfigParseError(msg)
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON in protocol specification {path}: {e}"
            raise ConfigParseError(msg)
        except Exception as e:
            msg = f"Failed to load protocol specification {path}: {e}"
            raise ConfigParseError(msg)

    def _load_layer2_model_base(self, model_name: str) -> dict[str, Any]:
        """Load Layer 2: Coach Model Base Definition from YAML."""
        path = self.system_root / "config" / "models" / f"{model_name}.yml"

        try:
            self._verify_read_only_protection(path)

            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # Validate schema version
            self._validate_schema_version(
                data, self.SUPPORTED_MODEL_VERSION, f"coach model '{model_name}'"
            )

            return {"model": data}

        except FileNotFoundError:
            # Try fallback to generic model
            if model_name != "generic_rv":
                logger.warning(f"Coach model {model_name} not found, falling back to generic_rv")
                return self._load_layer2_model_base("generic_rv")
            msg = f"Coach model definition not found: {path}"
            raise ConfigParseError(msg)
        except yaml.YAMLError as e:
            msg = f"Invalid YAML in coach model {path}: {e}"
            raise ConfigParseError(msg)
        except Exception as e:
            msg = f"Failed to load coach model {path}: {e}"
            raise ConfigParseError(msg)

    def _apply_layer3_user_patches(self) -> dict[str, Any]:
        """Apply Layer 3: User Structural Customizations via JSON Patch."""
        patches_file = self._get_user_patches_file()

        if not patches_file.exists():
            logger.debug("No user patches file found, skipping Layer 3")
            return self.config

        try:
            with patches_file.open("r", encoding="utf-8") as f:
                patches = json.load(f)

            if not isinstance(patches, list):
                msg = "User patches must be a list of JSON Patch operations"
                raise ConfigPatchError(msg)

            # Apply patches to the model section
            if "model" in self.config:
                modified_config = self.config.copy()
                modified_config["model"] = jsonpatch.apply_patch(
                    self.config["model"], patches, in_place=False
                )
                logger.info(f"Applied {len(patches)} user customizations")
                return modified_config

            return self.config

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in user patches file: {e}")
            self._flag_configuration_issue("user_patches_invalid_json")
            return self.config
        except jsonpatch.JsonPatchException as e:
            logger.error(f"Failed to apply user patches: {e}")
            self._flag_configuration_issue("user_patches_failed")
            return self.config
        except Exception as e:
            logger.error(f"Unexpected error applying user patches: {e}")
            self._flag_configuration_issue("user_patches_error")
            return self.config

    def _load_layer4_system_settings(self) -> dict[str, Any]:
        """Load Layer 4: System Settings from system.toml."""
        path = self.system_root / "config" / "system.toml"

        try:
            self._verify_read_only_protection(path)

            with path.open("rb") as f:
                data = tomllib.load(f)

            return {"system": data}

        except FileNotFoundError:
            logger.warning(f"System settings not found: {path}")
            return {"system": {}}
        except tomllib.TOMLDecodeError as e:
            msg = f"Invalid TOML in system settings {path}: {e}"
            raise ConfigParseError(msg)
        except Exception as e:
            msg = f"Failed to load system settings {path}: {e}"
            raise ConfigParseError(msg)

    def _load_layer5_user_overrides(self) -> dict[str, Any]:
        """Load Layer 5: User Config Overrides from config-overrides.toml."""
        path = self.user_root / "config-overrides.toml"

        if not path.exists():
            logger.debug("No user config overrides found")
            return {}

        try:
            with path.open("rb") as f:
                data = tomllib.load(f)

            logger.info(f"Loaded user config overrides from {path}")
            return data

        except tomllib.TOMLDecodeError as e:
            logger.error(f"Invalid TOML in user overrides {path}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Failed to load user overrides {path}: {e}")
            return {}

    def _load_model_selection_from_db(self) -> str:
        """Load the active coach model from database."""
        if not self.db_path.exists():
            logger.debug("Database not found, using default model")
            return self._get_default_model_from_system()

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT value FROM system_settings WHERE key = ?", ("active_coach_model",)
                )
                result = cursor.fetchone()

                if result:
                    return result[0]
                # Fall back to system default
                return self._get_default_model_from_system()

        except sqlite3.Error as e:
            logger.warning(f"Database error loading model selection: {e}")
            return self._get_default_model_from_system()

    def _load_layers_6_7_from_db(self) -> dict[str, Any]:
        """Load Layers 6-7: System state and user preferences from database."""
        if not self.db_path.exists():
            logger.debug("Database not found, skipping database layers")
            return {}

        config = {}

        try:
            with sqlite3.connect(self.db_path) as conn:
                # Load system settings (Layer 6)
                cursor = conn.execute("SELECT key, value FROM system_settings")
                system_settings = {row[0]: row[1] for row in cursor.fetchall()}
                if system_settings:
                    config["system_state"] = system_settings

                # Load user preferences (Layer 7)
                cursor = conn.execute("SELECT key, value FROM user_settings")
                user_settings = {row[0]: row[1] for row in cursor.fetchall()}
                if user_settings:
                    config["user_preferences"] = user_settings

        except sqlite3.Error as e:
            logger.warning(f"Database error loading state/preferences: {e}")

        return config

    def _merge_protocol_extensions(
        self, base_protocol: dict[str, Any], model_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge protocol extensions from coach model into base protocol."""
        result = base_protocol.copy()

        if "model" not in model_config:
            return result

        model_data = model_config["model"]
        if "protocol_extensions" in model_data:
            extensions = model_data["protocol_extensions"]

            if "protocol" in result and "pgns" in result["protocol"]:
                # Merge PGN extensions
                if "pgns" in extensions:
                    result["protocol"]["pgns"].update(extensions["pgns"])
                    logger.debug(f"Applied {len(extensions['pgns'])} PGN extensions")

        # Keep the model config alongside the protocol
        result.update(model_config)
        return result

    def _get_user_patches_file(self) -> Path:
        """Get the path to user patches file from database or default."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT value FROM system_settings WHERE key = ?", ("user_patches_file",)
                )
                result = cursor.fetchone()

                if result:
                    return Path(result[0])

        except sqlite3.Error:
            pass

        # Default location
        return self.user_root / "user_patches.json"

    def _get_default_model_from_system(self) -> str:
        """Get default coach model from system settings."""
        try:
            system_path = self.system_root / "config" / "system.toml"
            if system_path.exists():
                with system_path.open("rb") as f:
                    data = tomllib.load(f)

                return data.get("coach", {}).get("default_model", "generic_rv")
        except Exception:
            pass

        return "generic_rv"

    def _verify_read_only_protection(self, file_path: Path) -> None:
        """Verify that system config files have read-only permissions (444)."""
        try:
            if file_path.exists():
                # Check if file is read-only (444 permissions)
                stat_info = file_path.stat()
                permissions = oct(stat_info.st_mode)[-3:]

                if permissions != "444":
                    logger.warning(
                        f"System config file {file_path} has incorrect permissions: "
                        f"{permissions} (expected 444)"
                    )
                    # Attempt to fix permissions if we have write access to parent directory
                    try:
                        file_path.chmod(0o444)
                        logger.info(f"Fixed permissions for {file_path} to read-only (444)")
                    except PermissionError:
                        logger.warning(
                            f"Cannot fix permissions for {file_path} - system may be compromised"
                        )
                else:
                    logger.debug(
                        f"System config file {file_path} has correct read-only permissions"
                    )
        except Exception as e:
            logger.warning(f"Cannot verify permissions for {file_path}: {e}")

    def _validate_schema_version(
        self, config: dict[str, Any], min_version: str, config_type: str
    ) -> None:
        """Validate schema version compatibility."""
        schema_version = config.get("schema_version")
        if not schema_version:
            msg = f"Missing schema_version in {config_type} configuration file"
            raise ConfigVersionError(msg)

        # Simple version comparison (assumes semantic versioning)
        if self._version_less_than(schema_version, min_version):
            msg = (
                f"Unsupported schema version {schema_version} in {config_type}, "
                f"minimum required: {min_version}"
            )
            raise ConfigVersionError(msg)

    def _version_less_than(self, version1: str, version2: str) -> bool:
        """Compare semantic versions (simplified)."""
        try:
            v1_parts = [int(x) for x in version1.split(".")]
            v2_parts = [int(x) for x in version2.split(".")]

            # Pad with zeros if needed
            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))

            return v1_parts < v2_parts
        except ValueError:
            # If version parsing fails, assume incompatible
            return True

    def _flag_configuration_issue(self, issue_type: str) -> None:
        """Flag a configuration issue in the database for UI notification."""
        if not self.db_path.exists():
            return

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                    (f"config_issue_{issue_type}", "true"),
                )
                conn.commit()
                logger.debug(f"Flagged configuration issue: {issue_type}")
        except sqlite3.Error as e:
            logger.warning(f"Failed to flag configuration issue: {e}")


def create_configuration_loader(
    system_root: Path | None = None, user_root: Path | None = None, db_path: Path | None = None
) -> ConfigurationLoader:
    """
    Factory function to create a configuration loader with environment-based defaults.

    Args:
        system_root: Override system root directory
        user_root: Override user root directory
        db_path: Override database path

    Returns:
        ConfigurationLoader instance
    """
    # Allow environment variable overrides
    if system_root is None:
        system_root = Path(os.getenv("COACHIQ_CONFIG_SYSTEM_ROOT", "/var/lib/coachiq"))

    if user_root is None:
        user_root = Path(os.getenv("COACHIQ_CONFIG_USER_ROOT", "/var/lib/coachiq/user"))

    if db_path is None:
        db_path = Path(os.getenv("COACHIQ_CONFIG_DB_PATH", str(user_root / "coachiq.db")))

    return ConfigurationLoader(system_root=system_root, user_root=user_root, db_path=db_path)
