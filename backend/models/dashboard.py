"""
Dashboard Models

Pydantic models for aggregated dashboard data and analytics endpoints.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

HomeSectionId = Literal["alerts", "scenes", "power", "zones"]


class HomePreferences(BaseModel):
    """User-specific Home dashboard customization."""

    model_config = ConfigDict(populate_by_name=True)

    favorite_entity_ids: list[str] = Field(
        default_factory=list,
        alias="favoriteEntityIds",
        description="Entity IDs shown first on Home",
    )
    section_order: list[HomeSectionId] = Field(
        default_factory=lambda: ["alerts", "scenes", "power", "zones"],
        alias="sectionOrder",
        description="Home sections in display order",
    )
    hidden_sections: list[HomeSectionId] = Field(
        default_factory=list,
        alias="hiddenSections",
        description="Home sections hidden by the user",
    )


class DashboardPreferencesUpdate(BaseModel):
    """Complete synchronized preference payload for the current user."""

    home: HomePreferences = Field(description="Home dashboard customization")


class DashboardPreferencesResponse(BaseModel):
    """Synchronized preferences for the current authenticated user."""

    home: HomePreferences | None = Field(
        default=None,
        description="Saved Home customization, or null before the first synchronized update",
    )
    updated_at: datetime = Field(description="Last dashboard configuration update time")


class EntitySummary(BaseModel):
    """Summary statistics for entities."""

    total_entities: int = Field(description="Total number of entities")
    online_entities: int = Field(description="Number of online entities")
    active_entities: int = Field(description="Number of active entities")
    device_type_counts: dict[str, int] = Field(description="Count by device type")
    area_counts: dict[str, int] = Field(description="Count by area")
    health_score: float = Field(description="Overall system health score (0-100)")


class SystemMetrics(BaseModel):
    """System performance metrics."""

    uptime_seconds: int = Field(description="System uptime in seconds")
    message_rate: float = Field(description="CAN messages per second")
    error_rate: float = Field(description="Error rate percentage")
    memory_usage_mb: float = Field(description="Memory usage in MB")
    cpu_usage_percent: float = Field(description="CPU usage percentage")
    websocket_connections: int = Field(description="Active WebSocket connections")


class CANBusSummary(BaseModel):
    """CAN bus status summary."""

    interfaces_count: int = Field(description="Number of CAN interfaces")
    total_messages: int = Field(description="Total messages received")
    messages_per_minute: float = Field(description="Messages per minute")
    error_count: int = Field(description="Total error count")
    queue_length: int = Field(description="Current queue length")
    bus_load_percent: float = Field(description="Bus load percentage")


class ActivityEntry(BaseModel):
    """Single activity feed entry."""

    id: str = Field(description="Unique activity ID")
    timestamp: datetime = Field(description="Activity timestamp")
    event_type: str = Field(description="Type of event (entity_change, system_alert, etc.)")
    entity_id: str | None = Field(None, description="Related entity ID")
    title: str = Field(description="Human-readable activity title")
    description: str = Field(description="Activity description")
    severity: str = Field(description="Severity level (info, warning, error)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional event data")


class ActivityFeed(BaseModel):
    """Activity feed with recent events."""

    entries: list[ActivityEntry] = Field(description="Recent activity entries")
    total_count: int = Field(description="Total number of activities available")
    has_more: bool = Field(description="Whether more activities are available")


class DashboardSummary(BaseModel):
    """Aggregated dashboard data."""

    timestamp: datetime = Field(description="Data collection timestamp")
    entities: EntitySummary = Field(description="Entity summary statistics")
    system: SystemMetrics = Field(description="System performance metrics")
    can_bus: CANBusSummary = Field(description="CAN bus status summary")
    activity: ActivityFeed = Field(description="Recent activity feed")
    alerts: list[str] = Field(description="Active system alerts")
    quick_stats: dict[str, Any] = Field(description="Quick stats for dashboard cards")


class BulkControlRequest(BaseModel):
    """Request for bulk entity control operations."""

    entity_ids: list[str] = Field(description="List of entity IDs to control")
    command: str = Field(description="Control command (on, off, toggle, set)")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    ignore_errors: bool = Field(default=False, description="Continue on individual entity errors")


class BulkControlResult(BaseModel):
    """Result of a bulk control operation."""

    entity_id: str = Field(description="Entity ID")
    success: bool = Field(description="Whether the operation succeeded")
    message: str = Field(description="Result message")
    error: str | None = Field(None, description="Error message if failed")


class BulkControlResponse(BaseModel):
    """Response for bulk entity control operations."""

    total_requested: int = Field(description="Total entities requested")
    successful: int = Field(description="Number of successful operations")
    failed: int = Field(description="Number of failed operations")
    results: list[BulkControlResult] = Field(description="Individual operation results")
    summary: str = Field(description="Operation summary message")


class AlertDefinition(BaseModel):
    """System alert definition."""

    id: str = Field(description="Alert ID")
    name: str = Field(description="Alert name")
    description: str = Field(description="Alert description")
    condition: str = Field(description="Alert trigger condition")
    severity: str = Field(description="Alert severity (info, warning, error, critical)")
    enabled: bool = Field(description="Whether alert is enabled")
    threshold: float | None = Field(None, description="Alert threshold value")


class ActiveAlert(BaseModel):
    """Active system alert."""

    alert_id: str = Field(description="Alert definition ID")
    triggered_at: datetime = Field(description="When the alert was triggered")
    current_value: float = Field(description="Current metric value")
    threshold: float = Field(description="Alert threshold")
    message: str = Field(description="Alert message")
    severity: str = Field(description="Alert severity")
    acknowledged: bool = Field(default=False, description="Whether alert is acknowledged")


class SystemAnalytics(BaseModel):
    """System analytics and monitoring data."""

    alerts: list[ActiveAlert] = Field(description="Active system alerts")
    performance_trends: dict[str, list[float]] = Field(description="Performance trend data")
    health_checks: dict[str, bool] = Field(description="Health check results")
    recommendations: list[str] = Field(description="System optimization recommendations")
