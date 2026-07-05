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
from typing import Any

from backend.integrations.rvc.config_loader import (
    extract_coach_info,
    get_default_paths,
    load_device_mapping,
    load_rvc_spec,
)
from backend.integrations.rvc.decoder_core import DecodedValue, DecodeError
from backend.integrations.rvc.decoder_core import decode_payload as _decode_payload
from backend.integrations.rvc.decoder_core import get_bits as _get_bits
from backend.integrations.rvc.mapping_schema import (
    compile_entity_mapping,
    is_entity_first_mapping,
)
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

# Top-level keys in a coach mapping YAML that are configuration metadata
# rather than DGN sections. The mapping iterator MUST skip these or it would
# attempt to treat per-area / per-interface metadata as if it were a DGN's
# instance dictionary, silently producing phantom (dgn_hex, instance) entries.
#
# Keep this in lockstep with the structure of the coach mapping YAMLs in
# `config/`. The previous implementation inlined this list and missed
# `interface_requirements`, which the 2021_Entegra_Aspire_44R.yml mapping
# uses; that bug only avoided producing bogus mapping entries because the
# nested children happen to be dicts (not lists). Centralising the list
# stops the same bug from creeping back if a new section gets added to the
# coach mapping schema without updating decode.py.
DEVICE_MAPPING_METADATA_SECTIONS: tuple[str, ...] = (
    "coach_info",
    "dgn_pairs",
    "templates",
    "global_defaults",
    "defaults",
    "entities",
    "areas",
    "lighting_scenes",
    "lighting_groups",
    "validation_rules",
    "file_metadata",
    "can_interface_mapping",
    "interface_requirements",
)

# Re-export missing DGN functions for backward compatibility
__all__ = [
    "DEVICE_MAPPING_METADATA_SECTIONS",
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
    dgn_dict: dict[int, dict[str, Any]], dgn_id: int, data_bytes: bytes
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
        logger.warning("DGN %X not found in specification - storing for future processing", dgn_id)
        return {}, {}, False

    try:
        entry = dgn_dict[dgn_id]
        results, errors = decode_payload(entry, data_bytes)

        # Convert to the expected format for backward compatibility
        decoded = {}
        raw_values = {}

        for signal_name, result in results.items():
            if isinstance(result, DecodedValue):
                decoded[signal_name] = "n/a" if result.unavailable else str(result.value)
                if result.raw_value is not None:
                    raw_values[signal_name] = int(result.raw_value)
            elif isinstance(result, DecodeError):
                decoded[signal_name] = f"<error: {result.message}>"

        return decoded, raw_values, len(errors) == 0
    except Exception as e:
        logger.error("Error decoding DGN %X: %s", dgn_id, e)
        record_missing_dgn(dgn_id, context=f"decode_error: {e!s}")
        return {}, {}, False


@functools.cache
def load_config_data(
    rvc_spec_path_override: str | None = None,
    device_mapping_path_override: str | None = None,
) -> tuple[
    dict[int, dict[str, Any]],  # dgn_dict
    dict[str, Any],  # spec_meta
    dict[tuple[str, str], list[dict[str, Any]]],  # mapping_dict (values are device LISTS)
    dict[tuple[str, str], dict[str, Any]],  # entity_map
    set[str],  # entity_ids
    dict[str, dict[str, Any]],  # inst_map
    dict[str, dict[str, dict[str, Any]]],  # unique_instances
    dict[str, str],  # pgn_hex_to_name_map
    dict[str, Any],  # dgn_pairs
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
    dgn_dict: dict[int, dict[str, Any]] = {}
    pgn_hex_to_name_map: dict[str, str] = {}
    rvc_spec_dgn_pairs: dict[str, dict[str, Any]] = {}

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

    # Process mapping dictionary. Entity-first mappings (top-level
    # `entities:` key) compile through the validated schema in
    # mapping_schema.py; legacy DGN-first mappings (coach_mapping.default.yml)
    # run the original iterator.
    if is_entity_first_mapping(device_mapping):
        (
            mapping_dict,
            entity_map,
            entity_ids,
            inst_map,
            unique_instances,
        ) = compile_entity_mapping(device_mapping)
    else:
        (
            mapping_dict,
            entity_map,
            entity_ids,
            inst_map,
            unique_instances,
        ) = _compile_legacy_mapping(device_mapping)

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


def _compile_legacy_mapping(
    device_mapping: dict[str, Any],
) -> tuple[
    dict[tuple[str, str], list[dict[str, Any]]],
    dict[tuple[str, str], dict[str, Any]],
    set[str],
    dict[str, dict[str, Any]],
    dict[str, dict[str, dict[str, Any]]],
]:
    """Compile a legacy DGN-first coach mapping into the runtime lookups.

    Note the known wart this format carries: ``inst_map`` is last-write-wins
    across DGN sections, so section ORDER in the YAML decides which instance
    the control path uses. The entity-first schema (mapping_schema.py) fixes
    this by declaring command targets explicitly; new coach mappings should
    use it.
    """
    mapping_dict: dict[tuple[str, str], list[dict[str, Any]]] = {}
    entity_map: dict[tuple[str, str], dict[str, Any]] = {}
    entity_ids: set[str] = set()
    inst_map: dict[str, dict[str, Any]] = {}
    unique_instances: dict[str, dict[str, dict[str, Any]]] = {}

    for dgn_hex, instance_dict in device_mapping.items():
        if dgn_hex.startswith(("#", "_")):
            # Skip comment lines
            continue

        # Skip metadata sections (kept in lockstep with the coach mapping
        # YAML schema; see DEVICE_MAPPING_METADATA_SECTIONS for rationale).
        if dgn_hex in DEVICE_MAPPING_METADATA_SECTIONS:
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
                    inst_entry: dict[str, Any] = {
                        "dgn_hex": dgn_hex,
                        "instance": instance_id,
                    }
                    # Some entities are driven by more than one dimmer output and
                    # must be commanded on every instance (e.g. the bedroom
                    # ceiling light is instances 25 and 26). The coach mapping
                    # expresses this via an optional `command_instances` list on
                    # the command-DGN device entry; carry it through so the
                    # encoder can fan the command out.
                    command_instances = device.get("command_instances")
                    if isinstance(command_instances, list | tuple):
                        inst_entry["command_instances"] = list(command_instances)
                    inst_map[entity_id] = inst_entry

    return mapping_dict, entity_map, entity_ids, inst_map, unique_instances


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
    inst_map_structured = dict(inst_map)  # Keep as dict for now for compatibility

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
