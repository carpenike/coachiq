"""
Analytics Storage Service (Refactored with Repository Pattern)

Service for managing analytics data storage with performance monitoring.
"""

import logging
from typing import Any, List, Optional

from backend.core.performance import PerformanceMonitor
from backend.integrations.analytics_dashboard.config import AnalyticsDashboardSettings
from backend.models.analytics import (
    PatternAnalysis,
    SystemInsight,
    TrendPoint,
)
from backend.repositories.analytics_repository import AnalyticsRepository

logger = logging.getLogger(__name__)


class AnalyticsStorageService:
    """
    Analytics storage service refactored with repository pattern.

    Provides a service layer for analytics data management with
    performance monitoring and business logic.
    """

    def __init__(
        self,
        analytics_repository: AnalyticsRepository,
        performance_monitor: PerformanceMonitor,
    ) -> None:
        """Initialize storage service with repository.

        Args:
            analytics_repository: Repository for analytics data persistence
            performance_monitor: Performance monitoring instance
        """
        self.settings = AnalyticsDashboardSettings()
        self._repository = analytics_repository
        self._monitor = performance_monitor

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("Analytics storage service initialized with repository pattern")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        # Wrap methods with performance monitoring
        self.record_metric = self._monitor.monitor_service_method(
            "AnalyticsStorageService", "record_metric"
        )(self.record_metric)

        self.get_metrics_trend = self._monitor.monitor_service_method(
            "AnalyticsStorageService", "get_metrics_trend"
        )(self.get_metrics_trend)

        self.store_insight = self._monitor.monitor_service_method(
            "AnalyticsStorageService", "store_insight"
        )(self.store_insight)

        self.get_insights = self._monitor.monitor_service_method(
            "AnalyticsStorageService", "get_insights"
        )(self.get_insights)

        self.store_pattern = self._monitor.monitor_service_method(
            "AnalyticsStorageService", "store_pattern"
        )(self.store_pattern)

        self.get_patterns = self._monitor.monitor_service_method(
            "AnalyticsStorageService", "get_patterns"
        )(self.get_patterns)

        self.cleanup_old_data = self._monitor.monitor_service_method(
            "AnalyticsStorageService", "cleanup_old_data"
        )(self.cleanup_old_data)

        self.get_storage_stats = self._monitor.monitor_service_method(
            "AnalyticsStorageService", "get_storage_stats"
        )(self.get_storage_stats)

    async def record_metric(
        self, metric_name: str, value: float, metadata: dict[str, Any] | None = None
    ) -> bool:
        """
        Record metric using repository.

        Args:
            metric_name: Name of the metric
            value: Metric value
            metadata: Optional metadata dictionary

        Returns:
            True if successful, False otherwise
        """
        return await self._repository.record_metric(metric_name, value, metadata)

    async def get_metrics_trend(self, metric_name: str, hours: int = 24) -> list[TrendPoint]:
        """
        Get metric trend data using repository.

        Args:
            metric_name: Name of the metric
            hours: Number of hours of historical data to retrieve

        Returns:
            List of TrendPoint objects sorted by timestamp
        """
        return await self._repository.get_metrics_trend(metric_name, hours)

    async def store_insight(self, insight: SystemInsight) -> None:
        """
        Store insight using repository.

        Args:
            insight: SystemInsight object to store
        """
        await self._repository.store_insight(insight)

    async def get_insights(
        self,
        categories: list[str] | None = None,
        min_severity: str = "low",
        limit: int = 50,
        max_age_hours: int = 24,
    ) -> list[SystemInsight]:
        """
        Get insights using repository.

        Args:
            categories: Optional list of categories to filter by
            min_severity: Minimum severity level
            limit: Maximum number of insights to return
            max_age_hours: Maximum age in hours

        Returns:
            List of SystemInsight objects sorted by severity and impact
        """
        return await self._repository.get_insights(categories, min_severity, limit, max_age_hours)

    async def store_pattern(self, pattern: PatternAnalysis) -> None:
        """
        Store pattern using repository.

        Args:
            pattern: PatternAnalysis object to store
        """
        await self._repository.store_pattern(pattern)

    async def get_patterns(self, min_confidence: float = 0.5) -> list[PatternAnalysis]:
        """
        Get patterns using repository.

        Args:
            min_confidence: Minimum confidence level

        Returns:
            List of PatternAnalysis objects
        """
        return await self._repository.get_patterns(min_confidence)

    async def cleanup_old_data(self) -> None:
        """Clean up old data using repository."""
        await self._repository.cleanup_old_data()

    async def get_storage_stats(self) -> dict[str, Any]:
        """Get comprehensive storage statistics from repository."""
        stats = await self._repository.get_storage_stats()
        # Add service-level info
        stats.update(
            {
                "persistence_enabled": True,
                "storage_type": "repository_based",
            }
        )
        return stats

    def close(self) -> None:
        """Clean up resources when service is shut down."""
        # Service cleanup if needed
        logger.debug("Analytics storage service closed")
