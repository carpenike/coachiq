"""
Performance Analytics Feature

Feature integration for the performance analytics system following the
established feature management patterns.
"""

import asyncio
import logging
import time
import uuid
from typing import Any

from backend.integrations.analytics.benchmark import BenchmarkingEngine
from backend.integrations.analytics.config import PerformanceAnalyticsSettings
from backend.integrations.analytics.models import (
    MetricType,
    PerformanceMetric,
    PerformanceReport,
    PerformanceStatus,
    ResourceType,
)
from backend.integrations.analytics.optimizer import OptimizationEngine
from backend.integrations.analytics.telemetry import TelemetryCollector
from backend.integrations.analytics.trend_analyzer import TrendAnalyzer
from backend.services.feature_base import Feature
from backend.services.feature_models import SafetyClassification

logger = logging.getLogger(__name__)


class PerformanceAnalyticsFeature(Feature):
    """
    Performance analytics feature providing comprehensive performance monitoring
    and optimization capabilities across all RV protocols and systems.

    Integrates telemetry collection, benchmarking, trend analysis, and automated
    optimization recommendations following established feature management patterns.
    """

    def __init__(
        self,
        name: str = "performance_analytics",
        enabled: bool = False,
        core: bool = False,
        config: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        friendly_name: str | None = None,
        safety_classification: SafetyClassification | None = None,
        log_state_transitions: bool = True,
    ):
        """Initialize the performance analytics feature."""
        super().__init__(
            name=name,
            enabled=enabled,
            core=core,
            config=config,
            dependencies=dependencies,
            friendly_name=friendly_name or "Performance Analytics",
            safety_classification=safety_classification,
            log_state_transitions=log_state_transitions,
        )

        # Get settings internally
        from backend.core.config import get_settings

        settings = get_settings()

        # Store settings reference
        self.settings = settings

        # Get analytics-specific settings
        self.analytics_settings = getattr(
            settings, "performance_analytics", PerformanceAnalyticsSettings()
        )

        # Initialize components
        self.telemetry_collector: TelemetryCollector | None = None
        self.benchmarking_engine: BenchmarkingEngine | None = None
        self.trend_analyzer: TrendAnalyzer | None = None
        self.optimization_engine: OptimizationEngine | None = None

        # Performance data
        self._current_performance_status = PerformanceStatus.GOOD
        self._last_report_id: str | None = None

        # Integration hooks
        self._integration_callbacks: dict[str, Any] = {}

        # Statistics
        self._stats = {
            "startup_time": 0.0,
            "metrics_collected": 0,
            "recommendations_generated": 0,
            "reports_generated": 0,
            "performance_alerts": 0,
        }

        # Background tasks
        self._background_tasks: list[asyncio.Task] = []

    async def startup(self) -> None:
        """Initialize performance analytics components."""
        if not self.analytics_settings.enabled:
            logger.info("Performance analytics feature disabled")
            return

        try:
            start_time = time.perf_counter()

            # Initialize telemetry collector
            logger.info("Initializing telemetry collector")
            self.telemetry_collector = TelemetryCollector(self.analytics_settings)
            await self.telemetry_collector.startup()

            # Initialize benchmarking engine
            logger.info("Initializing benchmarking engine")
            self.benchmarking_engine = BenchmarkingEngine(self.analytics_settings)
            await self.benchmarking_engine.startup()

            # Initialize trend analyzer
            logger.info("Initializing trend analyzer")
            self.trend_analyzer = TrendAnalyzer(self.analytics_settings)
            await self.trend_analyzer.startup()

            # Initialize optimization engine
            logger.info("Initializing optimization engine")
            self.optimization_engine = OptimizationEngine(self.analytics_settings)
            await self.optimization_engine.startup()

            # Start background tasks
            await self._start_background_tasks()

            # Set up integration hooks
            await self._setup_integration_hooks()

            startup_time = time.perf_counter() - start_time
            self._stats["startup_time"] = startup_time

            logger.info(f"Performance analytics feature started successfully ({startup_time:.2f}s)")

        except Exception as e:
            logger.error(f"Failed to start performance analytics feature: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown performance analytics components."""
        try:
            # Cancel background tasks
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()

            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)

            self._background_tasks.clear()

            # Shutdown components
            if self.telemetry_collector:
                await self.telemetry_collector.shutdown()
                self.telemetry_collector = None

            if self.benchmarking_engine:
                await self.benchmarking_engine.shutdown()
                self.benchmarking_engine = None

            if self.trend_analyzer:
                await self.trend_analyzer.shutdown()
                self.trend_analyzer = None

            if self.optimization_engine:
                await self.optimization_engine.shutdown()
                self.optimization_engine = None

            logger.info("Performance analytics feature shutdown complete")

        except Exception as e:
            logger.error(f"Error during performance analytics shutdown: {e}")

    def is_healthy(self) -> bool:
        """Check if the performance analytics feature is healthy."""
        if not self.analytics_settings.enabled:
            return True

        return (
            self.telemetry_collector is not None
            and self.benchmarking_engine is not None
            and self.trend_analyzer is not None
            and self.optimization_engine is not None
        )

    @property
    def health(self) -> str:
        """Get the health status of the feature as a string."""
        if not self.analytics_settings.enabled:
            return "disabled"

        if self.is_healthy():
            return "healthy"
        return "unhealthy"

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive status of the performance analytics feature."""
        status = {
            "enabled": self.analytics_settings.enabled,
            "healthy": self.is_healthy(),
            "current_performance_status": self._current_performance_status.value,
            "components": {
                "telemetry_collector": self.telemetry_collector is not None,
                "benchmarking_engine": self.benchmarking_engine is not None,
                "trend_analyzer": self.trend_analyzer is not None,
                "optimization_engine": self.optimization_engine is not None,
            },
            "configuration": {
                "telemetry_collection": self.analytics_settings.enable_telemetry_collection,
                "benchmarking": self.analytics_settings.enable_benchmarking,
                "trend_analysis": self.analytics_settings.enable_trend_analysis,
                "optimization_recommendations": self.analytics_settings.enable_optimization_recommendations,
            },
            "statistics": self._stats.copy(),
        }

        # Add component-specific status
        if self.telemetry_collector:
            status["telemetry_statistics"] = self.telemetry_collector.get_collection_statistics()

        if self.benchmarking_engine:
            status["benchmark_statistics"] = self.benchmarking_engine.get_benchmark_statistics()

        if self.trend_analyzer:
            status["trend_statistics"] = self.trend_analyzer.get_trend_statistics()

        if self.optimization_engine:
            status["optimization_statistics"] = (
                self.optimization_engine.get_optimization_statistics()
            )

        return status

    # Public API methods for integration with other features

    def record_protocol_message(
        self,
        protocol: str,
        processing_time_ms: float,
        message_size: int = 0,
        interface: str | None = None,
    ) -> None:
        """
        Record protocol message performance for telemetry.

        Args:
            protocol: Protocol name (rvc, j1939, firefly, spartan_k2)
            processing_time_ms: Time taken to process message
            message_size: Message size in bytes
            interface: CAN interface name
        """
        if not self.telemetry_collector:
            return

        try:
            self.telemetry_collector.record_protocol_message(
                protocol, processing_time_ms, message_size, interface
            )
            self._stats["metrics_collected"] += 1

        except Exception as e:
            logger.error(f"Error recording protocol message for {protocol}: {e}")

    def record_api_request(
        self, endpoint: str, response_time_ms: float, status_code: int = 200
    ) -> None:
        """
        Record API request performance.

        Args:
            endpoint: API endpoint
            response_time_ms: Response time in milliseconds
            status_code: HTTP status code
        """
        if not self.telemetry_collector:
            return

        try:
            self.telemetry_collector.record_api_request(endpoint, response_time_ms, status_code)
            self._stats["metrics_collected"] += 1

        except Exception as e:
            logger.error(f"Error recording API request for {endpoint}: {e}")

    def record_websocket_latency(self, latency_ms: float, connection_id: str | None = None) -> None:
        """
        Record WebSocket latency.

        Args:
            latency_ms: WebSocket message latency
            connection_id: Connection identifier
        """
        if not self.telemetry_collector:
            return

        try:
            self.telemetry_collector.record_websocket_latency(latency_ms, connection_id)
            self._stats["metrics_collected"] += 1

        except Exception as e:
            logger.error(f"Error recording WebSocket latency: {e}")

    def record_can_interface_load(
        self, interface: str, load_percent: float, message_rate: float
    ) -> None:
        """
        Record CAN interface performance.

        Args:
            interface: CAN interface name
            load_percent: Bus load percentage
            message_rate: Messages per second
        """
        if not self.telemetry_collector:
            return

        try:
            self.telemetry_collector.record_can_interface_load(
                interface, load_percent, message_rate
            )
            self._stats["metrics_collected"] += 1

        except Exception as e:
            logger.error(f"Error recording CAN interface load for {interface}: {e}")

    def get_current_metrics(
        self, metric_type: str | None = None, time_window_seconds: float = 60.0
    ) -> list[dict[str, Any]]:
        """
        Get current performance metrics.

        Args:
            metric_type: Specific metric type to retrieve
            time_window_seconds: Time window for metrics

        Returns:
            List of performance metrics
        """
        if not self.telemetry_collector:
            return []

        try:
            # Convert string to MetricType enum if provided
            metric_type_enum = None
            if metric_type:
                try:
                    metric_type_enum = MetricType(metric_type.lower())
                except ValueError:
                    logger.warning(f"Unknown metric type: {metric_type}")
                    return []

            metrics = self.telemetry_collector.get_current_metrics(
                metric_type_enum, time_window_seconds
            )
            return [metric.to_dict() for metric in metrics]

        except Exception as e:
            logger.error(f"Error getting current metrics: {e}")
            return []

    def get_resource_utilization(self) -> dict[str, Any]:
        """Get current resource utilization."""
        if not self.telemetry_collector:
            return {}

        try:
            utilization = self.telemetry_collector.get_resource_utilization()
            return {
                resource_type.value: data.to_dict() for resource_type, data in utilization.items()
            }

        except Exception as e:
            logger.error(f"Error getting resource utilization: {e}")
            return {}

    def get_performance_trends(self, metric_type: str | None = None) -> dict[str, Any]:
        """
        Get performance trends.

        Args:
            metric_type: Specific metric type or None for all trends

        Returns:
            Performance trends data
        """
        if not self.trend_analyzer:
            return {}

        try:
            if metric_type:
                try:
                    metric_type_enum = MetricType(metric_type.lower())
                    trend = self.trend_analyzer.get_trend(metric_type_enum)
                    return trend.to_dict() if trend else {}
                except ValueError:
                    logger.warning(f"Unknown metric type: {metric_type}")
                    return {}

            trends = self.trend_analyzer.get_all_trends()
            return {metric_type.value: trend.to_dict() for metric_type, trend in trends.items()}

        except Exception as e:
            logger.error(f"Error getting performance trends: {e}")
            return {}

    def get_baseline_deviations(self, time_window_seconds: float = 3600.0) -> list[dict[str, Any]]:
        """
        Get performance baseline deviations.

        Args:
            time_window_seconds: Time window for deviations

        Returns:
            List of baseline deviation alerts
        """
        if not self.benchmarking_engine:
            return []

        try:
            return self.benchmarking_engine.get_deviation_alerts(None, time_window_seconds)

        except Exception as e:
            logger.error(f"Error getting baseline deviations: {e}")
            return []

    def get_optimization_recommendations(self) -> list[dict[str, Any]]:
        """Get current optimization recommendations."""
        if not self.optimization_engine:
            return []

        try:
            recommendations = self.optimization_engine.generate_recommendations()
            self._stats["recommendations_generated"] += len(recommendations)
            return [rec.to_dict() for rec in recommendations]

        except Exception as e:
            logger.error(f"Error getting optimization recommendations: {e}")
            return []

    def generate_performance_report(self, time_window_seconds: float = 3600.0) -> dict[str, Any]:
        """
        Generate comprehensive performance report.

        Args:
            time_window_seconds: Time window for report data

        Returns:
            Performance report data
        """
        try:
            report_id = str(uuid.uuid4())
            self._last_report_id = report_id

            # Collect current data
            current_metrics = {}
            if self.telemetry_collector:
                metrics = self.telemetry_collector.get_current_metrics(None, time_window_seconds)
                for metric in metrics:
                    current_metrics[metric.metric_type] = metric

            resource_utilization = {}
            if self.telemetry_collector:
                utilization = self.telemetry_collector.get_resource_utilization()
                resource_utilization = utilization

            performance_trends = {}
            if self.trend_analyzer:
                trends = self.trend_analyzer.get_all_trends()
                performance_trends = trends

            baseline_deviations = {}
            if self.benchmarking_engine:
                deviations = self.benchmarking_engine.get_deviation_alerts(
                    None, time_window_seconds
                )
                for deviation in deviations:
                    metric_type = MetricType(deviation["metric_type"])
                    baseline_deviations[metric_type] = (
                        deviation["severity"] != "normal",
                        deviation["deviation_percent"],
                    )

            optimization_recommendations = []
            if self.optimization_engine:
                # Update optimization engine with current data
                self.optimization_engine.update_performance_data(
                    current_metrics, resource_utilization, performance_trends
                )
                recommendations = self.optimization_engine.generate_recommendations()
                optimization_recommendations = recommendations

            # Determine overall status
            overall_status = self._determine_overall_performance_status(
                current_metrics, resource_utilization, baseline_deviations
            )

            # Generate status summary
            status_summary = self._generate_status_summary(
                overall_status, len(optimization_recommendations), len(baseline_deviations)
            )

            # Create performance report
            report = PerformanceReport(
                report_id=report_id,
                time_window_seconds=time_window_seconds,
                overall_status=overall_status,
                status_summary=status_summary,
                current_metrics=current_metrics,
                resource_utilization=resource_utilization,
                performance_trends=performance_trends,
                baseline_deviations=baseline_deviations,
                optimization_recommendations=optimization_recommendations,
            )

            self._stats["reports_generated"] += 1
            self._current_performance_status = overall_status

            return report.to_dict()

        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
            return {"report_id": str(uuid.uuid4()), "error": str(e), "generated_at": time.time()}

    # Internal helper methods

    async def _start_background_tasks(self) -> None:
        """Start background performance monitoring tasks."""
        # Start performance monitoring task
        if self.analytics_settings.enable_real_time_processing:
            monitoring_task = asyncio.create_task(self._performance_monitoring_loop())
            self._background_tasks.append(monitoring_task)

        # Start WebSocket update task
        if self.analytics_settings.enable_websocket_updates:
            websocket_task = asyncio.create_task(self._websocket_update_loop())
            self._background_tasks.append(websocket_task)

    async def _setup_integration_hooks(self) -> None:
        """Set up integration hooks with other features."""
        try:
            # This would typically register callbacks with protocol features
            # to automatically collect performance metrics
            logger.debug("Performance analytics integration hooks set up")

        except Exception as e:
            logger.warning(f"Could not set up all integration hooks: {e}")

    def _determine_overall_performance_status(
        self,
        current_metrics: dict[MetricType, PerformanceMetric],
        resource_utilization: dict[ResourceType, Any],
        baseline_deviations: dict[MetricType, tuple[bool, float]],
    ) -> PerformanceStatus:
        """Determine overall performance status."""
        # Check for critical resource utilization
        for resource_data in resource_utilization.values():
            if (
                hasattr(resource_data, "get_status")
                and resource_data.get_status() == PerformanceStatus.CRITICAL
            ):
                return PerformanceStatus.CRITICAL

        # Check for critical baseline deviations
        critical_deviations = sum(
            1 for is_dev, percent in baseline_deviations.values() if is_dev and percent > 50
        )
        if critical_deviations > 2:
            return PerformanceStatus.CRITICAL

        # Check for degraded performance
        degraded_resources = sum(
            1
            for resource_data in resource_utilization.values()
            if hasattr(resource_data, "get_status")
            and resource_data.get_status() == PerformanceStatus.DEGRADED
        )
        if degraded_resources > 1:
            return PerformanceStatus.DEGRADED

        # Check for acceptable performance
        warning_deviations = sum(
            1 for is_dev, percent in baseline_deviations.values() if is_dev and percent > 20
        )
        if warning_deviations > 1:
            return PerformanceStatus.ACCEPTABLE

        # Check for good performance
        non_optimal_metrics = sum(
            1 for metric in current_metrics.values() if not metric.is_optimal()
        )
        if non_optimal_metrics > 3:
            return PerformanceStatus.GOOD

        return PerformanceStatus.EXCELLENT

    def _generate_status_summary(
        self, status: PerformanceStatus, recommendation_count: int, deviation_count: int
    ) -> str:
        """Generate human-readable status summary."""
        if status == PerformanceStatus.EXCELLENT:
            return "System performance is excellent with all metrics within optimal ranges."
        if status == PerformanceStatus.GOOD:
            return f"System performance is good with {recommendation_count} optimization opportunities identified."
        if status == PerformanceStatus.ACCEPTABLE:
            return f"System performance is acceptable with {deviation_count} baseline deviations detected."
        if status == PerformanceStatus.DEGRADED:
            return (
                f"System performance is degraded. {recommendation_count} optimizations recommended."
            )
        # CRITICAL
        return "Critical performance issues detected. Immediate attention required."

    # Background monitoring tasks

    async def _performance_monitoring_loop(self) -> None:
        """Background task for continuous performance monitoring."""
        while True:
            try:
                # Collect and analyze current performance data
                if self.telemetry_collector and self.benchmarking_engine:
                    # Get current metrics for baseline analysis
                    current_metrics = self.telemetry_collector.get_current_metrics(
                        None, self.analytics_settings.telemetry_collection_interval_seconds
                    )

                    # Record metrics for baseline establishment
                    for metric in current_metrics:
                        self.benchmarking_engine.record_metric_for_baseline(metric)

                        # Record for trend analysis
                        if self.trend_analyzer:
                            self.trend_analyzer.record_metric_for_trend_analysis(metric)

                        # Check for deviations
                        (
                            is_deviated,
                            deviation_percent,
                            severity,
                        ) = self.benchmarking_engine.check_deviation(metric)
                        if is_deviated and severity in ["warning", "critical"]:
                            self._stats["performance_alerts"] += 1

                await asyncio.sleep(self.analytics_settings.telemetry_collection_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in performance monitoring loop: {e}")
                await asyncio.sleep(10.0)

    async def _websocket_update_loop(self) -> None:
        """Background task for WebSocket performance updates."""
        while True:
            try:
                # This would send performance updates via WebSocket
                # Implementation would depend on WebSocket integration

                await asyncio.sleep(self.analytics_settings.websocket_update_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in WebSocket update loop: {e}")
                await asyncio.sleep(30.0)
