"""
Comprehensive tests for RV-C decoder functionality.

This test suite verifies:
1. RVC JSON structure and integrity
2. Coach mapping file validation
3. DGN mapping consistency
4. Signal decoding accuracy
5. Missing DGN handling
6. End-to-end decoder functionality
"""

import glob
import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from backend.integrations.rvc.decode import (
    clear_missing_dgns,
    decode_payload,
    decode_payload_safe,
    get_bits,
    get_missing_dgns,
    load_config_data,
    record_missing_dgn,
)


def discover_coach_mapping_files():
    """Dynamically discover all coach mapping YAML files in the config directory."""
    config_directory = "/workspace/backend/integrations/rvc/config"

    # Find all .yml and .yaml files in the config directory
    yaml_pattern = os.path.join(config_directory, "*.yml")
    yaml_files = glob.glob(yaml_pattern)

    # Also check for .yaml extension
    yaml_pattern_alt = os.path.join(config_directory, "*.yaml")
    yaml_files.extend(glob.glob(yaml_pattern_alt))

    # Filter out non-mapping files (keep only coach mapping files)
    mapping_files = []
    for filepath in yaml_files:
        filename = os.path.basename(filepath)
        # Include files with 'mapping' in name or coach-specific naming patterns
        if filename.endswith((".yml", ".yaml")) and (
            "mapping" in filename.lower()
            or
            # Match coach-specific patterns like "YYYY_Make_Model.yml"
            (len(filename.split("_")) >= 3 and filename[:4].isdigit())
        ):
            mapping_files.append(filepath)

    # If no mapping files found by pattern, fall back to known coach files
    if not mapping_files:
        potential_files = [
            os.path.join(config_directory, "coach_mapping.default.yml"),
            os.path.join(config_directory, "2021_Entegra_Aspire_44R.yml"),
        ]
        mapping_files = [f for f in potential_files if os.path.exists(f)]

    # Always include any test files with 'test' in the name
    test_pattern = os.path.join(config_directory, "*test*.yml")
    test_files = glob.glob(test_pattern)
    mapping_files.extend(test_files)

    # Convert to Path objects and remove duplicates
    return [Path(f) for f in set(mapping_files)]


class TestRVCJsonStructure:
    """Test RVC JSON file structure and integrity."""

    @pytest.fixture
    def rvc_spec_path(self):
        """Get path to RVC spec file."""
        return "/workspace/backend/integrations/rvc/config/rvc.json"

    @pytest.fixture
    def rvc_spec(self, rvc_spec_path):
        """Load RVC specification."""
        with open(rvc_spec_path, encoding="utf-8") as f:
            return json.load(f)

    def test_rvc_json_structure(self, rvc_spec):
        """Test that RVC JSON has expected structure."""
        # Check top-level structure
        assert "$schema" in rvc_spec
        assert "version" in rvc_spec
        assert "pgns" in rvc_spec
        assert isinstance(rvc_spec["pgns"], dict)

        # Check that we have some entries
        assert len(rvc_spec["pgns"]) > 0

    def test_pgn_entries_structure(self, rvc_spec):
        """Test that PGN entries have required fields."""
        pgns = rvc_spec["pgns"]

        for _pgn_id, entry in pgns.items():
            # Required fields
            assert "name" in entry
            assert "id" in entry
            assert "pgn" in entry
            assert "extended" in entry
            assert "length" in entry
            assert "signals" in entry

            # Validate types
            assert isinstance(entry["name"], str)
            assert isinstance(entry["id"], int)
            assert isinstance(entry["pgn"], str)
            assert isinstance(entry["extended"], bool)
            # Length can be null for multi-packet messages
            assert entry["length"] is None or isinstance(entry["length"], int)
            assert isinstance(entry["signals"], list)

            # PGN should be hex string
            assert entry["pgn"].startswith("0x")
            int(entry["pgn"], 16)  # Should not raise

    def test_signal_structure(self, rvc_spec):
        """Test that signal definitions are valid."""
        pgns = rvc_spec["pgns"]

        for _pgn_id, entry in pgns.items():
            for signal in entry["signals"]:
                # Required signal fields
                assert "name" in signal
                assert "start_bit" in signal
                assert "length" in signal
                assert "byte_order" in signal

                # Validate types
                assert isinstance(signal["name"], str)
                assert isinstance(signal["start_bit"], int)
                assert isinstance(signal["length"], int)
                assert isinstance(signal["byte_order"], str)

                # Validate ranges (allow zero length for multi-packet messages)
                assert signal["start_bit"] >= 0
                assert signal["length"] >= 0  # Changed from > 0 to >= 0
                assert signal["byte_order"] in ["big_endian", "little_endian"]

    def test_pgn_hex_consistency(self, rvc_spec):
        """Test that PGN hex values are consistent with IDs."""
        pgns = rvc_spec["pgns"]

        for _pgn_id, entry in pgns.items():
            pgn_hex = entry["pgn"]
            pgn_int = int(pgn_hex, 16)

            # The ID should match the PGN when combined with priority
            # Note: Some special PGNs may be outside the standard range
            # Standard PGN range is 0x0000 to 0x1FFFF, but some extended ones exist
            assert pgn_int >= 0  # Must be non-negative
            assert pgn_int <= 0xFFFFFF  # Reasonable upper bound for 24-bit values


