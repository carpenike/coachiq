"""
Startup Performance Monitoring Middleware

Phase 2M: Startup Performance Monitoring
Provides comprehensive monitoring and metrics collection for application startup
performance, including initialization phases, service startup times, and health validation.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


@dataclass
class StartupPhaseMetrics:
    """Metrics for a single startup phase."""

    phase_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None
    sub_phases: Dict[str, 'StartupPhaseMetrics'] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def complete(self, success: bool = True, error_message: Optional[str] = None) -> None:
        """Mark phase as complete and calculate duration."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.success = success
        self.error_message = error_message

        logger.debug(
            f"Startup phase '{self.phase_name}' completed in {self.duration_ms:.2f}ms "
            f"(success: {self.success})"
        )


@dataclass
class StartupMetricsReport:
    """Complete startup metrics report."""

    total_startup_time_ms: float
    phases: Dict[str, StartupPhaseMetrics]
    service_registry_timing: Dict[str, float]
    health_check_results: Dict[str, bool]
    performance_baseline: Dict[str, float]
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    startup_timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_startup_time_ms": self.total_startup_time_ms,
            "phases": {
                name: {
                    "phase_name": phase.phase_name,
                    "duration_ms": phase.duration_ms,
                    "success": phase.success,
                    "error_message": phase.error_message,
                    "sub_phases": {
                        sub_name: {
                            "duration_ms": sub_phase.duration_ms,
                            "success": sub_phase.success,
                            "error_message": sub_phase.error_message
                        }
                        for sub_name, sub_phase in phase.sub_phases.items()
                    },
                    "metadata": phase.metadata
                }
                for name, phase in self.phases.items()
            },
            "service_registry_timing": self.service_registry_timing,
            "health_check_results": self.health_check_results,
            "performance_baseline": self.performance_baseline,
            "warnings": self.warnings,
            "errors": self.errors,
            "startup_timestamp": self.startup_timestamp
        }


