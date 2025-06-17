"""
RV-C (Recreational Vehicle Controller Area Network) integration package.

This package provides RV-C protocol support for decoding and encoding CAN messages
according to the RV-C specification. It includes:

- Message decoding from CAN frames
- Multi-packet BAM message reassembly
- Configuration loading and validation
- Missing DGN tracking
- Entity state management integration

Functions:
    - get_bits: Extract bits from binary data
    - decode_payload: Convert raw CAN data into decoded signal values
    - decode_payload_safe: Safely decode with missing DGN handling
    - load_config_data: Load RV-C specification and device mapping files
    - clear_config_cache: Clear cached configuration data
    - get_missing_dgns: Get tracked missing DGNs
    - clear_missing_dgns: Clear missing DGN tracking
    - record_missing_dgn: Record a missing DGN encounter
"""

# Import main functions for backward compatibility
# Import BAM handler for multi-packet support
from backend.integrations.rvc.bam_handler import BAMHandler
from backend.integrations.rvc.decode import (
    clear_config_cache,
    clear_missing_dgns,
    decode_payload,
    decode_payload_safe,
    get_bits,
    get_missing_dgns,
    load_config_data,
    load_config_data_v2,
    record_missing_dgn,
)

# Import decoder core functions
from backend.integrations.rvc.decoder_core import (
    decode_product_id,
    decode_string_payload,
)

__all__ = [
    "BAMHandler",
    "clear_config_cache",
    "clear_missing_dgns",
    "decode_payload",
    "decode_payload_safe",
    "decode_product_id",
    "decode_string_payload",
    "get_bits",
    "get_missing_dgns",
    "load_config_data",
    "load_config_data_v2",
    "record_missing_dgn",
]