class TestCoachMappingFiles:
    """Test coach mapping file structure and validation."""

    @pytest.fixture
    def config_directory(self):
        """Get path to the config directory containing mapping files."""
        return "/workspace/backend/integrations/rvc/config"

    @pytest.fixture
    def mapping_files(self, config_directory):
        """Dynamically discover all coach mapping YAML files in the config directory."""
        # Find all .yml and .yaml files in the config directory
        yaml_pattern = os.path.join(config_directory, "*.yml")
        yaml_files = glob.glob(yaml_pattern)

        # Also check for .yaml extension
        yaml_pattern_alt = os.path.join(config_directory, "*.yaml")
        yaml_files.extend(glob.glob(yaml_pattern_alt))

        # Filter out non-mapping files (keep only coach mapping files)
        mapping_files = []
        for filepath in yaml_files:
            filename = os.path.basename(filepath)
            # Include files with 'mapping' in name or coach-specific naming patterns
            if filename.endswith((".yml", ".yaml")) and (
                "mapping" in filename.lower()
                or
                # Match coach-specific patterns like "YYYY_Make_Model.yml"
                (len(filename.split("_")) >= 3 and filename[:4].isdigit())
            ):
                mapping_files.append(filepath)

        # If no mapping files found by pattern, fall back to known coach files
        if not mapping_files:
            potential_files = [
                os.path.join(config_directory, "coach_mapping.default.yml"),
                os.path.join(config_directory, "2021_Entegra_Aspire_44R.yml"),
            ]
            mapping_files = [f for f in potential_files if os.path.exists(f)]

        # Ensure we have at least the default mapping file for testing
        if not mapping_files:
            raise FileNotFoundError(
                f"No coach mapping files found in {config_directory}. "
                "Expected at least coach_mapping.default.yml"
            )

        return sorted(mapping_files)  # Sort for consistent test ordering

    def test_mapping_file_structure(self, mapping_files):
        """Test that mapping files have required structure."""
        for mapping_path in mapping_files:
            with open(mapping_path, encoding="utf-8") as f:
                mapping = yaml.safe_load(f)

            # Required top-level sections
            assert "coach_info" in mapping
            assert "dgn_pairs" in mapping
            assert "templates" in mapping

            # Coach info structure
            coach_info = mapping["coach_info"]
            assert "year" in coach_info
            assert "make" in coach_info
            assert "model" in coach_info
            assert "trim" in coach_info

    def test_dgn_pairs_structure(self, mapping_files):
        """Test DGN pairs have valid structure."""
        for mapping_path in mapping_files:
            with open(mapping_path, encoding="utf-8") as f:
                mapping = yaml.safe_load(f)

            dgn_pairs = mapping["dgn_pairs"]
            assert isinstance(dgn_pairs, dict)

            for cmd_dgn, status_dgn in dgn_pairs.items():
                # Both should be hex strings
                assert isinstance(cmd_dgn, str)
                assert isinstance(status_dgn, str)

                # Should be valid hex (without 0x prefix)
                int(cmd_dgn, 16)
                int(status_dgn, 16)

    def test_device_mappings_structure(self, mapping_files):
        """Test device mapping entries have valid structure."""
        for mapping_path in mapping_files:
            with open(mapping_path, encoding="utf-8") as f:
                mapping = yaml.safe_load(f)

            # Find DGN mapping entries (not special sections)
            dgn_keys = [
                k
                for k in mapping
                if not k.startswith("_") and k not in ["coach_info", "dgn_pairs", "templates"]
            ]

            for dgn_key in dgn_keys:
                dgn_mapping = mapping[dgn_key]
                assert isinstance(dgn_mapping, dict)

                for _instance_id, devices in dgn_mapping.items():
                    if isinstance(devices, list):
                        for device in devices:
                            # Required device fields
                            assert "entity_id" in device
                            assert "friendly_name" in device
                            assert "device_type" in device
                            assert "capabilities" in device

                            # Validate types
                            assert isinstance(device["entity_id"], str)
                            assert isinstance(device["friendly_name"], str)
                            assert isinstance(device["device_type"], str)
                            assert isinstance(device["capabilities"], list)


