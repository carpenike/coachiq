"""
Global test configuration and fixtures for the CoachIQ backend test suite.

This module provides reusable fixtures for testing FastAPI endpoints, services,
and integrations with proper mocking and isolation.
"""

import asyncio
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from backend.core.dependencies import (
    get_can_facade,
    get_config_service,
    get_entity_service,
)

# Persistence is now default - using dependencies from core.dependencies
from backend.core.services import CoreServices
from backend.main import app
from backend.services.database_engine import DatabaseSettings
from backend.services.database_manager import DatabaseManager

# Import performance test fixtures
# performance_timer is imported here to make it available as a fixture
# pylint: disable=unused-import


def _setup_test_app_state() -> None:
    """
    Set up minimal app state for testing.
    This ensures that the app.state has the necessary attributes
    that the dependency functions expect.
    """
    if not hasattr(app.state, "service_registry"):
        # Create basic mocks for app state
        app.state.service_registry = Mock()
        app.state.entity_service = Mock()
        app.state.can_service = Mock()
        app.state.config_service = Mock()
        app.state.app_state = Mock()
        app.state.docs_service = Mock()
        app.state.vector_service = Mock()


# ================================
# Test Database Configuration
# ================================


@pytest.fixture
def test_database_path() -> Generator[Path, None, None]:
    """
    Create a temporary SQLite database file for testing.

    This fixture creates a real SQLite database file in a temporary directory,
    which provides more realistic testing scenarios than in-memory databases.
    The database file is automatically cleaned up after the test.
    """
    with tempfile.TemporaryDirectory(prefix="coachiq_test_") as temp_dir:
        db_path = Path(temp_dir) / "test_coachiq.db"
        yield db_path
        # Cleanup is automatic when temp_dir context exits


@pytest.fixture
def test_database_settings(test_database_path: Path) -> DatabaseSettings:
    """
    Create database settings configured for testing with real SQLite files.

    Uses the temporary database path from test_database_path fixture
    to ensure each test gets a clean, isolated database.
    """
    return DatabaseSettings(
        sqlite_path=str(test_database_path),
        sqlite_timeout=10,  # Shorter timeout for tests
        echo_sql=False,  # Set to True to debug SQL in tests
        pool_size=1,  # Minimal pool for tests
        max_overflow=0,  # No overflow for tests
    )


@pytest.fixture
async def test_database_manager(
    test_database_settings: DatabaseSettings,
) -> AsyncGenerator[DatabaseManager, None]:
    """
    Create and initialize a test database manager with real SQLite.

    This fixture provides a fully initialized database manager that uses
    a temporary SQLite file, ensuring tests work with actual database
    operations rather than mocked persistence.
    """
    manager = DatabaseManager(test_database_settings)

    # Initialize the database manager
    initialized = await manager.initialize()
    if not initialized:
        pytest.fail("Failed to initialize test database manager")

    try:
        yield manager
    finally:
        # Clean up the database manager
        await manager.cleanup()


@pytest.fixture
async def test_persistence_feature(
    test_database_manager: DatabaseManager,
) -> AsyncGenerator[object, None]:
    """
    Create and initialize a test persistence feature with real SQLite.

    This fixture provides a fully configured persistence feature that uses
    the test database manager, enabling realistic testing of persistence
    operations without mocking the database layer.
    """
    # Initialize persistence feature with test configuration
    # persistence_feature = initialize_persistence_feature(  # Commented out - persistence is now default
    #     config={"database_manager": test_database_manager}
    # )

    # Set the database manager directly on the feature
    # Note: Accessing private member for test setup - this is acceptable in test code
    # persistence_feature._database_manager = test_database_manager  # Commented out - persistence is now default

    # try:
    #     # Start the persistence feature
    #     await persistence_feature.startup()
    #     yield persistence_feature
    # finally:
    #     # Clean up the persistence feature
    #     await persistence_feature.shutdown()
    # Temporary: return None since persistence is now default
    return None


# ================================
# CoreServices Test Fixtures
# ================================


@pytest.fixture
async def test_core_services(
    test_database_manager: DatabaseManager,
) -> AsyncGenerator[CoreServices, None]:
    """
    Create and initialize CoreServices with test database.

    This fixture provides a fully initialized CoreServices instance that uses
    the test database manager, enabling realistic testing of core infrastructure
    services without mocking the service layer.
    """
    from unittest.mock import patch

    core_services = CoreServices()

    # Patch the service initialization to use our test database manager
    with (
        patch("backend.core.services.PersistenceService") as mock_persistence_class,
        patch("backend.core.services.DatabaseManager") as mock_db_manager_class,
    ):
        # Create persistence service mock that works with our test database
        mock_persistence = Mock()
        mock_persistence.set_database_manager = Mock()
        mock_persistence_class.return_value = mock_persistence

        # Use the test database manager directly
        mock_db_manager_class.return_value = test_database_manager

        # Patch database schema validation to avoid Alembic issues in tests
        with patch.object(core_services, "_validate_database_schema"):
            await core_services.startup()

        try:
            yield core_services
        finally:
            await core_services.shutdown()


