"""
Services package for CoachIQ.

This package contains business logic services that implement core functionality
and features of the application.
"""

# CANService import removed - replaced by CANFacade
from backend.services.config_service import ConfigService
from backend.services.docs_service import DocsService
from backend.services.entity_service import EntityService

__all__ = [
    "CANService",
    "ConfigService",
    "DocsService",
    "EntityService",
]
