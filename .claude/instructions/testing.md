# Testing Instructions

## Testing Philosophy

- **Test Coverage**: Aim for >80% coverage on business logic
- **Test Types**: Unit tests for logic, integration tests for API endpoints, E2E for critical workflows
- **Mocking Strategy**: Mock external dependencies (CAN interfaces, file system) but test real business logic
- **Fast Feedback**: Tests should run quickly to enable TDD workflows

## Backend Testing (pytest)

### Configuration
```toml
# pyproject.toml
[tool.pytest.ini_options]
pythonpath = ["backend", "src"]
addopts = ["--import-mode=importlib"]
testpaths = ["tests"]

# Additional markers can be added for test categorization
markers = [
    "integration: Integration tests requiring external services",
    "performance: Performance benchmarking tests"
]
```

### Test Structure
```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock
from backend.core.config import get_settings
from backend.core.state import AppState

@pytest.fixture
async def app_state():
    """Provide clean app state for testing."""
    state = AppState()
    yield state
    await state.cleanup()

@pytest.fixture
def mock_can_interface():
    """Mock CAN interface for testing."""
    mock = AsyncMock()
    mock.send.return_value = True
    mock.receive.return_value = {"id": 0x123, "data": b"\x01\x02"}
    return mock

@pytest.fixture
def test_settings():
    """Test-specific configuration."""
    return get_settings(
        server={"host": "localhost", "port": 8000},
        can={"interfaces": ["vcan0"]},
        features={"enable_persistence": False}
    )
```

### Testing Patterns

#### Service Testing
```python
# tests/services/test_entity_service.py
import pytest
from backend.services.entity_service import EntityService
from backend.models.entity import EntityControlCommand

@pytest.mark.asyncio
async def test_entity_control_command(mock_can_interface, app_state):
    """Test entity control with mocked CAN interface."""
    service = EntityService(can_interface=mock_can_interface, state=app_state)

    command = EntityControlCommand(command="set", state="on", brightness=75)
    result = await service.control_entity("light_1", command)

    # CRITICAL: Use result.status, not result.success
    assert result.status == "success"
    mock_can_interface.send.assert_called_once()

    # Verify CAN message format
    call_args = mock_can_interface.send.call_args[0][0]
    assert call_args["id"] == 0x1FEDC123  # Expected RV-C PGN
```

#### API Router Testing
```python
# tests/api/test_entities.py
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_get_entities():
    """Test entity listing endpoint."""
    response = client.get("/api/entities")
    assert response.status_code == 200

    data = response.json()
    assert "entities" in data
    assert isinstance(data["entities"], list)

@pytest.mark.asyncio
async def test_control_entity(mock_entity_service):
    """Test entity control endpoint."""
    command = {"command": "set", "state": "on", "brightness": 75}

    response = client.post("/api/entities/light_1/control", json=command)
    assert response.status_code == 200

    result = response.json()
    assert result["status"] == "success"
```

#### WebSocket Testing
```python
# tests/websocket/test_handlers.py
import pytest
import json
from fastapi.testclient import TestClient
from backend.main import app

def test_websocket_connection():
    """Test WebSocket connection and message handling."""
    client = TestClient(app)

    with client.websocket_connect("/ws/entities") as websocket:
        # Test connection
        websocket.send_text('{"type": "subscribe", "topic": "entities"}')

        # Simulate entity update
        data = websocket.receive_text()
        message = json.loads(data)

        assert message["type"] == "entity_update"
        assert "entity" in message
```

#### Integration Testing
```python
# tests/integration/test_can_integration.py
import pytest
from backend.integrations.can.manager import CANManager
from backend.integrations.rvc.decode import RVCDecoder

@pytest.mark.integration
async def test_rvc_message_flow():
    """Test complete RV-C message processing flow."""
    can_manager = CANManager(interfaces=["vcan0"])
    decoder = RVCDecoder()

    # Send test message
    test_message = {
        "id": 0x1FEDC001,
        "data": b"\x01\x64\x00\x00\x00\x00\x00\x00"
    }

    await can_manager.send_message(test_message)

    # Verify processing
    received = await can_manager.receive_message(timeout=1.0)
    decoded = decoder.decode_message(received)

    assert decoded["dgn"] == "DC_DIMMER_COMMAND_2"
    assert decoded["instance"] == 1
    assert decoded["brightness"] == 100
```

