"""
Test suite for the core dependencies module.

This module tests FastAPI dependency injection functions for accessing
application state and services.
"""

from unittest.mock import Mock

import pytest

from backend.core.dependencies import (
    get_app_state,
    get_can_service,
    get_config_service,
    get_docs_service,
    get_entity_service,
    get_github_update_checker,
    get_service_registry,
    get_vector_service,
)


class TestDependencies:
    """Test class for dependency injection functions."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Create a mock request object
        self.mock_request = Mock()
        self.mock_app = Mock()
        self.mock_request.app = self.mock_app
        self.mock_app.state = Mock()

    @pytest.mark.unit
    def test_get_app_state_success(self):
        """Test successful retrieval of app state."""
        mock_state = Mock()
        self.mock_app.state.app_state = mock_state

        result = get_app_state(self.mock_request)

        assert result is mock_state

    @pytest.mark.unit
    def test_get_app_state_not_initialized(self):
        """Test error when app state is not initialized."""
        # Don't set the app_state attribute
        del self.mock_app.state.app_state

        with pytest.raises(RuntimeError, match="Application state not initialized"):
            get_app_state(self.mock_request)

    @pytest.mark.unit
    def test_get_entity_service_success(self):
        """Test successful retrieval of entity service."""
        mock_service = Mock()
        self.mock_app.state.entity_service = mock_service

        result = get_entity_service(self.mock_request)

        assert result is mock_service

    @pytest.mark.unit
    def test_get_entity_service_not_initialized(self):
        """Test error when entity service is not initialized."""
        del self.mock_app.state.entity_service

        with pytest.raises(RuntimeError, match="Entity service not initialized"):
            get_entity_service(self.mock_request)

    @pytest.mark.unit
    def test_get_can_service_success(self):
        """Test successful retrieval of CAN service."""
        mock_service = Mock()
        self.mock_app.state.can_service = mock_service

        result = get_can_service(self.mock_request)

        assert result is mock_service

    @pytest.mark.unit
    def test_get_can_service_not_initialized(self):
        """Test error when CAN service is not initialized."""
        del self.mock_app.state.can_service

        with pytest.raises(RuntimeError, match="CAN service not initialized"):
            get_can_service(self.mock_request)

    @pytest.mark.unit
    def test_get_service_registry_success(self):
        """Test successful retrieval of service registry."""
        mock_registry = Mock()
        self.mock_app.state.service_registry = mock_registry

        result = get_service_registry()

        assert result is mock_registry

    @pytest.mark.unit
    def test_get_service_registry_not_initialized(self):
        """Test error when service registry is not initialized."""
        # Need to mock the module-level _service_registry
        import backend.core.dependencies

        original_registry = backend.core.dependencies._service_registry
        backend.core.dependencies._service_registry = None

        try:
            with pytest.raises(RuntimeError, match="Service registry not initialized"):
                get_service_registry()
        finally:
            # Restore original value
            backend.core.dependencies._service_registry = original_registry

    @pytest.mark.unit
    def test_get_config_service_success(self):
        """Test successful retrieval of config service."""
        mock_service = Mock()
        self.mock_app.state.config_service = mock_service

        result = get_config_service(self.mock_request)

        assert result is mock_service

    @pytest.mark.unit
    def test_get_config_service_not_initialized(self):
        """Test error when config service is not initialized."""
        del self.mock_app.state.config_service

        with pytest.raises(RuntimeError, match="Config service not initialized"):
            get_config_service(self.mock_request)

    @pytest.mark.unit
    def test_get_docs_service_success(self):
        """Test successful retrieval of docs service."""
        mock_service = Mock()
        self.mock_app.state.docs_service = mock_service

        result = get_docs_service(self.mock_request)

        assert result is mock_service

    @pytest.mark.unit
    def test_get_docs_service_not_initialized(self):
        """Test error when docs service is not initialized."""
        del self.mock_app.state.docs_service

        with pytest.raises(RuntimeError, match="Docs service not initialized"):
            get_docs_service(self.mock_request)

    @pytest.mark.unit
    def test_get_vector_service_success(self):
        """Test successful retrieval of vector service."""
        mock_service = Mock()
        self.mock_app.state.vector_service = mock_service

        result = get_vector_service(self.mock_request)

        assert result is mock_service

    @pytest.mark.unit
    def test_get_vector_service_not_initialized(self):
        """Test error when vector service is not initialized."""
        del self.mock_app.state.vector_service

        with pytest.raises(RuntimeError, match="Vector service not initialized"):
            get_vector_service(self.mock_request)

    @pytest.mark.unit
    def test_get_github_update_checker_success(self):
        """Test successful retrieval of GitHub update checker."""
        mock_service_registry = Mock()
        mock_service = Mock()
        mock_update_checker = Mock()

        # Setup service registry
        self.mock_app.state.service_registry = mock_service_registry
        mock_service_registry.has_service.return_value = True
        mock_service_registry.get_service.return_value = mock_service
        mock_service.get_update_checker.return_value = mock_update_checker

        result = get_github_update_checker(self.mock_request)

        assert result is mock_update_checker
        mock_service.get_update_checker.assert_called_once()

    @pytest.mark.unit
    def test_get_github_update_checker_service_not_found(self):
        """Test error when GitHub update checker service is not found."""
        mock_service_registry = Mock()
        self.mock_app.state.service_registry = mock_service_registry
        mock_service_registry.has_service.return_value = False

        with pytest.raises(RuntimeError, match="GitHub update checker service not found"):
            get_github_update_checker(self.mock_request)

    @pytest.mark.unit
    def test_get_github_update_checker_service_disabled(self):
        """Test error when GitHub update checker service is disabled."""
        mock_service_registry = Mock()
        mock_service = Mock()

        self.mock_app.state.service_registry = mock_service_registry
        mock_service_registry.has_service.return_value = True
        mock_service_registry.get_service.return_value = mock_service
        mock_service.enabled = False

        with pytest.raises(RuntimeError, match="GitHub update checker service is not enabled"):
            get_github_update_checker(self.mock_request)

    @pytest.mark.unit
    def test_get_github_update_checker_service_registry_not_initialized(self):
        """Test error when service registry is not initialized for GitHub update checker."""
        del self.mock_app.state.service_registry

        with pytest.raises(RuntimeError, match="Service registry not initialized"):
            get_github_update_checker(self.mock_request)

    @pytest.mark.integration
    def test_multiple_dependencies_together(self):
        """Test that multiple dependencies can be retrieved together."""
        # Setup all services
        mock_app_state = Mock()
        mock_entity_service = Mock()
        mock_can_service = Mock()
        mock_config_service = Mock()

        self.mock_app.state.app_state = mock_app_state
        self.mock_app.state.entity_service = mock_entity_service
        self.mock_app.state.can_service = mock_can_service
        self.mock_app.state.config_service = mock_config_service

        # Test all dependencies can be retrieved
        assert get_app_state(self.mock_request) is mock_app_state
        assert get_entity_service(self.mock_request) is mock_entity_service
        assert get_can_service(self.mock_request) is mock_can_service
        assert get_config_service(self.mock_request) is mock_config_service

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "dependency_func,service_name,error_message",
        [
            (get_app_state, "app_state", "Application state not initialized"),
            (get_entity_service, "entity_service", "Entity service not initialized"),
            (get_can_service, "can_service", "CAN service not initialized"),
            (get_config_service, "config_service", "Config service not initialized"),
            (get_docs_service, "docs_service", "Docs service not initialized"),
            (get_vector_service, "vector_service", "Vector service not initialized"),
        ],
    )
    def test_all_dependencies_error_handling(self, dependency_func, service_name, error_message):
        """Test error handling for all dependency functions using parametrization."""
        # Ensure the service is not set
        if hasattr(self.mock_app.state, service_name):
            delattr(self.mock_app.state, service_name)

        with pytest.raises(RuntimeError, match=error_message):
            dependency_func(self.mock_request)
