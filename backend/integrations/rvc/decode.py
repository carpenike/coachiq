"""
backend.integrations.rvc.decode

Core decoding logic for RV-C CAN frames, including loading of spec and device mapping data.

This module serves as the main entry point for RV-C decoding functionality,
delegating to specialized submodules for different aspects of the decoding process.

Functions:
    - get_bits: Extracts a little-endian bitfield from a CAN payload
    - decode_payload: Decodes all signals in a spec entry
    - load_config_data: Loads and parses RVC spec and device mapping

The actual implementation is split across several modules:
    - config_loader: Handles loading and validation of configuration files
    - decoder_core: Core bit-level decoding logic
    - missing_dgns: Tracks DGNs not found in the specification
    - bam_handler: Handles multi-packet BAM message reassembly
"""

import functools
import logging

from backend.integrations.rvc.config_loader import (
    extract_coach_info,
    get_default_paths,
    load_device_mapping,
    load_rvc_spec,
)
from backend.integrations.rvc.decoder_core import decode_payload as _decode_payload
from backend.integrations.rvc.decoder_core import get_bits as _get_bits
from backend.integrations.rvc.decoder_core import DecodedValue, DecodeError
from backend.integrations.rvc.missing_dgns import (
    clear_missing_dgns,
    get_missing_dgns,
    record_missing_dgn,
)
from backend.models.common import CoachInfo
from backend.models.rvc_config import RVCConfiguration, RVCSpecMeta

logger = logging.getLogger(__name__)

# Re-export the core functions for backward compatibility
get_bits = _get_bits
decode_payload = _decode_payload

# Re-export missing DGN functions for backward compatibility
__all__ = [
    "clear_config_cache",
    "clear_missing_dgns",
    "decode_payload",
    "decode_payload_safe",
    "get_bits",
    "get_missing_dgns",
    "load_config_data",
    "load_config_data_v2",
    "record_missing_dgn",
]


def clear_config_cache() -> None:
    """Clear the configuration cache to force reloading."""
    load_config_data.cache_clear()
    load_config_data_v2.cache_clear()
    logger.debug("Configuration cache cleared")


def decode_payload_safe(
    dgn_dict: dict[int, dict], dgn_id: int, data_bytes: bytes
) -> tuple[dict[str, str], dict[str, int], bool]:
    """
    Safely decode a payload, handling missing DGNs gracefully.

    Args:
        dgn_dict: Dictionary mapping DGNs to specification entries
        dgn_id: The DGN ID to decode
        data_bytes: The CAN payload bytes

    Returns:
        tuple containing:
            - decoded: Dictionary of decoded signal values (empty if DGN missing)
            - raw_values: Dictionary of raw signal values (empty if DGN missing)
            - success: Boolean indicating if decoding was successful
    """
    if dgn_id not in dgn_dict:
        record_missing_dgn(dgn_id, context="decode_payload_safe")
        logger.warning(f"DGN {dgn_id:X} not found in specification - storing for future processing")
        return {}, {}, False

    try:
        entry = dgn_dict[dgn_id]
        results, errors = decode_payload(entry, data_bytes)

        # Convert to the expected format for backward compatibility
        decoded = {}
        raw_values = {}

        for signal_name, result in results.items():
            if isinstance(result, DecodedValue):
                decoded[signal_name] = str(result.value)
                if result.raw_value is not None:
                    raw_values[signal_name] = int(result.raw_value)
            elif isinstance(result, DecodeError):
                decoded[signal_name] = f"<error: {result.message}>"

        return decoded, raw_values, len(errors) == 0
    except Exception as e:
        logger.error(f"Error decoding DGN {dgn_id:X}: {e}")
        record_missing_dgn(dgn_id, context=f"decode_error: {e!s}")
        return {}, {}, False


