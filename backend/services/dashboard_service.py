"""
Dashboard Service (Refactored with Repository Pattern)

Service for aggregating dashboard data, managing activity feeds,
and providing optimized endpoints for frontend dashboard components.
"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from backend.core.config import get_features_settings
from backend.core.performance import PerformanceMonitor
from backend.models.dashboard import (
    ActiveAlert,
    ActivityEntry,
    ActivityFeed,
    AlertDefinition,
    BulkControlRequest,
    BulkControlResponse,
    BulkControlResult,
    CANBusSummary,
    DashboardSummary,
    EntitySummary,
    SystemAnalytics,
    SystemMetrics,
)
from backend.repositories.dashboard_config_repository import DashboardConfigRepository
from backend.repositories.entity_state_repository import EntityStateRepository

logger = logging.getLogger(__name__)


class ActivityTracker:
    """Tracks and manages system activity feed."""

    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self._activities: list[ActivityEntry] = []
        self._activity_lock = asyncio.Lock()

    async def add_activity(
        self,
        event_type: str,
        title: str,
        description: str,
        severity: str = "info",
        entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a new activity entry."""
        async with self._activity_lock:
            activity = ActivityEntry(
                id=str(uuid4()),
                timestamp=datetime.now(),
                event_type=event_type,
                entity_id=entity_id,
                title=title,
                description=description,
                severity=severity,
                metadata=metadata or {},
            )

            self._activities.insert(0, activity)  # Most recent first

            # Trim to max entries
            if len(self._activities) > self.max_entries:
                self._activities = self._activities[: self.max_entries]

    async def get_recent_activities(
        self, limit: int = 50, since: datetime | None = None
    ) -> ActivityFeed:
        """Get recent activity entries."""
        async with self._activity_lock:
            activities = self._activities

            if since:
                activities = [a for a in activities if a.timestamp >= since]

            limited_activities = activities[:limit]

            return ActivityFeed(
                entries=limited_activities,
                total_count=len(activities),
                has_more=len(activities) > limit,
            )


