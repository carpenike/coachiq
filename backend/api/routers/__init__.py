"""
API routers package.

This package contains the FastAPI routers for different API domains.
Each router is responsible for a specific area of functionality and delegates
business logic to appropriate services.
"""

from backend.api.routers import can, config, docs, logs

__all__ = [
    "can",
    "config",
    "docs",
    "logs",
]
