"""
Models package for CoachIQ.

This package contains Pydantic models for data validation, serialization, and
documentation across the application.
"""

from backend.models.can_message import CANMessage, CANMessageBatch, CANMessageFilter
from backend.models.common import CoachInfo, UserCoachInfo
from backend.models.entity import ControlCommand, ControlEntityResponse, Entity
from backend.models.unmapped import (
    SuggestedMapping,
    UnknownPGNEntry,
    UnmappedEntryModel,
)

__all__ = [
    "CANMessage",
    "CANMessageBatch",
    "CANMessageFilter",
    "CoachInfo",
    "ControlCommand",
    "ControlEntityResponse",
    "Entity",
    "SuggestedMapping",
    "UnknownPGNEntry",
    "UnmappedEntryModel",
    "UserCoachInfo",
]
