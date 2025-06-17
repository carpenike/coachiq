"""
Repository Pattern Implementation

Part of Phase 2R: AppState Repository Migration

This package contains repository classes that separate data concerns
from the monolithic AppState, following the Single Responsibility Principle.
"""

from backend.repositories.entity_state_repository import EntityStateRepository
from backend.repositories.rvc_config_repository import RVCConfigRepository
from backend.repositories.can_tracking_repository import CANTrackingRepository
from backend.repositories.diagnostics_repository import DiagnosticsRepository

__all__ = [
    "EntityStateRepository",
    "RVCConfigRepository",
    "CANTrackingRepository",
    "DiagnosticsRepository",
]