class StartupPerformanceMonitor:
    """
    Startup performance monitoring system.

    Tracks initialization phases, collects metrics, and provides
    performance baseline comparisons for startup optimization.
    """

    def __init__(self):
        self.startup_start_time: Optional[float] = None
        self.startup_end_time: Optional[float] = None
        self.current_phase: Optional[str] = None
        self.phases: Dict[str, StartupPhaseMetrics] = {}
        self.service_registry_timing: Dict[str, float] = {}
        self.health_checks: Dict[str, bool] = {}
        self.performance_baselines: Dict[str, float] = {
            # Target baselines from Phase 0-2L optimizations
            "config_loading_ms": 50.0,  # Should be cached now
            "service_registry_init_ms": 120.0,  # Current measured baseline
            "total_startup_ms": 500.0,  # Target for full startup
            "feature_manager_init_ms": 30.0,
            "websocket_setup_ms": 20.0,
        }
        self._phase_stack: List[str] = []

    def start_monitoring(self) -> None:
        """Start startup monitoring."""
        self.startup_start_time = time.time()
        logger.info("Startup performance monitoring initiated")

    def finish_monitoring(self) -> StartupMetricsReport:
        """Complete monitoring and generate report."""
        if self.startup_start_time is None:
            raise RuntimeError("Monitoring not started")

        self.startup_end_time = time.time()
        total_time_ms = (self.startup_end_time - self.startup_start_time) * 1000

        # Generate comprehensive report
        report = StartupMetricsReport(
            total_startup_time_ms=total_time_ms,
            phases=self.phases,
            service_registry_timing=self.service_registry_timing,
            health_check_results=self.health_checks,
            performance_baseline=self.performance_baselines
        )

        # Analyze performance against baselines
        self._analyze_performance(report)

        logger.info(f"Startup monitoring completed: {total_time_ms:.2f}ms total")
        return report

    @asynccontextmanager
    async def monitor_phase(self, phase_name: str, metadata: Optional[Dict[str, Any]] = None):
        """Async context manager for monitoring a startup phase."""
        phase_metrics = StartupPhaseMetrics(
            phase_name=phase_name,
            start_time=time.time(),
            metadata=metadata or {}
        )

        self.phases[phase_name] = phase_metrics
        self.current_phase = phase_name
        self._phase_stack.append(phase_name)

        logger.debug(f"Starting startup phase: {phase_name}")

        try:
            yield phase_metrics
            phase_metrics.complete(success=True)
        except Exception as e:
            error_msg = f"Phase {phase_name} failed: {str(e)}"
            phase_metrics.complete(success=False, error_message=error_msg)
            logger.error(error_msg, exc_info=True)
            raise
        finally:
            self._phase_stack.pop()
            self.current_phase = self._phase_stack[-1] if self._phase_stack else None

    def record_service_timing(self, service_name: str, duration_ms: float) -> None:
        """Record timing for a specific service initialization."""
        self.service_registry_timing[service_name] = duration_ms
        logger.debug(f"Service '{service_name}' initialized in {duration_ms:.2f}ms")

    def record_health_check(self, component: str, healthy: bool) -> None:
        """Record health check result for a component."""
        self.health_checks[component] = healthy
        status = "healthy" if healthy else "unhealthy"
        logger.debug(f"Health check '{component}': {status}")

    def _analyze_performance(self, report: StartupMetricsReport) -> None:
        """Analyze performance against baselines and add warnings/errors."""

        # Check total startup time
        if report.total_startup_time_ms > self.performance_baselines["total_startup_ms"] * 1.5:
            report.errors.append(
                f"Startup time {report.total_startup_time_ms:.1f}ms exceeds baseline "
                f"{self.performance_baselines['total_startup_ms']:.1f}ms by >50%"
            )
        elif report.total_startup_time_ms > self.performance_baselines["total_startup_ms"] * 1.2:
            report.warnings.append(
                f"Startup time {report.total_startup_time_ms:.1f}ms exceeds baseline "
                f"{self.performance_baselines['total_startup_ms']:.1f}ms by >20%"
            )

        # Check individual phase performance
        for phase_name, phase in report.phases.items():
            if not phase.success:
                report.errors.append(f"Phase '{phase_name}' failed: {phase.error_message}")
            elif phase.duration_ms and phase.duration_ms > 1000:  # >1 second is concerning
                report.warnings.append(
                    f"Phase '{phase_name}' took {phase.duration_ms:.1f}ms (>1s threshold)"
                )

        # Check service registry performance
        for service_name, duration in report.service_registry_timing.items():
            if duration > 200:  # >200ms for service init is slow
                report.warnings.append(
                    f"Service '{service_name}' initialization took {duration:.1f}ms"
                )

        # Check health status
        failed_health_checks = [comp for comp, healthy in report.health_check_results.items() if not healthy]
        if failed_health_checks:
            report.errors.extend([f"Health check failed: {comp}" for comp in failed_health_checks])

    def generate_performance_baseline_report(self, current_report: StartupMetricsReport) -> Dict[str, Any]:
        """
        Generate comprehensive performance baseline comparison report.

        Args:
            current_report: Current startup metrics report

        Returns:
            Dictionary containing baseline comparison analysis
        """
        baseline_report = {
            "timestamp": time.time(),
            "baseline_comparison": {},
            "performance_grade": "A",
            "improvement_recommendations": [],
            "regression_alerts": [],
            "trend_analysis": {},
            "optimization_score": 100.0,
        }

        # Compare against baselines
        comparisons = {}

        # Total startup time comparison
        actual_total = current_report.total_startup_time_ms
        baseline_total = self.performance_baselines["total_startup_ms"]
        total_diff_pct = ((actual_total - baseline_total) / baseline_total) * 100

        comparisons["total_startup"] = {
            "baseline_ms": baseline_total,
            "actual_ms": actual_total,
            "difference_ms": actual_total - baseline_total,
            "difference_percent": total_diff_pct,
            "meets_baseline": actual_total <= baseline_total,
            "grade": self._calculate_performance_grade(actual_total, baseline_total)
        }

        # Service registry timing comparison
        registry_total = sum(current_report.service_registry_timing.values())
        baseline_registry = self.performance_baselines["service_registry_init_ms"]
        registry_diff_pct = ((registry_total - baseline_registry) / baseline_registry) * 100

        comparisons["service_registry"] = {
            "baseline_ms": baseline_registry,
            "actual_ms": registry_total,
            "difference_ms": registry_total - baseline_registry,
            "difference_percent": registry_diff_pct,
            "meets_baseline": registry_total <= baseline_registry,
            "grade": self._calculate_performance_grade(registry_total, baseline_registry)
        }

        # Config loading comparison (if phase data available)
        config_phase = current_report.phases.get("config_loading")
        if config_phase and config_phase.duration_ms:
            baseline_config = self.performance_baselines["config_loading_ms"]
            config_diff_pct = ((config_phase.duration_ms - baseline_config) / baseline_config) * 100

            comparisons["config_loading"] = {
                "baseline_ms": baseline_config,
                "actual_ms": config_phase.duration_ms,
                "difference_ms": config_phase.duration_ms - baseline_config,
                "difference_percent": config_diff_pct,
                "meets_baseline": config_phase.duration_ms <= baseline_config,
                "grade": self._calculate_performance_grade(config_phase.duration_ms, baseline_config)
            }

        baseline_report["baseline_comparison"] = comparisons

        # Calculate overall performance grade
        grades = [comp["grade"] for comp in comparisons.values()]
        if grades:
            grade_scores = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
            avg_score = sum(grade_scores.get(grade, 1) for grade in grades) / len(grades)

            if avg_score >= 4.5:
                baseline_report["performance_grade"] = "A"
            elif avg_score >= 3.5:
                baseline_report["performance_grade"] = "B"
            elif avg_score >= 2.5:
                baseline_report["performance_grade"] = "C"
            elif avg_score >= 1.5:
                baseline_report["performance_grade"] = "D"
            else:
                baseline_report["performance_grade"] = "F"

        # Generate improvement recommendations
        recommendations = []

        if actual_total > baseline_total * 1.2:
            recommendations.append({
                "category": "startup_time",
                "priority": "high",
                "title": "Optimize overall startup time",
                "description": f"Startup time {actual_total:.1f}ms exceeds baseline {baseline_total:.1f}ms by {total_diff_pct:.1f}%",
                "suggested_actions": [
                    "Review service initialization order",
                    "Consider lazy loading for non-critical services",
                    "Optimize configuration loading patterns"
                ]
            })

        if registry_total > baseline_registry * 1.5:
            recommendations.append({
                "category": "service_registry",
                "priority": "medium",
                "title": "Optimize ServiceRegistry performance",
                "description": f"ServiceRegistry timing {registry_total:.1f}ms exceeds baseline {baseline_registry:.1f}ms",
                "suggested_actions": [
                    "Review service dependency resolution",
                    "Consider parallel service initialization",
                    "Optimize service factory functions"
                ]
            })

        # Identify slow services for optimization
        slow_services = [
            (name, timing) for name, timing in current_report.service_registry_timing.items()
            if timing > 200  # >200ms threshold
        ]

        if slow_services:
            slow_services.sort(key=lambda x: x[1], reverse=True)
            recommendations.append({
                "category": "slow_services",
                "priority": "medium",
                "title": "Optimize slow service initialization",
                "description": f"Found {len(slow_services)} services with >200ms initialization time",
                "suggested_actions": [
                    f"Optimize {slow_services[0][0]} ({slow_services[0][1]:.1f}ms)",
                    "Review service factory implementations",
                    "Consider caching expensive initialization operations"
                ],
                "affected_services": slow_services[:5]
            })

        baseline_report["improvement_recommendations"] = recommendations

        # Check for performance regressions
        regressions = []

        for component, comparison in comparisons.items():
            if comparison["difference_percent"] > 20:  # >20% regression
                regressions.append({
                    "component": component,
                    "regression_percent": comparison["difference_percent"],
                    "severity": "high" if comparison["difference_percent"] > 50 else "medium",
                    "description": f"{component} performance degraded by {comparison['difference_percent']:.1f}%"
                })

        baseline_report["regression_alerts"] = regressions

        # Calculate optimization score
        score = 100.0

        # Deduct points for baseline misses
        for comparison in comparisons.values():
            if not comparison["meets_baseline"]:
                penalty = min(30, abs(comparison["difference_percent"]))
                score -= penalty

        # Deduct points for errors and warnings
        score -= len(current_report.errors) * 15
        score -= len(current_report.warnings) * 5

        baseline_report["optimization_score"] = max(0, score)

        return baseline_report

    def _calculate_performance_grade(self, actual: float, baseline: float) -> str:
        """Calculate performance grade for a metric."""
        if actual <= baseline:
            return "A"
        elif actual <= baseline * 1.2:
            return "B"
        elif actual <= baseline * 1.5:
            return "C"
        elif actual <= baseline * 2.0:
            return "D"
        else:
            return "F"


