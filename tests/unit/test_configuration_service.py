"""
Unit Tests for ConfigurationService

Tests TTL caching behavior, thread safety, and hot-reload functionality
for the centralized configuration service in
``backend/core/configuration_service.py``.

Filesystem layout
-----------------
The production service reads configuration from FOUR file types under a
single ``config_dir``::

    rvc.json                       # Complete RV-C spec (all DGNs in one file)
    <device_type>_mapping.yml      # Per-device mapping, e.g. coach_mapping.yml
    coach_mapping.default.yml      # Fallback when a per-device mapping is absent
    protocol_config.yml            # Per-protocol config, top-level keys per protocol

There is NO per-DGN file layout (``dgn_specs/0xNNNN.yaml``) and no per-protocol
file layout (``protocols/<name>.yaml``). The previous version of this file
asserted against an aspirational per-DGN layout that was never implemented in
production; that test body has been rewritten in PR #119 against the real
layout. See PR #119's commit message for the full audit.
"""

import json
import tempfile
import threading
import time
from pathlib import Path

import pytest
import yaml

from backend.core.configuration_service import (
    ConfigurationLoadError,
    ConfigurationService,
)

# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for test configuration files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def config_service(temp_config_dir):
    """Create a configuration service instance with short TTL for testing."""
    return ConfigurationService(temp_config_dir, cache_ttl=1, max_cache_size=10)


def _write_rvc_json(config_dir: Path, dgns: dict[str, dict]) -> Path:
    """Helper: write a minimal ``rvc.json`` containing the given DGN map."""
    spec_file = config_dir / "rvc.json"
    spec = {"version": "test", "dgns": dgns}
    spec_file.write_text(json.dumps(spec))
    return spec_file


def _write_default_mapping(config_dir: Path, mapping: dict) -> Path:
    """Helper: write the default ``coach_mapping.default.yml``."""
    mapping_file = config_dir / "coach_mapping.default.yml"
    mapping_file.write_text(yaml.safe_dump(mapping))
    return mapping_file


def _write_device_mapping(config_dir: Path, device_type: str, mapping: dict) -> Path:
    """Helper: write a per-device mapping ``<device_type>_mapping.yml``."""
    mapping_file = config_dir / f"{device_type}_mapping.yml"
    mapping_file.write_text(yaml.safe_dump(mapping))
    return mapping_file


def _write_protocol_config(config_dir: Path, all_configs: dict) -> Path:
    """Helper: write ``protocol_config.yml`` keyed by protocol name."""
    config_file = config_dir / "protocol_config.yml"
    config_file.write_text(yaml.safe_dump(all_configs))
    return config_file


# ----------------------------------------------------------------------------
# Constructor / initialization
# ----------------------------------------------------------------------------


class TestInitialization:
    """Constructor + cache-shape assertions."""

    def test_initialization(self, temp_config_dir):
        """Custom cache_ttl + max_cache_size are propagated to the dgn_cache."""
        service = ConfigurationService(temp_config_dir, cache_ttl=300, max_cache_size=1000)

        assert service.config_dir == temp_config_dir
        # Only the dgn_cache uses the user-supplied max_cache_size; the other
        # caches have their own fixed sizes (current production design).
        assert service.dgn_cache.maxsize == 1000
        assert service.dgn_cache.ttl == 300
        assert service.mapping_cache.maxsize == 100
        assert service.spec_cache.maxsize == 10
        assert service.protocol_cache.maxsize == 50

    def test_missing_config_dir_raises(self, tmp_path):
        """Pointing the service at a nonexistent directory must error fast."""
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(ConfigurationLoadError):
            ConfigurationService(nonexistent)


# ----------------------------------------------------------------------------
# get_full_spec
# ----------------------------------------------------------------------------


class TestFullSpec:
    """``rvc.json`` loading + caching."""

    def test_returns_none_when_missing(self, config_service):
        """No ``rvc.json`` on disk -> returns None, no exception."""
        assert config_service.get_full_spec() is None

    def test_loads_and_caches(self, config_service, temp_config_dir):
        """First call loads from disk; subsequent calls return the same object."""
        _write_rvc_json(temp_config_dir, {"1FED1": {"name": "Test"}})

        spec1 = config_service.get_full_spec()
        spec2 = config_service.get_full_spec()

        assert spec1 == {"version": "test", "dgns": {"1FED1": {"name": "Test"}}}
        assert spec1 is spec2  # cache hit returns same object


# ----------------------------------------------------------------------------
# get_dgn_spec
# ----------------------------------------------------------------------------


