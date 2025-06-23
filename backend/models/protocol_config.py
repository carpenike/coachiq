"""
Protocol Configuration Models

Database models for storing protocol enablement and configuration.
This allows runtime protocol management without requiring restarts.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ProtocolConfigModel(BaseModel):
    """
    Protocol configuration stored in database.

    This model represents the runtime configuration for protocols,
    allowing dynamic enable/disable without application restart.
    """

    protocol_name: str = Field(..., description="Protocol identifier (rvc, j1939, firefly)")
    enabled: bool = Field(default=False, description="Whether protocol is enabled")
    config: dict[str, Any] = Field(
        default_factory=dict, description="Protocol-specific configuration"
    )
    priority: int = Field(default=0, description="Startup priority (lower numbers start first)")
    requires_restart: bool = Field(
        default=True, description="Whether changing this protocol requires app restart"
    )
    last_modified: datetime = Field(
        default_factory=datetime.utcnow, description="Last configuration change timestamp"
    )
    modified_by: str | None = Field(None, description="User who last modified configuration")

    # Runtime metadata
    last_health_check: datetime | None = Field(None, description="Last successful health check")
    health_status: str | None = Field(None, description="Current health status")
    error_message: str | None = Field(None, description="Last error message if protocol failed")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "protocol_name": "j1939",
                "enabled": True,
                "config": {
                    "enable_cummins_extensions": True,
                    "enable_allison_extensions": True,
                    "baud_rate": 250000,
                    "filters": ["engine", "transmission"],
                },
                "priority": 10,
                "requires_restart": True,
                "last_modified": "2024-01-20T12:00:00Z",
                "modified_by": "admin",
            }
        }


class ProtocolConfigUpdate(BaseModel):
    """Update model for protocol configuration."""

    enabled: bool | None = None
    config: dict[str, Any] | None = None
    priority: int | None = None
    modified_by: str | None = None


class ProtocolRuntimeStatus(BaseModel):
    """Runtime status information for a protocol."""

    protocol_name: str
    enabled: bool
    config_source: str = Field(..., description="Where config came from (db, env, yaml)")
    service_registered: bool
    service_healthy: bool
    uptime_seconds: float | None = None
    message_count: int | None = None
    error_count: int | None = None
    last_error: str | None = None
    last_activity: datetime | None = None
