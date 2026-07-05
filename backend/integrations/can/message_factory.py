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


def create_thermostat_can_message(  # noqa: PLR0913 - one arg per THERMOSTAT_COMMAND_1 field
    instance: int,
    operating_mode: int,
    fan_mode: int,
    schedule_mode: int,
    fan_speed_raw: int,
    setpoint_heat_raw: int,
    setpoint_cool_raw: int,
) -> can.Message:
    """
    Constructs a can.Message for an RV-C THERMOSTAT_COMMAND_1 (DGN 0x1FEF9).

    The payload mirrors the THERMOSTAT_STATUS_1 layout the G6 broadcasts
    (observed on the coach bus): instance, packed mode byte, fan speed
    (0-200 half-percent), then heat and cool setpoints as little-endian
    uint16 in 1/32 K steps.

    Args:
        instance: Thermostat zone instance (0-6 on the Aspire 44R).
        operating_mode: 0=off, 1=cool, 2=heat, 3=auto, 4=fan only, 5=aux heat.
        fan_mode: 0=auto, 1=on.
        schedule_mode: 0=disabled, 1=enabled.
        fan_speed_raw: 0-200 (half-percent; 0 = automatic).
        setpoint_heat_raw: uint16 Table 5.3 temperature (raw = (degC+273)*32).
        setpoint_cool_raw: uint16 Table 5.3 temperature.

    Returns:
        A can.Message object ready to be sent.
    """
    pgn = 0x1FEF9
    prio = 6
    sa = 0xF9  # CoachIQ's source address, same as the light command path
    arbitration_id = (prio << 26) | (pgn << 8) | sa  # 0x19FEF9F9

    mode_byte = (operating_mode & 0x0F) | ((fan_mode & 0x03) << 4) | ((schedule_mode & 0x03) << 6)
    payload_data = bytes(
        [
            instance & 0xFF,
            mode_byte,
            fan_speed_raw & 0xFF,
            setpoint_heat_raw & 0xFF,
            (setpoint_heat_raw >> 8) & 0xFF,
            setpoint_cool_raw & 0xFF,
            (setpoint_cool_raw >> 8) & 0xFF,
            0xFF,  # byte7 unused
        ]
    )

    return can.Message(arbitration_id=arbitration_id, data=payload_data, is_extended_id=True)


def create_water_heater_can_message(instance: int, operating_mode: int) -> can.Message:
    """
    Constructs a can.Message for an RV-C WATERHEATER_COMMAND (DGN 0x1FFF6).

    Sets the operating mode only (0=off, 1=combustion, 2=electric,
    3=gas/electric, 4=automatic); the setpoint field carries the RV-C
    "no change" sentinel (0xFFFF). Layout mirrors WATERHEATER_STATUS per
    RV-C Sec. 6.9.3 — NOT yet wire-verified against the coach's Aqua-Hot
    node (see docs/can-re-findings.md before trusting it blindly).

    Args:
        instance: Water heater instance (1 on the Aspire 44R; 0 = all).
        operating_mode: Target mode (burner bit 0x1 | electric bit 0x2).

    Returns:
        A can.Message object ready to be sent.
    """
    pgn = 0x1FFF6
    prio = 6
    sa = 0xF9  # CoachIQ's source address, same as the other command paths
    arbitration_id = (prio << 26) | (pgn << 8) | sa  # 0x19FFF6F9

    payload_data = bytes(
        [
            instance & 0xFF,
            operating_mode & 0xFF,
            0xFF,  # setpoint LSB: no change
            0xFF,  # setpoint MSB: no change
            0xFF,
            0xFF,
            0xFF,
            0xFF,
        ]
    )

    return can.Message(arbitration_id=arbitration_id, data=payload_data, is_extended_id=True)
