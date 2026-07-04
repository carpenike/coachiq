"""
CAN Message Factory

Provides factory functions for creating RV-C specific CAN messages.
Extracted from the original can_manager to support the service layer architecture.
"""

import can


def create_light_can_message(pgn: int, instance: int, brightness_can_level: int) -> can.Message:
    """
    Constructs a can.Message for an RV-C light command.

    Args:
        pgn: The Parameter Group Number for the light command.
        instance: The instance ID of the light.
        brightness_can_level: The target brightness level, scaled for CAN (e.g., 0-200).

    Returns:
        A can.Message object ready to be sent.
    """
    # Determine Arbitration ID components
    prio = 6  # Typical priority for commands
    sa = 0xF9  # Source Address (typically the controller/gateway)
    dp = (pgn >> 16) & 1  # Data Page
    pf = (pgn >> 8) & 0xFF  # PDU Format
    da = 0xFF  # Destination Address (broadcast)

    if pf < 0xF0:  # PDU1 format (destination address is DA)
        arbitration_id = (prio << 26) | (dp << 24) | (pf << 16) | (da << 8) | sa
    else:  # PDU2 format (destination address is in PS field, effectively broadcast if DA is 0xFF)
        ps = pgn & 0xFF  # PDU Specific (contains group extension or specific address)
        arbitration_id = (prio << 26) | (dp << 24) | (pf << 16) | (ps << 8) | sa

    # Construct payload. Byte layout verified on the live coach bus against the
    # Firefly dimmer modules (see docs/can-re-findings.md): sending
    # 19FEDBF9#19FF6400FF00FFFF set instance 0x19 to op_status 0x64 and
    # ...#19FF0000FF00FFFF turned it off, with DC_DIMMER_STATUS_3 echoing the
    # commanded level exactly. Group must be 0xFF (none), duration 0xFF
    # (instant), byte5 0x00 — the previous 0x7C/0x00/0xFF values were no-ops.
    payload_data = bytes(
        [
            instance,  # byte0: instance
            0xFF,  # byte1: group = none
            brightness_can_level,  # byte2: level (0-200, 0xC8 = 100%, 0x00 = off)
            0x00,  # byte3: command = set level
            0xFF,  # byte4: duration = instant
            0x00,  # byte5
            0xFF,  # byte6
            0xFF,  # byte7
        ]
    )

    return can.Message(arbitration_id=arbitration_id, data=payload_data, is_extended_id=True)
