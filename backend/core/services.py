"""
DEPRECATED: Legacy Core Services Layer - REMOVED

This module contained the deprecated CoreServices class which has been removed.
All services are now managed by ServiceRegistry with dependency injection.

Migration Guide:
- OLD: get_core_services().persistence
- NEW: Depends(get_persistence_service)

- OLD: get_core_services().database_manager  
- NEW: Depends(get_database_manager)

See backend/core/core_services_removal.py for complete migration instructions.
"""

import logging

logger = logging.getLogger(__name__)

# Legacy functions removed - CoreServices pattern completely deprecated
# All services are now accessed via ServiceRegistry dependency injection