class DashboardService:
    """
    Service for aggregating dashboard data and managing system analytics.

    Refactored to use repository pattern with performance monitoring.
    """

    def __init__(
        self,
        dashboard_repository: DashboardConfigRepository,
        entity_repository: EntityStateRepository,
        performance_monitor: PerformanceMonitor,
        # These will be injected by dependency injection later
        entity_service: Any | None = None,
        can_service: Any | None = None,
        websocket_manager: Any | None = None,
    ):
        """Initialize the dashboard service with repositories."""
        self._dashboard_repo = dashboard_repository
        self._entity_repo = entity_repository
        self._monitor = performance_monitor

        # Services will be injected later
        self._entity_service = entity_service
        self._can_service = can_service
        self._websocket_manager = websocket_manager

        # Activity tracking
        features = get_features_settings()
        self.activity_tracker = ActivityTracker(max_entries=features.activity_feed_limit)

        # Cache settings
        self.cache_ttl = features.dashboard_cache_ttl
        self._cache: dict[str, Any] = {}
        self._cache_timestamps: dict[str, float] = {}

        # System start time for uptime calculation
        self._start_time = time.time()

        # Alert management
        self._alerts: list[ActiveAlert] = []
        self._alert_definitions: list[AlertDefinition] = []

        # Initialize default alert definitions
        self._initialize_default_alerts()

        # Apply performance monitoring decorators
        self._apply_monitoring()

    def _initialize_default_alerts(self) -> None:
        """Initialize default system alert definitions."""
        default_alerts = [
            AlertDefinition(
                id="high_error_rate",
                name="High CAN Error Rate",
                description="CAN bus error rate exceeds threshold",
                condition="can_error_rate > 5.0",
                severity="warning",
                enabled=True,
                threshold=5.0,
            ),
            AlertDefinition(
                id="low_entity_health",
                name="Low Entity Health Score",
                description="System entity health score is below threshold",
                condition="entity_health_score < 80.0",
                severity="warning",
                enabled=True,
                threshold=80.0,
            ),
            AlertDefinition(
                id="no_can_activity",
                name="No CAN Activity",
                description="No CAN messages received recently",
                condition="can_message_rate < 1.0",
                severity="error",
                enabled=True,
                threshold=1.0,
            ),
        ]
        self._alert_definitions.extend(default_alerts)

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        # Wrap methods with performance monitoring
        self.get_entity_summary = self._monitor.monitor_service_method(
            "DashboardService", "get_entity_summary"
        )(self.get_entity_summary)

        self.get_system_metrics = self._monitor.monitor_service_method(
            "DashboardService", "get_system_metrics"
        )(self.get_system_metrics)

        self.get_can_bus_summary = self._monitor.monitor_service_method(
            "DashboardService", "get_can_bus_summary"
        )(self.get_can_bus_summary)

        self.get_dashboard_summary = self._monitor.monitor_service_method(
            "DashboardService", "get_dashboard_summary"
        )(self.get_dashboard_summary)

        self.bulk_control_entities = self._monitor.monitor_service_method(
            "DashboardService", "bulk_control_entities"
        )(self.bulk_control_entities)

        self.get_dashboard_config = self._monitor.monitor_service_method(
            "DashboardService", "get_dashboard_config"
        )(self.get_dashboard_config)

        self.update_widget_layout = self._monitor.monitor_service_method(
            "DashboardService", "update_widget_layout"
        )(self.update_widget_layout)

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if cache_key not in self._cache_timestamps:
            return False

        age = time.time() - self._cache_timestamps[cache_key]
        return age < self.cache_ttl

    def _get_cached_or_none(self, cache_key: str) -> Any:
        """Get cached value if valid, None otherwise."""
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key)
        return None

    def _set_cache(self, cache_key: str, value: Any) -> None:
        """Set cache value with timestamp."""
        self._cache[cache_key] = value
        self._cache_timestamps[cache_key] = time.time()

    async def get_entity_summary(self) -> EntitySummary:
        """Get aggregated entity statistics."""
        cache_key = "entity_summary"
        cached = self._get_cached_or_none(cache_key)
        if cached:
            return cached

        # Get all entities from repository
        entities = self._entity_repo.get_all_entities()

        total_entities = len(entities)
        online_entities = 0
        active_entities = 0
        device_type_counts = defaultdict(int)
        area_counts = defaultdict(int)

        current_time = time.time()

        for entity in entities.values():
            # Count by device type
            device_type = entity.config.get("device_type", "unknown")
            device_type_counts[device_type] += 1

            # Count by area
            area = entity.config.get("suggested_area", "unassigned")
            area_counts[area] += 1

            # Check if online (seen in last 5 minutes)
            if (
                entity.current_state.timestamp
                and (current_time - entity.current_state.timestamp) < 300
            ):
                online_entities += 1

            # Check if active (entity is considered active if it has a state other than 'unknown')
            if entity.current_state.state != "unknown":
                active_entities += 1

        # Calculate health score
        online_ratio = online_entities / total_entities if total_entities > 0 else 0
        health_score = min(100, online_ratio * 100)

        summary = EntitySummary(
            total_entities=total_entities,
            online_entities=online_entities,
            active_entities=active_entities,
            device_type_counts=dict(device_type_counts),
            area_counts=dict(area_counts),
            health_score=health_score,
        )

        self._set_cache(cache_key, summary)
        return summary

    async def get_system_metrics(self) -> SystemMetrics:
        """Get system performance metrics."""
        cache_key = "system_metrics"
        cached = self._get_cached_or_none(cache_key)
        if cached:
            return cached

        # Get CAN statistics if service is available
        message_rate = 0.0
        error_rate = 0.0

        if self._can_service:
            try:
                can_stats = await self._can_service.get_bus_statistics()
                summary = can_stats.get("summary", {})
                message_rate = summary.get("message_rate", 0.0)
                error_rate = summary.get("error_rate", 0.0)
            except Exception as e:
                logger.warning(f"Failed to get CAN stats for metrics: {e}")

        # Calculate uptime
        uptime_seconds = int(time.time() - self._start_time)

        # Get WebSocket connection count
        websocket_connections = 0
        if self._websocket_manager:
            websocket_connections = self._websocket_manager.total_connections

        # TODO: Add actual memory and CPU monitoring
        memory_usage_mb = 0.0  # Placeholder
        cpu_usage_percent = 0.0  # Placeholder

        metrics = SystemMetrics(
            uptime_seconds=uptime_seconds,
            message_rate=message_rate,
            error_rate=error_rate,
            memory_usage_mb=memory_usage_mb,
            cpu_usage_percent=cpu_usage_percent,
            websocket_connections=websocket_connections,
        )

        self._set_cache(cache_key, metrics)
        return metrics

    async def get_can_bus_summary(self) -> CANBusSummary:
        """Get CAN bus status summary."""
        cache_key = "can_bus_summary"
        cached = self._get_cached_or_none(cache_key)
        if cached:
            return cached

        can_summary = CANBusSummary(
            interfaces_count=0,
            total_messages=0,
            messages_per_minute=0.0,
            error_count=0,
            queue_length=0,
            bus_load_percent=0.0,
        )

        if self._can_service:
            try:
                # Get CAN statistics
                can_stats = await self._can_service.get_bus_statistics()
                summary = can_stats.get("summary", {})
                interfaces = can_stats.get("interfaces", {})

                # Get queue status
                queue_status = await self._can_service.get_queue_status()
                queue_length = queue_status.get("queue_length", 0)

                total_messages = summary.get("total_messages", 0)
                error_count = summary.get("total_errors", 0)
                message_rate = summary.get("message_rate", 0.0)

                # Calculate messages per minute and bus load
                messages_per_minute = message_rate * 60
                bus_load_percent = min(100, (message_rate / 1000) * 100)  # Assuming 1000 msg/s max

                can_summary = CANBusSummary(
                    interfaces_count=len(interfaces),
                    total_messages=total_messages,
                    messages_per_minute=messages_per_minute,
                    error_count=error_count,
                    queue_length=queue_length,
                    bus_load_percent=bus_load_percent,
                )

            except Exception as e:
                logger.warning(f"Failed to get CAN stats for summary: {e}")

        self._set_cache(cache_key, can_summary)
        return can_summary

    async def get_dashboard_summary(self) -> DashboardSummary:
        """Get complete aggregated dashboard data."""
        # Run all data collection concurrently
        entities_task = self.get_entity_summary()
        metrics_task = self.get_system_metrics()
        can_task = self.get_can_bus_summary()
        activity_task = self.activity_tracker.get_recent_activities(limit=10)

        entities, metrics, can_bus, activity = await asyncio.gather(
            entities_task, metrics_task, can_task, activity_task
        )

        # Check for active alerts
        await self._check_alerts(entities, metrics, can_bus)
        active_alerts = [alert.message for alert in self._alerts]

        # Create quick stats for dashboard cards
        quick_stats = {
            "entities_online_ratio": entities.online_entities / max(entities.total_entities, 1),
            "can_health": "healthy" if can_bus.error_count < 10 else "degraded",
            "message_rate_trend": "stable",  # TODO: Calculate actual trend
            "system_status": ("operational" if len(active_alerts) == 0 else "attention_needed"),
        }

        return DashboardSummary(
            timestamp=datetime.now(),
            entities=entities,
            system=metrics,
            can_bus=can_bus,
            activity=activity,
            alerts=active_alerts,
            quick_stats=quick_stats,
        )

    async def bulk_control_entities(self, request: BulkControlRequest) -> BulkControlResponse:
        """Perform bulk control operations on multiple entities."""
        features = get_features_settings()

        # Validate request size
        if len(request.entity_ids) > features.bulk_operation_limit:
            msg = f"Too many entities requested. Maximum: {features.bulk_operation_limit}"
            raise ValueError(msg)

        results = []
        successful = 0
        failed = 0

        # Process each entity
        for entity_id in request.entity_ids:
            try:
                # Use entity service if available
                if self._entity_service:
                    from backend.models.entity import ControlCommand

                    # Extract state and brightness from parameters
                    state = request.parameters.get("state")
                    brightness = request.parameters.get("brightness")

                    control_command = ControlCommand(
                        command=request.command, state=state, brightness=brightness
                    )

                    response = await self._entity_service.control_entity(entity_id, control_command)

                    if response.status == "success":
                        successful += 1
                        results.append(
                            BulkControlResult(
                                entity_id=entity_id,
                                success=True,
                                message=f"Command '{request.command}' executed successfully",
                                error=None,
                            )
                        )
                    else:
                        failed += 1
                        results.append(
                            BulkControlResult(
                                entity_id=entity_id,
                                success=False,
                                message=f"Command '{request.command}' failed",
                                error=f"Status: {response.status}",
                            )
                        )
                else:
                    # No entity service available
                    failed += 1
                    results.append(
                        BulkControlResult(
                            entity_id=entity_id,
                            success=False,
                            message="Entity service not available",
                            error="Service dependency missing",
                        )
                    )

            except Exception as e:
                failed += 1
                error_msg = str(e)
                logger.error(f"Bulk control failed for entity {entity_id}: {error_msg}")

                results.append(
                    BulkControlResult(
                        entity_id=entity_id,
                        success=False,
                        message="Operation failed",
                        error=error_msg,
                    )
                )

                if not request.ignore_errors:
                    break

        # Log the bulk operation
        await self.activity_tracker.add_activity(
            event_type="bulk_control",
            title=f"Bulk {request.command} operation",
            description=f"Controlled {len(request.entity_ids)} entities: {successful} successful, {failed} failed",
            severity="info" if failed == 0 else "warning",
            metadata={
                "command": request.command,
                "total_entities": len(request.entity_ids),
                "successful": successful,
                "failed": failed,
            },
        )

        summary = f"Bulk operation completed: {successful} successful, {failed} failed"

        return BulkControlResponse(
            total_requested=len(request.entity_ids),
            successful=successful,
            failed=failed,
            results=results,
            summary=summary,
        )

    async def _check_alerts(
        self, entities: EntitySummary, metrics: SystemMetrics, can_bus: CANBusSummary
    ) -> None:
        """Check alert conditions and update active alerts."""
        current_time = datetime.now()

        # Clear old alerts (older than 1 hour)
        cutoff_time = current_time - timedelta(hours=1)
        self._alerts = [alert for alert in self._alerts if alert.triggered_at >= cutoff_time]

        # Check each alert definition
        for alert_def in self._alert_definitions:
            if not alert_def.enabled:
                continue

            should_trigger = False
            current_value = 0.0

            # Evaluate alert conditions
            if alert_def.id == "high_error_rate":
                current_value = metrics.error_rate
                should_trigger = (
                    alert_def.threshold is not None and current_value > alert_def.threshold
                )

            elif alert_def.id == "low_entity_health":
                current_value = entities.health_score
                should_trigger = (
                    alert_def.threshold is not None and current_value < alert_def.threshold
                )

            elif alert_def.id == "no_can_activity":
                current_value = metrics.message_rate
                should_trigger = (
                    alert_def.threshold is not None and current_value < alert_def.threshold
                )

            # Check if alert is already active
            existing_alert = next(
                (alert for alert in self._alerts if alert.alert_id == alert_def.id),
                None,
            )

            if should_trigger and not existing_alert:
                # Trigger new alert
                new_alert = ActiveAlert(
                    alert_id=alert_def.id,
                    triggered_at=current_time,
                    current_value=current_value,
                    threshold=alert_def.threshold,
                    message=f"{alert_def.name}: {alert_def.description}",
                    severity=alert_def.severity,
                )

                self._alerts.append(new_alert)

                # Log alert activation
                await self.activity_tracker.add_activity(
                    event_type="system_alert",
                    title=f"Alert: {alert_def.name}",
                    description=alert_def.description,
                    severity=alert_def.severity,
                    metadata={
                        "alert_id": alert_def.id,
                        "current_value": current_value,
                        "threshold": alert_def.threshold,
                    },
                )

    async def get_dashboard_config(self, user_id: str) -> dict:
        """Get dashboard configuration for user."""
        config = await self._dashboard_repo.get_by_user_id(user_id)
        if not config:
            config = await self._dashboard_repo.create_default(user_id)
        return config.to_dict()

    async def update_widget_layout(self, user_id: str, layout: dict) -> dict:
        """Update dashboard widget layout."""
        config = await self._dashboard_repo.update_layout(user_id, layout)
        return config.to_dict()

    async def get_system_analytics(self) -> SystemAnalytics:
        """Get system analytics and monitoring data."""
        # TODO: Implement performance trends and health checks
        performance_trends = {
            "message_rate": [],  # Last 24 hours of message rates
            "error_rate": [],  # Last 24 hours of error rates
            "entity_health": [],  # Last 24 hours of entity health scores
        }

        health_checks = {
            "can_interface": True,  # TODO: Actual health check
            "entity_manager": True,
            "websocket": True,
            "database": True,
        }

        recommendations = []
        if len(self._alerts) > 0:
            recommendations.append("Review and acknowledge active system alerts")

        # Add more intelligent recommendations based on system state
        entity_summary = await self.get_entity_summary()
        if entity_summary.health_score < 90:
            recommendations.append("Check offline entities and CAN connections")

        return SystemAnalytics(
            alerts=self._alerts,
            performance_trends=performance_trends,
            health_checks=health_checks,
            recommendations=recommendations,
        )

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an active alert."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True

                await self.activity_tracker.add_activity(
                    event_type="alert_acknowledged",
                    title=f"Alert acknowledged: {alert_id}",
                    description="Alert has been acknowledged by user",
                    severity="info",
                    metadata={"alert_id": alert_id},
                )

                return True

        return False

    async def get_activity_feed(
        self, limit: int = 50, since: datetime | None = None
    ) -> ActivityFeed:
        """Get recent activity feed."""
        return await self.activity_tracker.get_recent_activities(limit=limit, since=since)
