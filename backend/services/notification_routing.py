"""
Advanced Notification Routing with Conditional Delivery

This module implements intelligent notification routing for RV-C environments,
providing conditional delivery based on rules, user preferences, system state,
and priority escalation patterns.

Key Features:
- Rule-based routing with flexible conditions
- User preference management
- Priority escalation and fallback routing
- Time-based routing (quiet hours, schedules)
- Geographic and context-aware routing
- A/B testing support for notification strategies
- Emergency override capabilities

Example:
    >>> router = NotificationRouter()
    >>> await router.initialize()
    >>> route = await router.determine_route(
    ...     notification, user_preferences, system_context
    ... )
    >>> channels = route.target_channels
"""

import logging
import re
from collections.abc import Callable
from datetime import datetime, time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.models.notification import NotificationChannel, NotificationPayload, NotificationType


class RoutingConditionType(str, Enum):
    """Types of routing conditions."""

    TIME_BASED = "time_based"
    PRIORITY_BASED = "priority_based"
    CONTENT_BASED = "content_based"
    USER_PREFERENCE = "user_preference"
    SYSTEM_STATE = "system_state"
    GEOGRAPHIC = "geographic"
    CUSTOM = "custom"


class EscalationTrigger(str, Enum):
    """Escalation trigger conditions."""

    NO_RESPONSE = "no_response"
    DELIVERY_FAILURE = "delivery_failure"
    CRITICAL_PRIORITY = "critical_priority"
    SYSTEM_ALERT = "system_alert"
    TIME_THRESHOLD = "time_threshold"


class RoutingRule(BaseModel):
    """A single routing rule with conditions and actions."""

    id: str
    name: str
    description: str | None = None
    priority: int = 100  # Lower number = higher priority
    enabled: bool = True

    # Condition evaluation
    condition_type: RoutingConditionType
    conditions: dict[str, Any]

    # Target configuration
    target_channels: list[NotificationChannel]
    channel_config: dict[str, Any] = Field(default_factory=dict)

    # Escalation configuration
    escalation_enabled: bool = False
    escalation_trigger: EscalationTrigger | None = None
    escalation_delay_minutes: int = 15
    escalation_channels: list[NotificationChannel] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    tags: list[str] = Field(default_factory=list)