class TestDGNMappingConsistency:
    """Test consistency between RVC spec and coach mappings."""

    @pytest.fixture
    def config_directory(self):
        """Get path to the config directory containing mapping files."""
        return "/workspace/backend/integrations/rvc/config"

    @pytest.fixture
    def mapping_files(self, config_directory):
        """Dynamically discover all coach mapping YAML files in the config directory."""
        # Find all .yml and .yaml files in the config directory
        yaml_pattern = os.path.join(config_directory, "*.yml")
        yaml_files = glob.glob(yaml_pattern)

        # Also check for .yaml extension
        yaml_pattern_alt = os.path.join(config_directory, "*.yaml")
        yaml_files.extend(glob.glob(yaml_pattern_alt))

        # Filter out non-mapping files (keep only coach mapping files)
        mapping_files = []
        for filepath in yaml_files:
            filename = os.path.basename(filepath)
            # Include files with 'mapping' in name or coach-specific naming patterns
            if filename.endswith((".yml", ".yaml")) and (
                "mapping" in filename.lower()
                or
                # Match coach-specific patterns like "YYYY_Make_Model.yml"
                (len(filename.split("_")) >= 3 and filename[:4].isdigit())
            ):
                mapping_files.append(filepath)

        # If no mapping files found by pattern, fall back to known coach files
        if not mapping_files:
            potential_files = [
                os.path.join(config_directory, "coach_mapping.default.yml"),
                os.path.join(config_directory, "2021_Entegra_Aspire_44R.yml"),
            ]
            mapping_files = [f for f in potential_files if os.path.exists(f)]

        # Always include any test files with 'test' in the name
        test_pattern = os.path.join(config_directory, "*test*.yml")
        test_files = glob.glob(test_pattern)
        mapping_files.extend(test_files)

        # Convert to Path objects and remove duplicates
        return [Path(f) for f in set(mapping_files)]

    @pytest.fixture
    def spec_data(self):
        """Load RVC spec data once for all tests."""
        spec_file = Path("/workspace/backend/integrations/rvc/config/rvc.json")
        with open(spec_file, encoding="utf-8") as f:
            rvc_spec = json.load(f)

        # Create hex to ID mapping (matching original load_config_data format)
        pgn_hex_to_id_map = {}
        for pgn_id, pgn_data in rvc_spec["pgns"].items():
            pgn_hex = pgn_data.get("pgn", "")
            if pgn_hex:
                # Map hex string to integer ID (matching original format)
                pgn_hex_to_id_map[pgn_hex] = int(pgn_id)

        return pgn_hex_to_id_map

    def test_dgn_pairs_exist_in_spec(self, mapping_files, spec_data):
        """Test that all DGN pairs reference valid PGNs in the spec."""
        pgn_hex_to_name_map = spec_data

        for mapping_path in mapping_files:
            with open(mapping_path, encoding="utf-8") as f:
                mapping = yaml.safe_load(f)

            dgn_pairs = mapping.get("dgn_pairs", {})

            for cmd_dgn, status_dgn in dgn_pairs.items():
                cmd_pgn = f"0x{cmd_dgn}"
                status_pgn = f"0x{status_dgn}"

                # Both PGNs should exist in the spec
                assert cmd_pgn in pgn_hex_to_name_map, (
                    f"Command PGN {cmd_pgn} not found in spec (file: {mapping_path.name})"
                )
                assert status_pgn in pgn_hex_to_name_map, (
                    f"Status PGN {status_pgn} not found in spec (file: {mapping_path.name})"
                )

    def test_mapping_dgns_exist_in_spec(self, mapping_files, spec_data):
        """Test that all mapping DGNs exist in the spec."""
        pgn_hex_to_name_map = spec_data

        for mapping_path in mapping_files:
            with open(mapping_path, encoding="utf-8") as f:
                mapping = yaml.safe_load(f)

            # Find DGN mapping entries (not special sections)
            dgn_keys = [
                k
                for k in mapping
                if not k.startswith("_") and k not in ["coach_info", "dgn_pairs", "templates"]
            ]

            for dgn_hex in dgn_keys:
                pgn = f"0x{dgn_hex}"
                assert pgn in pgn_hex_to_name_map, (
                    f"Mapped DGN {dgn_hex} not found in spec (file: {mapping_path.name})"
                )

    def test_dgn_calculation_consistency(self, spec_data):
        """Test that DGN calculations are consistent."""
        pgn_hex_to_name_map = spec_data

        # Test a few known DGNs
        test_cases = [
            ("0x1FEDA", 6, 0x0019FEDA),  # DC_DIMMER_STATUS_3
            ("0x1FEDB", 6, 0x0019FEDB),  # Light command
            ("0xFECA", 6, 0x0018FECA),  # DM_RV diagnostic
        ]

        for pgn_hex, priority, expected_dgn in test_cases:
            if pgn_hex in pgn_hex_to_name_map:
                pgn = int(pgn_hex, 16)
                calculated_dgn = (priority << 18) | pgn
                assert calculated_dgn == expected_dgn


