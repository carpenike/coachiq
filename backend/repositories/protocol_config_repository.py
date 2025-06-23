"""
Protocol Configuration Repository

Manages protocol configuration storage in SQLite database.
Provides caching and change notification for dynamic protocol management.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from backend.models.protocol_config import (
    ProtocolConfigModel,
    ProtocolConfigUpdate,
)
from backend.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ProtocolConfigRepository(BaseRepository):
    """
    Repository for protocol configuration management.

    Stores protocol enablement and configuration in SQLite,
    allowing runtime changes without application restart.
    """

    def __init__(self, database_manager, performance_monitor):
        """Initialize repository with database connection."""
        super().__init__(database_manager, performance_monitor, "protocol_config")
        self._cache: dict[str, ProtocolConfigModel] = {}
        self._cache_timestamp: datetime | None = None
        self._cache_ttl_seconds = 60  # Cache for 1 minute

    async def initialize(self) -> None:
        """Initialize database schema for protocol configuration."""
        await self._create_tables()
        await self._seed_default_protocols()

    async def _create_tables(self) -> None:
        """Create protocol configuration tables."""
        create_sql = """
        CREATE TABLE IF NOT EXISTS protocol_config (
            protocol_name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            config TEXT NOT NULL DEFAULT '{}',
            priority INTEGER NOT NULL DEFAULT 0,
            requires_restart INTEGER NOT NULL DEFAULT 1,
            last_modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            modified_by TEXT,
            last_health_check TIMESTAMP,
            health_status TEXT,
            error_message TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_protocol_enabled
            ON protocol_config(enabled);
        CREATE INDEX IF NOT EXISTS idx_protocol_priority
            ON protocol_config(priority);
        """

        await self._execute_write(create_sql)
        logger.info("Protocol configuration tables initialized")

    async def _seed_default_protocols(self) -> None:
        """Seed default protocol configurations if not present."""
        # Check if we have any protocols configured
        count_sql = "SELECT COUNT(*) FROM protocol_config"
        result = await self._execute_read(count_sql)

        if result and result[0][0] > 0:
            return  # Already seeded

        # Seed default protocols
        defaults = [
            {
                "protocol_name": "rvc",
                "enabled": True,
                "config": {"always_enabled": True},
                "priority": 0,
                "requires_restart": False,
            },
            {
                "protocol_name": "j1939",
                "enabled": False,
                "config": {
                    "enable_cummins_extensions": True,
                    "enable_allison_extensions": True,
                },
                "priority": 10,
                "requires_restart": True,
            },
            {
                "protocol_name": "firefly",
                "enabled": False,
                "config": {
                    "enable_multiplexing": True,
                    "enable_custom_dgns": True,
                },
                "priority": 20,
                "requires_restart": True,
            },
        ]

        insert_sql = """
        INSERT INTO protocol_config
            (protocol_name, enabled, config, priority, requires_restart)
        VALUES (?, ?, ?, ?, ?)
        """

        for proto in defaults:
            await self._execute_write(
                insert_sql,
                (
                    proto["protocol_name"],
                    1 if proto["enabled"] else 0,
                    json.dumps(proto["config"]),
                    proto["priority"],
                    1 if proto["requires_restart"] else 0,
                ),
            )

        logger.info("Seeded default protocol configurations")

    async def get_protocol_config(
        self, protocol_name: str, use_cache: bool = True
    ) -> ProtocolConfigModel | None:
        """
        Get configuration for a specific protocol.

        Args:
            protocol_name: Name of the protocol
            use_cache: Whether to use cached data

        Returns:
            Protocol configuration or None if not found
        """
        # Check cache first
        if use_cache and self._is_cache_valid():
            return self._cache.get(protocol_name)

        sql = """
        SELECT protocol_name, enabled, config, priority, requires_restart,
               last_modified, modified_by, last_health_check, health_status,
               error_message
        FROM protocol_config
        WHERE protocol_name = ?
        """

        result = await self._execute_read(sql, (protocol_name,))
        if not result:
            return None

        row = result[0]
        config = ProtocolConfigModel(
            protocol_name=row[0],
            enabled=bool(row[1]),
            config=json.loads(row[2]) if row[2] else {},
            priority=row[3],
            requires_restart=bool(row[4]),
            last_modified=datetime.fromisoformat(row[5]) if row[5] else None,
            modified_by=row[6],
            last_health_check=datetime.fromisoformat(row[7]) if row[7] else None,
            health_status=row[8],
            error_message=row[9],
        )

        # Update cache
        self._cache[protocol_name] = config
        return config

    async def get_all_protocols(self, enabled_only: bool = False) -> list[ProtocolConfigModel]:
        """
        Get all protocol configurations.

        Args:
            enabled_only: Whether to return only enabled protocols

        Returns:
            List of protocol configurations
        """
        sql = """
        SELECT protocol_name, enabled, config, priority, requires_restart,
               last_modified, modified_by, last_health_check, health_status,
               error_message
        FROM protocol_config
        """

        if enabled_only:
            sql += " WHERE enabled = 1"

        sql += " ORDER BY priority, protocol_name"

        results = await self._execute_read(sql)
        protocols = []

        for row in results:
            config = ProtocolConfigModel(
                protocol_name=row[0],
                enabled=bool(row[1]),
                config=json.loads(row[2]) if row[2] else {},
                priority=row[3],
                requires_restart=bool(row[4]),
                last_modified=datetime.fromisoformat(row[5]) if row[5] else None,
                modified_by=row[6],
                last_health_check=datetime.fromisoformat(row[7]) if row[7] else None,
                health_status=row[8],
                error_message=row[9],
            )
            protocols.append(config)

            # Update cache
            self._cache[config.protocol_name] = config

        self._cache_timestamp = datetime.utcnow()
        return protocols

    async def update_protocol_config(
        self, protocol_name: str, update: ProtocolConfigUpdate
    ) -> ProtocolConfigModel | None:
        """
        Update protocol configuration.

        Args:
            protocol_name: Name of the protocol
            update: Configuration updates

        Returns:
            Updated configuration or None if not found
        """
        # Get current config
        current = await self.get_protocol_config(protocol_name, use_cache=False)
        if not current:
            return None

        # Build update SQL dynamically
        updates = []
        params = []

        if update.enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if update.enabled else 0)

        if update.config is not None:
            updates.append("config = ?")
            params.append(json.dumps(update.config))

        if update.priority is not None:
            updates.append("priority = ?")
            params.append(update.priority)

        if update.modified_by is not None:
            updates.append("modified_by = ?")
            params.append(update.modified_by)

        # Always update timestamp
        updates.append("last_modified = CURRENT_TIMESTAMP")

        # Build SQL with safe column assignments (no user input in column names)
        sql = f"""
        UPDATE protocol_config
        SET {", ".join(updates)}
        WHERE protocol_name = ?
        """  # nosec B608

        params.append(protocol_name)
        await self._execute_write(sql, params)

        # Invalidate cache
        self._invalidate_cache()

        # Return updated config
        return await self.get_protocol_config(protocol_name, use_cache=False)

    async def update_protocol_health(
        self, protocol_name: str, health_status: str, error_message: str | None = None
    ) -> None:
        """
        Update protocol health status.

        Args:
            protocol_name: Name of the protocol
            health_status: Current health status
            error_message: Optional error message
        """
        sql = """
        UPDATE protocol_config
        SET last_health_check = CURRENT_TIMESTAMP,
            health_status = ?,
            error_message = ?
        WHERE protocol_name = ?
        """

        await self._execute_write(sql, (health_status, error_message, protocol_name))

        # Update cache if present
        if protocol_name in self._cache:
            self._cache[protocol_name].last_health_check = datetime.utcnow()
            self._cache[protocol_name].health_status = health_status
            self._cache[protocol_name].error_message = error_message

    async def get_protocols_requiring_restart(self) -> list[str]:
        """Get list of protocols that require restart when changed."""
        sql = """
        SELECT protocol_name
        FROM protocol_config
        WHERE requires_restart = 1 AND enabled = 1
        ORDER BY priority
        """

        results = await self._execute_read(sql)
        return [row[0] for row in results]

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._cache_timestamp:
            return False

        age = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return age < self._cache_ttl_seconds

    def _invalidate_cache(self) -> None:
        """Invalidate the configuration cache."""
        self._cache.clear()
        self._cache_timestamp = None

    async def get_health_status(self) -> dict:
        """Get repository health status."""
        try:
            # Count protocols
            count_sql = "SELECT COUNT(*), SUM(enabled) FROM protocol_config"
            result = await self._execute_read(count_sql)
            total_protocols = result[0][0] if result else 0
            enabled_protocols = result[0][1] if result else 0

            return {
                "healthy": True,
                "total_protocols": total_protocols,
                "enabled_protocols": enabled_protocols,
                "cache_valid": self._is_cache_valid(),
            }
        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return {
                "healthy": False,
                "error": str(e),
            }
