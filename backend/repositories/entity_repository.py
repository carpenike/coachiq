"""Entity Repositories

Repositories for entity data management including:
- Entity configuration storage
- Runtime state persistence
- Historical data tracking
- CAN command auditing
"""

import logging
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class EntityConfigRepository(MonitoredRepository):
    """Repository for entity configuration management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage (would integrate with YAML files in production)
        self._entity_configs: dict[str, dict[str, Any]] = {}
        self._coach_mappings: dict[str, dict[str, Any]] = {}
        self._coach_metadata: dict[str, Any] = {
            "version": "1.0",
            "last_updated": datetime.now(UTC).isoformat(),
        }

    @MonitoredRepository._monitored_operation("load_coach_mapping")
    async def load_coach_mapping(self, coach_model: str) -> dict[str, Any]:
        """Load coach mapping configuration.

        Args:
            coach_model: Coach model identifier

        Returns:
            Coach mapping configuration
        """
        # In production, would load from YAML files
        if coach_model not in self._coach_mappings:
            # Create default mapping
            self._coach_mappings[coach_model] = {
                "model": coach_model,
                "entities": {},
                "created_at": datetime.now(UTC).isoformat(),
            }

        return self._coach_mappings[coach_model]

    @MonitoredRepository._monitored_operation("save_entity_mapping")
    async def save_entity_mapping(self, entity_id: str, config: dict[str, Any]) -> bool:
        """Save entity mapping configuration.

        Args:
            entity_id: Entity identifier
            config: Entity configuration

        Returns:
            True if saved successfully
        """
        self._entity_configs[entity_id] = {
            **config,
            "entity_id": entity_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        logger.debug(f"Saved entity mapping for {entity_id}")
        return True

    @MonitoredRepository._monitored_operation("get_all_entity_configs")
    async def get_all_entity_configs(self) -> dict[str, dict[str, Any]]:
        """Get all entity configurations.

        Returns:
            Dictionary of entity configurations
        """
        return dict(self._entity_configs)

    @MonitoredRepository._monitored_operation("delete_entity_config")
    async def delete_entity_config(self, entity_id: str) -> bool:
        """Delete entity configuration.

        Args:
            entity_id: Entity to delete

        Returns:
            True if deleted successfully
        """
        if entity_id in self._entity_configs:
            del self._entity_configs[entity_id]
            logger.info(f"Deleted entity config for {entity_id}")
            return True
        return False

    @MonitoredRepository._monitored_operation("get_coach_metadata")
    async def get_coach_metadata(self) -> dict[str, Any]:
        """Get coach metadata.

        Returns:
            Coach metadata information
        """
        return dict(self._coach_metadata)


class EntityStateRepository(MonitoredRepository):
    """Repository for runtime entity state management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage
        self._entity_states: dict[str, dict[str, Any]] = {}
        self._transient_states: dict[str, dict[str, Any]] = {}
        self._optimistic_updates: dict[str, dict[str, Any]] = {}

    @MonitoredRepository._monitored_operation("save_entity_state")
    async def save_entity_state(self, entity_id: str, state: dict[str, Any]) -> bool:
        """Save entity runtime state.

        Args:
            entity_id: Entity identifier
            state: Runtime state data

        Returns:
            True if saved successfully
        """
        self._entity_states[entity_id] = {
            **state,
            "entity_id": entity_id,
            "last_updated": datetime.now(UTC).isoformat(),
        }

        logger.debug(f"Saved state for entity {entity_id}")
        return True

    @MonitoredRepository._monitored_operation("get_entity_state")
    async def get_entity_state(self, entity_id: str) -> dict[str, Any] | None:
        """Get entity runtime state.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity state or None
        """
        return self._entity_states.get(entity_id)

    @MonitoredRepository._monitored_operation("save_bulk_states")
    async def save_bulk_states(self, states: dict[str, dict[str, Any]]) -> int:
        """Save multiple entity states.

        Args:
            states: Dictionary of entity states

        Returns:
            Number of states saved
        """
        timestamp = datetime.now(UTC).isoformat()
        count = 0

        for entity_id, state in states.items():
            self._entity_states[entity_id] = {
                **state,
                "entity_id": entity_id,
                "last_updated": timestamp,
            }
            count += 1

        logger.info(f"Saved {count} entity states in bulk")
        return count

    @MonitoredRepository._monitored_operation("get_all_states")
    async def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Get all entity states.

        Returns:
            Dictionary of all entity states
        """
        return dict(self._entity_states)

    @MonitoredRepository._monitored_operation("save_transient_state")
    async def save_transient_state(self, entity_id: str, key: str, value: Any) -> bool:
        """Save transient state value.

        Args:
            entity_id: Entity identifier
            key: State key
            value: State value

        Returns:
            True if saved successfully
        """
        if entity_id not in self._transient_states:
            self._transient_states[entity_id] = {}

        self._transient_states[entity_id][key] = {
            "value": value,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        logger.debug(f"Saved transient state {key} for entity {entity_id}")
        return True

    @MonitoredRepository._monitored_operation("get_transient_state")
    async def get_transient_state(self, entity_id: str, key: str) -> Any | None:
        """Get transient state value.

        Args:
            entity_id: Entity identifier
            key: State key

        Returns:
            State value or None
        """
        if entity_id in self._transient_states:
            state_data = self._transient_states[entity_id].get(key)
            if state_data:
                return state_data.get("value")
        return None

    @MonitoredRepository._monitored_operation("track_optimistic_update")
    async def track_optimistic_update(
        self, entity_id: str, command: dict[str, Any], deadline: float
    ) -> str:
        """Track an optimistic update for reconciliation.

        Args:
            entity_id: Entity identifier
            command: Command that triggered update
            deadline: Reconciliation deadline timestamp

        Returns:
            Tracking ID
        """
        tracking_id = str(uuid.uuid4())

        self._optimistic_updates[tracking_id] = {
            "entity_id": entity_id,
            "command": command,
            "sent_at": time.time(),
            "deadline": deadline,
            "reconciled": False,
        }

        return tracking_id

    @MonitoredRepository._monitored_operation("reconcile_update")
    async def reconcile_update(self, tracking_id: str, actual_state: dict[str, Any]) -> bool:
        """Reconcile an optimistic update with actual state.

        Args:
            tracking_id: Update tracking ID
            actual_state: Actual hardware state

        Returns:
            True if reconciled successfully
        """
        if tracking_id in self._optimistic_updates:
            update = self._optimistic_updates[tracking_id]
            update["reconciled"] = True
            update["actual_state"] = actual_state
            update["reconciled_at"] = time.time()

            # Log if there's a discrepancy
            expected = update["command"].get("state")
            actual = actual_state.get("state")
            if expected != actual:
                logger.warning(
                    f"Optimistic update discrepancy for {update['entity_id']}: "
                    f"expected={expected}, actual={actual}"
                )

            return True
        return False


class EntityHistoryRepository(MonitoredRepository):
    """Repository for entity state history tracking."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage with limited retention
        self._history: list[dict[str, Any]] = []
        self._history_by_entity: dict[str, list[int]] = defaultdict(list)
        self._max_history_size = 50000

    @MonitoredRepository._monitored_operation("record_state_change")
    async def record_state_change(
        self,
        entity_id: str,
        timestamp: float,
        old_state: Any,
        new_state: Any,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record entity state change.

        Args:
            entity_id: Entity identifier
            timestamp: Change timestamp
            old_state: Previous state
            new_state: New state
            metadata: Additional metadata

        Returns:
            Change ID
        """
        change_id = str(uuid.uuid4())

        change_record = {
            "change_id": change_id,
            "entity_id": entity_id,
            "timestamp": timestamp,
            "old_state": old_state,
            "new_state": new_state,
            "metadata": metadata or {},
            "recorded_at": datetime.now(UTC).isoformat(),
        }

        # Add to history
        index = len(self._history)
        self._history.append(change_record)
        self._history_by_entity[entity_id].append(index)

        # Trim if needed
        if len(self._history) > self._max_history_size:
            self._trim_old_history()

        logger.debug(f"Recorded state change for entity {entity_id}")
        return change_id

    @MonitoredRepository._monitored_operation("get_entity_history")
    async def get_entity_history(
        self, entity_id: str, start_time: float, end_time: float
    ) -> list[dict[str, Any]]:
        """Get entity history within time range.

        Args:
            entity_id: Entity identifier
            start_time: Start timestamp
            end_time: End timestamp

        Returns:
            List of state changes
        """
        history = []

        for index in reversed(self._history_by_entity.get(entity_id, [])):
            if index < len(self._history):
                record = self._history[index]
                if start_time <= record["timestamp"] <= end_time:
                    history.append(record)
                elif record["timestamp"] < start_time:
                    break  # Older than range

        return history

    @MonitoredRepository._monitored_operation("get_latest_states")
    async def get_latest_states(self, entity_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get latest state changes for an entity.

        Args:
            entity_id: Entity identifier
            limit: Maximum number of changes

        Returns:
            List of recent state changes
        """
        indices = self._history_by_entity.get(entity_id, [])
        recent_indices = indices[-limit:] if len(indices) > limit else indices

        history = []
        for index in reversed(recent_indices):
            if index < len(self._history):
                history.append(self._history[index])

        return history

    @MonitoredRepository._monitored_operation("cleanup_old_history")
    async def cleanup_old_history(self, retention_days: int = 7) -> int:
        """Clean up old history records.

        Args:
            retention_days: Days to retain history

        Returns:
            Number of records cleaned
        """
        cutoff = time.time() - (retention_days * 24 * 3600)
        original_count = len(self._history)

        # Filter history
        self._history = [record for record in self._history if record["timestamp"] > cutoff]

        # Rebuild indices
        self._rebuild_indices()

        cleaned = original_count - len(self._history)
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old history records")

        return cleaned

    def _trim_old_history(self) -> None:
        """Trim oldest history when at capacity."""
        # Keep most recent 80% of records
        keep_count = int(self._max_history_size * 0.8)
        self._history = self._history[-keep_count:]
        self._rebuild_indices()

        logger.info("Trimmed old history records")

    def _rebuild_indices(self) -> None:
        """Rebuild entity indices after history modification."""
        self._history_by_entity.clear()

        for index, record in enumerate(self._history):
            entity_id = record["entity_id"]
            self._history_by_entity[entity_id].append(index)


class CanCommandRepository(MonitoredRepository):
    """Repository for CAN command auditing."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage
        self._commands: list[dict[str, Any]] = []
        self._commands_by_entity: dict[str, list[int]] = defaultdict(list)
        self._commands_by_user: dict[str, list[int]] = defaultdict(list)
        self._max_commands = 10000

    @MonitoredRepository._monitored_operation("record_command")
    async def record_command(
        self,
        entity_id: str,
        command: dict[str, Any],
        timestamp: float,
        user_id: str | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> str:
        """Record a CAN command.

        Args:
            entity_id: Entity that received command
            command: Command details
            timestamp: Command timestamp
            user_id: User who issued command
            success: Whether command succeeded
            error: Error message if failed

        Returns:
            Command ID
        """
        command_id = str(uuid.uuid4())

        command_record = {
            "command_id": command_id,
            "entity_id": entity_id,
            "command": command,
            "timestamp": timestamp,
            "user_id": user_id,
            "success": success,
            "error": error,
            "recorded_at": datetime.now(UTC).isoformat(),
        }

        # Add to storage
        index = len(self._commands)
        self._commands.append(command_record)
        self._commands_by_entity[entity_id].append(index)

        if user_id:
            self._commands_by_user[user_id].append(index)

        # Trim if needed
        if len(self._commands) > self._max_commands:
            self._trim_old_commands()

        logger.debug(
            f"Recorded {'successful' if success else 'failed'} command for entity {entity_id}"
        )
        return command_id

    @MonitoredRepository._monitored_operation("get_recent_commands")
    async def get_recent_commands(self, entity_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent commands for an entity.

        Args:
            entity_id: Entity identifier
            limit: Maximum number of commands

        Returns:
            List of recent commands
        """
        indices = self._commands_by_entity.get(entity_id, [])
        recent_indices = indices[-limit:] if len(indices) > limit else indices

        commands = []
        for index in reversed(recent_indices):
            if index < len(self._commands):
                commands.append(self._commands[index])

        return commands

    @MonitoredRepository._monitored_operation("get_commands_by_user")
    async def get_commands_by_user(self, user_id: str, hours: int = 24) -> list[dict[str, Any]]:
        """Get commands issued by a user.

        Args:
            user_id: User identifier
            hours: Time window in hours

        Returns:
            List of commands
        """
        cutoff = time.time() - (hours * 3600)
        commands = []

        for index in reversed(self._commands_by_user.get(user_id, [])):
            if index < len(self._commands):
                command = self._commands[index]
                if command["timestamp"] < cutoff:
                    break
                commands.append(command)

        return commands

    @MonitoredRepository._monitored_operation("get_failed_commands")
    async def get_failed_commands(self, hours: int = 1) -> list[dict[str, Any]]:
        """Get failed commands within time window.

        Args:
            hours: Time window in hours

        Returns:
            List of failed commands
        """
        cutoff = time.time() - (hours * 3600)
        failed_commands = []

        # Scan recent commands
        for command in reversed(self._commands):
            if command["timestamp"] < cutoff:
                break
            if not command["success"]:
                failed_commands.append(command)

        return failed_commands

    def _trim_old_commands(self) -> None:
        """Trim oldest commands when at capacity."""
        # Keep most recent 80% of commands
        keep_count = int(self._max_commands * 0.8)
        self._commands = self._commands[-keep_count:]

        # Rebuild indices
        self._commands_by_entity.clear()
        self._commands_by_user.clear()

        for index, command in enumerate(self._commands):
            entity_id = command["entity_id"]
            self._commands_by_entity[entity_id].append(index)

            user_id = command.get("user_id")
            if user_id:
                self._commands_by_user[user_id].append(index)

        logger.info("Trimmed old command records")
