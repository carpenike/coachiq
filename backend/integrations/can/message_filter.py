"""
CAN Message Filtering System

Advanced filtering and monitoring rules for CAN bus messages.
Supports complex filter expressions, real-time monitoring, and alerting.
"""

import asyncio
import fnmatch
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from backend.services.feature_base import Feature
from backend.services.feature_models import SafetyClassification

logger = logging.getLogger(__name__)


class FilterOperator(str, Enum):
    """Filter comparison operators."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    MATCHES = "matches"  # Regex match
    WILDCARD = "wildcard"  # Glob pattern


class FilterField(str, Enum):
    """Fields that can be filtered."""

    CAN_ID = "can_id"
    PGN = "pgn"
    SOURCE_ADDRESS = "source_address"
    DESTINATION_ADDRESS = "destination_address"
    DATA = "data"
    DATA_LENGTH = "data_length"
    INTERFACE = "interface"
    PROTOCOL = "protocol"
    MESSAGE_TYPE = "message_type"
    DECODED_FIELD = "decoded_field"


class FilterAction(str, Enum):
    """Actions to take when filter matches."""

    PASS = "pass"  # Allow message through
    BLOCK = "block"  # Block message
    LOG = "log"  # Log message
    ALERT = "alert"  # Send alert
    CAPTURE = "capture"  # Capture to buffer
    FORWARD = "forward"  # Forward to another interface
    MODIFY = "modify"  # Modify message (advanced)


@dataclass
class FilterCondition:
    """Single filter condition."""

    field: FilterField
    operator: FilterOperator
    value: Any
    case_sensitive: bool = True
    negate: bool = False

    def evaluate(self, message: Dict[str, Any]) -> bool:
        """Evaluate condition against message."""
        try:
            # Extract field value
            field_value = self._extract_field_value(message)
            if field_value is None:
                return self.negate

            # Perform comparison
            result = self._compare(field_value, self.value)

            return not result if self.negate else result

        except Exception as e:
            logger.debug(f"Filter condition evaluation error: {e}")
            return False

    def _extract_field_value(self, message: Dict[str, Any]) -> Any:
        """Extract field value from message."""
        if self.field == FilterField.CAN_ID:
            return message.get("can_id", message.get("arbitration_id"))
        elif self.field == FilterField.PGN:
            can_id = message.get("can_id", message.get("arbitration_id", 0))
            return (can_id >> 8) & 0x3FFFF
        elif self.field == FilterField.SOURCE_ADDRESS:
            can_id = message.get("can_id", message.get("arbitration_id", 0))
            return can_id & 0xFF
        elif self.field == FilterField.DESTINATION_ADDRESS:
            # For J1939 PDU2 format
            can_id = message.get("can_id", message.get("arbitration_id", 0))
            pgn = (can_id >> 8) & 0x3FFFF
            if (pgn & 0xFF00) >= 0xF000:  # PDU2 format
                return (pgn & 0xFF)
            return None
        elif self.field == FilterField.DATA:
            data = message.get("data", b"")
            if isinstance(data, str):
                return data.upper()
            return data.hex().upper()
        elif self.field == FilterField.DATA_LENGTH:
            data = message.get("data", b"")
            if isinstance(data, str):
                return len(data) // 2
            return len(data)
        elif self.field == FilterField.INTERFACE:
            return message.get("interface", "")
        elif self.field == FilterField.PROTOCOL:
            return message.get("protocol", "unknown")
        elif self.field == FilterField.MESSAGE_TYPE:
            return message.get("message_type", "")
        elif self.field == FilterField.DECODED_FIELD:
            # Special handling for decoded fields
            decoded = message.get("decoded", {})
            if isinstance(self.value, dict) and "name" in self.value:
                field_name = self.value["name"]
                return decoded.get(field_name)
        return None

    def _compare(self, field_value: Any, filter_value: Any) -> bool:
        """Compare field value with filter value."""
        # Convert to string for string operations
        if self.operator in [FilterOperator.CONTAINS, FilterOperator.NOT_CONTAINS,
                            FilterOperator.MATCHES, FilterOperator.WILDCARD]:
            field_str = str(field_value)
            filter_str = str(filter_value)
            if not self.case_sensitive:
                field_str = field_str.lower()
                filter_str = filter_str.lower()

            if self.operator == FilterOperator.CONTAINS:
                return filter_str in field_str
            elif self.operator == FilterOperator.NOT_CONTAINS:
                return filter_str not in field_str
            elif self.operator == FilterOperator.MATCHES:
                return bool(re.match(filter_str, field_str))
            elif self.operator == FilterOperator.WILDCARD:
                return fnmatch.fnmatch(field_str, filter_str)

        # Numeric comparisons
        try:
            # Convert hex strings to int
            if isinstance(field_value, str) and field_value.startswith("0x"):
                field_value = int(field_value, 16)
            if isinstance(filter_value, str) and filter_value.startswith("0x"):
                filter_value = int(filter_value, 16)

            if self.operator == FilterOperator.EQUALS:
                return field_value == filter_value
            elif self.operator == FilterOperator.NOT_EQUALS:
                return field_value != filter_value
            elif self.operator == FilterOperator.GREATER_THAN:
                return float(field_value) > float(filter_value)
            elif self.operator == FilterOperator.LESS_THAN:
                return float(field_value) < float(filter_value)
            elif self.operator == FilterOperator.GREATER_EQUAL:
                return float(field_value) >= float(filter_value)
            elif self.operator == FilterOperator.LESS_EQUAL:
                return float(field_value) <= float(filter_value)
            elif self.operator == FilterOperator.IN:
                return field_value in filter_value
            elif self.operator == FilterOperator.NOT_IN:
                return field_value not in filter_value

        except (ValueError, TypeError):
            # Fallback to string comparison
            if self.operator == FilterOperator.EQUALS:
                return str(field_value) == str(filter_value)
            elif self.operator == FilterOperator.NOT_EQUALS:
                return str(field_value) != str(filter_value)

        return False


@dataclass
class FilterRule:
    """Complete filter rule with conditions and actions."""

    id: str
    name: str
    description: str = ""
    enabled: bool = True
    priority: int = 50  # 0-100, higher = higher priority
    conditions: List[FilterCondition] = field(default_factory=list)
    condition_logic: str = "AND"  # AND or OR
    actions: List[Dict[str, Any]] = field(default_factory=list)
    statistics: Dict[str, int] = field(default_factory=lambda: {
        "matches": 0,
        "last_match": 0,
    })

    def evaluate(self, message: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Evaluate rule against message.

        Returns:
            Tuple of (matches, actions_to_execute)
        """
        if not self.enabled:
            return False, []

        # Evaluate conditions
        if not self.conditions:
            return False, []

        if self.condition_logic == "AND":
            matches = all(cond.evaluate(message) for cond in self.conditions)
        else:  # OR
            matches = any(cond.evaluate(message) for cond in self.conditions)

        if matches:
            self.statistics["matches"] += 1
            self.statistics["last_match"] = int(time.time())
            return True, self.actions

        return False, []


