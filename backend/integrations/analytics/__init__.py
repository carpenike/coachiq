"""
Performance Analytics Integration

This module provides comprehensive performance analytics capabilities for the
CoachIQ multi-protocol RV communication platform using Prometheus-style metrics.

Key Features:
- Real-time telemetry collection from all CAN protocols
- Performance baseline establishment and anomaly detection
- Resource utilization monitoring (CPU, memory, network, CAN interfaces)
- Statistical trend analysis with historical tracking
- Automated optimization recommendations

Prometheus Integration:
- Extends existing backend metrics infrastructure
- Uses Counter, Gauge, Histogram metrics with collision avoidance
- Provides protocol-specific metrics for RV-C, J1939, Firefly, Spartan K2
- Real-time performance dashboards and alerting

Industry Best Practices Implemented:
- Lightweight, non-blocking telemetry collection
- Memory-efficient data structures with bounded storage
- Statistical baseline establishment with deviation detection
- Comprehensive resource monitoring with low overhead
- Context-aware anomaly detection and alerting
"""

from backend.integrations.analytics.config import PerformanceAnalyticsSettings
from backend.integrations.analytics.metrics import (
    get_can_interface_utilization,
    get_protocol_errors,
    get_protocol_latency,
    get_protocol_message_rate,
    get_resource_utilization,
    initialize_performance_metrics,
)
from backend.integrations.analytics.models import (
    OptimizationLevel,
    OptimizationRecommendation,
    PerformanceAlert,
    PerformanceBaseline,
    ProtocolType,
    TrendAnalysis,
)
from backend.integrations.analytics.optimizer import OptimizationEngine
from backend.integrations.analytics.telemetry import TelemetryCollector
from backend.integrations.analytics.trend_analyzer import TrendAnalyzer

__all__ = [
    "OptimizationEngine",
    "OptimizationLevel",
    "OptimizationRecommendation",
    "PerformanceAlert",
    "PerformanceAnalyticsSettings",
    "PerformanceBaseline",
    "ProtocolType",
    "TelemetryCollector",
    "TrendAnalysis",
    "TrendAnalyzer",
    "get_can_interface_utilization",
    "get_protocol_errors",
    "get_protocol_latency",
    "get_protocol_message_rate",
    "get_resource_utilization",
    "initialize_performance_metrics",
]
