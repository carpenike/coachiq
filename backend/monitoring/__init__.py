"""
Monitoring module for CoachIQ backend.

Provides comprehensive monitoring capabilities including:
- Health probe metrics and alerting
- Performance monitoring
- System resource tracking
- Safety-critical system monitoring
"""

from .health_probe_metrics import (
    HealthProbeMonitor,
    ProbeMetric,
    ProbeStatistics,
    get_health_monitoring_summary,
    health_probe_monitor,
    record_health_probe,
)

__all__ = [
    "HealthProbeMonitor",
    "ProbeMetric",
    "ProbeStatistics",
    "get_health_monitoring_summary",
    "health_probe_monitor",
    "record_health_probe",
]