#### CAN System Testing (Real-time Features)
```python
# tests/integrations/test_can_real_time.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from backend.can.feature import CANBusFeature
from backend.core.state import app_state

@pytest.mark.asyncio
async def test_can_message_reception():
    """Test CAN message reception using AsyncBufferedReader pattern."""
    can_feature = CANBusFeature(config={"simulate": False})

    # Mock AsyncBufferedReader
    mock_reader = AsyncMock()
    mock_message = AsyncMock()
    mock_message.arbitration_id = 0x1FEDC001
    mock_message.data = bytearray([0x01, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    mock_message.dlc = 8
    mock_message.is_extended_id = True

    mock_reader.get_message.return_value = mock_message

    # Test message processing
    await can_feature._process_received_message(mock_message, "can0")

    # Verify sniffer entry was added
    assert len(app_state.can_command_sniffer_log) > 0
    latest_entry = app_state.can_command_sniffer_log[-1]
    assert latest_entry["interface"] == "can0"
    assert latest_entry["direction"] == "rx"

@pytest.mark.asyncio
async def test_can_memory_management():
    """Test CAN buffer memory management with FIFO culling."""
    from backend.core.state import app_state

    # Fill buffer beyond limit
    for i in range(1100):  # Exceed 1000 limit
        app_state.add_can_sniffer_entry({
            "timestamp": i,
            "interface": "can0",
            "can_id": f"{i:08X}",
            "data": "0102030405060708",
            "dlc": 8
        })

    # Verify FIFO culling occurred
    assert len(app_state.can_command_sniffer_log) == 1000
    # First entry should be removed
    assert app_state.can_command_sniffer_log[0]["timestamp"] >= 100

@pytest.mark.asyncio
async def test_can_data_type_handling():
    """Test handling of different CAN data types (str, bytes, bytearray)."""
    can_feature = CANBusFeature()

    # Test string data
    await can_feature._process_message({
        "arbitration_id": 0x123,
        "data": "0102030405060708"
    })

    # Test bytearray data (from AsyncBufferedReader)
    await can_feature._process_message({
        "arbitration_id": 0x123,
        "data": bytearray([0x01, 0x02, 0x03, 0x04])
    })

    # Test bytes data
    await can_feature._process_message({
        "arbitration_id": 0x123,
        "data": b"\x01\x02\x03\x04"
    })

    # All should process without errors

@pytest.mark.asyncio
async def test_entity_state_update_from_can():
    """Test entity state updates from CAN message responses."""
    can_feature = CANBusFeature()

    # Mock entity service
    with patch('backend.core.dependencies.get_entity_service') as mock_es:
        mock_entity_service = AsyncMock()
        mock_entity = AsyncMock()
        mock_entity_service.get_entity.return_value = mock_entity
        mock_entity_service.update_entity_state.return_value = mock_entity
        mock_es.return_value = mock_entity_service

        # Test entity update
        await can_feature._update_entity_from_can_message(
            "light_1",
            {"device_type": "light"},
            {"brightness": 75},
            {"operating_status": 150},
            {"timestamp": 1234567890}
        )

        # Verify entity manager was called
        mock_entity_manager.update_entity_state.assert_called_once()

@pytest.mark.asyncio
async def test_pending_command_completion():
    """Test correlation of CAN responses with pending commands."""
    can_feature = CANBusFeature()

    # Add pending command
    app_state.pending_commands.append({
        "entity_id": "light_1",
        "timestamp": 1234567890,
        "command": "toggle"
    })

    # Process response
    await can_feature._check_pending_command_completion(
        "light_1",
        {"timestamp": 1234567892}  # 2 seconds later
    )

    # Command should be within correlation window
    assert len(app_state.pending_commands) >= 0
```

### Test Factories
```python
# tests/factories.py
from backend.models.entity import Entity, EntityState
from datetime import datetime

class EntityFactory:
    @staticmethod
    def create_light(
        entity_id: str = "light_1",
        name: str = "Test Light",
        state: str = "off",
        brightness: int = 0
    ) -> Entity:
        return Entity(
            id=entity_id,
            name=name,
            device_type="light",
            state=EntityState(
                state=state,
                brightness=brightness,
                last_updated=datetime.now()
            )
        )

    @staticmethod
    def create_can_message(pgn: int = 0x1FEDC, data: bytes = b"\x00" * 8):
        return {
            "id": pgn,
            "data": data,
            "timestamp": datetime.now()
        }
```