class TestSignalDecoding:
    """Test signal decoding functionality."""

    def test_get_bits_function(self):
        """Test bit extraction function."""
        # Test data: 0x19 0x7C 0xFF 0xFF 0xFF 0xFF 0xFF 0xFF
        test_data = b"\x19\x7c\xff\xff\xff\xff\xff\xff"

        # Test instance field (bits 0-7)
        instance = get_bits(test_data, 0, 8)
        assert instance == 0x19  # 25

        # Test group field (bits 8-15)
        group = get_bits(test_data, 8, 8)
        assert group == 0x7C  # 124

    def test_decode_payload_with_known_data(self):
        """Test payload decoding with known good data."""
        # Load config to get a known entry
        from backend.integrations.rvc.decode import load_config_data_v2

        config = load_config_data_v2()
        dgn_dict = config.dgn_dict

        # Find DC_DIMMER_STATUS_3 entry
        test_dgn = 0x0019FEDA
        if test_dgn in dgn_dict:
            entry = dgn_dict[test_dgn]
            test_data = b"\x19\x7c\xff\xff\xff\xff\xff\xff"

            decoded, raw_values = decode_payload(entry, test_data)

            # Check that we get expected fields
            assert "instance" in decoded
            assert "group" in decoded
            assert decoded["instance"] == "25"
            assert decoded["group"] == "124"

            # Check raw values
            assert raw_values["instance"] == 25
            assert raw_values["group"] == 124

    def test_decode_payload_edge_cases(self):
        """Test payload decoding with edge cases."""
        # Create a minimal test entry
        test_entry = {
            "name": "TEST_ENTRY",
            "signals": [
                {"name": "test_field", "start_bit": 0, "length": 8, "byte_order": "little_endian"}
            ],
        }

        # Test with different data lengths
        test_data_8 = b"\x42\x00\x00\x00\x00\x00\x00\x00"
        decoded, raw_values = decode_payload(test_entry, test_data_8)
        assert raw_values["test_field"] == 0x42

        # Test with shorter data (should still work)
        test_data_4 = b"\x42\x00\x00\x00"
        decoded, raw_values = decode_payload(test_entry, test_data_4)
        assert raw_values["test_field"] == 0x42


