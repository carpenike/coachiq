"""
J1939 protocol integration module.

This module provides support for the J1939 protocol used in heavy-duty vehicle
communications, including engine, transmission, and chassis systems.

Key features:
- Standard J1939 PGN decoding
- Cummins engine-specific extensions
- Allison transmission support
- Chassis system integration (Spartan K2, etc.)
- Protocol bridging with RV-C
- Security and validation features
"""

from backend.integrations.j1939.decoder import J1939Decoder

__all__ = ["J1939Decoder"]