## Frontend Testing (Vitest)

### Configuration
```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true
  },
  resolve: {
    alias: {
      "@": "/src"
    }
  }
});
```

### Test Setup
```typescript
// src/test/setup.ts
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";

// Cleanup after each test
afterEach(() => {
  cleanup();
});

// Mock WebSocket globally
global.WebSocket = vi.fn(() => ({
  send: vi.fn(),
  close: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn()
}));
```

### Component Testing
```typescript
// src/components/__tests__/entity-card.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EntityCard } from "@/components/entity-card";

const TestWrapper = ({ children }: { children: React.ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } }
  });

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
};

describe("EntityCard", () => {
  it("renders entity information correctly", () => {
    const entity = {
      id: "light_1",
      name: "Living Room Light",
      state: "on",
      brightness: 75
    };

    render(<EntityCard entity={entity} />, { wrapper: TestWrapper });

    expect(screen.getByText("Living Room Light")).toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeChecked();
  });

  it("calls control API on toggle", async () => {
    const mockControlEntity = vi.fn();
    vi.mock("@/hooks/useEntities", () => ({
      useControlEntity: () => ({ mutate: mockControlEntity })
    }));

    const entity = { id: "light_1", name: "Test Light", state: "off" };

    render(<EntityCard entity={entity} />, { wrapper: TestWrapper });

    const toggle = screen.getByRole("switch");
    fireEvent.click(toggle);

    expect(mockControlEntity).toHaveBeenCalledWith({
      entityId: "light_1",
      command: { command: "toggle" }
    });
  });
});
```

### Hook Testing
```typescript
// src/hooks/__tests__/useWebSocket.test.tsx
import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWebSocket } from "@/hooks/useWebSocket";

describe("useWebSocket", () => {
  it("establishes WebSocket connection", () => {
    const { result } = renderHook(() => useWebSocket("ws://localhost:8000/ws"));

    expect(result.current.isConnected).toBe(false);

    // Simulate connection
    act(() => {
      result.current.socket?.onopen?.(new Event("open"));
    });

    expect(result.current.isConnected).toBe(true);
  });

  it("handles reconnection on disconnect", () => {
    vi.useFakeTimers();

    const { result } = renderHook(() => useWebSocket("ws://localhost:8000/ws"));

    // Simulate disconnect
    act(() => {
      result.current.socket?.onclose?.(new CloseEvent("close"));
    });

    expect(result.current.isConnected).toBe(false);

    // Fast-forward reconnection timer
    act(() => {
      vi.advanceTimersByTime(3000);
    });

    // Should attempt reconnection
    expect(global.WebSocket).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it("handles CAN message streaming", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useCANScanWebSocket({ onMessage, autoConnect: true })
    );

    // Simulate WebSocket connection
    act(() => {
      result.current.socket?.onopen?.(new Event("open"));
    });

    // Simulate CAN message
    const canMessage = {
      timestamp: Date.now(),
      interface: "can0",
      can_id: "1FEDC001",
      data: "0164000000000000",
      direction: "rx"
    };

    act(() => {
      result.current.socket?.onmessage?.(new MessageEvent("message", {
        data: JSON.stringify(canMessage)
      }));
    });

    expect(onMessage).toHaveBeenCalledWith(canMessage);
  });

  it("implements health endpoint fallback", async () => {
    // Mock fetch to simulate health endpoint
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 404
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: "healthy" })
      } as Response);

    const { result } = renderHook(() => useHealthCheck());

    // First attempt should fail at /api/healthz
    await act(async () => {
      await result.current.checkHealth();
    });

    // Should fallback to /healthz
    expect(global.fetch).toHaveBeenCalledWith('/api/healthz');
    expect(global.fetch).toHaveBeenCalledWith('/healthz');
    expect(result.current.status).toBe('healthy');
  });
});
```

## Test Commands

### Backend Testing
```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=backend --cov-report=term --cov-report=html

# Run specific test files
poetry run pytest tests/services/test_entity_service.py

# Run integration tests only
poetry run pytest -m integration

# Performance tests
poetry run pytest -m performance --benchmark-only
```

### Frontend Testing
```bash
cd frontend

# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Run in watch mode
npm run test:watch

# Run specific test files
npm test entity-card
```

