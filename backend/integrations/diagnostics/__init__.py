"""
Advanced Diagnostics Integration

This module provides comprehensive diagnostic capabilities for multi-protocol
RV communication systems, including:

- Cross-protocol diagnostic trouble code (DTC) processing
- Predictive maintenance based on performance patterns
- Fault correlation across multiple systems
- Advanced analytics and trend analysis
- Integration with RV-C, J1939, and OEM-specific protocols

Architecture:
- Builds on existing diagnostic extraction from protocols
- Unified diagnostic data model across all protocols
- Real-time fault correlation and pattern recognition
- Integration with existing feature management system
- Comprehensive configuration via Pydantic settings
"""

from backend.integrations.diagnostics.config import AdvancedDiagnosticsSettings
from backend.integrations.diagnostics.handler import DiagnosticHandler
from backend.integrations.diagnostics.models import (
    DiagnosticTroubleCode,
    FaultCorrelation,
    MaintenancePrediction,
    ServiceRecommendation,
    SystemHealthStatus,
)
from backend.integrations.diagnostics.predictive import PredictiveMaintenanceEngine

__all__ = [
    "AdvancedDiagnosticsSettings",
    "DiagnosticHandler",
    "DiagnosticTroubleCode",
    "FaultCorrelation",
    "MaintenancePrediction",
    "PredictiveMaintenanceEngine",
    "ServiceRecommendation",
    "SystemHealthStatus",
]