class MessageFilter(Feature):
    """
    CAN message filtering system.

    Features:
    - Complex filter expressions
    - Real-time monitoring
    - Action execution (pass/block/alert)
    - Filter statistics
    - Performance optimization
    """

    def __init__(
        self,
        name: str = "can_message_filter",
        enabled: bool = True,
        core: bool = False,
        max_rules: int = 100,
        alert_callback: Optional[Callable] = None,
        capture_buffer_size: int = 10000,
    ):
        """Initialize message filter."""
        super().__init__(
            name=name,
            enabled=enabled,
            core=core,
            safety_classification=SafetyClassification.OPERATIONAL,
            dependencies=["can_interface"],
        )

        self.max_rules = max_rules
        self.alert_callback = alert_callback
        self.capture_buffer_size = capture_buffer_size

        # Filter rules by ID
        self.rules: Dict[str, FilterRule] = {}

        # Rules sorted by priority
        self._sorted_rules: List[FilterRule] = []

        # Capture buffer for filtered messages
        self.capture_buffer: List[Dict[str, Any]] = []

        # Performance tracking
        self.stats = {
            "messages_processed": 0,
            "messages_passed": 0,
            "messages_blocked": 0,
            "messages_captured": 0,
            "alerts_sent": 0,
            "processing_time_ms": 0.0,
            "last_update": time.time(),
        }

        # Default system rules
        self._initialize_default_rules()

    def _initialize_default_rules(self):
        """Initialize default system filter rules."""
        # Example: Block invalid CAN IDs
        self.add_rule(FilterRule(
            id="system_invalid_can_id",
            name="Block Invalid CAN IDs",
            description="Blocks messages with invalid CAN IDs",
            enabled=False,  # Disabled by default
            priority=90,
            conditions=[
                FilterCondition(
                    field=FilterField.CAN_ID,
                    operator=FilterOperator.GREATER_THAN,
                    value=0x1FFFFFFF,  # Max 29-bit ID
                ),
            ],
            actions=[
                {"action": FilterAction.BLOCK},
                {"action": FilterAction.LOG, "level": "warning"},
            ],
        ))

    async def startup(self) -> None:
        """Start message filter."""
        logger.info("Starting CAN message filter")
        self._sort_rules()

    async def shutdown(self) -> None:
        """Shutdown message filter."""
        logger.info("Shutting down CAN message filter")

    def add_rule(self, rule: FilterRule) -> bool:
        """Add a filter rule."""
        if len(self.rules) >= self.max_rules:
            logger.warning(f"Maximum number of filter rules ({self.max_rules}) reached")
            return False

        if rule.id in self.rules:
            logger.warning(f"Filter rule with ID {rule.id} already exists")
            return False

        self.rules[rule.id] = rule
        self._sort_rules()
        logger.info(f"Added filter rule: {rule.name} (ID: {rule.id})")
        return True

    def update_rule(self, rule_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing rule."""
        if rule_id not in self.rules:
            return False

        rule = self.rules[rule_id]

        # Update fields
        for field, value in updates.items():
            if hasattr(rule, field):
                setattr(rule, field, value)

        self._sort_rules()
        logger.info(f"Updated filter rule: {rule.name} (ID: {rule_id})")
        return True

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a filter rule."""
        if rule_id not in self.rules:
            return False

        # Don't allow removal of system rules
        if rule_id.startswith("system_"):
            logger.warning(f"Cannot remove system rule: {rule_id}")
            return False

        del self.rules[rule_id]
        self._sort_rules()
        logger.info(f"Removed filter rule: {rule_id}")
        return True

    def get_rule(self, rule_id: str) -> Optional[FilterRule]:
        """Get a specific rule."""
        return self.rules.get(rule_id)

    def get_all_rules(self) -> List[FilterRule]:
        """Get all filter rules."""
        return list(self.rules.values())

    def _sort_rules(self):
        """Sort rules by priority (higher first)."""
        self._sorted_rules = sorted(
            self.rules.values(),
            key=lambda r: r.priority,
            reverse=True
        )

    async def process_message(self, message: Dict[str, Any]) -> bool:
        """
        Process a CAN message through filters.

        Returns:
            True if message should be passed, False if blocked
        """
        start_time = time.time()
        self.stats["messages_processed"] += 1

        should_pass = True
        should_capture = False
        alerts_to_send = []

        try:
            # Process rules in priority order
            for rule in self._sorted_rules:
                if not rule.enabled:
                    continue

                matches, actions = rule.evaluate(message)
                if not matches:
                    continue

                # Execute actions
                for action in actions:
                    action_type = action.get("action")

                    if action_type == FilterAction.BLOCK:
                        should_pass = False
                        self.stats["messages_blocked"] += 1
                        logger.debug(f"Message blocked by rule: {rule.name}")

                    elif action_type == FilterAction.LOG:
                        level = action.get("level", "info")
                        log_func = getattr(logger, level, logger.info)
                        log_func(f"Filter match: {rule.name} - {message}")

                    elif action_type == FilterAction.ALERT:
                        alerts_to_send.append({
                            "rule": rule,
                            "message": message,
                            "alert_data": action,
                        })

                    elif action_type == FilterAction.CAPTURE:
                        should_capture = True

                    elif action_type == FilterAction.FORWARD:
                        # TODO: Implement message forwarding
                        pass

                    elif action_type == FilterAction.MODIFY:
                        # TODO: Implement message modification (advanced)
                        pass

                # Stop processing if blocked
                if not should_pass:
                    break

            # Handle captures
            if should_capture:
                self._capture_message(message)

            # Send alerts
            for alert in alerts_to_send:
                await self._send_alert(alert)

            # Update stats
            if should_pass:
                self.stats["messages_passed"] += 1

            # Update processing time
            processing_time = (time.time() - start_time) * 1000
            self.stats["processing_time_ms"] = (
                0.9 * self.stats["processing_time_ms"] + 0.1 * processing_time
            )

            return should_pass

        except Exception as e:
            logger.error(f"Error processing message through filters: {e}")
            return True  # Pass on error

    def _capture_message(self, message: Dict[str, Any]):
        """Capture message to buffer."""
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = time.time()

        # Add to buffer with size limit
        self.capture_buffer.append(message)
        if len(self.capture_buffer) > self.capture_buffer_size:
            self.capture_buffer.pop(0)

        self.stats["messages_captured"] += 1

    async def _send_alert(self, alert_data: Dict[str, Any]):
        """Send alert for matched rule."""
        try:
            self.stats["alerts_sent"] += 1

            if self.alert_callback:
                await self.alert_callback(alert_data)
            else:
                logger.warning(f"Filter alert: {alert_data['rule'].name}")

        except Exception as e:
            logger.error(f"Error sending filter alert: {e}")

    def get_captured_messages(
        self,
        limit: Optional[int] = None,
        since_timestamp: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Get captured messages."""
        messages = self.capture_buffer

        # Filter by timestamp
        if since_timestamp:
            messages = [
                m for m in messages
                if m.get("timestamp", 0) > since_timestamp
            ]

        # Limit results
        if limit:
            messages = messages[-limit:]

        return messages

    def clear_capture_buffer(self):
        """Clear the capture buffer."""
        self.capture_buffer.clear()
        logger.info("Cleared capture buffer")

    def get_statistics(self) -> Dict[str, Any]:
        """Get filter statistics."""
        self.stats["last_update"] = time.time()
        self.stats["active_rules"] = len([r for r in self.rules.values() if r.enabled])
        self.stats["total_rules"] = len(self.rules)
        self.stats["capture_buffer_size"] = len(self.capture_buffer)

        # Add per-rule statistics
        rule_stats = []
        for rule in self.rules.values():
            rule_stats.append({
                "id": rule.id,
                "name": rule.name,
                "enabled": rule.enabled,
                "priority": rule.priority,
                "matches": rule.statistics["matches"],
                "last_match": rule.statistics["last_match"],
            })

        return {
            **self.stats,
            "rules": rule_stats,
        }

    def reset_statistics(self):
        """Reset all statistics."""
        self.stats = {
            "messages_processed": 0,
            "messages_passed": 0,
            "messages_blocked": 0,
            "messages_captured": 0,
            "alerts_sent": 0,
            "processing_time_ms": 0.0,
            "last_update": time.time(),
        }

        # Reset per-rule statistics
        for rule in self.rules.values():
            rule.statistics = {
                "matches": 0,
                "last_match": 0,
            }

        logger.info("Reset filter statistics")

    def export_rules(self) -> str:
        """Export rules as JSON."""
        rules_data = []
        for rule in self.rules.values():
            rule_dict = {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "enabled": rule.enabled,
                "priority": rule.priority,
                "condition_logic": rule.condition_logic,
                "conditions": [
                    {
                        "field": cond.field.value,
                        "operator": cond.operator.value,
                        "value": cond.value,
                        "case_sensitive": cond.case_sensitive,
                        "negate": cond.negate,
                    }
                    for cond in rule.conditions
                ],
                "actions": rule.actions,
            }
            rules_data.append(rule_dict)

        return json.dumps(rules_data, indent=2)

    def import_rules(self, rules_json: str) -> int:
        """Import rules from JSON."""
        try:
            rules_data = json.loads(rules_json)
            imported = 0

            for rule_dict in rules_data:
                # Skip system rules
                if rule_dict.get("id", "").startswith("system_"):
                    continue

                # Create conditions
                conditions = []
                for cond_dict in rule_dict.get("conditions", []):
                    conditions.append(FilterCondition(
                        field=FilterField(cond_dict["field"]),
                        operator=FilterOperator(cond_dict["operator"]),
                        value=cond_dict["value"],
                        case_sensitive=cond_dict.get("case_sensitive", True),
                        negate=cond_dict.get("negate", False),
                    ))

                # Create rule
                rule = FilterRule(
                    id=rule_dict["id"],
                    name=rule_dict["name"],
                    description=rule_dict.get("description", ""),
                    enabled=rule_dict.get("enabled", True),
                    priority=rule_dict.get("priority", 50),
                    conditions=conditions,
                    condition_logic=rule_dict.get("condition_logic", "AND"),
                    actions=rule_dict.get("actions", []),
                )

                if self.add_rule(rule):
                    imported += 1

            logger.info(f"Imported {imported} filter rules")
            return imported

        except Exception as e:
            logger.error(f"Error importing filter rules: {e}")
            return 0