## Testing Best Practices

### General Principles
- **Arrange-Act-Assert**: Structure tests clearly with setup, execution, and verification
- **Single Responsibility**: Each test should verify one specific behavior
- **Descriptive Names**: Test names should clearly describe what is being tested
- **Independent Tests**: Tests should not depend on each other's state

### Critical Testing Requirements (Lessons from Session)
Based on debugging session learnings, always test these patterns:

#### API Response Format Testing
```python
# CRITICAL: Always test response.status, never response.success
def test_entity_control_response_format():
    response = client.post("/api/entities/light_1/control", json={"command": "toggle"})
    result = response.json()

    # Test correct attribute name
    assert "status" in result
    assert result["status"] in ["success", "error", "pending"]

    # Ensure we don't accidentally use old format
    assert "success" not in result
```

#### CAN Data Type Compatibility Testing
```python
# CRITICAL: Test all CAN data types that AsyncBufferedReader returns
@pytest.mark.asyncio
async def test_can_data_type_compatibility():
    can_feature = CANBusFeature()

    # Test bytearray (from AsyncBufferedReader)
    await can_feature._process_message({
        "arbitration_id": 0x123,
        "data": bytearray([0x01, 0x02])  # AsyncBufferedReader returns this
    })

    # Test string (legacy compatibility)
    await can_feature._process_message({
        "arbitration_id": 0x123,
        "data": "0102"
    })

    # Test bytes (converted format)
    await can_feature._process_message({
        "arbitration_id": 0x123,
        "data": b"\x01\x02"
    })
```

#### Real-time Memory Management Testing
```python
# CRITICAL: Test memory management for long-running systems
@pytest.mark.asyncio
async def test_real_time_memory_limits():
    from backend.core.state import app_state

    # Test buffer size limits
    initial_count = len(app_state.can_command_sniffer_log)

    # Add many entries
    for i in range(1500):  # Beyond 1000 limit
        app_state.add_can_sniffer_entry({"timestamp": i, "data": "test"})

    # Verify FIFO culling
    assert len(app_state.can_command_sniffer_log) <= 1000

    # Test time-based cleanup for pending commands
    old_pending = {"timestamp": time.time() - 10, "entity_id": "test"}
    recent_pending = {"timestamp": time.time(), "entity_id": "test"}

    app_state.pending_commands = [old_pending, recent_pending]
    app_state.cleanup_pending_commands()  # Should remove old ones

    assert len(app_state.pending_commands) == 1
    assert app_state.pending_commands[0]["entity_id"] == "test"
```

#### Health Endpoint Pattern Testing
```typescript
// CRITICAL: Test health endpoint at root level, not /api/
describe("Health Endpoint", () => {
  it("uses correct health endpoint path", async () => {
    const response = await fetch('/healthz');  // Not /api/healthz
    expect(response.ok).toBe(true);
  });

  it("implements fallback for incorrect paths", async () => {
    // Test that old /api/healthz gets redirected or handled gracefully
    const response = await fetch('/api/healthz');
    expect(response.status).toBe(404);  // Should not exist
  });
});
```

### Mocking Guidelines
- **Mock External Dependencies**: Always mock CAN interfaces, file system, external APIs
- **Real Business Logic**: Don't mock your own services unless testing integration points
- **Mock Data**: Use factories for consistent test data creation
- **Async Mocking**: Use `AsyncMock` for async dependencies

### Coverage Targets
- **Services**: >90% coverage for business logic
- **API Routes**: 100% coverage for happy path and error scenarios
- **Components**: >80% coverage focusing on user interactions
- **Integration**: Critical user flows end-to-end

### Performance Testing
```python
# Backend performance testing
@pytest.mark.performance
def test_entity_query_performance(benchmark):
    """Benchmark entity query performance."""
    result = benchmark(entity_service.get_all_entities)
    assert len(result) > 0
    assert benchmark.stats["mean"] < 0.1  # 100ms max
```

## CI/CD Integration

All tests must pass in CI before code can be merged:
1. **Backend**: `poetry run pytest --cov=backend --cov-report=xml`
2. **Frontend**: `cd frontend && npm test && npm run test:coverage`
3. **Integration**: Selected integration tests on staging environment
4. **Performance**: Regression testing on performance benchmarks
