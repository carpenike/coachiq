"""
Unit Tests for Configuration Service

Tests TTL caching behavior, thread safety, and hot-reload functionality
for the enhanced configuration service implementation.
"""

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest
import yaml

from backend.core.configuration_service import ConfigurationService


class TestConfigurationService:
    """Test configuration service TTL caching and hot-reload functionality."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for test configuration files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def config_service(self, temp_config_dir):
        """Create a configuration service instance for testing."""
        return ConfigurationService(temp_config_dir, cache_ttl=1, max_cache_size=10)

    def test_initialization(self, temp_config_dir):
        """Test configuration service initialization."""
        service = ConfigurationService(temp_config_dir, cache_ttl=300, max_cache_size=1000)

        assert service.config_dir == temp_config_dir
        assert service.dgn_cache.maxsize == 1000
        assert service.dgn_cache.ttl == 300
        assert service.mapping_cache.maxsize == 100
        assert service.spec_cache.maxsize == 10
        assert service.protocol_cache.maxsize == 50

    def test_dgn_spec_caching(self, config_service, temp_config_dir):
        """Test DGN specification caching behavior."""
        # Create a test DGN spec file
        dgn_file = temp_config_dir / "dgn_specs" / "0x1FED1.yaml"
        dgn_file.parent.mkdir(parents=True, exist_ok=True)

        test_spec = {
            "dgn": "0x1FED1",
            "name": "Test DGN",
            "signals": [{"name": "test_signal", "start_bit": 0, "length": 8}],
        }

        with open(dgn_file, "w") as f:
            yaml.dump(test_spec, f)

        # First call should load from file
        spec1 = config_service.get_dgn_spec(0x1FED1)
        assert spec1 == test_spec

        # Second call should use cache
        spec2 = config_service.get_dgn_spec(0x1FED1)
        assert spec2 == test_spec
        assert spec1 is spec2  # Should be same object from cache

    def test_dgn_spec_cache_miss(self, config_service):
        """Test DGN specification cache miss behavior."""
        # Non-existent DGN should return None
        spec = config_service.get_dgn_spec(0x9999)
        assert spec is None

    def test_device_mapping_caching(self, config_service, temp_config_dir):
        """Test device mapping caching behavior."""
        # Create a test device mapping file
        mapping_file = temp_config_dir / "device_mappings" / "test_device.yaml"
        mapping_file.parent.mkdir(parents=True, exist_ok=True)

        test_mapping = {
            "device_type": "test_device",
            "dgns": ["0x1FED1", "0x1FED2"],
            "configuration": {"sample_rate": 100},
        }

        with open(mapping_file, "w") as f:
            yaml.dump(test_mapping, f)

        # First call should load from file
        mapping1 = config_service.get_device_mapping("test_device")
        assert mapping1 == test_mapping

        # Second call should use cache
        mapping2 = config_service.get_device_mapping("test_device")
        assert mapping2 == test_mapping
        assert mapping1 is mapping2  # Should be same object from cache

    def test_protocol_config_caching(self, config_service, temp_config_dir):
        """Test protocol configuration caching behavior."""
        # Create a test protocol config file
        protocol_file = temp_config_dir / "protocols" / "rvc.yaml"
        protocol_file.parent.mkdir(parents=True, exist_ok=True)

        test_config = {
            "protocol": "rvc",
            "version": "2.0",
            "features": {"enable_encoder": True, "enable_security": True},
        }

        with open(protocol_file, "w") as f:
            yaml.dump(test_config, f)

        # First call should load from file
        config1 = config_service.get_protocol_config("rvc")
        assert config1 == test_config

        # Second call should use cache
        config2 = config_service.get_protocol_config("rvc")
        assert config2 == test_config
        assert config1 is config2  # Should be same object from cache

    def test_complete_spec_caching(self, config_service, temp_config_dir):
        """Test complete specification caching behavior."""
        # Create a test complete spec file
        spec_file = temp_config_dir / "specs" / "rvc_complete.json"
        spec_file.parent.mkdir(parents=True, exist_ok=True)

        test_spec = {
            "version": "2.0",
            "dgns": {"0x1FED1": {"name": "Test DGN 1"}, "0x1FED2": {"name": "Test DGN 2"}},
        }

        import json

        with open(spec_file, "w") as f:
            json.dump(test_spec, f)

        # First call should load from file
        spec1 = config_service.get_complete_spec("rvc_complete")
        assert spec1 == test_spec

        # Second call should use cache
        spec2 = config_service.get_complete_spec("rvc_complete")
        assert spec2 == test_spec
        assert spec1 is spec2  # Should be same object from cache

    def test_cache_ttl_expiration(self, temp_config_dir):
        """Test that cache entries expire after TTL."""
        # Use very short TTL for testing
        service = ConfigurationService(temp_config_dir, cache_ttl=0.1, max_cache_size=10)

        # Create a test DGN spec file
        dgn_file = temp_config_dir / "dgn_specs" / "0x1FED1.yaml"
        dgn_file.parent.mkdir(parents=True, exist_ok=True)

        test_spec = {"dgn": "0x1FED1", "name": "Test DGN"}

        with open(dgn_file, "w") as f:
            yaml.dump(test_spec, f)

        # Load spec into cache
        spec1 = service.get_dgn_spec(0x1FED1)
        assert spec1 == test_spec

        # Wait for TTL to expire
        time.sleep(0.2)

        # Should reload from file (not cached)
        spec2 = service.get_dgn_spec(0x1FED1)
        assert spec2 == test_spec
        # Objects should be different (reloaded)
        assert spec1 is not spec2

    def test_cache_size_limit(self, temp_config_dir):
        """Test that cache respects size limits."""
        # Use small cache size for testing
        service = ConfigurationService(temp_config_dir, cache_ttl=300, max_cache_size=2)

        # Create test DGN spec directory
        dgn_dir = temp_config_dir / "dgn_specs"
        dgn_dir.mkdir(parents=True, exist_ok=True)

        # Create multiple DGN specs
        for i in range(5):
            dgn_file = dgn_dir / f"0x{0x1FED1 + i:04X}.yaml"
            test_spec = {"dgn": f"0x{0x1FED1 + i:04X}", "name": f"Test DGN {i}"}

            with open(dgn_file, "w") as f:
                yaml.dump(test_spec, f)

        # Load specs into cache (should evict older entries)
        for i in range(5):
            service.get_dgn_spec(0x1FED1 + i)

        # Cache should only contain recent entries
        assert len(service.dgn_cache) <= 2

    def test_hot_reload_configuration(self, config_service, temp_config_dir):
        """Test hot-reload of configuration files."""
        # Create initial DGN spec file
        dgn_file = temp_config_dir / "dgn_specs" / "0x1FED1.yaml"
        dgn_file.parent.mkdir(parents=True, exist_ok=True)

        initial_spec = {"dgn": "0x1FED1", "name": "Initial DGN", "version": 1}

        with open(dgn_file, "w") as f:
            yaml.dump(initial_spec, f)

        # Load initial spec
        spec1 = config_service.get_dgn_spec(0x1FED1)
        assert spec1["version"] == 1

        # Trigger hot reload
        config_service.reload_configuration()

        # Update the file
        updated_spec = {"dgn": "0x1FED1", "name": "Updated DGN", "version": 2}

        with open(dgn_file, "w") as f:
            yaml.dump(updated_spec, f)

        # Should load updated spec after reload
        spec2 = config_service.get_dgn_spec(0x1FED1)
        assert spec2["version"] == 2

    def test_thread_safety(self, config_service, temp_config_dir):
        """Test thread safety of cache operations."""
        # Create a test DGN spec file
        dgn_file = temp_config_dir / "dgn_specs" / "0x1FED1.yaml"
        dgn_file.parent.mkdir(parents=True, exist_ok=True)

        test_spec = {"dgn": "0x1FED1", "name": "Thread Safety Test"}

        with open(dgn_file, "w") as f:
            yaml.dump(test_spec, f)

        results = []
        exceptions = []

        def worker():
            """Worker thread that accesses cache concurrently."""
            try:
                for _ in range(100):
                    spec = config_service.get_dgn_spec(0x1FED1)
                    results.append(spec)
                    time.sleep(0.001)  # Small delay to increase contention
            except Exception as e:
                exceptions.append(e)

        # Start multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check that no exceptions occurred
        assert len(exceptions) == 0, f"Thread safety violations: {exceptions}"

        # Check that all results are consistent
        assert len(results) == 1000  # 10 threads * 100 operations
        for result in results:
            assert result == test_spec

    def test_error_handling_invalid_yaml(self, config_service, temp_config_dir):
        """Test error handling for invalid YAML files."""
        # Create invalid YAML file
        dgn_file = temp_config_dir / "dgn_specs" / "0x1FED1.yaml"
        dgn_file.parent.mkdir(parents=True, exist_ok=True)

        with open(dgn_file, "w") as f:
            f.write("invalid: yaml: content: [")

        # Should handle invalid YAML gracefully
        spec = config_service.get_dgn_spec(0x1FED1)
        assert spec is None

    def test_error_handling_missing_file(self, config_service):
        """Test error handling for missing configuration files."""
        # Request non-existent spec
        spec = config_service.get_dgn_spec(0x9999)
        assert spec is None

        mapping = config_service.get_device_mapping("non_existent")
        assert mapping is None

        protocol = config_service.get_protocol_config("non_existent")
        assert protocol is None

        complete_spec = config_service.get_complete_spec("non_existent")
        assert complete_spec is None

    def test_cache_key_generation(self, config_service):
        """Test that cache keys are generated correctly."""
        # Test DGN cache keys
        assert "dgn_1FED1" in str(config_service._get_dgn_cache_key(0x1FED1))

        # Test different representations generate same key
        key1 = config_service._get_dgn_cache_key(0x1FED1)
        key2 = config_service._get_dgn_cache_key(130769)  # Same as 0x1FED1
        assert key1 == key2

    def test_cache_statistics(self, config_service, temp_config_dir):
        """Test cache statistics and monitoring."""
        # Create test files
        dgn_file = temp_config_dir / "dgn_specs" / "0x1FED1.yaml"
        dgn_file.parent.mkdir(parents=True, exist_ok=True)

        test_spec = {"dgn": "0x1FED1", "name": "Stats Test"}

        with open(dgn_file, "w") as f:
            yaml.dump(test_spec, f)

        # Initial cache should be empty
        stats = config_service.get_cache_statistics()
        assert stats["dgn_cache"]["size"] == 0
        assert stats["dgn_cache"]["hits"] == 0
        assert stats["dgn_cache"]["misses"] == 0

        # Load spec (cache miss)
        config_service.get_dgn_spec(0x1FED1)

        stats = config_service.get_cache_statistics()
        assert stats["dgn_cache"]["size"] == 1
        assert stats["dgn_cache"]["misses"] == 1

        # Load same spec again (cache hit)
        config_service.get_dgn_spec(0x1FED1)

        stats = config_service.get_cache_statistics()
        assert stats["dgn_cache"]["size"] == 1
        assert stats["dgn_cache"]["hits"] == 1
        assert stats["dgn_cache"]["misses"] == 1

    def test_memory_usage_optimization(self, temp_config_dir):
        """Test memory usage optimization with large datasets."""
        # Use small cache to test memory optimization
        service = ConfigurationService(temp_config_dir, cache_ttl=300, max_cache_size=5)

        # Create directory for test files
        dgn_dir = temp_config_dir / "dgn_specs"
        dgn_dir.mkdir(parents=True, exist_ok=True)

        # Create many large specs to test memory usage
        for i in range(20):
            dgn_file = dgn_dir / f"0x{0x1FED1 + i:04X}.yaml"
            # Create larger spec with many signals
            large_spec = {
                "dgn": f"0x{0x1FED1 + i:04X}",
                "name": f"Large DGN {i}",
                "signals": [
                    {
                        "name": f"signal_{j}",
                        "start_bit": j * 8,
                        "length": 8,
                        "description": f"Test signal {j} with long description",
                    }
                    for j in range(50)  # 50 signals per DGN
                ],
            }

            with open(dgn_file, "w") as f:
                yaml.dump(large_spec, f)

        # Load all specs (should trigger cache eviction)
        for i in range(20):
            service.get_dgn_spec(0x1FED1 + i)

        # Cache should remain within size limits
        assert len(service.dgn_cache) <= 5

        stats = service.get_cache_statistics()
        assert stats["dgn_cache"]["size"] <= 5
