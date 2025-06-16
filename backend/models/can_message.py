"""
CAN Message models for the backend API.

This module contains Pydantic models for CAN bus message representation,
supporting both standard and extended CAN frames, as well as RV-C specific
message structures.
"""

from typing import ClassVar

from pydantic import BaseModel, Field, conlist


class CANMessage(BaseModel):
    """
    Represents a CAN message for transmission or reception.

    This model supports both standard (11-bit) and extended (29-bit) CAN IDs,
    and includes fields for RV-C protocol support.
    """

    can_id: int = Field(
        ...,
        description="CAN arbitration ID (11-bit standard or 29-bit extended)",
        ge=0,
        le=0x1FFFFFFF,  # Max 29-bit ID
    )
    data: bytes = Field(
        ...,
        description="Message data payload (0-8 bytes for CAN 2.0, up to 64 for CAN FD)",
        min_length=0,
        max_length=64,
    )
    extended: bool = Field(
        default=True,
        description="Whether this is an extended frame (29-bit ID)",
    )
    is_bam: bool = Field(
        default=False,
        description="Whether this is part of a BAM (Broadcast Announce Message) sequence",
    )
    target_pgn: int | None = Field(
        default=None,
        description="Target PGN for BAM messages",
        ge=0,
        le=0x3FFFF,  # 18-bit PGN
    )
    interface: str | None = Field(
        default=None,
        description="CAN interface name (e.g., 'can0', 'can1')",
    )
    timestamp: float | None = Field(
        default=None,
        description="Message timestamp in seconds since epoch",
    )
    is_error: bool = Field(
        default=False,
        description="Whether this is an error frame",
    )
    is_remote: bool = Field(
        default=False,
        description="Whether this is a remote transmission request frame",
    )

    class Config:
        """Pydantic model configuration."""

        json_encoders: ClassVar[dict] = {
            bytes: lambda v: v.hex().upper(),  # Encode bytes as hex string
        }

    def to_dict(self) -> dict:
        """
        Convert to dictionary representation.

        Returns:
            Dictionary with CAN message data
        """
        return {
            "can_id": self.can_id,
            "data": self.data.hex().upper(),
            "extended": self.extended,
            "is_bam": self.is_bam,
            "target_pgn": self.target_pgn,
            "interface": self.interface,
            "timestamp": self.timestamp,
            "is_error": self.is_error,
            "is_remote": self.is_remote,
        }

    @property
    def dlc(self) -> int:
        """Data Length Code - the number of data bytes."""
        return len(self.data)

    @property
    def pgn(self) -> int | None:
        """
        Extract PGN from CAN ID for RV-C messages.

        RV-C uses 29-bit extended CAN IDs:
        Priority (3 bits) + PGN (18 bits) + Source (8 bits)
        """
        if self.extended:
            return (self.can_id >> 8) & 0x3FFFF
        return None

    @property
    def source_address(self) -> int | None:
        """Extract source address from CAN ID for RV-C messages."""
        if self.extended:
            return self.can_id & 0xFF
        return None

    @property
    def priority(self) -> int | None:
        """Extract priority from CAN ID for RV-C messages."""
        if self.extended:
            return (self.can_id >> 26) & 0x7
        return None

    def __str__(self) -> str:
        """String representation of the CAN message."""
        id_str = f"{self.can_id:08X}" if self.extended else f"{self.can_id:03X}"
        data_str = self.data.hex().upper()
        interface_str = f" [{self.interface}]" if self.interface else ""
        return f"CAN{interface_str} ID: {id_str} Data: {data_str} DLC: {self.dlc}"


class CANMessageBatch(BaseModel):
    """Represents a batch of CAN messages for bulk operations."""

    messages: conlist(CANMessage, min_length=1, max_length=1000) = Field(  # type: ignore[valid-type]
        ...,
        description="List of CAN messages to process",
    )
    interface: str | None = Field(
        default=None,
        description="Default interface for all messages (can be overridden per message)",
    )


class CANMessageFilter(BaseModel):
    """Filter criteria for CAN message queries."""

    can_id: int | None = Field(
        default=None,
        description="Filter by specific CAN ID",
    )
    pgn: int | None = Field(
        default=None,
        description="Filter by PGN (RV-C messages only)",
    )
    source_address: int | None = Field(
        default=None,
        description="Filter by source address (RV-C messages only)",
    )
    interface: str | None = Field(
        default=None,
        description="Filter by interface name",
    )
    start_time: float | None = Field(
        default=None,
        description="Filter messages after this timestamp",
    )
    end_time: float | None = Field(
        default=None,
        description="Filter messages before this timestamp",
    )
    limit: int = Field(
        default=100,
        description="Maximum number of messages to return",
        ge=1,
        le=10000,
    )