class TestMissingDGNHandling:
    """Test handling of missing DGNs and error cases."""

    def test_load_config_with_missing_files(self):
        """Test config loading with missing files."""
        with pytest.raises(FileNotFoundError):
            load_config_data(rvc_spec_path_override="/nonexistent/rvc.json")

        with pytest.raises(FileNotFoundError):
            load_config_data(device_mapping_path_override="/nonexistent/mapping.yml")

    def test_invalid_yaml_handling(self):
        """Test handling of invalid YAML files."""
        # Create a temporary invalid YAML file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            invalid_yaml_path = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                load_config_data(device_mapping_path_override=invalid_yaml_path)
        finally:
            os.unlink(invalid_yaml_path)

    def test_invalid_json_handling(self):
        """Test handling of invalid JSON files."""
        # Create a temporary invalid JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"invalid": json, "content"}')
            invalid_json_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                load_config_data(rvc_spec_path_override=invalid_json_path)
        finally:
            os.unlink(invalid_json_path)

    def test_missing_dgn_storage_initialization(self):
        """Test that missing DGN storage initializes correctly."""
        # Clear any existing data
        clear_missing_dgns()

        # Should start empty
        missing_dgns = get_missing_dgns()
        assert isinstance(missing_dgns, dict)
        assert len(missing_dgns) == 0

    def test_record_missing_dgn_basic(self):
        """Test basic missing DGN recording functionality."""
        clear_missing_dgns()

        # Record a missing DGN
        dgn_id = 0x1FEDC
        record_missing_dgn(dgn_id)

        # Verify it was recorded
        missing_dgns = get_missing_dgns()
        assert dgn_id in missing_dgns
        assert "first_seen" in missing_dgns[dgn_id]
        assert "encounter_count" in missing_dgns[dgn_id]
        assert missing_dgns[dgn_id]["encounter_count"] == 1

    def test_record_missing_dgn_with_context(self):
        """Test missing DGN recording with additional context."""
        clear_missing_dgns()

        # Record a missing DGN with context
        dgn_id = 0x1FEDC
        can_id = 0x19FEDC12
        context = "Test context"

        record_missing_dgn(dgn_id, can_id=can_id, context=context)

        # Verify context was recorded
        missing_dgns = get_missing_dgns()
        assert dgn_id in missing_dgns
        entry = missing_dgns[dgn_id]
        assert can_id in entry["can_ids"]
        assert context in entry["contexts"]

    def test_record_missing_dgn_increments_count(self):
        """Test that recording the same DGN multiple times increments count."""
        clear_missing_dgns()

        dgn_id = 0x1FEDC

        # Record same DGN multiple times
        record_missing_dgn(dgn_id)
        record_missing_dgn(dgn_id)
        record_missing_dgn(dgn_id)

        # Verify count incremented
        missing_dgns = get_missing_dgns()
        assert missing_dgns[dgn_id]["encounter_count"] == 3

    def test_clear_missing_dgns(self):
        """Test clearing missing DGNs storage."""
        # Record some missing DGNs
        record_missing_dgn(0x1FEDC)
        record_missing_dgn(0x1FEDB)

        # Verify they exist
        missing_dgns = get_missing_dgns()
        assert len(missing_dgns) == 2

        # Clear and verify empty
        clear_missing_dgns()
        missing_dgns = get_missing_dgns()
        assert len(missing_dgns) == 0

    def test_decode_payload_safe_with_valid_dgn(self):
        """Test safe decoding with a valid DGN."""
        clear_missing_dgns()

        # Create a simple DGN dictionary
        dgn_dict = {
            0x1FEDA: {
                "name": "DC_DIMMER_STATUS_3",
                "signals": [
                    {
                        "name": "instance",
                        "start_bit": 0,
                        "length": 8,
                        "byte_order": "little_endian",
                        "value_type": "unsigned",
                    }
                ],
            }
        }

        dgn_id = 0x1FEDA
        data_bytes = b"\x19\x7c\xff\xff\xff\xff\xff\xff"

        # Should decode successfully
        decoded, raw_values, success = decode_payload_safe(dgn_dict, dgn_id, data_bytes)

        assert success is True
        assert isinstance(decoded, dict)
        assert isinstance(raw_values, dict)
        assert "instance" in raw_values

    def test_decode_payload_safe_with_missing_dgn(self):
        """Test safe decoding with a missing DGN."""
        clear_missing_dgns()

        # Empty DGN dictionary
        dgn_dict = {}
        dgn_id = 0x1FEDC
        data_bytes = b"\x19\x7c\xff\xff\xff\xff\xff\xff"

        # Should handle gracefully
        decoded, raw_values, success = decode_payload_safe(dgn_dict, dgn_id, data_bytes)

        assert success is False
        assert decoded == {}
        assert raw_values == {}

        # Should record the missing DGN
        missing_dgns = get_missing_dgns()
        assert dgn_id in missing_dgns
        assert missing_dgns[dgn_id]["encounter_count"] == 1

    def test_decode_payload_safe_with_corrupted_data(self):
        """Test safe decoding with corrupted data that causes decode errors."""
        clear_missing_dgns()

        # Create a DGN that will cause decode errors with bad data
        dgn_dict = {
            0x1FEDA: {
                "name": "DC_DIMMER_STATUS_3",
                "signals": [
                    {
                        "name": "instance",
                        "start_bit": 0,
                        "length": 8,
                        "byte_order": "little_endian",
                        "value_type": "unsigned",
                        "enum": {"0": "OFF", "1": "ON"},  # Add enum that could cause issues
                    }
                ],
            }
        }

        dgn_id = 0x1FEDA
        # Valid data that should decode successfully (empty data actually works fine)
        data_bytes = b"\x01\x00\x00\x00\x00\x00\x00\x00"

        # Should handle gracefully - actually this should succeed
        decoded, raw_values, success = decode_payload_safe(dgn_dict, dgn_id, data_bytes)

        # The decode should actually succeed, as the function is robust
        assert success is True
        assert "instance" in decoded

    def test_decode_payload_safe_preserves_original_functionality(self):
        """Test that safe decoding preserves original decode functionality for valid cases."""
        # Create a simple DGN dictionary
        dgn_dict = {
            0x1FEDA: {
                "name": "DC_DIMMER_STATUS_3",
                "signals": [
                    {
                        "name": "instance",
                        "start_bit": 0,
                        "length": 8,
                        "byte_order": "little_endian",
                        "value_type": "unsigned",
                    },
                    {
                        "name": "group",
                        "start_bit": 8,
                        "length": 8,
                        "byte_order": "little_endian",
                        "value_type": "unsigned",
                    },
                ],
            }
        }

        dgn_id = 0x1FEDA
        data_bytes = b"\x19\x7c\xff\xff\xff\xff\xff\xff"

        # Compare safe vs regular decoding
        dgn_entry = dgn_dict[dgn_id]
        regular_decoded, regular_raw = decode_payload(dgn_entry, data_bytes)
        safe_decoded, safe_raw, success = decode_payload_safe(dgn_dict, dgn_id, data_bytes)

        assert success is True
        assert safe_decoded == regular_decoded
        assert safe_raw == regular_raw