# Global monitor instance
_startup_monitor: Optional[StartupPerformanceMonitor] = None


def get_startup_monitor() -> StartupPerformanceMonitor:
    """Get the global startup monitor instance."""
    global _startup_monitor
    if _startup_monitor is None:
        _startup_monitor = StartupPerformanceMonitor()
    return _startup_monitor


class StartupMonitoringMiddleware(BaseHTTPMiddleware):
    """
    HTTP middleware that provides startup performance data via API endpoints.

    This middleware adds startup performance metrics to request context
    and provides endpoints for retrieving startup analysis.
    """

    def __init__(self, app: FastAPI, monitor: Optional[StartupPerformanceMonitor] = None):
        super().__init__(app)
        self.monitor = monitor or get_startup_monitor()
        self._startup_report: Optional[StartupMetricsReport] = None

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and add startup metrics context."""

        # Add startup metrics to request state for API access
        request.state.startup_monitor = self.monitor
        request.state.startup_report = self._startup_report

        # Process request normally
        response = await call_next(request)

        # Add startup performance headers for debugging
        if self._startup_report:
            response.headers["X-Startup-Time"] = f"{self._startup_report.total_startup_time_ms:.1f}ms"
            if self._startup_report.warnings:
                response.headers["X-Startup-Warnings"] = str(len(self._startup_report.warnings))
            if self._startup_report.errors:
                response.headers["X-Startup-Errors"] = str(len(self._startup_report.errors))

        return response

    def set_startup_report(self, report: StartupMetricsReport) -> None:
        """Set the startup report after monitoring completes."""
        self._startup_report = report
        logger.info(f"Startup report set: {report.total_startup_time_ms:.1f}ms total")


# Utility functions for easy integration

def start_startup_monitoring() -> StartupPerformanceMonitor:
    """Start startup monitoring and return monitor instance."""
    monitor = get_startup_monitor()
    monitor.start_monitoring()
    return monitor


async def monitor_startup_phase(phase_name: str, metadata: Optional[Dict[str, Any]] = None):
    """Convenience function for monitoring a startup phase."""
    monitor = get_startup_monitor()
    return monitor.monitor_phase(phase_name, metadata)


def record_service_startup_time(service_name: str, start_time: float) -> None:
    """Record service startup timing."""
    duration_ms = (time.time() - start_time) * 1000
    monitor = get_startup_monitor()
    monitor.record_service_timing(service_name, duration_ms)


def record_component_health(component: str, healthy: bool) -> None:
    """Record component health check result."""
    monitor = get_startup_monitor()
    monitor.record_health_check(component, healthy)


def complete_startup_monitoring() -> StartupMetricsReport:
    """Complete startup monitoring and return report."""
    monitor = get_startup_monitor()
    return monitor.finish_monitoring()
