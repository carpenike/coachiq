"""
Predictive Maintenance Service

Implements Gemini's hybrid edge/cloud approach for predictive maintenance with:
- Component health scoring with dynamic thresholds
- Tiered alerting system (Watch, Advise, Alert)
- Trend analysis with EWMA and anomaly detection
- Maintenance lifecycle tracking
- Proactive recommendations based on usage patterns and fleet data
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from backend.core.performance import PerformanceMonitor
from backend.models.predictive_maintenance import (
    ComponentHealthModel,
    MaintenanceHistoryModel,
    MaintenanceRecommendationModel,
    RVHealthOverviewModel,
)
from backend.repositories.predictive_maintenance_repository import PredictiveMaintenanceRepository

logger = logging.getLogger(__name__)


class PredictiveMaintenanceService:
    """
    Service for predictive maintenance analysis and recommendations.

    Implements a sophisticated health scoring system with trend analysis,
    anomaly detection, and proactive maintenance recommendations.
    """

    def __init__(
        self,
        maintenance_repository: PredictiveMaintenanceRepository,
        performance_monitor: PerformanceMonitor,
        database_manager=None,
    ):
        """Initialize the predictive maintenance service.

        Args:
            maintenance_repository: Repository for maintenance data
            performance_monitor: Performance monitoring instance
            database_manager: Optional database manager for backward compatibility
        """
        self._repository = maintenance_repository
        self._monitor = performance_monitor
        self._db_manager = database_manager

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("PredictiveMaintenanceService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        # Monitor key service methods
        self.get_health_overview = self._monitor.monitor_service_method(
            "PredictiveMaintenanceService", "get_health_overview"
        )(self.get_health_overview)

        self.get_component_health = self._monitor.monitor_service_method(
            "PredictiveMaintenanceService", "get_component_health"
        )(self.get_component_health)

        self.get_maintenance_recommendations = self._monitor.monitor_service_method(
            "PredictiveMaintenanceService", "get_maintenance_recommendations"
        )(self.get_maintenance_recommendations)

        self.log_maintenance_activity = self._monitor.monitor_service_method(
            "PredictiveMaintenanceService", "log_maintenance_activity"
        )(self.log_maintenance_activity)

    async def get_health_overview(self) -> dict[str, Any]:
        """Get overall RV health overview with system breakdown."""
        overview = await self._repository.calculate_health_overview()
        return overview.to_dict()

    async def get_component_health(
        self,
        system_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get health status for all components with optional filtering."""
        components = await self._repository.get_components_filtered(system_type, status)

        # Sort by health score (worst first) and then by status priority
        status_priority = {"alert": 0, "advise": 1, "watch": 2, "healthy": 3}
        components.sort(key=lambda c: (status_priority.get(c.status, 4), c.health_score))

        return [component.to_dict() for component in components]

    async def get_component_health_detail(self, component_id: str) -> dict[str, Any] | None:
        """Get detailed health information for a specific component."""
        component = await self._repository.get_component_by_id(component_id)
        return component.to_dict() if component else None

    async def get_maintenance_recommendations(
        self,
        level: str | None = None,
        component_id: str | None = None,
        acknowledged: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Get maintenance recommendations with filtering."""
        recommendations = await self._repository.get_recommendations(
            level=level, component_id=component_id, include_dismissed=False
        )

        # Apply acknowledged filter if specified
        if acknowledged is not None:
            recommendations = [
                r for r in recommendations if (r.acknowledged_at is not None) == acknowledged
            ]

        # Sort by priority (highest first) and then by creation date
        recommendations.sort(key=lambda r: (r.priority, r.created_at))

        return [rec.to_dict() for rec in recommendations]

    async def acknowledge_recommendation(self, recommendation_id: str) -> bool:
        """Acknowledge a maintenance recommendation."""
        success = await self._repository.acknowledge_recommendation(recommendation_id)
        if success:
            logger.info(f"Acknowledged recommendation: {recommendation_id}")
        return success

    async def get_component_trends(
        self,
        component_id: str,
        metric: str | None = None,
        days: int = 30,
    ) -> dict[str, Any] | None:
        """Get trend analysis data for a component."""
        trend_data = await self._repository.generate_trend_data(component_id, metric, days)
        if not trend_data:
            return None

        # Add trend analysis
        trend_points = trend_data.get("trend_points", [])
        if len(trend_points) >= 2:
            start_value = trend_points[0]["value"]
            end_value = trend_points[-1]["value"]
            change_percent = ((end_value - start_value) / start_value) * 100

            if abs(change_percent) < 2:
                trend_analysis = "Stable performance with minimal variation"
            elif change_percent > 2:
                trend_analysis = f"Improving trend: {change_percent:.1f}% increase over {days} days"
            else:
                trend_analysis = (
                    f"Declining trend: {abs(change_percent):.1f}% decrease over {days} days"
                )
        else:
            trend_analysis = "Insufficient data for trend analysis"

        trend_data["trend_analysis"] = trend_analysis
        return trend_data

    async def log_maintenance_activity(self, maintenance_entry: Any) -> str:
        """Log a maintenance activity and update component health."""
        entry_id = f"maint_{uuid.uuid4().hex[:12]}"

        # Get component for name
        component = await self._repository.get_component_by_id(maintenance_entry.component_id)
        component_name = component.component_name if component else maintenance_entry.component_id

        # Create maintenance history entry
        history_entry = MaintenanceHistoryModel(
            entry_id=entry_id,
            component_id=maintenance_entry.component_id,
            component_name=component_name,
            maintenance_type=maintenance_entry.maintenance_type,
            description=maintenance_entry.description,
            performed_at=datetime.now(),
            cost=maintenance_entry.cost,
            performed_by=maintenance_entry.performed_by,
            location=maintenance_entry.location,
            notes=maintenance_entry.notes,
        )

        # Save history entry
        await self._repository.add_maintenance_history(history_entry)

        # Update component health based on maintenance type
        if component:
            updates = {}

            if maintenance_entry.maintenance_type in ["replacement", "rebuild"]:
                # Reset component health for replacements
                updates = {
                    "health_score": 100.0,
                    "status": "healthy",
                    "anomaly_count": 0,
                    "trend_direction": "stable",
                    "usage_hours": 0.0,
                    "usage_cycles": 0,
                }
            elif maintenance_entry.maintenance_type in ["service", "repair"]:
                # Improve health for service/repair
                new_health = min(100.0, component.health_score + 15.0)
                new_anomaly_count = max(0, component.anomaly_count - 2)
                new_status = (
                    "healthy"
                    if new_health > 80
                    else "watch"
                    if new_health > 60
                    else component.status
                )

                updates = {
                    "health_score": new_health,
                    "anomaly_count": new_anomaly_count,
                    "status": new_status,
                }

            # Update last maintenance date
            updates["last_maintenance"] = datetime.now()

            # Set next maintenance due date
            maintenance_intervals = {
                "battery": 180,
                "generator": 365,
                "pump": 365,
                "hvac": 365,
                "slide_out": 365,
            }
            interval = maintenance_intervals.get(component.component_type, 365)
            updates["next_maintenance_due"] = datetime.now() + timedelta(days=interval)

            await self._repository.update_component_health(maintenance_entry.component_id, updates)

        logger.info(
            f"Logged maintenance activity: {entry_id} for component {maintenance_entry.component_id}"
        )
        return entry_id

    async def get_maintenance_history(
        self,
        component_id: str | None = None,
        maintenance_type: str | None = None,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Get maintenance history with filtering."""
        history = await self._repository.get_maintenance_history(
            component_id=component_id, maintenance_type=maintenance_type, days=days
        )

        # Sort by date (most recent first)
        history.sort(key=lambda h: h.performed_at, reverse=True)

        return [entry.to_dict() for entry in history]