@pytest.fixture
def mock_core_services() -> CoreServices:
    """
    Create a CoreServices instance with fully mocked services.

    Use this fixture for unit tests that need to isolate the code under test
    from actual database operations. All core services are mocked.
    """
    core_services = CoreServices()

    # Mock all services
    mock_persistence = Mock()
    mock_db_manager = Mock()

    core_services._persistence = mock_persistence
    core_services._database_manager = mock_db_manager
    core_services._initialized = True

    return core_services


# ================================
# Event Loop Configuration
# ================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create an instance of the default event loop for the test session.
    This ensures consistent async behavior across all tests.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ================================
# HTTP Client Fixtures
# ================================


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """
    Synchronous TestClient fixture for FastAPI.
    Use this for standard API endpoint testing where async is not required.
    """
    _setup_test_app_state()
    with TestClient(app=app, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def client_with_persistence(
    test_persistence_feature: object,
) -> Generator[TestClient, None, None]:
    """
    Synchronous TestClient fixture with real database persistence.

    Use this for testing API endpoints that require actual database
    operations. The persistence feature is initialized with a real
    SQLite database file for more realistic testing.
    """
    _setup_test_app_state()

    # Override persistence dependencies with test instances
    app.dependency_overrides[get_persistence_feature] = lambda: test_persistence_feature  # type: ignore[attr-defined]
    app.dependency_overrides[get_database_manager] = (
        lambda: test_persistence_feature._database_manager  # noqa: SLF001
    )  # type: ignore[attr-defined]

    with TestClient(app=app, base_url="http://test") as test_client:
        yield test_client

    # Clean up overrides
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Asynchronous AsyncClient fixture for FastAPI.
    Use this for testing async endpoints, WebSockets, or when you need
    to await client operations directly in your test.
    Note: If you encounter issues with this fixture, ensure httpx is up to date (>=0.23).
    """
    from httpx import ASGITransport

    _setup_test_app_state()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def async_client_with_persistence(
    test_persistence_feature: object,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Asynchronous AsyncClient fixture with real database persistence.

    Use this for testing async endpoints that require actual database
    operations. The persistence feature is initialized with a real
    SQLite database file for comprehensive integration testing.
    """
    from httpx import ASGITransport

    _setup_test_app_state()

    # Override persistence dependencies with test instances
    app.dependency_overrides[get_persistence_feature] = lambda: test_persistence_feature  # type: ignore[attr-defined]
    app.dependency_overrides[get_database_manager] = (
        lambda: test_persistence_feature._database_manager  # noqa: SLF001
    )  # type: ignore[attr-defined]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    # Clean up overrides
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
def client_with_core_services(
    test_core_services: CoreServices,
) -> Generator[TestClient, None, None]:
    """
    Synchronous TestClient fixture with CoreServices dependency injection.

    Use this for testing API endpoints that require CoreServices infrastructure
    such as persistence and database access. This replaces the legacy
    persistence feature dependency pattern.
    """
    _setup_test_app_state()

    # Add CoreServices to app state
    app.state.core_services = test_core_services
    app.state.persistence_service = test_core_services.persistence
    app.state.database_manager = test_core_services.database_manager

    # Override legacy dependencies for backward compatibility
    app.dependency_overrides[get_persistence_feature] = lambda: test_core_services.persistence  # type: ignore[attr-defined]
    app.dependency_overrides[get_database_manager] = lambda: test_core_services.database_manager  # type: ignore[attr-defined]

    with TestClient(app=app, base_url="http://test") as test_client:
        yield test_client

    # Clean up overrides
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
async def async_client_with_core_services(
    test_core_services: CoreServices,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Asynchronous AsyncClient fixture with CoreServices dependency injection.

    Use this for testing async endpoints that require CoreServices infrastructure.
    This provides the most realistic testing environment for CoreServices integration.
    """
    from httpx import ASGITransport

    _setup_test_app_state()

    # Add CoreServices to app state
    app.state.core_services = test_core_services
    app.state.persistence_service = test_core_services.persistence
    app.state.database_manager = test_core_services.database_manager

    # Override legacy dependencies for backward compatibility
    app.dependency_overrides[get_persistence_feature] = lambda: test_core_services.persistence  # type: ignore[attr-defined]
    app.dependency_overrides[get_database_manager] = lambda: test_core_services.database_manager  # type: ignore[attr-defined]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    # Clean up overrides
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


# ================================
# Service Mock Fixtures
# ================================


@pytest.fixture
def mock_app_state() -> Mock:
    """
    Mock for the AppState service with common methods.
    Provides a clean mock that can be customized per test.
    """
    mock = Mock()
    mock.get_entity = Mock(return_value=None)
    mock.update_entity = Mock()
    mock.get_all_entities = Mock(return_value=[])
    mock.get_state = Mock(return_value={})
    mock.update_state = Mock()
    return mock


@pytest.fixture
def mock_entity_service() -> AsyncMock:
    """
    Mock for the EntityService with common async methods.
    Use this to mock entity business logic operations.
    """
    mock = AsyncMock()
    mock.list_entities = AsyncMock(return_value={})
    mock.list_entity_ids = AsyncMock(return_value=[])
    mock.get_entity = AsyncMock(return_value=None)
    mock.get_entity_history = AsyncMock(return_value=[])
    mock.get_unmapped_entries = AsyncMock(return_value={})
    mock.get_unknown_pgns = AsyncMock(return_value={})
    mock.get_metadata = AsyncMock(return_value={})
    mock.control_light = AsyncMock()
    return mock


@pytest.fixture
def mock_can_service() -> AsyncMock:
    """
    Mock for the CAN service with common async methods.
    Use this to mock CANbus operations in tests.
    """
    mock = AsyncMock()
    mock.send_message = AsyncMock()
    mock.receive_message = AsyncMock(return_value=None)
    mock.get_status = AsyncMock(return_value={})
    return mock


@pytest.fixture
def mock_config_service() -> Mock:
    """
    Mock for the ConfigService with common methods.
    Use this to mock configuration operations.
    """
    mock = Mock()
    mock.get_config = Mock(return_value={})
    mock.update_config = Mock()
    mock.validate_config = Mock(return_value=True)
    return mock


@pytest.fixture
def mock_service_registry() -> Mock:
    """
    Mock for the ServiceRegistry with common methods.
    Use this to mock service management operations.
    """
    mock = Mock()
    mock.has_service = Mock(return_value=True)
    mock.get_service = Mock(return_value=Mock())
    mock.get_service_status = Mock(return_value="healthy")
    mock.check_system_health = AsyncMock(return_value={"status": "healthy", "services": {}})
    return mock


# ================================
# Dependency Override Fixtures
# ================================


@pytest.fixture
def override_app_state(mock_app_state: Mock) -> Generator[Mock, None, None]:
    """
    Override the app_state dependency with a mock.
    Use this when testing endpoints that depend on app state.
    """
    # app.dependency_overrides[get_app_state] = lambda: mock_app_state  # Removed - using ServiceRegistry
    yield mock_app_state
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
def override_entity_service(
    mock_entity_service: AsyncMock,
) -> Generator[AsyncMock, None, None]:
    """
    Override the entity_service dependency with a mock.
    Use this when testing endpoints that depend on entity operations.
    """
    app.dependency_overrides[get_entity_service] = lambda: mock_entity_service  # type: ignore[attr-defined]
    yield mock_entity_service
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
def override_can_service(
    mock_can_service: AsyncMock,
) -> Generator[AsyncMock, None, None]:
    """
    Override the can_service dependency with a mock.
    Use this when testing endpoints that depend on CAN operations.
    """
    app.dependency_overrides[get_can_facade] = lambda: mock_can_service  # type: ignore[attr-defined]
    yield mock_can_service
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
def override_config_service(mock_config_service: Mock) -> Generator[Mock, None, None]:
    """
    Override the config_service dependency with a mock.
    Use this when testing endpoints that depend on configuration.
    """
    app.dependency_overrides[get_config_service] = lambda: mock_config_service  # type: ignore[attr-defined]
    yield mock_config_service
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
def override_service_registry(mock_service_registry: Mock) -> Generator[Mock, None, None]:
    """
    Override the service_registry dependency with a mock.
    Use this when testing endpoints that depend on service management.
    """
    app.state.service_registry = mock_service_registry
    yield mock_service_registry
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
def override_all_services(
    mock_app_state: Mock,
    mock_entity_service: AsyncMock,
    mock_can_service: AsyncMock,
    mock_config_service: Mock,
    mock_service_registry: Mock,
) -> Generator[dict[str, Mock | AsyncMock], None, None]:
    """
    Override all major service dependencies with mocks.
    Use this for comprehensive endpoint testing.
    """
    app.dependency_overrides.update(
        {
            get_entity_service: lambda: mock_entity_service,
            get_can_facade: lambda: mock_can_service,
            get_config_service: lambda: mock_config_service,
        }
    )  # type: ignore[attr-defined]
    app.state.service_registry = mock_service_registry
    yield {
        "app_state": mock_app_state,
        "entity_service": mock_entity_service,
        "can_service": mock_can_service,
        "config_service": mock_config_service,
        "service_registry": mock_service_registry,
    }
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


# ================================
# Test Data Fixtures
# ================================


@pytest.fixture
def sample_entity_data() -> dict[str, int | str | dict[str, int]]:
    """
    Sample entity data for testing.
    Returns a dictionary with typical entity properties.
    """
    return {
        "id": 1,
        "name": "Test Entity",
        "type": "sensor",
        "value": 100,
        "unit": "temperature",
        "properties": {
            "min_value": 0,
            "max_value": 200,
            "precision": 1,
        },
    }


@pytest.fixture
def sample_can_message() -> dict[str, int | list[int] | bool | float]:
    """
    Sample CAN message data for testing.
    Returns a dictionary with typical CAN message properties.
    """
    return {
        "arbitration_id": 0x18FEF100,
        "data": [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08],
        "is_extended_id": True,
        "timestamp": 1234567890.123,
    }


@pytest.fixture
def sample_config_data() -> dict[str, str | dict[str, bool | int]]:
    """
    Sample configuration data for testing.
    Returns a dictionary with typical configuration properties.
    """
    return {
        "can_interface": "can0",
        "log_level": "INFO",
        "features": {
            "entity_discovery": True,
            "can_logging": False,
        },
        "thresholds": {
            "temperature_warning": 80,
            "pressure_critical": 100,
        },
    }


# ================================
# Integration Test Fixtures
# ================================


@pytest.fixture
def mock_can_bus() -> Mock:
    """
    Mock for CAN bus interface operations.
    Use this to mock hardware-level CAN interactions.
    """
    mock_instance = Mock()
    mock_instance.send.return_value = True
    mock_instance.receive.return_value = None
    mock_instance.is_connected.return_value = True
    return mock_instance


@pytest.fixture
def mock_rvc_decoder() -> Mock:
    """
    Mock for RV-C protocol decoder.
    Use this to mock RV-C message decoding operations.
    """
    mock_instance = Mock()
    mock_instance.decode_message.return_value = {"decoded": True}
    mock_instance.is_valid_message.return_value = True
    return mock_instance


# ================================
# WebSocket Test Fixtures
# ================================


@pytest.fixture
def websocket_test_client() -> Generator[TestClient, None, None]:
    """
    Test client configured for WebSocket testing.
    Use this for testing WebSocket connections and messaging.
    """
    from starlette.testclient import TestClient as StarletteTestClient

    _setup_test_app_state()
    with StarletteTestClient(app) as client:
        yield client


# ================================
# State Cleanup Fixtures
# ================================


@pytest.fixture(autouse=True)
def clean_app_state() -> None:
    """
    Automatically clean up application state after each test.
    Ensures test isolation by preventing state leakage.
    """
    # Clean up any global state if needed
    # This is a placeholder for actual state cleanup


@pytest.fixture(autouse=True)
def reset_dependency_overrides() -> Generator[None, None, None]:
    """
    Automatically reset FastAPI dependency overrides after each test.
    Ensures clean dependency injection state.
    """
    yield
    app.dependency_overrides.clear()  # type: ignore[attr-defined]


# ================================
# Pytest Configuration
# ================================


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "api: API endpoint tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "can: CAN bus related tests")
    config.addinivalue_line("markers", "websocket: WebSocket tests")
    config.addinivalue_line("markers", "performance: Performance tests")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Automatically mark tests based on their location."""
    for item in items:
        # Add markers based on test file location
        if "test_api" in str(item.fspath):
            item.add_marker(pytest.mark.api)
        elif "test_services" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "test_integrations" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "test_websocket" in str(item.fspath):
            item.add_marker(pytest.mark.websocket)

        # Mark tests that contain 'can' in their name
        if "can" in item.name.lower():
            item.add_marker(pytest.mark.can)

        # Mark performance tests
        if "performance" in item.name.lower() or "perf" in item.name.lower():
            item.add_marker(pytest.mark.performance)
