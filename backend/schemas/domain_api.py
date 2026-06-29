"""Shared response schemas for Domain API v1 endpoints."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticsServiceFeatures(BaseModel):
    """Feature flags reported by the diagnostics service-health endpoint."""

    real_time_monitoring: bool = Field(..., description="Real-time diagnostics enabled")
    predictive_alerts: bool = Field(..., description="Predictive diagnostics alerts enabled")
    cross_protocol_analysis: bool = Field(..., description="Cross-protocol analysis enabled")


class DiagnosticsHealthResponse(BaseModel):
    """Service-health response for the diagnostics v2 domain."""

    status: str = Field(..., description="Diagnostics domain health status")
    domain: str = Field(..., description="Domain name")
    version: str = Field(..., description="Domain API version")
    diagnostics_services: DiagnosticsServiceFeatures = Field(
        ..., description="Diagnostics feature availability"
    )
    timestamp: str = Field(..., description="Health timestamp")


class DiagnosticTroubleCodeCollection(BaseModel):
    """Diagnostic trouble-code collection with dynamic item details."""

    dtcs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="DTC detail objects from the diagnostics handler; keys vary by protocol",
    )
    total_count: int = Field(..., description="Total DTC count after filters")
    active_count: int = Field(..., description="Unresolved active DTC count after filters")
    by_severity: dict[str, int] = Field(default_factory=dict, description="Counts by severity")
    by_protocol: dict[str, int] = Field(default_factory=dict, description="Counts by protocol")


DiagnosticHealthTrend = Literal["improving", "stable", "degrading"]


class DiagnosticStatisticsMetrics(BaseModel):
    """Core diagnostic processing metrics."""

    total_dtcs: int = Field(..., description="Total DTCs observed")
    active_dtcs: int = Field(..., description="Currently active DTCs")
    resolved_dtcs: int = Field(..., description="Resolved DTCs")
    processing_rate: float = Field(..., description="Diagnostic processing rate")
    system_health_trend: DiagnosticHealthTrend = Field(..., description="System health trend")


class DiagnosticAccuracySummary(BaseModel):
    """Accuracy summary for diagnostics analysis features."""

    accuracy: float = Field(..., description="Accuracy score")


class DiagnosticStatisticsResponse(BaseModel):
    """Diagnostic statistics response grouped by metrics and model quality."""

    metrics: DiagnosticStatisticsMetrics = Field(..., description="Diagnostic metrics")
    correlation: DiagnosticAccuracySummary = Field(..., description="Correlation accuracy")
    prediction: DiagnosticAccuracySummary = Field(..., description="Prediction accuracy")


class SystemDomainFeatures(BaseModel):
    """Feature flags reported by the system service-health endpoint."""

    system_monitoring: bool = Field(..., description="System monitoring enabled")
    service_management: bool = Field(..., description="Service management enabled")
    configuration_api: bool = Field(..., description="Configuration API enabled")


class SystemHealthResponse(BaseModel):
    """Service-health response for the system v2 domain."""

    status: str = Field(..., description="System domain health status")
    domain: str = Field(..., description="Domain name")
    version: str = Field(..., description="Domain API version")
    features: SystemDomainFeatures = Field(..., description="System feature availability")
    timestamp: str = Field(..., description="Health timestamp")


class HealthServiceMetadata(BaseModel):
    """Service metadata used by system status responses."""

    name: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    environment: str = Field(..., description="Runtime environment")
    hostname: str = Field(..., description="System hostname")
    platform: str = Field(..., description="Operating system platform")


class IETFHealthStatusResponse(BaseModel):
    """IETF health+json response emitted by system status with format=ietf."""

    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(..., description="IETF health status: pass/warn/fail")
    version: str = Field(..., description="Health check format version")
    release_id: str = Field(
        ...,
        validation_alias="releaseId",
        serialization_alias="releaseId",
        description="Application release identifier",
    )
    service_id: str = Field(
        ...,
        validation_alias="serviceId",
        serialization_alias="serviceId",
        description="Service identifier",
    )
    description: str = Field(..., description="Human-readable health description")
    timestamp: str = Field(..., description="Health timestamp")
    service: HealthServiceMetadata = Field(..., description="Service metadata")
    response_time_ms: float = Field(..., description="Response time in milliseconds")