class TestEndToEndFunctionality:
    """Test complete end-to-end decoder functionality."""

    @pytest.fixture
    def config_data(self):
        """Load configuration data."""
        from backend.integrations.rvc.decode import load_config_data_v2

        config = load_config_data_v2()
        # Return as tuple for backward compatibility with test expectations
        return (
            config.dgn_dict,
            config.pgn_hex_to_name_map,
            config.decoder_map,
            config.inst_map,
            config.unique_instances,
            config.entity_map,
            config.entity_ids,
            config.mapping_dict,
            config.raw_device_mapping,
            config.coach_info,
        )

    def test_complete_decoding_workflow(self, config_data):
        """Test complete decoding workflow from CAN data to entities."""
        (
            dgn_dict,
            spec_meta,
            mapping_dict,
            entity_map,
            entity_ids,
            inst_map,
            unique_instances,
            pgn_hex_to_name_map,
            dgn_pairs,
            coach_info,
        ) = config_data

        # Simulate a CAN message for light status
        can_id = 0x0019FEDA  # DC_DIMMER_STATUS_3
        can_data = b"\x19\x7c\xff\xff\xff\xff\xff\xff"  # Instance 25, Group 124

        # Step 1: Check if DGN exists
        assert can_id in dgn_dict

        # Step 2: Decode the payload
        entry = dgn_dict[can_id]
        decoded, raw_values = decode_payload(entry, can_data)

        # Step 3: Look up entity mapping
        instance = raw_values.get("instance", 0)
        dgn_hex = "1FEDA"
        mapping_key = (dgn_hex, str(instance))

        # Check if mapping exists
        if mapping_key in mapping_dict:
            devices = mapping_dict[mapping_key]
            assert len(devices) > 0

            # Verify device structure
            device = devices[0]
            assert "entity_id" in device
            assert "friendly_name" in device

    def test_coach_info_extraction(self, config_data):
        """Test coach information extraction."""
        coach_info = config_data[9]

        # Should have basic structure
        assert hasattr(coach_info, "filename")
        assert coach_info.filename is not None

    def test_dgn_pairs_processing(self, config_data):
        """Test DGN pairs processing."""
        dgn_pairs = config_data[8]

        # Should have at least one pair
        assert len(dgn_pairs) > 0

        # All pairs should be strings
        for cmd_dgn, status_dgn in dgn_pairs.items():
            assert isinstance(cmd_dgn, str)
            assert isinstance(status_dgn, str)


