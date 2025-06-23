"""
Tests for CoreServices - mandatory infrastructure service management.

This module tests the CoreServices class which manages mandatory infrastructure
services like persistence and database management that must always be available.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.core.services import (
    CoreServices,
    CoreServicesError,
    get_core_services,
    initialize_core_services,
    shutdown_core_services,
)


class TestCoreServices:
    """Test the CoreServices class functionality."""

    def test_init(self):
        """Test CoreServices initialization."""
        core_services = CoreServices()

        assert core_services._persistence is None
        assert core_services._database_manager is None
        assert not core_services.initialized

    @pytest.mark.asyncio
    async def test_startup_success(self):
        """Test successful CoreServices startup."""
        core_services = CoreServices()

        with (
            patch("backend.core.services.PersistenceService") as mock_persistence,
            patch("backend.core.services.DatabaseManager") as mock_db_manager,
            patch.object(core_services, "_validate_database_schema") as mock_validate,
        ):
            mock_persistence_instance = Mock()
            mock_db_manager_instance = Mock()
            mock_persistence.return_value = mock_persistence_instance
            mock_db_manager.return_value = mock_db_manager_instance
            mock_validate.return_value = None

            await core_services.startup()

            assert core_services._persistence is not None
            assert core_services._database_manager is not None
            assert core_services.initialized

            # Verify the persistence service was configured with database manager
            mock_persistence_instance.set_database_manager.assert_called_once_with(
                mock_db_manager_instance
            )

    @pytest.mark.asyncio
    async def test_startup_failure_cleanup(self):
        """Test that startup failure cleans up partially initialized services."""
        core_services = CoreServices()

        with (
            patch("backend.core.services.PersistenceService") as mock_persistence,
            patch("backend.core.services.DatabaseManager") as mock_db_manager,
            patch.object(core_services, "_validate_database_schema") as mock_validate,
        ):
            mock_persistence.return_value = Mock()
            mock_db_manager.side_effect = Exception("Database init failed")

            with pytest.raises(CoreServicesError, match="Failed to initialize core services"):
                await core_services.startup()

            assert not core_services.initialized
            # Ensure shutdown was called for cleanup
            assert core_services._persistence is None

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test CoreServices shutdown sequence."""
        core_services = CoreServices()

        # Mock initialized services
        mock_db_manager = AsyncMock()
        mock_persistence = AsyncMock()
        core_services._database_manager = mock_db_manager
        core_services._persistence = mock_persistence
        core_services._initialized = True

        await core_services.shutdown()

        # Verify shutdown was called in reverse order
        mock_db_manager.shutdown.assert_called_once()
        mock_persistence.shutdown.assert_called_once()
        assert not core_services.initialized

    @pytest.mark.asyncio
    async def test_shutdown_with_errors(self):
        """Test that shutdown continues even if individual services fail."""
        core_services = CoreServices()

        # Mock services that will fail during shutdown
        mock_db_manager = AsyncMock()
        mock_persistence = AsyncMock()
        mock_db_manager.shutdown.side_effect = Exception("DB shutdown failed")
        mock_persistence.shutdown.side_effect = Exception("Persistence shutdown failed")

        core_services._database_manager = mock_db_manager
        core_services._persistence = mock_persistence
        core_services._initialized = True

        # Should not raise even with failures
        await core_services.shutdown()

        # Both shutdowns should have been attempted
        mock_db_manager.shutdown.assert_called_once()
        mock_persistence.shutdown.assert_called_once()
        assert not core_services.initialized

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test CoreServices health check functionality."""
        core_services = CoreServices()

        # Mock healthy services
        mock_db_manager = AsyncMock()
        mock_persistence = AsyncMock()
        mock_db_manager.health_check = AsyncMock()
        mock_persistence.health_check = AsyncMock()

        core_services._database_manager = mock_db_manager
        core_services._persistence = mock_persistence

        health = await core_services.check_health()

        assert "database_manager" in health
        assert "persistence" in health
        assert health["database_manager"]["status"] == "healthy"
        assert health["persistence"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_with_failures(self):
        """Test health check when services are unhealthy."""
        core_services = CoreServices()

        # Mock failing services
        mock_db_manager = AsyncMock()
        mock_persistence = AsyncMock()
        mock_db_manager.health_check.side_effect = Exception("DB unhealthy")
        mock_persistence.health_check = AsyncMock()  # This one works

        core_services._database_manager = mock_db_manager
        core_services._persistence = mock_persistence

        health = await core_services.check_health()

        assert health["database_manager"]["status"] == "unhealthy"
        assert "error" in health["database_manager"]
        assert health["persistence"]["status"] == "healthy"

    def test_persistence_property(self):
        """Test persistence property access."""
        core_services = CoreServices()

        # Should raise if not initialized
        with pytest.raises(RuntimeError, match="Core services not initialized"):
            _ = core_services.persistence

        # Should work if initialized
        mock_persistence = Mock()
        core_services._persistence = mock_persistence
        assert core_services.persistence is mock_persistence

    def test_database_manager_property(self):
        """Test database_manager property access."""
        core_services = CoreServices()

        # Should raise if not initialized
        with pytest.raises(RuntimeError, match="Core services not initialized"):
            _ = core_services.database_manager

        # Should work if initialized
        mock_db_manager = Mock()
        core_services._database_manager = mock_db_manager
        assert core_services.database_manager is mock_db_manager

    @pytest.mark.asyncio
    async def test_database_schema_validation(self):
        """Test database schema validation during startup."""
        core_services = CoreServices()

        with (
            patch("backend.core.services.PersistenceService") as mock_persistence,
            patch("backend.core.services.DatabaseManager") as mock_db_manager,
            patch("backend.core.config.get_persistence_settings") as mock_get_settings,
            patch("alembic.config.Config") as mock_alembic_config,
            patch("alembic.script.ScriptDirectory") as mock_script_dir,
            patch("sqlalchemy.create_engine") as mock_create_engine,
        ):
            # Mock successful validation
            mock_persistence.return_value = Mock()
            mock_db_manager_instance = Mock()
            mock_db_manager.return_value = mock_db_manager_instance

            mock_settings = Mock()
            mock_settings.get_database_dir.return_value = Mock(__truediv__=lambda x, y: "test.db")
            mock_get_settings.return_value = mock_settings

            mock_script = Mock()
            mock_script.get_current_head.return_value = "abc123"
            mock_script_dir.from_config.return_value = mock_script

            mock_engine = Mock()
            mock_connection = Mock()
            mock_context = Mock()
            mock_context.get_current_revision.return_value = "abc123"  # Same as head
            mock_engine.connect.return_value.__enter__.return_value = mock_connection
            mock_create_engine.return_value = mock_engine

            with patch("alembic.runtime.migration.MigrationContext") as mock_migration_context:
                mock_migration_context.configure.return_value = mock_context

                await core_services.startup()

                assert core_services.initialized
                # Verify Alembic was called for validation
                mock_alembic_config.assert_called_once_with("alembic.ini")


class TestCoreServicesGlobalFunctions:
    """Test global CoreServices management functions."""

    @pytest.mark.asyncio
    async def test_initialize_core_services(self):
        """Test global CoreServices initialization."""
        with patch("backend.core.services.CoreServices") as mock_core_services_class:
            mock_instance = AsyncMock()
            mock_core_services_class.return_value = mock_instance

            result = await initialize_core_services()

            mock_instance.startup.assert_called_once()
            assert result is mock_instance

    @pytest.mark.asyncio
    async def test_initialize_core_services_already_initialized(self):
        """Test that initialize_core_services handles already initialized state."""
        # First call should initialize
        with patch("backend.core.services.CoreServices") as mock_core_services_class:
            mock_instance = AsyncMock()
            mock_core_services_class.return_value = mock_instance

            result1 = await initialize_core_services()
            result2 = await initialize_core_services()

            # Should return same instance
            assert result1 is result2
            # Startup should only be called once
            mock_instance.startup.assert_called_once()

    def test_get_core_services_not_initialized(self):
        """Test get_core_services raises when not initialized."""
        # Reset global state
        import backend.core.services

        backend.core.services._core_services_instance = None

        with pytest.raises(RuntimeError, match="Core services not initialized"):
            get_core_services()

    @pytest.mark.asyncio
    async def test_shutdown_core_services(self):
        """Test global CoreServices shutdown."""
        # Initialize first
        with patch("backend.core.services.CoreServices") as mock_core_services_class:
            mock_instance = AsyncMock()
            mock_core_services_class.return_value = mock_instance

            await initialize_core_services()

            # Now test shutdown
            await shutdown_core_services()

            mock_instance.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_core_services_not_initialized(self):
        """Test shutdown when not initialized."""
        # Reset global state
        import backend.core.services

        backend.core.services._core_services_instance = None

        # Should not raise
        await shutdown_core_services()


class TestCoreServicesIntegration:
    """Integration tests for CoreServices with real components."""

    @pytest.mark.asyncio
    async def test_real_components_integration(self, test_database_settings):
        """Test CoreServices with real database components."""
        from backend.core.services import CoreServices

        core_services = CoreServices()

        with patch("backend.core.config.get_persistence_settings") as mock_get_settings:
            mock_get_settings.return_value = test_database_settings

            # This should use real services but with test database
            await core_services.startup()

            try:
                assert core_services.initialized
                assert core_services.persistence is not None
                assert core_services.database_manager is not None

                # Test that services can be used
                health = await core_services.check_health()
                assert "persistence" in health
                assert "database_manager" in health

            finally:
                await core_services.shutdown()