@functools.cache
def load_config_data(
    rvc_spec_path_override: str | None = None,
    device_mapping_path_override: str | None = None,
) -> tuple[
    dict[int, dict],  # dgn_dict
    dict,  # spec_meta
    dict[tuple[str, str], dict],  # mapping_dict
    dict[tuple[str, str], dict],  # entity_map
    set[str],  # entity_ids
    dict[str, dict],  # inst_map
    dict[str, dict],  # unique_instances
    dict[str, str],  # pgn_hex_to_name_map
    dict,  # dgn_pairs
    CoachInfo,  # coach_info
]:
    """
    Load and parse RVC spec and device mapping data.

    DEPRECATED: This function returns a complex 10-element tuple that makes code
    difficult to maintain and test. Use load_config_data_v2() instead, which returns
    a structured RVCConfiguration object with proper type hints and convenient
    access methods.

    This function uses @functools.cache to automatically cache the loaded data
    and avoid redundant file I/O and parsing when the same configuration is
    requested multiple times during startup.

    Args:
        rvc_spec_path_override: Optional path override for RVC spec JSON
        device_mapping_path_override: Optional path override for device mapping YAML

    Returns:
        tuple containing:
            - dgn_dict: Dictionary mapping DGNs to specification entries
            - spec_meta: Metadata from the RVC spec
            - mapping_dict: Dictionary mapping (DGN, instance) pairs to device entries
            - entity_map: Dictionary mapping entity IDs to device entries
            - entity_ids: Set of all entity IDs for validation
            - inst_map: Dictionary mapping entity IDs to (dgn_hex, instance) pairs
            - unique_instances: Dictionary of DGN instances with only one device
            - pgn_hex_to_name_map: Dictionary mapping DGN hex strings to PGN names
            - dgn_pairs: Dictionary mapping DGNs to useful metadata for faster lookups
            - coach_info: CoachInfo object with detected coach metadata
    """
    # Log deprecation warning
    import warnings

    warnings.warn(
        "load_config_data() is deprecated and returns a complex 10-element tuple. "
        "Use load_config_data_v2() instead for a structured RVCConfiguration object.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Get default paths if not overridden
    rvc_spec_path, device_mapping_path = get_default_paths()
    if rvc_spec_path_override:
        rvc_spec_path = rvc_spec_path_override
    if device_mapping_path_override:
        device_mapping_path = device_mapping_path_override

    # Load RVC spec and device mapping using the new modules
    rvc_spec = load_rvc_spec(rvc_spec_path)
    device_mapping = load_device_mapping(device_mapping_path)

    # Process DGN dictionary
    dgn_dict = {}
    pgn_hex_to_name_map = {}
    rvc_spec_dgn_pairs = {}

    for pgn_name, pgn_entry in rvc_spec["pgns"].items():
        pgn = int(pgn_entry["pgn"], 16)
        priority = int(pgn_entry.get("priority", "6"), 16)
        dgn = (priority << 18) | pgn

        # Add dgn_hex to the entry for easier lookups
        pgn_entry["dgn_hex"] = pgn_entry["pgn"]

        dgn_dict[dgn] = pgn_entry
        pgn_hex_to_name_map[pgn_entry["pgn"]] = pgn_name
        rvc_spec_dgn_pairs[pgn_entry["pgn"]] = {
            "dgn": dgn,
            "name": pgn_name,
        }

    # Extract dgn_pairs from device mapping (command PGN -> status PGN mapping)
    dgn_pairs = device_mapping.get("dgn_pairs", {})

    # Extract spec metadata
    spec_meta = {
        "version": rvc_spec.get("version", "unknown"),
        "source": rvc_spec.get("source", "unknown"),
        "rvc_verison": rvc_spec.get("rvc_version", "unknown"),
    }

    # Extract coach info from mapping file
    coach_info = extract_coach_info(device_mapping, device_mapping_path)

    # Process mapping dictionary
    mapping_dict = {}
    entity_map = {}
    entity_ids = set()
    inst_map = {}
    unique_instances = {}

    for dgn_hex, instance_dict in device_mapping.items():
        if dgn_hex.startswith(("#", "_")):
            # Skip comment lines
            continue

        # Skip metadata sections
        if dgn_hex in (
            "coach_info",
            "dgn_pairs",
            "templates",
            "global_defaults",
            "areas",
            "lighting_scenes",
            "lighting_groups",
            "validation_rules",
            "file_metadata",
            "can_interface_mapping",
        ):
            continue

        for instance_id, devices in instance_dict.items():
            if not isinstance(devices, list):
                continue  # Skip non-list entries

            mapping_dict[(dgn_hex, str(instance_id))] = devices

            if len(devices) == 1:
                # Only store uniquely identifiable instances
                unique_instances.setdefault(dgn_hex, {})[str(instance_id)] = devices[0]

            for device in devices:
                entity_id = device.get("entity_id")
                if entity_id:
                    entity_ids.add(entity_id)
                    entity_map[(dgn_hex, str(instance_id))] = device
                    inst_map[entity_id] = {
                        "dgn_hex": dgn_hex,
                        "instance": instance_id,
                    }

    return (
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
    )


@functools.cache
def load_config_data_v2(
    rvc_spec_path_override: str | None = None,
    device_mapping_path_override: str | None = None,
) -> RVCConfiguration:
    """
    Load and parse RVC spec and device mapping data into a structured object.

    This is the new version that returns a properly typed RVCConfiguration object
    instead of a complex tuple. It provides the same functionality with better
    type safety and easier access patterns.

    Args:
        rvc_spec_path_override: Optional path override for RVC spec JSON
        device_mapping_path_override: Optional path override for device mapping YAML

    Returns:
        RVCConfiguration object containing all loaded configuration data
    """
    # Load the data using the existing function
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
    ) = load_config_data(rvc_spec_path_override, device_mapping_path_override)

    # Convert inst_map to use RVCEntityMapping objects
    inst_map_structured = {}
    for entity_id, mapping in inst_map.items():
        inst_map_structured[entity_id] = mapping  # Keep as dict for now for compatibility

    # Create structured spec metadata
    spec_meta_structured = RVCSpecMeta(
        version=spec_meta.get("version", "unknown"),
        source=spec_meta.get("source", "unknown"),
        rvc_version=spec_meta.get("rvc_verison", "unknown"),  # Note: typo in original
    )

    # Return structured configuration
    return RVCConfiguration(
        dgn_dict=dgn_dict,
        spec_meta=spec_meta_structured,
        mapping_dict=mapping_dict,
        entity_map=entity_map,
        entity_ids=entity_ids,
        inst_map=inst_map_structured,
        unique_instances=unique_instances,
        pgn_hex_to_name_map=pgn_hex_to_name_map,
        dgn_pairs=dgn_pairs,
        coach_info=coach_info,
    )
