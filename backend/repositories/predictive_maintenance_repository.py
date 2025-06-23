"""Predictive Maintenance Repository

Handles data access for predictive maintenance including:
- Component health tracking
- Maintenance history
- Recommendations management
- Trend data storage
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.models.predictive_maintenance import (
    ComponentHealthModel,
    MaintenanceHistoryModel,
    MaintenanceRecommendationModel,
    RVHealthOverviewModel,
)
from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class PredictiveMaintenanceRepository(MonitoredRepository):
    """Repository for predictive maintenance data management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage (would be database tables in production)
        self._component_health: dict[str, ComponentHealthModel] = {}
        self._maintenance_history: dict[str, MaintenanceHistoryModel] = {}
        self._recommendations: dict[str, MaintenanceRecommendationModel] = {}

        # Initialize sample data
        self._initialize_sample_data()

    def _initialize_sample_data(self) -> None:
        """Initialize with sample component data for demonstration."""
        sample_components = [
            {
                "component_id": "battery_coach_main",
                "component_type": "battery",
                "component_name": "Coach Battery Bank",
                "health_score": 78.0,
                "status": "advise",
                "remaining_useful_life_days": 120,
                "usage_hours": 2340.5,
                "anomaly_count": 3,
                "trend_direction": "degrading",
                "last_maintenance": datetime.now() - timedelta(days=180),
                "next_maintenance_due": datetime.now() + timedelta(days=30),
            },
            {
                "component_id": "generator_main",
                "component_type": "generator",
                "component_name": "Main Generator",
                "health_score": 92.0,
                "status": "healthy",
                "remaining_useful_life_days": 800,
                "usage_hours": 156.2,
                "anomaly_count": 0,
                "trend_direction": "stable",
                "last_maintenance": datetime.now() - timedelta(days=90),
                "next_maintenance_due": datetime.now() + timedelta(days=270),
            },
            {
                "component_id": "slides_living_room",
                "component_type": "slide_out",
                "component_name": "Living Room Slide",
                "health_score": 85.0,
                "status": "watch",
                "remaining_useful_life_days": 1200,
                "usage_cycles": 234,
                "anomaly_count": 1,
                "trend_direction": "stable",
                "last_maintenance": datetime.now() - timedelta(days=365),
                "next_maintenance_due": datetime.now() + timedelta(days=90),
            },
            {
                "component_id": "water_pump_fresh",
                "component_type": "pump",
                "component_name": "Fresh Water Pump",
                "health_score": 65.0,
                "status": "advise",
                "remaining_useful_life_days": 45,
                "usage_hours": 891.3,
                "anomaly_count": 5,
                "trend_direction": "degrading",
                "last_maintenance": datetime.now() - timedelta(days=730),
                "next_maintenance_due": datetime.now() + timedelta(days=15),
            },
            {
                "component_id": "hvac_main",
                "component_type": "hvac",
                "component_name": "Main Air Conditioner",
                "health_score": 88.0,
                "status": "healthy",
                "remaining_useful_life_days": 1500,
                "usage_hours": 445.7,
                "anomaly_count": 0,
                "trend_direction": "stable",
                "last_maintenance": datetime.now() - timedelta(days=120),
                "next_maintenance_due": datetime.now() + timedelta(days=240),
            },
        ]

        for component_data in sample_components:
            component = ComponentHealthModel(**component_data)
            self._component_health[component.component_id] = component

        # Sample recommendations
        sample_recommendations = [
            {
                "recommendation_id": "rec_battery_test",
                "component_id": "battery_coach_main",
                "component_name": "Coach Battery Bank",
                "level": "advise",
                "title": "Battery Performance Declining",
                "message": "Your coach battery health is at 78%. It consistently drops below optimal voltage under load. Consider having it tested before your next long trip.",
                "priority": 2,
                "estimated_cost": 350.0,
                "estimated_time_hours": 1.0,
                "urgency_days": 30,
                "created_at": datetime.now() - timedelta(days=5),
                "maintenance_type": "inspection",
            },
            {
                "recommendation_id": "rec_pump_replacement",
                "component_id": "water_pump_fresh",
                "component_name": "Fresh Water Pump",
                "level": "alert",
                "title": "Water Pump Requires Attention",
                "message": "Fresh water pump showing significant performance degradation. Power draw has increased 40% and pressure drops detected. Replacement recommended within 2 weeks.",
                "priority": 1,
                "estimated_cost": 180.0,
                "estimated_time_hours": 2.5,
                "urgency_days": 14,
                "created_at": datetime.now() - timedelta(days=2),
                "maintenance_type": "replacement",
            },
            {
                "recommendation_id": "rec_slide_lubrication",
                "component_id": "slides_living_room",
                "component_name": "Living Room Slide",
                "level": "watch",
                "title": "Slide Maintenance Due",
                "message": "Living room slide is due for annual lubrication and inspection. Operation is normal but preventive maintenance is recommended.",
                "priority": 3,
                "estimated_cost": 75.0,
                "estimated_time_hours": 0.5,
                "urgency_days": 90,
                "created_at": datetime.now() - timedelta(days=1),
                "maintenance_type": "service",
            },
        ]

        for rec_data in sample_recommendations:
            recommendation = MaintenanceRecommendationModel(**rec_data)
            self._recommendations[recommendation.recommendation_id] = recommendation

    @MonitoredRepository._monitored_operation("get_all_components")
    async def get_all_components(self) -> list[ComponentHealthModel]:
        """Get all component health records.

        Returns:
            List of component health models
        """
        return list(self._component_health.values())

    @MonitoredRepository._monitored_operation("get_components_filtered")
    async def get_components_filtered(
        self, system_type: str | None = None, status: str | None = None
    ) -> list[ComponentHealthModel]:
        """Get filtered component health records.

        Args:
            system_type: Filter by component type
            status: Filter by health status

        Returns:
            Filtered list of component health models
        """
        components = list(self._component_health.values())

        if system_type:
            components = [c for c in components if c.component_type == system_type]
        if status:
            components = [c for c in components if c.status == status]

        return components

    @MonitoredRepository._monitored_operation("get_component_by_id")
    async def get_component_by_id(self, component_id: str) -> ComponentHealthModel | None:
        """Get a specific component by ID.

        Args:
            component_id: Component identifier

        Returns:
            Component health model or None
        """
        return self._component_health.get(component_id)

    @MonitoredRepository._monitored_operation("update_component_health")
    async def update_component_health(self, component_id: str, updates: dict[str, Any]) -> bool:
        """Update component health data.

        Args:
            component_id: Component to update
            updates: Dictionary of updates

        Returns:
            True if successful
        """
        component = self._component_health.get(component_id)
        if not component:
            return False

        # Update fields
        for key, value in updates.items():
            if hasattr(component, key):
                setattr(component, key, value)

        return True

    @MonitoredRepository._monitored_operation("get_recommendations")
    async def get_recommendations(
        self,
        level: str | None = None,
        component_id: str | None = None,
        include_dismissed: bool = False,
    ) -> list[MaintenanceRecommendationModel]:
        """Get maintenance recommendations.

        Args:
            level: Filter by recommendation level
            component_id: Filter by component
            include_dismissed: Include dismissed recommendations

        Returns:
            List of recommendations
        """
        recommendations = list(self._recommendations.values())

        if level:
            recommendations = [r for r in recommendations if r.level == level]
        if component_id:
            recommendations = [r for r in recommendations if r.component_id == component_id]
        if not include_dismissed:
            recommendations = [r for r in recommendations if not r.dismissed]

        return recommendations

    @MonitoredRepository._monitored_operation("acknowledge_recommendation")
    async def acknowledge_recommendation(self, recommendation_id: str) -> bool:
        """Mark a recommendation as acknowledged.

        Args:
            recommendation_id: Recommendation to acknowledge

        Returns:
            True if successful
        """
        recommendation = self._recommendations.get(recommendation_id)
        if not recommendation:
            return False

        recommendation.acknowledged_at = datetime.now()
        return True

    @MonitoredRepository._monitored_operation("add_maintenance_history")
    async def add_maintenance_history(self, entry: MaintenanceHistoryModel) -> str:
        """Add a maintenance history entry.

        Args:
            entry: Maintenance history entry

        Returns:
            Entry ID
        """
        self._maintenance_history[entry.entry_id] = entry
        return entry.entry_id

    @MonitoredRepository._monitored_operation("get_maintenance_history")
    async def get_maintenance_history(
        self,
        component_id: str | None = None,
        maintenance_type: str | None = None,
        days: int = 90,
    ) -> list[MaintenanceHistoryModel]:
        """Get maintenance history.

        Args:
            component_id: Filter by component
            maintenance_type: Filter by type
            days: History lookback period

        Returns:
            List of maintenance history entries
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        history = [
            entry
            for entry in self._maintenance_history.values()
            if entry.performed_at >= cutoff_date
        ]

        if component_id:
            history = [h for h in history if h.component_id == component_id]
        if maintenance_type:
            history = [h for h in history if h.maintenance_type == maintenance_type]

        return history

    @MonitoredRepository._monitored_operation("generate_trend_data")
    async def generate_trend_data(
        self, component_id: str, metric: str | None = None, days: int = 30
    ) -> dict[str, Any] | None:
        """Generate trend data for a component.

        Args:
            component_id: Component to analyze
            metric: Specific metric to track
            days: Number of days for trend

        Returns:
            Trend analysis data or None
        """
        component = self._component_health.get(component_id)
        if not component:
            return None

        # Generate sample trend data for demonstration
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        trend_points = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            if component.component_type == "battery":
                # Simulate declining battery voltage trend
                base_voltage = 12.6
                decline_factor = i * 0.01
                noise = (i % 7) * 0.05
                voltage = base_voltage - decline_factor + noise
                trend_points.append(
                    {"timestamp": date.isoformat(), "value": round(voltage, 2), "metric": "voltage"}
                )
            else:
                # Generic health score trend
                base_score = component.health_score
                variation = (i % 10) * 2 - 5
                score = max(0, min(100, base_score + variation))
                trend_points.append(
                    {
                        "timestamp": date.isoformat(),
                        "value": round(score, 1),
                        "metric": "health_score",
                    }
                )

        # Define normal ranges
        normal_ranges = {
            "battery": {"min": 12.2, "max": 12.8, "metric": "voltage"},
            "generator": {"min": 80.0, "max": 100.0, "metric": "health_score"},
            "pump": {"min": 70.0, "max": 100.0, "metric": "health_score"},
            "hvac": {"min": 85.0, "max": 100.0, "metric": "health_score"},
            "slide_out": {"min": 80.0, "max": 100.0, "metric": "health_score"},
        }

        normal_range = normal_ranges.get(
            component.component_type, {"min": 0, "max": 100, "metric": "health_score"}
        )

        # Detect anomalies
        anomalies = []
        for point in trend_points:
            if point["value"] < normal_range["min"] or point["value"] > normal_range["max"]:
                anomalies.append(
                    {
                        "timestamp": point["timestamp"],
                        "value": point["value"],
                        "severity": "high"
                        if point["value"] < normal_range["min"] * 0.9
                        else "medium",
                        "description": f"{normal_range['metric']} outside normal range",
                    }
                )

        return {
            "component_id": component_id,
            "metric_name": normal_range["metric"],
            "trend_points": trend_points,
            "normal_range": normal_range,
            "anomalies": anomalies,
            "prediction_confidence": 0.85,
        }

    @MonitoredRepository._monitored_operation("calculate_health_overview")
    async def calculate_health_overview(self) -> RVHealthOverviewModel:
        """Calculate overall RV health overview.

        Returns:
            RV health overview model
        """
        components = list(self._component_health.values())

        if not components:
            return RVHealthOverviewModel(
                overall_health_score=100.0,
                status="healthy",
                components_monitored=0,
                last_updated=datetime.now(),
            )

        # Calculate overall health score
        total_weight = len(components)
        overall_score = sum(comp.health_score for comp in components) / total_weight

        # Determine overall status
        status_priority = {"healthy": 0, "watch": 1, "advise": 2, "alert": 3}
        worst_status = max(components, key=lambda c: status_priority.get(c.status, 0)).status

        # Count active recommendations
        active_recs = [r for r in self._recommendations.values() if not r.dismissed]
        critical_alerts = len([r for r in active_recs if r.level == "alert"])
        active_recommendations = len(active_recs)

        # System health breakdown
        system_breakdown = {}
        for component in components:
            system_type = component.component_type
            if system_type not in system_breakdown:
                system_breakdown[system_type] = []
            system_breakdown[system_type].append(component.health_score)

        system_health = {
            system: sum(scores) / len(scores) for system, scores in system_breakdown.items()
        }

        return RVHealthOverviewModel(
            overall_health_score=round(overall_score, 1),
            status=worst_status,
            critical_alerts=critical_alerts,
            active_recommendations=active_recommendations,
            components_monitored=len(components),
            last_updated=datetime.now(),
            system_health_breakdown=system_health,
        )