class UserNotificationPreferences(BaseModel):
    """User-specific notification preferences."""

    user_id: str
    email: str | None = None
    phone: str | None = None

    # Channel preferences
    preferred_channels: list[NotificationChannel] = Field(default_factory=list)
    blocked_channels: list[NotificationChannel] = Field(default_factory=list)

    # Time preferences
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    timezone: str = "UTC"

    # Priority preferences
    min_priority_email: NotificationType = NotificationType.WARNING
    min_priority_sms: NotificationType = NotificationType.ERROR
    min_priority_push: NotificationType = NotificationType.INFO

    # Emergency overrides
    emergency_contact_enabled: bool = True
    emergency_channels: list[NotificationChannel] = Field(default_factory=list)

    # Content filtering
    keyword_filters: list[str] = Field(default_factory=list)
    category_preferences: dict[str, bool] = Field(default_factory=dict)

    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SystemContext(BaseModel):
    """Current system context for routing decisions."""

    # System state
    system_load: float = 0.0
    queue_depth: int = 0
    error_rate: float = 0.0

    # Geographic context
    location: str | None = None
    timezone: str = "UTC"

    # Network state
    connectivity_status: dict[str, bool] = Field(default_factory=dict)
    estimated_delivery_times: dict[str, float] = Field(default_factory=dict)

    # Emergency state
    emergency_mode: bool = False
    maintenance_mode: bool = False

    # A/B testing
    ab_test_variant: str | None = None
    experiment_id: str | None = None

    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RoutingDecision(BaseModel):
    """Result of routing decision process."""

    notification_id: str
    target_channels: list[NotificationChannel]
    channel_priorities: dict[str, int] = Field(default_factory=dict)

    # Timing information
    immediate_delivery: bool = True
    scheduled_for: datetime | None = None

    # Escalation plan
    escalation_plan: list[dict[str, Any]] = Field(default_factory=list)

    # Metadata
    applied_rules: list[str] = Field(default_factory=list)
    rule_evaluation_time_ms: float = 0.0
    routing_reason: str = "default_routing"

    # Overrides and special handling
    emergency_override: bool = False
    user_preference_override: bool = False

    created_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationRouter:
    """
    Advanced notification routing engine for RV-C environments.

    Determines optimal delivery channels and timing based on rules,
    user preferences, system context, and priority escalation needs.
    """

    def __init__(self):
        """Initialize notification router."""
        self.logger = logging.getLogger(f"{__name__}.NotificationRouter")

        # Routing configuration
        self.routing_rules: list[RoutingRule] = []
        self.user_preferences: dict[str, UserNotificationPreferences] = {}
        self.default_channels = [NotificationChannel.SYSTEM]

        # Rule evaluation functions
        self.condition_evaluators: dict[RoutingConditionType, Callable] = {
            RoutingConditionType.TIME_BASED: self._evaluate_time_condition,
            RoutingConditionType.PRIORITY_BASED: self._evaluate_priority_condition,
            RoutingConditionType.CONTENT_BASED: self._evaluate_content_condition,
            RoutingConditionType.USER_PREFERENCE: self._evaluate_user_preference_condition,
            RoutingConditionType.SYSTEM_STATE: self._evaluate_system_state_condition,
            RoutingConditionType.GEOGRAPHIC: self._evaluate_geographic_condition,
            RoutingConditionType.CUSTOM: self._evaluate_custom_condition,
        }

        # Statistics
        self.stats = {
            "total_routings": 0,
            "rule_matches": 0,
            "escalations_triggered": 0,
            "emergency_overrides": 0,
            "default_routings": 0,
            "avg_evaluation_time_ms": 0.0,
        }

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize routing engine with default rules."""
        try:
            # Load default routing rules
            await self._load_default_rules()

            self._initialized = True
            self.logger.info("NotificationRouter initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize NotificationRouter: {e}")
            raise

    async def determine_route(
        self,
        notification: NotificationPayload,
        user_id: str | None = None,
        system_context: SystemContext | None = None,
    ) -> RoutingDecision:
        """
        Determine routing for notification based on rules and context.

        Args:
            notification: Notification to route
            user_id: Optional user ID for preference lookup
            system_context: Current system context

        Returns:
            RoutingDecision: Routing decision with channels and timing
        """
        if not self._initialized:
            await self.initialize()

        start_time = datetime.utcnow()

        try:
            self.stats["total_routings"] += 1

            # Get user preferences
            user_prefs = None
            if user_id:
                user_prefs = self.user_preferences.get(user_id)

            # Get system context
            if not system_context:
                system_context = SystemContext()

            # Check for emergency override
            if self._is_emergency_notification(notification, system_context):
                return self._create_emergency_routing(notification, user_prefs)

            # Evaluate routing rules
            decision = await self._evaluate_routing_rules(notification, user_prefs, system_context)

            # Apply user preferences
            decision = self._apply_user_preferences(decision, user_prefs, notification)

            # Create escalation plan if needed
            if self._should_create_escalation_plan(notification, decision):
                decision.escalation_plan = self._create_escalation_plan(
                    notification, user_prefs, system_context
                )

            # Calculate timing
            evaluation_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            decision.rule_evaluation_time_ms = evaluation_time

            # Update statistics
            self._update_statistics(decision, evaluation_time)

            self.logger.debug(
                f"Routed notification {notification.id} to {len(decision.target_channels)} channels "
                f"in {evaluation_time:.2f}ms"
            )

            return decision

        except Exception as e:
            self.logger.error(f"Routing failed for notification {notification.id}: {e}")
            return self._create_fallback_routing(notification)

    async def add_routing_rule(self, rule: RoutingRule) -> bool:
        """Add new routing rule."""
        try:
            # Validate rule
            await self._validate_routing_rule(rule)

            # Remove existing rule with same ID
            self.routing_rules = [r for r in self.routing_rules if r.id != rule.id]

            # Insert rule in priority order
            inserted = False
            for i, existing_rule in enumerate(self.routing_rules):
                if rule.priority < existing_rule.priority:
                    self.routing_rules.insert(i, rule)
                    inserted = True
                    break

            if not inserted:
                self.routing_rules.append(rule)

            self.logger.info(f"Added routing rule: {rule.name}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add routing rule: {e}")
            return False

    async def update_user_preferences(
        self, user_id: str, preferences: UserNotificationPreferences
    ) -> bool:
        """Update user notification preferences."""
        try:
            preferences.updated_at = datetime.utcnow()
            self.user_preferences[user_id] = preferences

            self.logger.info(f"Updated preferences for user {user_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to update user preferences: {e}")
            return False

    def get_user_preferences(self, user_id: str) -> UserNotificationPreferences | None:
        """Get user notification preferences."""
        return self.user_preferences.get(user_id)

    def get_routing_rules(self, enabled_only: bool = True) -> list[RoutingRule]:
        """Get current routing rules."""
        if enabled_only:
            return [rule for rule in self.routing_rules if rule.enabled]
        return self.routing_rules.copy()

    def get_statistics(self) -> dict[str, Any]:
        """Get routing statistics."""
        return self.stats.copy()

    # Private implementation methods

    async def _load_default_rules(self) -> None:
        """Load default routing rules."""
        default_rules = [
            # Emergency notifications - always use all channels
            RoutingRule(
                id="emergency_critical",
                name="Emergency Critical Notifications",
                description="Route critical/emergency notifications to all available channels",
                priority=1,
                condition_type=RoutingConditionType.PRIORITY_BASED,
                conditions={"min_priority": NotificationType.CRITICAL.value},
                target_channels=[
                    NotificationChannel.SMTP,
                    NotificationChannel.PUSHOVER,
                    NotificationChannel.SYSTEM,
                ],
                escalation_enabled=True,
                escalation_trigger=EscalationTrigger.NO_RESPONSE,
                escalation_delay_minutes=5,
                escalation_channels=[NotificationChannel.PUSHOVER],
            ),
            # Quiet hours routing
            RoutingRule(
                id="quiet_hours",
                name="Quiet Hours Routing",
                description="Reduce notifications during quiet hours",
                priority=10,
                condition_type=RoutingConditionType.TIME_BASED,
                conditions={
                    "quiet_hours": True,
                    "min_priority_during_quiet": NotificationType.ERROR.value,
                },
                target_channels=[NotificationChannel.SMTP, NotificationChannel.SYSTEM],
            ),
            # High priority routing
            RoutingRule(
                id="high_priority",
                name="High Priority Routing",
                description="Enhanced delivery for error-level notifications",
                priority=20,
                condition_type=RoutingConditionType.PRIORITY_BASED,
                conditions={"min_priority": NotificationType.ERROR.value},
                target_channels=[
                    NotificationChannel.SMTP,
                    NotificationChannel.PUSHOVER,
                    NotificationChannel.SYSTEM,
                ],
                escalation_enabled=True,
                escalation_trigger=EscalationTrigger.DELIVERY_FAILURE,
                escalation_delay_minutes=15,
            ),
            # System maintenance routing
            RoutingRule(
                id="maintenance_mode",
                name="Maintenance Mode Routing",
                description="Minimal notifications during maintenance",
                priority=5,
                condition_type=RoutingConditionType.SYSTEM_STATE,
                conditions={"maintenance_mode": True},
                target_channels=[NotificationChannel.SYSTEM],
            ),
            # Default routing
            RoutingRule(
                id="default",
                name="Default Routing",
                description="Standard notification routing",
                priority=1000,
                condition_type=RoutingConditionType.PRIORITY_BASED,
                conditions={"min_priority": NotificationType.INFO.value},
                target_channels=[NotificationChannel.SYSTEM, NotificationChannel.PUSHOVER],
            ),
        ]

        for rule in default_rules:
            await self.add_routing_rule(rule)

    def _is_emergency_notification(
        self, notification: NotificationPayload, system_context: SystemContext
    ) -> bool:
        """Check if notification requires emergency routing."""
        # Critical priority notifications
        if notification.level == NotificationType.CRITICAL:
            return True

        # System in emergency mode
        if system_context.emergency_mode:
            return True

        # Emergency keywords in message
        emergency_keywords = ["emergency", "critical", "failure", "alarm", "alert"]
        message_lower = notification.message.lower()
        if any(keyword in message_lower for keyword in emergency_keywords):
            return True

        return False

    def _create_emergency_routing(
        self, notification: NotificationPayload, user_prefs: UserNotificationPreferences | None
    ) -> RoutingDecision:
        """Create emergency routing decision."""
        self.stats["emergency_overrides"] += 1

        # Use all available channels for emergency
        channels = [
            NotificationChannel.SMTP,
            NotificationChannel.PUSHOVER,
            NotificationChannel.SYSTEM,
        ]

        # Add user emergency channels if available
        if user_prefs and user_prefs.emergency_contact_enabled:
            channels.extend(user_prefs.emergency_channels)

        # Remove duplicates while preserving order
        unique_channels = []
        for channel in channels:
            if channel not in unique_channels:
                unique_channels.append(channel)

        return RoutingDecision(
            notification_id=notification.id,
            target_channels=unique_channels,
            channel_priorities={channel.value: 1 for channel in unique_channels},
            immediate_delivery=True,
            emergency_override=True,
            routing_reason="emergency_routing",
            applied_rules=["emergency_override"],
        )

    async def _evaluate_routing_rules(
        self,
        notification: NotificationPayload,
        user_prefs: UserNotificationPreferences | None,
        system_context: SystemContext,
    ) -> RoutingDecision:
        """Evaluate routing rules to determine best match."""
        context = {
            "notification": notification,
            "user_preferences": user_prefs,
            "system_context": system_context,
        }

        # Evaluate rules in priority order
        for rule in self.routing_rules:
            if not rule.enabled:
                continue

            try:
                evaluator = self.condition_evaluators.get(rule.condition_type)
                if not evaluator:
                    continue

                if await evaluator(rule.conditions, context):
                    self.stats["rule_matches"] += 1

                    return RoutingDecision(
                        notification_id=notification.id,
                        target_channels=rule.target_channels.copy(),
                        channel_priorities={
                            channel.value: 100 - rule.priority for channel in rule.target_channels
                        },
                        immediate_delivery=True,
                        routing_reason=f"rule_match:{rule.id}",
                        applied_rules=[rule.id],
                    )

            except Exception as e:
                self.logger.warning(f"Rule evaluation failed for {rule.id}: {e}")
                continue

        # No rules matched - use default routing
        self.stats["default_routings"] += 1
        return RoutingDecision(
            notification_id=notification.id,
            target_channels=self.default_channels.copy(),
            routing_reason="default_fallback",
            applied_rules=[],
        )

    async def _evaluate_time_condition(
        self, conditions: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Evaluate time-based routing conditions."""
        user_prefs = context.get("user_preferences")

        if conditions.get("quiet_hours") and user_prefs:
            current_time = datetime.utcnow().time()

            if user_prefs.quiet_hours_start and user_prefs.quiet_hours_end:
                # Check if current time is in quiet hours
                start = user_prefs.quiet_hours_start
                end = user_prefs.quiet_hours_end

                if start <= end:
                    # Same day range
                    in_quiet_hours = start <= current_time <= end
                else:
                    # Overnight range
                    in_quiet_hours = current_time >= start or current_time <= end

                if in_quiet_hours:
                    # Check if notification priority meets threshold
                    notification = context["notification"]
                    min_priority = NotificationType(
                        conditions.get("min_priority_during_quiet", "error")
                    )

                    return (
                        notification.level.value
                        in [
                            NotificationType.ERROR.value,
                            NotificationType.CRITICAL.value,
                        ]
                        if min_priority == NotificationType.ERROR
                        else True
                    )

        return False

    async def _evaluate_priority_condition(
        self, conditions: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Evaluate priority-based routing conditions."""
        notification = context["notification"]
        min_priority = conditions.get("min_priority")

        if not min_priority:
            return True

        priority_levels = {
            NotificationType.INFO.value: 1,
            NotificationType.SUCCESS.value: 1,
            NotificationType.WARNING.value: 2,
            NotificationType.ERROR.value: 3,
            NotificationType.CRITICAL.value: 4,
        }

        notification_level = priority_levels.get(notification.level.value, 1)
        required_level = priority_levels.get(min_priority, 1)

        return notification_level >= required_level

    async def _evaluate_content_condition(
        self, conditions: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Evaluate content-based routing conditions."""
        notification = context["notification"]

        # Keyword matching. Earlier revisions used naive substring
        # matching (``"update" in "Status Update"`` -> True), which
        # produced false-positive routes for any notification whose
        # title happened to contain a configured keyword as a
        # substring. Use word-boundary regex matching so the configured
        # keyword "update" matches "Status update" but NOT
        # "updateserver" or arbitrary substring collisions.
        keywords = conditions.get("keywords", [])
        if keywords:
            haystack = f"{notification.message or ''} {notification.title or ''}".lower()
            for keyword in keywords:
                if not keyword:
                    continue
                pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
                if re.search(pattern, haystack):
                    return True

        # Tag matching
        required_tags = conditions.get("tags", [])
        if required_tags:
            notification_tags = notification.tags or []
            return any(tag in notification_tags for tag in required_tags)

        # Component matching
        component = conditions.get("source_component")
        if component:
            return notification.source_component == component

        return False

    async def _evaluate_user_preference_condition(
        self, conditions: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Evaluate user preference conditions."""
        user_prefs = context.get("user_preferences")
        if not user_prefs:
            return False

        notification = context["notification"]

        # Check channel preferences
        preferred_channels = conditions.get("preferred_channels", [])
        if preferred_channels:
            user_preferred = [ch.value for ch in user_prefs.preferred_channels]
            return any(ch in user_preferred for ch in preferred_channels)

        # Check priority thresholds
        channel_priority_map = {
            "email": user_prefs.min_priority_email,
            "sms": user_prefs.min_priority_sms,
            "push": user_prefs.min_priority_push,
        }

        for channel, min_priority in channel_priority_map.items():
            if conditions.get(f"check_{channel}_priority"):
                priority_levels = {
                    NotificationType.INFO: 1,
                    NotificationType.SUCCESS: 1,
                    NotificationType.WARNING: 2,
                    NotificationType.ERROR: 3,
                    NotificationType.CRITICAL: 4,
                }

                notification_level = priority_levels.get(notification.level, 1)
                required_level = priority_levels.get(min_priority, 1)

                return notification_level >= required_level

        return False

    async def _evaluate_system_state_condition(
        self, conditions: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Evaluate system state conditions."""
        system_context = context["system_context"]

        # Maintenance mode check
        if conditions.get("maintenance_mode") is not None:
            return system_context.maintenance_mode == conditions["maintenance_mode"]

        # Emergency mode check
        if conditions.get("emergency_mode") is not None:
            return system_context.emergency_mode == conditions["emergency_mode"]

        # System load thresholds
        max_load = conditions.get("max_system_load")
        if max_load is not None:
            return system_context.system_load <= max_load

        # Queue depth thresholds
        max_queue_depth = conditions.get("max_queue_depth")
        if max_queue_depth is not None:
            return system_context.queue_depth <= max_queue_depth

        return False

    async def _evaluate_geographic_condition(
        self, conditions: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Evaluate geographic routing conditions."""
        system_context = context["system_context"]

        # Location-based routing
        allowed_locations = conditions.get("allowed_locations", [])
        if allowed_locations and system_context.location:
            return system_context.location in allowed_locations

        # Timezone-based routing
        allowed_timezones = conditions.get("allowed_timezones", [])
        if allowed_timezones:
            return system_context.timezone in allowed_timezones

        return False

    async def _evaluate_custom_condition(
        self, conditions: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Evaluate custom routing conditions."""
        # Placeholder for custom condition evaluation
        # Could be extended to support user-defined evaluation functions
        return conditions.get("always_match", False)

    def _apply_user_preferences(
        self,
        decision: RoutingDecision,
        user_prefs: UserNotificationPreferences | None,
        notification: NotificationPayload,
    ) -> RoutingDecision:
        """Apply user preferences to routing decision.

        Adds preferred channels and removes blocked channels, but ALSO
        respects per-channel minimum-priority thresholds so a user who
        opts into SMTP only for WARNING+ doesn't get every INFO
        notification emailed to them. Earlier revisions added every
        preferred channel unconditionally, which silently spammed
        users for INFO notifications they had configured to ignore.
        """
        if not user_prefs:
            return decision

        # Filter out blocked channels
        if user_prefs.blocked_channels:
            blocked = [ch.value for ch in user_prefs.blocked_channels]
            decision.target_channels = [
                ch for ch in decision.target_channels if ch.value not in blocked
            ]

        # Map of channel -> per-channel minimum-priority threshold the
        # user configured. Channels not in the map have no per-channel
        # threshold and are always added when preferred.
        priority_levels = {
            NotificationType.INFO: 1,
            NotificationType.SUCCESS: 1,
            NotificationType.WARNING: 2,
            NotificationType.ERROR: 3,
            NotificationType.CRITICAL: 4,
        }
        notification_level = priority_levels.get(notification.level, 1)

        per_channel_min = {
            NotificationChannel.SMTP: user_prefs.min_priority_email,
            NotificationChannel.PUSHOVER: user_prefs.min_priority_push,
        }

        # Add preferred channels if not already included AND the
        # notification meets that channel's minimum priority.
        for preferred_channel in user_prefs.preferred_channels:
            min_priority = per_channel_min.get(preferred_channel)
            if min_priority is not None:
                required_level = priority_levels.get(min_priority, 1)
                if notification_level < required_level:
                    # User opted into this channel only for higher priorities;
                    # honour the threshold and skip the add.
                    continue
            if preferred_channel not in decision.target_channels:
                decision.target_channels.append(preferred_channel)
                decision.user_preference_override = True

        # Symmetrically, REMOVE channels from a base routing decision
        # if the user's per-channel threshold says this notification
        # is too low priority for that channel. (Without this, the
        # "Default Routing" rule could attach SMTP to an INFO and
        # the user's WARNING-only preference would be ignored.)
        decision.target_channels = [
            ch
            for ch in decision.target_channels
            if (
                per_channel_min.get(ch) is None
                or notification_level >= priority_levels.get(per_channel_min[ch], 1)  # type: ignore[arg-type]
            )
        ]

        return decision

    def _should_create_escalation_plan(
        self, notification: NotificationPayload, decision: RoutingDecision
    ) -> bool:
        """Determine if escalation plan should be created."""
        # Always escalate critical notifications
        if notification.level == NotificationType.CRITICAL:
            return True

        # Escalate error notifications with multiple channels
        if notification.level == NotificationType.ERROR and len(decision.target_channels) > 1:
            return True

        return False

    def _create_escalation_plan(
        self,
        notification: NotificationPayload,
        user_prefs: UserNotificationPreferences | None,
        system_context: SystemContext,
    ) -> list[dict[str, Any]]:
        """Create escalation plan for notification."""
        plan = []

        # First escalation: Add more channels after delay
        escalation_channels = [NotificationChannel.PUSHOVER]
        if user_prefs and user_prefs.emergency_channels:
            escalation_channels.extend(user_prefs.emergency_channels)

        plan.append(
            {
                "trigger": EscalationTrigger.NO_RESPONSE.value,
                "delay_minutes": 15,
                "additional_channels": [ch.value for ch in escalation_channels],
                "priority_boost": True,
            }
        )

        # Second escalation: Emergency contact after longer delay
        if notification.level == NotificationType.CRITICAL:
            plan.append(
                {
                    "trigger": EscalationTrigger.NO_RESPONSE.value,
                    "delay_minutes": 30,
                    "additional_channels": [NotificationChannel.PUSHOVER.value],
                    "emergency_override": True,
                }
            )

        return plan

    def _create_fallback_routing(self, notification: NotificationPayload) -> RoutingDecision:
        """Create fallback routing when normal routing fails."""
        return RoutingDecision(
            notification_id=notification.id,
            target_channels=self.default_channels.copy(),
            routing_reason="fallback_routing",
            applied_rules=[],
        )

    async def _validate_routing_rule(self, rule: RoutingRule) -> None:
        """Validate routing rule configuration."""
        if not rule.target_channels:
            raise ValueError("Routing rule must specify target channels")

        if rule.escalation_enabled and not rule.escalation_trigger:
            raise ValueError("Escalation enabled but no trigger specified")

        # Validate condition format
        evaluator = self.condition_evaluators.get(rule.condition_type)
        if not evaluator:
            raise ValueError(f"Unknown condition type: {rule.condition_type}")

    def _update_statistics(self, decision: RoutingDecision, evaluation_time_ms: float) -> None:
        """Update routing statistics."""
        # Update average evaluation time
        total_time = self.stats["avg_evaluation_time_ms"] * (self.stats["total_routings"] - 1)
        self.stats["avg_evaluation_time_ms"] = (total_time + evaluation_time_ms) / self.stats[
            "total_routings"
        ]

        # Count escalations
        if decision.escalation_plan:
            self.stats["escalations_triggered"] += 1