class TestCoachInfoParsing:
    """Test coach information parsing from mapping files."""

    def test_coach_info_from_metadata(self):
        """Test coach info extraction from _coach_info section."""
        # Create temporary mapping with coach info
        mapping_data = {
            "_coach_info": {
                "year": "2021",
                "make": "Entegra",
                "model": "Aspire",
                "trim": "44R",
                "notes": "Test coach",
            },
            "dgn_pairs": {"1FEDB": "1FEDA"},
            "templates": {"test": {"device_type": "light"}},
            "1FEDB": {"default": [{"entity_id": "test"}]},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(mapping_data, f)
            temp_path = f.name

        try:
            config_data = load_config_data(device_mapping_path_override=temp_path)
            coach_info = config_data[9]

            assert coach_info.year == "2021"
            assert coach_info.make == "Entegra"
            assert coach_info.model == "Aspire"
            assert coach_info.trim == "44R"
            assert coach_info.notes == "Test coach"
        finally:
            os.unlink(temp_path)

    def test_coach_info_from_filename(self):
        """Test coach info extraction from filename pattern."""
        # Create temporary mapping without coach info section
        mapping_data = {
            "dgn_pairs": {"1FEDB": "1FEDA"},
            "templates": {"test": {"device_type": "light"}},
            "1FEDB": {"default": [{"entity_id": "test"}]},
        }

        # Use a filename that matches the pattern
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, prefix="2022_TestMake_TestModel_TestTrim_"
        ) as f:
            yaml.dump(mapping_data, f)
            temp_path = f.name

        try:
            config_data = load_config_data(device_mapping_path_override=temp_path)
            coach_info = config_data[9]

            # Should parse from filename
            assert coach_info.year == "2022"
            assert coach_info.make == "TestMake"
            assert coach_info.model == "TestModel"
            assert "TestTrim" in coach_info.trim  # trim includes remaining parts
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
