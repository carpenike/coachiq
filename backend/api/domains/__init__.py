"""
Domain API Routers Package

This package contains domain-specific API routers for the v2 API architecture.
Each domain provides enhanced capabilities over the legacy monolithic API.

Domain routers:
- entities: Entity management and control operations
- diagnostics: Diagnostic trouble codes and system health
- networks: Network topology and device discovery
- system: System-level configuration and monitoring

Safety-Critical Implementation:
- All domain APIs are disabled by default via feature flags
- Command/acknowledgment patterns for vehicle control
- State reconciliation with RV-C bus as source of truth
- Comprehensive audit logging for all operations
"""

import logging
from collections.abc import Callable

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Registry of domain router registration functions
DOMAIN_ROUTERS: dict[str, Callable] = {}


def register_domain_router(domain_name: str):
    """Decorator to register domain router factory functions"""

    def decorator(register_func: Callable):
        DOMAIN_ROUTERS[domain_name] = register_func
        return register_func

    return decorator


def register_all_domain_routers(app: FastAPI) -> None:
    """
    Register all available domain routers unconditionally

    Per CLAUDE.md: Domain API v2 is the ONLY implementation and should not be behind feature flags

    Args:
        app: FastAPI application instance
    """
    for domain_name, register_func in DOMAIN_ROUTERS.items():
        try:
            router = register_func()
            app.include_router(router, prefix=f"/api/v2/{domain_name}")
            logger.info("✅ Registered domain router: %s", domain_name)
        except Exception as e:
            logger.error("❌ Failed to register domain router %s: %s", domain_name, e)


# Import domain modules to trigger registration
try:
    from . import diagnostics, entities, networks, system

    # Explicitly reference imported modules to satisfy linter
    _domain_modules = [entities, diagnostics, networks, system]
except ImportError as e:
    logger.warning("⚠️  Some domain modules not available: %s", e)
    _domain_modules = []