class TestDgnSpec:
    """``get_dgn_spec(dgn: int)`` resolves via ``rvc.json``."""

    def test_dgn_spec_caching(self, config_service, temp_config_dir):
        """Second lookup returns the cached object."""
        # Production lookup uses the 4-char uppercase hex key in rvc.json.
        _write_rvc_json(temp_config_dir, {"1FED1": {"name": "Test DGN"}})

        spec1 = config_service.get_dgn_spec(0x1FED1)
        spec2 = config_service.get_dgn_spec(0x1FED1)

        assert spec1 == {"name": "Test DGN"}
        assert spec1 is spec2

    def test_dgn_spec_cache_miss_returns_none(self, config_service, temp_config_dir):
        """A DGN not in rvc.json returns None (no exception)."""
        _write_rvc_json(temp_config_dir, {"1FED1": {"name": "Other"}})

        assert config_service.get_dgn_spec(0x9999) is None

    def test_dgn_spec_no_spec_file_returns_none(self, config_service):
        """No rvc.json at all -> all DGN lookups return None."""
        assert config_service.get_dgn_spec(0x1FED1) is None

    def test_dgn_spec_cache_size_limit(self, temp_config_dir):
        """``max_cache_size`` is enforced by the underlying TTLCache."""
        service = ConfigurationService(temp_config_dir, cache_ttl=300, max_cache_size=2)

        # Populate rvc.json with several DGNs so all lookups hit the cache.
        _write_rvc_json(
            temp_config_dir,
            {f"{0x1FED1 + i:04X}": {"name": f"DGN {i}"} for i in range(5)},
        )

        for i in range(5):
            service.get_dgn_spec(0x1FED1 + i)

        assert len(service.dgn_cache) <= 2

    def test_dgn_spec_ttl_expiration(self, temp_config_dir):
        """Cached DGN is reloaded after TTL expires."""
        # Use very short TTL; cachetools' TTLCache uses time.monotonic() and
        # a >TTL sleep is enough to evict the entry on the next access.
        service = ConfigurationService(temp_config_dir, cache_ttl=1, max_cache_size=10)

        _write_rvc_json(temp_config_dir, {"1FED1": {"name": "Cached"}})
        service.get_dgn_spec(0x1FED1)
        assert "dgn_1FED1" in service.dgn_cache

        # Wait past the TTL; the next access must NOT find the entry in cache.
        time.sleep(1.5)
        # Confirm the cache is empty (TTLCache lazily evicts on access; the
        # __contains__ trigger above + this fresh probe both count as access).
        assert "dgn_1FED1" not in service.dgn_cache


# ----------------------------------------------------------------------------
# get_device_mapping
# ----------------------------------------------------------------------------


class TestDeviceMapping:
    """``get_device_mapping(device_type: str)`` reads YAML mappings."""

    def test_loads_specific_mapping_when_present(self, config_service, temp_config_dir):
        """``<device_type>_mapping.yml`` takes precedence over the default."""
        specific = {"device_type": "coach", "dgns": ["0x1FED1"]}
        _write_device_mapping(temp_config_dir, "coach", specific)

        result = config_service.get_device_mapping("coach")
        assert result == specific

    def test_falls_back_to_default(self, config_service, temp_config_dir):
        """Without a device-specific file, falls back to coach_mapping.default.yml."""
        default = {"device_type": "default", "dgns": []}
        _write_default_mapping(temp_config_dir, default)

        # Request a device type with no specific file.
        result = config_service.get_device_mapping("unknown_device")
        assert result == default

    def test_returns_none_when_no_mappings_exist(self, config_service):
        """No mapping files at all -> None."""
        assert config_service.get_device_mapping("anything") is None

    def test_caching(self, config_service, temp_config_dir):
        """Second call returns the cached object."""
        _write_default_mapping(temp_config_dir, {"device_type": "x"})

        m1 = config_service.get_device_mapping("anything")
        m2 = config_service.get_device_mapping("anything")
        assert m1 is m2


# ----------------------------------------------------------------------------
# get_protocol_config
# ----------------------------------------------------------------------------


class TestProtocolConfig:
    """``get_protocol_config(protocol: str)`` reads ``protocol_config.yml``."""

    def test_returns_default_when_no_file(self, config_service):
        """Without protocol_config.yml the service returns built-in defaults."""
        result = config_service.get_protocol_config("rvc")

        # The built-in default for "rvc" is non-empty and includes priority/data_rate.
        assert result is not None
        assert result["priority"] == 6
        assert result["data_rate"] == 250000

    def test_reads_user_override(self, config_service, temp_config_dir):
        """A protocol entry in protocol_config.yml overrides the built-in default."""
        _write_protocol_config(
            temp_config_dir,
            {"rvc": {"priority": 3, "data_rate": 500000, "extended_id": True, "timeout_ms": 50}},
        )

        result = config_service.get_protocol_config("rvc")
        assert result == {
            "priority": 3,
            "data_rate": 500000,
            "extended_id": True,
            "timeout_ms": 50,
        }

    def test_unknown_protocol_falls_back_to_default(self, config_service, temp_config_dir):
        """Asking for a protocol not in the file returns the built-in default."""
        _write_protocol_config(temp_config_dir, {"j1939": {"priority": 6}})

        result = config_service.get_protocol_config("rvc")
        # Built-in rvc default has priority 6, data_rate 250000, etc.
        assert result["priority"] == 6
        assert result["data_rate"] == 250000

    def test_caching(self, config_service):
        """Second call returns the cached object even when only the default applies."""
        c1 = config_service.get_protocol_config("rvc")
        c2 = config_service.get_protocol_config("rvc")
        assert c1 is c2


