"""RV-C spec/mapping file loader (renamed from ConfigurationService in audit A10).

Provides TTL-cached loading of RV-C DGN specifications, coach mappings, and
protocol settings from disk with hot-reload support.

Renamed from ``ConfigurationService`` -> ``RVCSpecLoader`` in audit cycle
2026-05-13 PR A10 to clarify that this is a *spec-file loader*, not the
application configuration object (which is Pydantic ``Settings``). See
ADR-0008 for the three-tier config layering rationale.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, cast

import yaml
from cachetools import TTLCache

logger = logging.getLogger(__name__)


class RVCSpecLoadError(Exception):
    """Raised when configuration loading fails."""


class RVCSpecLoader:
    """
    Centralized configuration service with TTL caching and hot-reload support.

    This service manages all configuration data for the RV-C decoder system,
    including DGN specifications, device mappings, and protocol settings.
    Uses TTL caching for performance and supports thread-safe reloading.
    """

    def __init__(
        self,
        config_dir: Path,
        cache_ttl: int = 300,  # 5 minutes default
        max_cache_size: int = 1000,
    ):
        """
        Initialize the configuration service.

        Args:
            config_dir: Directory containing configuration files
            cache_ttl: Time-to-live for cached entries in seconds
            max_cache_size: Maximum number of entries in each cache
        """
        self.config_dir = Path(config_dir)
        self.cache_ttl = cache_ttl

        # TTL caches for different configuration types. cast() because
        # cachetools' TTLCache constructor leaves its type variables
        # unsolved, which made pyright's inference (and the CI error-count
        # baseline) flap whenever the package import graph changed.
        self.dgn_cache = cast(
            "TTLCache[str, dict[str, Any]]", TTLCache(maxsize=max_cache_size, ttl=cache_ttl)
        )
        self.mapping_cache = cast(
            "TTLCache[str, dict[str, Any]]", TTLCache(maxsize=100, ttl=cache_ttl)
        )
        self.spec_cache = cast("TTLCache[str, dict[str, Any]]", TTLCache(maxsize=10, ttl=cache_ttl))
        self.protocol_cache = cast(
            "TTLCache[str, dict[str, Any]]", TTLCache(maxsize=50, ttl=cache_ttl)
        )

        # Thread safety for cache operations
        self._cache_lock = threading.RLock()

        # File modification tracking for hot-reload
        self._file_timestamps: dict[str, float] = {}
        self._last_check = time.time()
        self._check_interval = 10.0  # Check for file changes every 10 seconds

        # Validate configuration directory exists
        if not self.config_dir.exists():
            msg = f"Configuration directory does not exist: {self.config_dir}"
            raise RVCSpecLoadError(msg)

    def get_dgn_spec(self, dgn: int) -> dict[str, Any] | None:
        """
        Get DGN specification from cache or load from file.

        Args:
            dgn: Data Group Number (DGN) to look up

        Returns:
            DGN specification dictionary or None if not found
        """
        cache_key = f"dgn_{dgn:04X}"

        with self._cache_lock:
            # Check cache first
            if cache_key in self.dgn_cache:
                logger.debug(f"DGN {dgn:04X} found in cache")
                return self.dgn_cache[cache_key]

        # Load from file
        spec = self._load_dgn_spec(dgn)
        if spec:
            with self._cache_lock:
                self.dgn_cache[cache_key] = spec
            logger.debug(f"DGN {dgn:04X} loaded and cached")

        return spec

    def get_device_mapping(self, device_type: str) -> dict[str, Any] | None:
        """
        Get device mapping configuration.

        Args:
            device_type: Type of device (e.g., "coach", "engine", "transmission")

        Returns:
            Device mapping dictionary or None if not found
        """
        cache_key = f"mapping_{device_type}"

        with self._cache_lock:
            if cache_key in self.mapping_cache:
                return self.mapping_cache[cache_key]

        mapping = self._load_device_mapping(device_type)
        if mapping:
            with self._cache_lock:
                self.mapping_cache[cache_key] = mapping

        return mapping

    def get_protocol_config(self, protocol: str) -> dict[str, Any] | None:
        """
        Get protocol-specific configuration.

        Args:
            protocol: Protocol name ("rvc", "j1939", "can")

        Returns:
            Protocol configuration dictionary or None if not found
        """
        cache_key = f"protocol_{protocol}"

        with self._cache_lock:
            if cache_key in self.protocol_cache:
                return self.protocol_cache[cache_key]

        config = self._load_protocol_config(protocol)
        if config:
            with self._cache_lock:
                self.protocol_cache[cache_key] = config

        return config

    def get_full_spec(self) -> dict[str, Any] | None:
        """
        Get the complete RV-C specification.

        Returns:
            Complete specification dictionary or None if not found
        """
        cache_key = "full_rvc_spec"

        with self._cache_lock:
            if cache_key in self.spec_cache:
                return self.spec_cache[cache_key]

        spec = self._load_full_spec()
        if spec:
            with self._cache_lock:
                self.spec_cache[cache_key] = spec

        return spec

    def reload_configuration(self) -> None:
        """
        Force reload of all cached configuration.

        This method clears all caches and forces fresh loading
        of configuration files on next access.
        """
        with self._cache_lock:
            self.dgn_cache.clear()
            self.mapping_cache.clear()
            self.spec_cache.clear()
            self.protocol_cache.clear()
            self._file_timestamps.clear()

        logger.info("Configuration caches cleared - will reload on next access")

    def check_for_updates(self) -> bool:
        """
        Check if any configuration files have been modified.

        Returns:
            True if files were modified and caches were cleared
        """
        current_time = time.time()

        # Rate limit file system checks
        if current_time - self._last_check < self._check_interval:
            return False

        self._last_check = current_time
        files_changed = False

        # Check key configuration files
        config_files = [
            "rvc.json",
            "coach_mapping.default.yml",
            "protocol_config.yml",
        ]

        for filename in config_files:
            file_path = self.config_dir / filename
            if file_path.exists():
                current_mtime = file_path.stat().st_mtime
                stored_mtime = self._file_timestamps.get(filename, 0)

                if current_mtime > stored_mtime:
                    logger.info(f"Configuration file modified: {filename}")
                    self._file_timestamps[filename] = current_mtime
                    files_changed = True

        if files_changed:
            self.reload_configuration()

        return files_changed

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache statistics for monitoring.

        Returns:
            Dictionary with cache hit/miss ratios and sizes
        """
        with self._cache_lock:
            return {
                "dgn_cache": {
                    "size": len(self.dgn_cache),
                    "maxsize": self.dgn_cache.maxsize,
                    "ttl": self.dgn_cache.ttl,
                },
                "mapping_cache": {
                    "size": len(self.mapping_cache),
                    "maxsize": self.mapping_cache.maxsize,
                    "ttl": self.mapping_cache.ttl,
                },
                "spec_cache": {
                    "size": len(self.spec_cache),
                    "maxsize": self.spec_cache.maxsize,
                    "ttl": self.spec_cache.ttl,
                },
                "protocol_cache": {
                    "size": len(self.protocol_cache),
                    "maxsize": self.protocol_cache.maxsize,
                    "ttl": self.protocol_cache.ttl,
                },
            }

    def _load_dgn_spec(self, dgn: int) -> dict[str, Any] | None:
        """Load DGN specification from the main RV-C spec file."""
        try:
            full_spec = self.get_full_spec()
            if not full_spec:
                return None

            # Look for the DGN in the spec
            dgns = full_spec.get("dgns", {})
            dgn_hex = f"{dgn:04X}"

            if dgn_hex in dgns:
                return dgns[dgn_hex]

            # Also check decimal format
            dgn_dec = str(dgn)
            if dgn_dec in dgns:
                return dgns[dgn_dec]

            logger.warning(f"DGN {dgn:04X} not found in specification")
            return None

        except Exception as e:
            logger.error(f"Error loading DGN {dgn:04X}: {e}")
            return None

    def _load_device_mapping(self, device_type: str) -> dict[str, Any] | None:
        """Load device mapping from YAML file."""
        try:
            # Try specific device mapping first
            mapping_file = self.config_dir / f"{device_type}_mapping.yml"
            if not mapping_file.exists():
                # Fall back to default mapping
                mapping_file = self.config_dir / "coach_mapping.default.yml"

            if not mapping_file.exists():
                logger.warning(f"No mapping file found for device type: {device_type}")
                return None

            with mapping_file.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f)

        except Exception as e:
            logger.error(f"Error loading device mapping for {device_type}: {e}")
            return None

    def _load_protocol_config(self, protocol: str) -> dict[str, Any] | None:
        """Load protocol-specific configuration."""
        try:
            config_file = self.config_dir / "protocol_config.yml"
            if not config_file.exists():
                # Return default configuration
                return self._get_default_protocol_config(protocol)

            with config_file.open("r", encoding="utf-8") as f:
                all_configs = yaml.safe_load(f)

            return all_configs.get(protocol, self._get_default_protocol_config(protocol))

        except Exception as e:
            logger.error(f"Error loading protocol config for {protocol}: {e}")
            return self._get_default_protocol_config(protocol)

    def _load_full_spec(self) -> dict[str, Any] | None:
        """Load the complete RV-C specification from JSON file."""
        try:
            spec_file = self.config_dir / "rvc.json"
            if not spec_file.exists():
                logger.error(f"RV-C specification file not found: {spec_file}")
                return None

            with spec_file.open("r", encoding="utf-8") as f:
                spec = json.load(f)

            logger.debug("RV-C specification loaded successfully")
            return spec

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in RV-C specification: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading RV-C specification: {e}")
            return None

    def _get_default_protocol_config(self, protocol: str) -> dict[str, Any]:
        """Get default configuration for a protocol."""
        defaults = {
            "rvc": {
                "priority": 6,
                "data_rate": 250000,
                "extended_id": True,
                "timeout_ms": 100,
            },
            "j1939": {
                "priority": 3,
                "data_rate": 250000,
                "extended_id": True,
                "timeout_ms": 50,
                "address_claiming": True,
            },
            "can": {
                "data_rate": 250000,
                "extended_id": False,
                "timeout_ms": 10,
            },
        }

        return defaults.get(protocol, {})
