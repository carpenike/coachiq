"""
CAN-related models for the backend API.

This module contains Pydantic models for CAN bus operations and statistics.
"""

from pydantic import BaseModel, Field


class CANInterfaceStats(BaseModel):
    """Statistics for a CAN interface."""

    name: str
    state: str | None = None
    restart_ms: int | None = None
    bitrate: int | None = None
    sample_point: float | None = None
    tq: int | None = None  # Time quantum in nanoseconds
    prop_seg: int | None = None
    phase_seg1: int | None = None
    phase_seg2: int | None = None
    sjw: int | None = None  # Synchronization Jump Width
    brp: int | None = None  # Bitrate Prescaler
    clock_freq: int | None = Field(default=None, alias="clock")  # Clock frequency Hz
    notes: str | None = None  # Additional notes or platform-specific information

    # From ip -s link show
    tx_packets: int | None = None
    rx_packets: int | None = None
    tx_bytes: int | None = None
    rx_bytes: int | None = None
    tx_errors: int | None = None
    rx_errors: int | None = None
    tx_dropped: int | None = None
    rx_dropped: int | None = None
    bus_errors: int | None = None  # General bus errors
    restarts: int | None = None  # Controller restarts
    arbitration_lost: int | None = None  # Controller arbitration lost count

    # Additional details from ip -details link show
    link_type: str | None = Field(default=None, alias="link/can")
    promiscuity: int | None = None
    allmulti: int | None = None
    minmtu: int | None = None
    maxmtu: int | None = None
    parentbus: str | None = None
    parentdev: str | None = None

    # Specific error counters if available (these might vary by controller)
    error_warning: int | None = None  # Entered error warning state count
    error_passive: int | None = None  # Entered error passive state count
    bus_off: int | None = None  # Entered bus off state count

    # Raw details string for any unparsed info, if needed for debugging
    raw_details: str | None = None


class AllCANStats(BaseModel):
    """Statistics for all CAN interfaces."""

    interfaces: dict[str, CANInterfaceStats]
