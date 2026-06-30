"""Root-owned service lifecycle status values."""

from enum import Enum


class ServiceStatus(Enum):
    """Service lifecycle status."""

    PENDING = "PENDING"
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