# ----------------------------------------------------------------------------
# Hot reload
# ----------------------------------------------------------------------------


class TestReload:
    """``reload_configuration`` and ``check_for_updates`` semantics."""

    def test_reload_clears_caches(self, config_service, temp_config_dir):
        """After reload, the next get_full_spec() must hit the disk again."""
        _write_rvc_json(temp_config_dir, {"1FED1": {"version": 1}})
        spec1 = config_service.get_full_spec()
        assert spec1["dgns"]["1FED1"]["version"] == 1

        # Mutate file + reload.
        _write_rvc_json(temp_config_dir, {"1FED1": {"version": 2}})
        config_service.reload_configuration()

        spec2 = config_service.get_full_spec()
        assert spec2["dgns"]["1FED1"]["version"] == 2
        assert spec1 is not spec2

    def test_check_for_updates_rate_limits(self, config_service, temp_config_dir):
        """``check_for_updates`` only checks the filesystem every _check_interval seconds."""
        _write_rvc_json(temp_config_dir, {"1FED1": {"version": 1}})

        # First call sets the timestamp baseline.
        # We can't easily prove the rate limit without sleeping for the full
        # interval, so just confirm the method doesn't crash and returns bool.
        result1 = config_service.check_for_updates()
        result2 = config_service.check_for_updates()
        assert isinstance(result1, bool)
        assert isinstance(result2, bool)
        # The second call within _check_interval seconds is rate-limited.
        assert result2 is False


# ----------------------------------------------------------------------------
# Cache stats
# ----------------------------------------------------------------------------


class TestCacheStats:
    """``get_cache_stats`` (NOT ``get_cache_statistics`` — that name was
    invented by the old test file and never existed in production)."""

    def test_returns_size_maxsize_ttl_per_cache(self, config_service):
        """The stats dict reports size/maxsize/ttl for each of the four caches."""
        stats = config_service.get_cache_stats()

        for cache_name in ("dgn_cache", "mapping_cache", "spec_cache", "protocol_cache"):
            assert cache_name in stats, f"missing {cache_name} in stats"
            for field in ("size", "maxsize", "ttl"):
                assert field in stats[cache_name], f"missing {field} in {cache_name}"

    def test_size_increases_with_use(self, config_service, temp_config_dir):
        """Loading a DGN increases dgn_cache.size by 1."""
        _write_rvc_json(temp_config_dir, {"1FED1": {"name": "Test"}})

        before = config_service.get_cache_stats()["dgn_cache"]["size"]
        config_service.get_dgn_spec(0x1FED1)
        after = config_service.get_cache_stats()["dgn_cache"]["size"]

        assert after == before + 1


# ----------------------------------------------------------------------------
# Thread safety
# ----------------------------------------------------------------------------


class TestThreadSafety:
    """The internal RLock guards cache reads/writes across threads."""

    def test_concurrent_dgn_lookups(self, config_service, temp_config_dir):
        """10 threads x 100 ops on the same DGN must not raise or return inconsistent data."""
        _write_rvc_json(temp_config_dir, {"1FED1": {"name": "Thread Safety"}})

        results = []
        exceptions: list[BaseException] = []

        def worker():
            try:
                for _ in range(100):
                    spec = config_service.get_dgn_spec(0x1FED1)
                    results.append(spec)
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert exceptions == [], f"Thread safety violations: {exceptions}"
        assert len(results) == 1000
        # Every result is the same dict (same identity, since it's the cached object).
        first = results[0]
        for r in results:
            assert r == first


# ----------------------------------------------------------------------------
# Error handling
# ----------------------------------------------------------------------------


class TestErrorHandling:
    """Bad input data must not crash the service."""

    def test_invalid_json_in_rvc_returns_none(self, config_service, temp_config_dir):
        """Malformed rvc.json -> ``get_full_spec`` returns None."""
        (temp_config_dir / "rvc.json").write_text("{not valid json")

        assert config_service.get_full_spec() is None

    def test_missing_files_return_none(self, config_service):
        """All accessors return None when their backing file is absent."""
        assert config_service.get_dgn_spec(0x1FED1) is None
        assert config_service.get_device_mapping("nope") is None
        # protocol falls back to a built-in default rather than None — see
        # TestProtocolConfig.test_returns_default_when_no_file. That's the
        # documented behavior of get_protocol_config.
