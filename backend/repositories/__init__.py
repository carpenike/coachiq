"""
Repository Pattern Implementation

This package contains repository classes that decompose what used to be
the monolithic ``AppState`` into focused, single-responsibility data
access objects. ``AppState`` itself was removed in 2026-05; the
repository pattern is the canonical replacement.
"""

from backend.repositories.can_tracking_repository import CANTrackingRepository
from backend.repositories.diagnostics_repository import DiagnosticsRepository
from backend.repositories.entity_state_repository import EntityStateRepository
from backend.repositories.rvc_config_repository import RVCConfigRepository
from backend.repositories.system_state_repository import SystemStateRepository

__all__ = [
    "CANTrackingRepository",
    "DiagnosticsRepository",
    "EntityStateRepository",
    "RVCConfigRepository",
    "SystemStateRepository",
]
