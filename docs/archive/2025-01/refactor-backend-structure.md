# Refactor Backend Structure to Modular Architecture

## 1. Refactoring Objective

### 1.1. Purpose
- Reorganize the backend structure to improve modularity, maintainability, and extensibility
- Prepare the codebase for new features like coach maintenance tracking
- Create clear separation of concerns between different functional areas
- Establish a consistent pattern for future backend development
- Transition from the current mixed structure to a more standardized FastAPI monorepo organization

### 1.2. Scope
- Affected: `src/core_daemon/`, `src/rvc_decoder/`, `src/common/`
- Unchanged: Business logic and API functionality will remain the same, only the structure changes
- Boundaries: Focus is on backend reorganization; no changes to frontend integration or overall system behavior

## 2. Current State Analysis

### 2.1. Code Structure
- Backend code is currently split across multiple directories:
  - `src/common/`: Shared models and utilities
  - `src/core_daemon/`: FastAPI application, API routers, state management
  - `src/rvc_decoder/`: DGN decoding, mappings
- The `core_daemon` module contains a mix of concerns (API, WebSockets, state management)
- Future plans already include coach maintenance and other features that would benefit from clearer separation

### 2.2. Code Quality Concerns
- Limited separation between API definition, business logic, and data access
- Tight coupling between components makes it difficult to add new features without modifying existing code
- Core daemon has grown to include various responsibilities that could be better separated
- Limited modularity makes testing more difficult

### 2.3. Test Coverage
- Existing tests need to be updated to reflect the new structure
- Current testing approach focused on high-level API tests rather than modular unit tests
- Refactoring provides an opportunity to improve test organization and coverage

## 3. Refactoring Plan

### 3.1. Architectural Changes
- Create a new `backend/` directory at the project root to house all backend code
- Organize code by functional areas rather than technical layers
- Separate core application configuration from business logic
- Create a clear distinction between API definition and service implementation
- Establish dedicated directories for integrations (RV-C, future integrations like Victron)
- Prepare for new features like coach maintenance tracking

### 3.2. Code Structure Changes
- New structure:
  ```
  backend/
  ├── api/                 # API definition and routes
  │   ├── routers/         # APIRouter modules organized by domain
  │   └── endpoints/       # Endpoint implementations
  ├── core/                # Core application logic
  │   ├── config.py        # Configuration handling
  │   ├── app.py           # FastAPI app factory
  │   └── state.py         # Application state management
  ├── integrations/        # External system integrations
  │   ├── can/             # CAN bus integration
  │   └── rvc/             # RV-C decoder (moved from src/rvc_decoder)
  ├── services/            # Business logic services
  │   ├── entity_service.py # Entity-related business logic
  │   ├── can_service.py   # CAN-related business logic
  │   └── maintenance/     # New maintenance tracking features
  ├── models/              # Pydantic models
  │   ├── common.py        # Shared models (from src/common/models.py)
  │   ├── entities.py      # Entity-related models
  │   └── maintenance.py   # New maintenance-related models
  ├── middleware/          # HTTP and WebSocket middleware
  ├── websocket/           # WebSocket handlers
  └── main.py              # Entry point
  ```

- Files to be moved or refactored (with analysis):

  ### Core Components
  - `src/core_daemon/app_state.py` → `backend/core/state.py`
    - **Purpose**: Manages in-memory application state, entity data, history, and client connections
    - **Analysis**: Core application component that other modules depend on
    - **Dependencies**: Imports from config, metrics, models
    - **Refactoring Notes**: Will require careful handling of circular dependencies with websocket.py

  - `src/core_daemon/config.py` → `backend/core/config.py`
    - **Purpose**: Handles application configuration, logging, path resolution, and environment settings
    - **Analysis**: Configuration is a core concern, correctly placed in core module
    - **Dependencies**: Minimal external dependencies
    - **Refactoring Notes**: Should be one of the first files to migrate to avoid dependency issues

  - `src/core_daemon/main.py` → `backend/main.py`
    - **Purpose**: Application entry point, initialization, and orchestration
    - **Analysis**: High-level bootstrap code that ties components together
    - **Dependencies**: Imports from many modules
    - **Refactoring Notes**: Should be simplified to delegate more responsibility to service modules

  - `src/core_daemon/metrics.py` → `backend/core/metrics.py` (Missing in original plan)
    - **Purpose**: Defines Prometheus metrics for monitoring
    - **Analysis**: Core infrastructure concern used across multiple components
    - **Dependencies**: Minimal external dependencies
    - **Refactoring Notes**: Important to migrate early as it's used by many components

  ### API and Routers
  - `src/core_daemon/api_routers/*.py` → `backend/api/routers/*.py`
    - **Purpose**: Define API endpoints organized by domain
    - **Analysis**: Properly placed in api/routers, but contain business logic that should be extracted
    - **Dependencies**: Import app_state and models extensively
    - **Refactoring Notes**: Business logic should be extracted to service modules

  ### Integration Components
  - `src/core_daemon/can_manager.py` → `backend/integrations/can/manager.py`
    - **Purpose**: Manages CAN bus communication, listeners, and message construction
    - **Analysis**: Hardware integration component, correctly placed in integrations
    - **Dependencies**: Minimal external dependencies
    - **Refactoring Notes**: Clean interfaces between this and business logic should be established

  - `src/core_daemon/can_processing.py` → `backend/integrations/can/processing.py`
    - **Purpose**: Processes incoming CAN messages, updates application state
    - **Analysis**: Handles integration between CAN bus and application state
    - **Dependencies**: Imports app_state, websocket, metrics, models
    - **Refactoring Notes**: Consider splitting business logic into a separate service

  - `src/rvc_decoder/*` → `backend/integrations/rvc/*`
    - **Purpose**: Decodes RV-C protocol messages from CAN frames
    - **Analysis**: Protocol-specific integration, correctly placed in integrations
    - **Dependencies**: Imports common.models
    - **Refactoring Notes**: Clean separation from business logic should be maintained

  ### WebSocket Handling
  - `src/core_daemon/websocket.py` → `backend/websocket/handlers.py`
    - **Purpose**: Manages WebSocket connections, clients, and message broadcasting
    - **Analysis**: Communication layer separate from HTTP API, warrants its own module
    - **Dependencies**: Circular dependency with app_state
    - **Refactoring Notes**: Circular dependency with app_state needs careful handling

  ### Models
  - `src/common/models.py` → `backend/models/common.py`
    - **Purpose**: Shared Pydantic models used across modules
    - **Analysis**: Base models that should be accessible to all components
    - **Dependencies**: Minimal (just Pydantic)
    - **Refactoring Notes**: Should be migrated early as other components depend on it

  - `src/core_daemon/models.py` → Split into domain-specific models:
    - **Purpose**: Contains multiple domain-specific Pydantic models
    - **Analysis**: Should be split by domain to improve separation of concerns
    - **Split Strategy**:
      - `backend/models/entities.py`: Entity-related models
      - `backend/models/can.py`: CAN-related models
      - `backend/models/github.py`: GitHub update models
    - **Refactoring Notes**: Update imports in dependent files after splitting

  ### Additional Components (Missing in original plan)
  - `src/core_daemon/feature_manager.py` → `backend/services/feature_manager.py`
    - **Purpose**: Manages feature flags and optional components
    - **Analysis**: Business logic that manages application features
    - **Dependencies**: Various application components
    - **Refactoring Notes**: Consider refactoring into a proper service pattern

  - `src/core_daemon/middleware.py` → `backend/middleware/http.py`
    - **Purpose**: HTTP middleware like CORS and metrics collection
    - **Analysis**: Web framework infrastructure component
    - **Dependencies**: Imports metrics
    - **Refactoring Notes**: Consider expanding to include additional middleware

### 3.3. Feature Management System (Modern Approach)

### Overview
The backend now uses a modern, config-driven, dependency-aware feature management system. This system is designed for extensibility, testability, and clear separation of feature logic. It consists of:

- **FeatureManager**: Central service for feature registration, dependency resolution, lifecycle management, and status reporting. Features are loaded from a YAML config and registered at startup.
- **Feature Base Class**: All features inherit from `Feature` (see `backend/services/feature_base.py`), which provides lifecycle hooks (`startup`, `shutdown`), health reporting, and dependency declaration.
- **YAML Configuration**: Features and their dependencies are defined in `backend/services/feature_flags.yaml`. This file controls which features are enabled, their core/optional status, and their dependencies.

### Key Patterns
- **Config-Driven**: Features are enabled/disabled and configured via YAML, not hardcoded.
- **Dependency-Aware**: Features can declare dependencies on other features. The manager resolves and starts them in the correct order.
- **Extensible**: New features are added by subclassing `Feature` and registering with the manager.
- **Service-Oriented**: All feature logic and registration must use the new pattern; legacy ad-hoc feature flags are deprecated.

### Example YAML
```yaml
canbus:
  enabled: true
  core: true
  depends_on: []
frontend:
  enabled: true
  core: true
  depends_on: []
maintenance_tracking:
  enabled: false
  core: false
  depends_on: [canbus]
```

### Example Feature Class
```python
from backend.services.feature_base import Feature

class MaintenanceTrackingFeature(Feature):
    async def startup(self):
        # Custom startup logic
        pass
    async def shutdown(self):
        # Custom shutdown logic
        pass
    @property
    def health(self) -> str:
        return "healthy" if self.enabled else "disabled"
```

### Example FeatureManager Usage
```python
from backend.services.feature_manager import FeatureManager
from backend.services.feature_base import Feature

manager = FeatureManager()
manager.register_feature(MaintenanceTrackingFeature(name="maintenance_tracking", enabled=True, core=False))
manager.is_enabled("maintenance_tracking")  # True/False
```

### Migration Notes
- All feature logic and registration must use the new FeatureManager/Feature/YAML pattern.
- Remove legacy feature flag code and update all imports to use `backend/services/feature_manager.py` and `feature_base.py`.
- Update documentation and OpenAPI specs to reflect feature-conditional endpoints.

---

### 3.4. Interface Changes
- No changes to public APIs; internal imports will be updated
- Maintain backward compatibility during transition
- Code refactoring will preserve API contracts and behavior

### 3.5. Testing Strategy
- Update existing tests to use the new import paths
- Add unit tests for newly refactored modules
- Improve test isolation with the new modular structure
- Use the refactoring as an opportunity to increase test coverage

## 4. Implementation Strategy

### 4.1. Phased Approach

The migration will follow a dependency-driven phased approach, starting with the least dependent components and gradually working up to the most integrated ones:

- **Phase 1: Foundation Setup**
  - Set up the new directory structure
  - Create minimal entry points and infrastructure
  - Migrate low-dependency modules first:
    1. `src/common/models.py` → `backend/models/common.py`
    2. `src/core_daemon/config.py` → `backend/core/config.py`
    3. `src/core_daemon/metrics.py` → `backend/core/metrics.py`
    4. `src/rvc_decoder/*` → `backend/integrations/rvc/*`
  - **Status:** _Complete. The foundational backend directory structure and initial package files are already in place._

- **Phase 2: Core Services Migration**
  - Create initial service layer modules
  - Move key components with carefully managed dependencies:
    1. Split `src/core_daemon/models.py` into domain-specific model files
    2. `src/core_daemon/middleware.py` → `backend/middleware/http.py`
    3. `src/core_daemon/can_manager.py` → `backend/integrations/can/manager.py`
    4. Create skeleton for `entity_service.py` and `can_service.py`
    5. Create enhanced feature management:
      - Create `backend/services/feature_base.py` with improved Feature base class
      - Create `backend/services/feature_manager.py` with FeatureManager service class
      - Add `backend/services/feature_flags.yaml` for config-driven feature definitions
      - Require all feature logic and registration to use the new FeatureManager/Feature/YAML pattern
      - Remove legacy feature flag code and update all imports to use new backend module paths
      - Update documentation and OpenAPI specs to reflect feature-conditional endpoints
      - Add feature dependency resolution logic
  - **Status:** _Complete. All core service skeletons, feature management, and migration to the new backend structure are done. Proceed to Phase 3 for state, API, and integration migration._

- **Phase 3: State and API Migration**
  - Handle the more complex interdependent components:
    1. Refactor `src/core_daemon/app_state.py` → `backend/core/state.py`
    2. Migrate `src/core_daemon/websocket.py` → `backend/websocket/handlers.py`
    3. Move API routers to `backend/api/routers/` with service layer refactoring
    4. Refactor `src/core_daemon/can_processing.py` → `backend/integrations/can/processing.py`
    5. Move `src/core_daemon/feature_manager.py` → `backend/services/feature_manager.py`

- **Phase 4: Entry Point and Final Integration**
  - Tie everything together with the main application:
    1. Create a simplified `backend/main.py`
    2. Implement dependency injection where appropriate
    3. Create a compatibility layer for transition period
    4. Add comprehensive test coverage for the new structure

- **Phase 3: Service Refactoring**
  - Split monolithic services into domain-specific modules
  - Create proper separation between API, services, and data access
  - Update imports and references

- **Phase 4: New Features & Cleanup**
  - Implement coach maintenance features in the new structure
  - Remove deprecated code paths
  - Update documentation

### 4.2. Dependency Challenges and Solutions

During the analysis, several dependency challenges were identified that will require special handling:

#### Circular Dependencies
- **app_state.py ↔ websocket.py**: These files import from each other, creating a circular dependency
  - **Solution**: Create a new module `backend/core/events.py` to handle the event dispatch that both modules need
  - **Strategy**: Extract the shared functionality to break the circular dependency

#### Heavy State Dependencies
- Many modules directly import from app_state.py, creating tight coupling
  - **Solution**: Implement a service layer that accesses state rather than having components access state directly
  - **Strategy**: Create services like `entity_service.py` that mediate access to application state

#### Business Logic in API Routers
- API router files contain business logic that should be in service modules
  - **Solution**: Extract business logic from routers to dedicated service modules
  - **Strategy**: Routers should only handle HTTP concerns; service modules handle business logic

### 4.3. Risk Mitigation
- Maintain comprehensive test coverage throughout the refactoring
- Implement changes incrementally, testing at each step
- Create compatibility layers where needed during the transition
- Document all changes clearly for future reference
- Create explicit interfaces between modules to reduce coupling
- Use dependency injection where appropriate to improve testability

### 4.4. Validation Checkpoints

Each phase of migration requires validation to ensure functionality is preserved:

#### Phase 1 Validation
- Verify models can be imported and used in existing code
- Ensure configuration loading works correctly
- Confirm metrics registration is functioning
- Test RV-C decoder functionality in isolation

#### Phase 2 Validation
- Verify domain-specific models properly replace the original models module
- Ensure middleware functions correctly with new imports
- Test CAN manager initialization and operation
- Validate initial service layer functionality

#### Phase 3 Validation
- Confirm application state management is fully functional
- Test WebSocket connections and message broadcasting
- Verify API endpoints respond correctly with refactored dependencies
- Ensure CAN message processing updates state correctly
- Check feature manager functionality

#### Phase 4 Validation
- Run full integration tests with the new main entry point
- Test API endpoints to verify that external behavior remains consistent
- Check WebSocket functionality to ensure real-time updates work correctly
- Verify that CAN bus integration continues to function as expected
- Ensure backwards compatibility is maintained for existing clients

## 5. Code Migration Guide

### 5.1. Old vs. New Patterns
- **BEFORE**: Mixed responsibility modules with tight coupling:
  ```python
  # Direct import from core_daemon
  from core_daemon.app_state import update_entity_state
  ```

- **AFTER**: Clear separation of concerns with modular imports:
  ```python
  # Service-oriented approach
  from backend.services.entity_service import update_entity
  ```

### 5.2. Deprecation Path
- Keep old modules initially with imports from new locations
- Gradually migrate callers to use new import paths
- Remove deprecated code after all callers are updated

## 6. Documentation Updates

### 6.1. Code Documentation
- Update all docstrings to reflect new module locations
- Update architecture documentation with new structure
- Create diagrams showing the revised component organization
- Document patterns for extending the system with new services

### 6.2. User Documentation
- Update API documentation to reflect any path changes or enhancements
- Document the transition if relevant to users of the system
- Update developer setup instructions for the new structure

## 7. Execution Checklist

### 7.1. Preparation
- [ ] Create detailed dependency graph of existing modules
- [ ] Map all import statements across the codebase
- [ ] Establish test baseline to verify functionality preservation
- [ ] Create comprehensive test cases for critical functionality
- [ ] Draft interface definitions for new service modules
- [ ] Create new directory structure

### 7.2. Phase 1: Foundation Setup
- [ ] Migrate `common/models.py` to `backend/models/common.py`
- [ ] Migrate `core_daemon/config.py` to `backend/core/config.py`
- [ ] Migrate `core_daemon/metrics.py` to `backend/core/metrics.py`
- [ ] Migrate `rvc_decoder/` to `backend/integrations/rvc/`
- [ ] Verify imports still work with compatibility layer
- [ ] Run tests to verify phase 1 components function correctly

### 7.3. Core Components Phase (Week 2-3)
- [x] Split domain-specific models:
  - [x] Create `backend/models/entities.py`, `backend/models/can.py`, etc.
  - [x] Update imports in dependent files
  - [x] Create compatibility imports
- [x] Migrate middleware:
  - [x] `src/core_daemon/middleware.py` → `backend/middleware/http.py`
- [x] Migrate CAN integration:
  - [x] `src/core_daemon/can_manager.py` → `backend/integrations/can/manager.py`
  - [x] Create `backend/integrations/can/interface.py` implementing `IntegrationInterface`
- [x] Create initial service layer:
  - [x] `backend/services/entity_service.py`
  - [x] `backend/services/can_service.py`
- [x] Create enhanced feature management:
  - [x] Create `backend/services/feature_base.py` with improved Feature base class
  - [x] Create `backend/services/feature_manager.py` with FeatureManager service class
  - [x] Add `backend/services/feature_flags.yaml` for config-driven feature definitions
  - [x] Require all feature logic and registration to use the new FeatureManager/Feature/YAML pattern
  - [x] Remove legacy feature flag code and update all imports to use new backend module paths
  - [x] Update documentation and OpenAPI specs to reflect feature-conditional endpoints
  - [x] Add feature dependency resolution logic
- [x] Create tests for all migrated components (to be expanded in later phases)

_Phase 2 complete: All core service skeletons, feature management, and migration to the new backend structure are done. Proceed to Phase 3 for state, API, and integration migration._

### 7.4. Phase 3: State and API Migration
- [ ] Refactor `core_daemon/app_state.py` to `backend/core/state.py`
- [ ] Migrate `core_daemon/websocket.py` to `backend/websocket/handlers.py`
- [ ] Migrate API routers with extracted business logic:
  - [ ] `core_daemon/api_routers/entities.py` → `backend/api/routers/entities.py`
  - [ ] `core_daemon/api_routers/can.py` → `backend/api/routers/can.py`
  - [ ] Other API router modules
- [ ] Move business logic to appropriate service modules
- [ ] Migrate `core_daemon/can_processing.py` to `backend/integrations/can/processing.py`
- [ ] Migrate `core_daemon/feature_manager.py` to `backend/services/feature_manager.py`
- [ ] Run tests to verify phase 3 components function correctly

### 7.5. Phase 4: Entry Point and Final Integration
- [ ] Create simplified `backend/main.py` with proper service initialization
- [ ] Implement dependency injection where appropriate
- [ ] Create compatibility layer for transition period
- [ ] Add new coach maintenance service structure
- [ ] Ensure all imports are updated throughout the codebase
- [ ] Run full integration tests

### 7.6. Verification
- [ ] Run complete test suite
- [ ] Verify API behavior with automated and manual testing
- [ ] Test WebSocket functionality thoroughly
- [ ] Check performance metrics for any regressions
- [ ] Test CAN bus integration with hardware or simulators
- [ ] Review code quality with static analysis tools
- [ ] Verify backward compatibility with existing clients

### 7.7. Documentation & Cleanup
- [ ] Update architecture documentation with new structure
- [ ] Create sequence diagrams for key workflows
- [ ] Update API documentation to reflect any changes
- [ ] Remove deprecated code paths
- [ ] Update VS Code tasks and development workflows
- [ ] Update any CI/CD configurations
- [ ] Document lessons learned during the refactoring

## 8. References

- [FastAPI Bigger Applications Guide](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [Python Application Layouts](https://realpython.com/python-application-layouts/)
- Current `docs/architecture/backend.md` documentation
- Existing plan in project documentation about future architecture

## 9. Integration Interface Patterns

One key goal of this refactoring is to prepare for additional device integration types beyond RV-C CAN bus. The new architecture should flexibly support different communication protocols with a common interface pattern.

### 9.1. Common Integration Interface

The following pattern defines a common interface that all integration types will implement:

```python
# backend/integrations/interfaces.py
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Protocol, TypeVar

class DeviceMessage(Protocol):
    """Protocol for messages from any device integration."""
    source_id: str
    timestamp: float
    raw_data: Any

T = TypeVar('T', bound=DeviceMessage)

class IntegrationInterface(ABC):
    """Common interface for all device integrations."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the integration and establish connections."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean shutdown of the integration."""
        pass

    @abstractmethod
    async def send_message(self, target_id: str, message_data: Any) -> bool:
        """Send a message to a specific device."""
        pass

    @abstractmethod
    async def get_message_stream(self) -> AsyncIterator[T]:
        """Return an async iterator yielding device messages."""
        pass

    @abstractmethod
    async def get_available_devices(self) -> List[Dict[str, Any]]:
        """Return a list of available devices with their metadata."""
        pass

    @abstractmethod
    def register_message_handler(self, handler: Callable[[T], None]) -> None:
        """Register a handler for incoming messages."""
        pass
```

### 9.2. Concrete Implementations

#### RV-C CAN Implementation

```python
# backend/integrations/can/interface.py
import asyncio
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from backend.integrations.interfaces import IntegrationInterface
from backend.integrations.can.manager import CANManager
from backend.integrations.can.models import CANMessage

class CANIntegration(IntegrationInterface):
    """RV-C CAN bus integration implementation."""

    def __init__(self, config: Dict[str, Any]):
        self.can_manager = CANManager(config)
        self.handlers = []

    async def initialize(self) -> None:
        """Initialize CAN bus connection and start listening."""
        await self.can_manager.initialize()
        asyncio.create_task(self._process_messages())

    async def shutdown(self) -> None:
        """Shutdown CAN bus connections."""
        await self.can_manager.shutdown()

    async def send_message(self, target_id: str, message_data: Any) -> bool:
        """Send a message to the CAN bus."""
        return await self.can_manager.send_message(int(target_id, 16), message_data)

    async def get_message_stream(self) -> AsyncIterator[CANMessage]:
        """Return an async iterator yielding CAN messages."""
        queue = asyncio.Queue()

        def _handler(msg: CANMessage):
            queue.put_nowait(msg)

        self.register_message_handler(_handler)

        while True:
            yield await queue.get()

    async def get_available_devices(self) -> List<Dict[str, Any]]:
        """Return a list of available CAN nodes."""
        return [
            {"id": hex(node_id), "type": "can_node", "last_seen": timestamp}
            for node_id, timestamp in self.can_manager.get_active_nodes()
        ]

    def register_message_handler(self, handler: Callable[[CANMessage], None]) -> None:
        """Register a handler for CAN messages."""
        self.handlers.append(handler)

    async def _process_messages(self):
        """Process incoming messages and notify handlers."""
        async for msg in self.can_manager.listen():
            for handler in self.handlers:
                asyncio.create_task(asyncio.to_thread(handler, msg))
```

#### IP-Based Device Implementation

```python
# backend/integrations/ip/interface.py
import asyncio
import aiohttp
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from backend.integrations.interfaces import IntegrationInterface
from backend.integrations.ip.models import IPDeviceMessage

class IPDeviceIntegration(IntegrationInterface):
    """Integration for IP-based devices (e.g., Victron Venus OS)."""

    def __init__(self, config: Dict[str, Any]):
        self.devices = []
        self.config = config
        self.handlers = []
        self.session = None
        self.running = False

    async def initialize(self) -> None:
        """Initialize connections to IP devices."""
        self.session = aiohttp.ClientSession()
        self.devices = await self._discover_devices()
        self.running = True
        asyncio.create_task(self._poll_devices())

    async def shutdown(self) -> None:
        """Close connections to IP devices."""
        self.running = False
        if self.session:
            await self.session.close()

    async def send_message(self, target_id: str, message_data: Any) -> bool:
        """Send a command to an IP device."""
        device = next((d for d in self.devices if d["id"] == target_id), None)
        if not device:
            return False

        try:
            url = f"http://{device['address']}/api/v1/setValue"
            async with self.session.post(url, json=message_data) as response:
                return response.status == 200
        except Exception:
            return False

    async def get_message_stream(self) -> AsyncIterator[IPDeviceMessage]:
        """Return an async iterator yielding device status updates."""
        queue = asyncio.Queue()

        def _handler(msg: IPDeviceMessage):
            queue.put_nowait(msg)

        self.register_message_handler(_handler)

        while True:
            yield await queue.get()

    async def get_available_devices(self) -> List<Dict[str, Any]]:
        """Return a list of available IP devices."""
        return self.devices

    def register_message_handler(self, handler: Callable[[IPDeviceMessage], None]) -> None:
        """Register a handler for device messages."""
        self.handlers.append(handler)

    async def _discover_devices(self) -> List[Dict[str, Any]]:
        """Discover IP devices on the network."""
        # Example: scan network, use mDNS, or predefined list
        discovered = []

        if "static_devices" in self.config:
            for device in self.config["static_devices"]:
                discovered.append({
                    "id": device["id"],
                    "address": device["address"],
                    "type": "ip_device",
                    "model": device.get("model", "unknown")
                })

        # Implement network discovery here

        return discovered

    async def _poll_devices(self):
        """Poll connected devices for status updates."""
        while self.running:
            for device in self.devices:
                try:
                    url = f"http://{device['address']}/api/v1/status"
                    async with self.session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            message = IPDeviceMessage(
                                source_id=device["id"],
                                timestamp=data.get("timestamp", 0),
                                raw_data=data,
                                device_type=device.get("model", "unknown")
                            )
                            for handler in self.handlers:
                                asyncio.create_task(asyncio.to_thread(handler, message))
                except Exception as e:
                    print(f"Error polling device {device['id']}: {e}")

            await asyncio.sleep(self.config.get("poll_interval", 5))
```

#### Bluetooth Device Implementation

```python
# backend/integrations/bluetooth/interface.py
import asyncio
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from backend.integrations.interfaces import IntegrationInterface
from backend.integrations.bluetooth.models import BluetoothMessage
from backend.integrations.bluetooth.scanner import BluetoothScanner

class BluetoothIntegration(IntegrationInterface):
    """Integration for Bluetooth devices."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.scanner = BluetoothScanner()
        self.devices = []
        self.handlers = []
        self.running = False

    async def initialize(self) -> None:
        """Initialize Bluetooth scanning."""
        await self.scanner.initialize()
        self.running = True
        asyncio.create_task(self._scan_loop())

    async def shutdown(self) -> None:
        """Stop Bluetooth scanning."""
        self.running = False
        await self.scanner.stop()

    async def send_message(self, target_id: str, message_data: Any) -> bool:
        """Send a message to a Bluetooth device."""
        device = next((d for d in self.devices if d["id"] == target_id), None)
        if not device:
            return False

        return await self.scanner.send_command(device["address"], message_data)

    async def get_message_stream(self) -> AsyncIterator[BluetoothMessage]:
        """Return an async iterator yielding Bluetooth messages."""
        queue = asyncio.Queue()

        def _handler(msg: BluetoothMessage):
            queue.put_nowait(msg)

        self.register_message_handler(_handler)

        while True:
            yield await queue.get()

    async def get_available_devices(self) -> List[Dict[str, Any]]:
        """Return a list of available Bluetooth devices."""
        return self.devices

    def register_message_handler(self, handler: Callable[[BluetoothMessage], None]) -> None:
        """Register a handler for Bluetooth messages."""
        self.handlers.append(handler)

    async def _scan_loop(self):
        """Continuously scan for Bluetooth devices."""
        while self.running:
            devices = await self.scanner.scan()
            self.devices = [
                {
                    "id": device.address.replace(":", ""),
                    "address": device.address,
                    "name": device.name or "Unknown",
                    "type": "bluetooth",
                    "rssi": device.rssi
                }
                for device in devices
            ]

            # Process advertisement data
            for device in devices:
                if device.advertisement_data:
                    message = BluetoothMessage(
                        source_id=device.address.replace(":", ""),
                        timestamp=device.last_seen,
                        raw_data=device.advertisement_data,
                        device_name=device.name or "Unknown",
                        rssi=device.rssi
                    )

                    for handler in self.handlers:
                        asyncio.create_task(asyncio.to_thread(handler, message))

            await asyncio.sleep(self.config.get("scan_interval", 30))
```

### 9.3. Integration Factory and Registry

To make it easy to use different integrations:

```python
# backend/integrations/factory.py
from typing import Dict, Any, Optional, Type

from backend.integrations.interfaces import IntegrationInterface
from backend.integrations.can.interface import CANIntegration
from backend.integrations.ip.interface import IPDeviceIntegration
from backend.integrations.bluetooth.interface import BluetoothIntegration

class IntegrationRegistry:
    """Registry of available integration types."""

    _integrations: Dict[str, Type[IntegrationInterface]] = {
        "can": CANIntegration,
        "ip": IPDeviceIntegration,
        "bluetooth": BluetoothIntegration,
    }

    @classmethod
    def register_integration(cls, name: str, integration_class: Type[IntegrationInterface]) -> None:
        """Register a new integration type."""
        cls._integrations[name] = integration_class

    @classmethod
    def create_integration(cls, name: str, config: Dict[str, Any]) -> Optional[IntegrationInterface]:
        """Create an integration instance by name."""
        if name not in cls._integrations:
            return None

        return cls._integrations[name](config)

    @classmethod
    def get_available_integrations(cls) -> Dict[str, Type[IntegrationInterface]]:
        """Get all registered integration types."""
        return cls._integrations.copy()
```

## 10. Example Implementations

### 10.1. New Maintenance Service Example

As an example of how the new architecture would accommodate a coach maintenance tracking feature:

#### Models
```python
# backend/models/maintenance.py
from datetime import date, datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union

class MaintenanceItemType(str, Enum):
    """Types of maintenance items."""
    SCHEDULED = "scheduled"
    MILEAGE = "mileage"
    ENGINE_HOURS = "engine_hours"
    CALENDAR = "calendar"

class MaintenanceStatus(str, Enum):
    """Status of a maintenance item."""
    UPCOMING = "upcoming"
    DUE = "due"
    OVERDUE = "overdue"
    COMPLETED = "completed"

class MaintenanceItem(BaseModel):
    """Represents a maintenance item to be tracked."""
    id: str
    name: str
    description: str = ""
    type: MaintenanceItemType
    interval_value: float
    interval_unit: str  # days, miles, hours, months
    last_performed: Optional[datetime] = None
    last_value: Optional[float] = None  # miles or hours when last performed
    next_due_date: Optional[date] = None
    next_due_value: Optional[float] = None  # miles or hours
    status: MaintenanceStatus = MaintenanceStatus.UPCOMING
    notes: str = ""
    tags: List[str] = Field(default_factory=list)
    custom_fields: Dict[str, Union[str, int, float, bool]] = Field(default_factory=dict)

class MaintenanceRecord(BaseModel):
    """Record of a completed maintenance task."""
    id: str
    item_id: str
    completion_date: datetime
    value_at_completion: Optional[float] = None  # miles or hours
    technician: Optional[str] = None
    cost: Optional[float] = None
    notes: str = ""
    attachments: List[str] = Field(default_factory=list)
```

#### Service
```python
# backend/services/maintenance/schedule_service.py
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from backend.models.maintenance import (
    MaintenanceItem,
    MaintenanceRecord,
    MaintenanceStatus,
    MaintenanceItemType
)
from backend.core.state import get_state_value
from backend.services.entity_service import get_entity_value

class MaintenanceScheduleService:
    """Service for managing maintenance schedules."""

    def __init__(self):
        self._items: Dict[str, MaintenanceItem] = {}
        self._records: Dict[str, List[MaintenanceRecord]] = {}

    def add_item(self, item: MaintenanceItem) -> MaintenanceItem:
        """Add a new maintenance item to track."""
        self._items[item.id] = item
        self._update_item_status(item.id)
        return item

    def get_item(self, item_id: str) -> Optional[MaintenanceItem]:
        """Get a maintenance item by ID."""
        return self._items.get(item_id)

    def get_all_items(self) -> List[MaintenanceItem]:
        """Get all maintenance items."""
        return list(self._items.values())

    def get_due_items(self) -> List[MaintenanceItem]:
        """Get all items that are due or overdue."""
        return [
            item for item in self._items.values()
            if item.status in (MaintenanceStatus.DUE, MaintenanceStatus.OVERDUE)
        ]

    def add_record(self, record: MaintenanceRecord) -> Tuple[MaintenanceRecord, MaintenanceItem]:
        """Add a new maintenance record and update the item status."""
        if record.item_id not in self._items:
            raise ValueError(f"Maintenance item {record.item_id} not found")

        if record.item_id not in self._records:
            self._records[record.item_id] = []

        self._records[record.item_id].append(record)

        # Update the maintenance item
        item = self._items[record.item_id]
        item.last_performed = record.completion_date

        if record.value_at_completion is not None:
            item.last_value = record.value_at_completion

        # Recalculate next due date/value
        self._update_item_status(record.item_id)

        return record, self._items[record.item_id]

    def get_records(self, item_id: str) -> List[MaintenanceRecord]:
        """Get all maintenance records for an item."""
        return self._records.get(item_id, [])

    def _update_item_status(self, item_id: str) -> None:
        """Update the status of a maintenance item."""
        item = self._items[item_id]

        if item.type == MaintenanceItemType.SCHEDULED:
            if not item.last_performed:
                # Never performed, set to upcoming
                item.status = MaintenanceStatus.UPCOMING
                return

            # Calculate next due date based on interval
            if item.interval_unit == "days":
                item.next_due_date = (
                    item.last_performed + timedelta(days=item.interval_value)
                ).date()
            elif item.interval_unit == "months":
                # Simple month calculation (not exact)
                item.next_due_date = (
                    item.last_performed + timedelta(days=item.interval_value * 30)
                ).date()

            # Determine status based on due date
            today = date.today()
            if item.next_due_date <= today:
                item.status = MaintenanceStatus.OVERDUE
            elif (item.next_due_date - today).days <= 7:  # Within a week
                item.status = MaintenanceStatus.DUE
            else:
                item.status = MaintenanceStatus.UPCOMING

        elif item.type == MaintenanceItemType.MILEAGE:
            if not item.last_value:
                item.status = MaintenanceStatus.UPCOMING
                return

            # Get current mileage from entity
            current_mileage = get_entity_value("vehicle", "odometer", 0)

            # Calculate next due mileage
            item.next_due_value = item.last_value + item.interval_value

            # Determine status based on mileage
            if current_mileage >= item.next_due_value:
                item.status = MaintenanceStatus.OVERDUE
            elif current_mileage >= (item.next_due_value - 500):  # Within 500 miles
                item.status = MaintenanceStatus.DUE
            else:
                item.status = MaintenanceStatus.UPCOMING

        # Similar logic for ENGINE_HOURS and CALENDAR types
```

#### API Router
```python
# backend/api/routers/maintenance.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from uuid import uuid4

from backend.services.maintenance.schedule_service import MaintenanceScheduleService
from backend.models.maintenance import MaintenanceItem, MaintenanceRecord

router = APIRouter(prefix="/api/maintenance", tags=["Maintenance"])

def get_maintenance_service():
    """Dependency injection for the maintenance service."""
    return MaintenanceScheduleService()

@router.get("/items", response_model=List[MaintenanceItem])
async def get_maintenance_items(
    service: MaintenanceScheduleService = Depends(get_maintenance_service)
):
    """Get all maintenance items."""
    return service.get_all_items()

@router.get("/items/due", response_model=List[MaintenanceItem])
async def get_due_items(
    service: MaintenanceScheduleService = Depends(get_maintenance_service)
):
    """Get maintenance items that are due or overdue."""
    return service.get_due_items()

@router.get("/items/{item_id}", response_model=MaintenanceItem)
async def get_maintenance_item(
    item_id: str,
    service: MaintenanceScheduleService = Depends(get_maintenance_service)
):
    """Get a specific maintenance item."""
    item = service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Maintenance item not found")
    return item

@router.post("/items", response_model=MaintenanceItem)
async def create_maintenance_item(
    item: MaintenanceItem,
    service: MaintenanceScheduleService = Depends(get_maintenance_service)
):
    """Create a new maintenance item."""
    if not item.id:
        item.id = str(uuid4())
    return service.add_item(item)

@router.get("/records/{item_id}", response_model=List[MaintenanceRecord])
async def get_maintenance_records(
    item_id: str,
    service: MaintenanceScheduleService = Depends(get_maintenance_service)
):
    """Get maintenance records for a specific item."""
    if not service.get_item(item_id):
        raise HTTPException(status_code=404, detail="Maintenance item not found")
    return service.get_records(item_id)

@router.post("/records", response_model=MaintenanceRecord)
async def create_maintenance_record(
    record: MaintenanceRecord,
    service: MaintenanceScheduleService = Depends(get_maintenance_service)
):
    """Create a new maintenance record."""
    if not record.id:
        record.id = str(uuid4())

    try:
        saved_record, _ = service.add_record(record)
        return saved_record
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### 10.2. Main Application Integration

Here's an example of how the main application would initialize and integrate all components:

```python
# backend/main.py
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings, get_settings
from backend.core.state import AppState
from backend.core.events import EventBus
from backend.middleware.http import metrics_middleware
from backend.services.feature_manager import FeatureManager, get_feature_manager
from backend.api.routers import entities, can, websocket, maintenance
from backend.integrations.factory import IntegrationRegistry
from backend.services.feature_manager import FeatureManager
from backend.core.metrics import setup_metrics

logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.app_version,
    )

    # Configure middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(metrics_middleware)

    # Configure exception handlers
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # Register API routers
    app.include_router(entities.router)
    app.include_router(can.router)
    app.include_router(websocket.router)

    # Initialize feature manager with dependency injection
    feature_manager = get_feature_manager(settings=settings)

    # Register feature-dependent routers conditionally
    if feature_manager.is_enabled("maintenance_tracking"):
        app.include_router(maintenance.router)

    # Setup metrics
    setup_metrics(app)

    return app

async def start_background_tasks(app: FastAPI):
    """Start background tasks for the application."""
    app.state.integrations = {}

    # Initialize each configured integration
    registry = IntegrationRegistry()
    for integration_config in settings.integrations:
        name = integration_config["type"]
        config = integration_config["config"]

        integration = registry.create_integration(name, config)
        if integration:
            await integration.initialize()
            app.state.integrations[name] = integration
            logger.info(f"Initialized {name} integration")
        else:
            logger.error(f"Failed to create integration: {name}")

    # Initialize application state
    app.state.app_state = AppState()
    await app.state.app_state.initialize()

    # Connect integrations to message handlers
    for name, integration in app.state.integrations.items():
        if name == "can":
            from backend.integrations.can.processing import process_can_message
            integration.register_message_handler(process_can_message)
        elif name == "ip":
            from backend.integrations.ip.processing import process_ip_message
            integration.register_message_handler(process_ip_message)
        elif name == "bluetooth":
            from backend.integrations.bluetooth.processing import process_bluetooth_message
            integration.register_message_handler(process_bluetooth_message)

async def shutdown_background_tasks(app: FastAPI):
    """Shutdown background tasks for the application."""
    for name, integration in app.state.integrations.items():
        await integration.shutdown()
        logger.info(f"Shutdown {name} integration")

    # Clean up application state
    await app.state.app_state.shutdown()

app = create_app()

@app.on_event("startup")
async def startup_event():
    """Run startup tasks."""
    await start_background_tasks(app)
    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Run shutdown tasks."""
    await shutdown_background_tasks(app)
    logger.info("Application shutdown complete")
```

## 11. Detailed Migration Plan

### 11.1. Expanded File Migration Path

The following details the specific migration path for each file, with additional details on handling dependencies and refactoring considerations.

#### Common Models
- **Source**: `src/common/models.py`
- **Target**: `backend/models/common.py`
- **Dependencies**: Minimal (Pydantic)
- **Migration Steps**:
  1. Create `backend/models/common.py`
  2. Copy content, update imports if needed
  3. Verify imports continue to work in both old and new locations
  4. Consider adding a deprecation warning in the original file

#### Configuration
- **Source**: `src/core_daemon/config.py`
- **Target**: `backend/core/config.py`
- **Dependencies**: Minimal
- **Migration Steps**:
  1. Create `backend/core/config.py`
  2. Copy content, ensuring any absolute paths are updated
  3. Add any new configuration options for the refactored structure
  4. Consider compatibility for transition period

#### Metrics
- **Source**: `src/core_daemon/metrics.py`
- **Target**: `backend/core/metrics.py`
- **Dependencies**: Minimal
- **Migration Steps**:
  1. Create `backend/core/metrics.py`
  2. Copy content with minimal changes
  3. Consider enhancing with service-specific metrics

#### RV-C Decoder
- **Source**: `src/rvc_decoder/*`
- **Target**: `backend/integrations/rvc/*`
- **Dependencies**: `common.models`
- **Migration Steps**:
  1. Create `backend/integrations/rvc/` directory
  2. Copy all files, updating imports to use `backend/models/common`
  3. Create clear interface boundaries with other components

#### Domain-Specific Models
- **Source**: `src/core_daemon/models.py`
- **Target**: Multiple model files:
  - `backend/models/entities.py`
  - `backend/models/can.py`
  - `backend/models/github.py`
- **Dependencies**: `common.models`
- **Migration Steps**:
  1. Create each target file
  2. Carefully split models by domain
  3. Update imports across files for split models
  4. Create compatibility layer for transition period

#### CAN Manager
- **Source**: `src/core_daemon/can_manager.py`
- **Target**: `backend/integrations/can/manager.py`
- **Dependencies**: Several
- **Migration Steps**:
  1. Create `backend/integrations/can/manager.py`
  2. Create `backend/integrations/can/interface.py` implementing `IntegrationInterface`
  3. Adapt manager class to work with the new interface
  4. Preserve existing functionality during transition

#### Events Broker (New)
- **Target**: `backend/core/events.py`
- **Purpose**: Break circular dependencies between app_state and websocket
- **Implementation Steps**:
  1. Create event broker system with publish/subscribe pattern
  2. Extract shared functionality from app_state and websocket
  3. Update both modules to use the event broker instead of direct imports

#### Application State
- **Source**: `src/core_daemon/app_state.py`
- **Target**: `backend/core/state.py`
- **Dependencies**: Several, including circular dependency with websocket
- **Migration Steps**:
  1. Create events broker first
  2. Create `backend/core/state.py` with dependency on events broker
  3. Refactor to reduce coupling with other components
  4. Implement proper service interfaces

#### WebSocket Handling
- **Source**: `src/core_daemon/websocket.py`
- **Target**: `backend/websocket/handlers.py`
- **Dependencies**: Several, including circular dependency with app_state
- **Migration Steps**:
  1. Create `backend/websocket/handlers.py` using events broker
  2. Extract business logic to appropriate services
  3. Implement clear API for message broadcasting

#### API Routers
- **Source**: `src/core_daemon/api_routers/*.py`
- **Target**: `backend/api/routers/*.py`
- **Dependencies**: Many
- **Migration Steps**:
  1. Create service modules first
  2. Extract business logic from routers to services
  3. Create new router files with slimmer implementation
  4. Ensure backward compatibility during transition

#### Feature Manager Service
- **Source**: `src/core_daemon/feature_manager.py`, `src/core_daemon/feature_base.py`
- **Target**: `backend/services/feature_manager.py`, `backend/services/feature_base.py`
- **Dependencies**: Core, Events Broker, Settings
- **Migration Steps**:
  1. Create `backend/services/feature_base.py` with enhanced `Feature` base class:
     - Add dependency management between features
     - Improve type safety and async support
     - Maintain health reporting capabilities
     - Add proper documentation for overridable methods
     - Implement standardized health status reporting
  2. Create `backend/services/feature_manager.py` as a proper service class:
     - Implement `FeatureManager` class with dependency injection support
     - Add methods for feature flag checking (`is_enabled`)
     - Add enhanced methods for feature querying and management
     - Implement topological sorting for dependency resolution
     - Integrate with the events system for feature state changes
     - Connect feature flags to application settings
     - Maintain existing feature registration and lifecycle management
  3. Create FastAPI dependency function for service injection
  4. Implement integration with settings system for feature flags
  5. Update references to use the new service-based API
  6. Add example modules like maintenance tracking that use the feature flag system

#### Middleware
- **Source**: `src/core_daemon/middleware.py`
- **Target**: `backend/middleware/http.py`
- **Dependencies**: Metrics
- **Migration Steps**:
  1. Create `backend/middleware/http.py`
  2. Update imports for metrics
  3. Consider adding other middleware modules as needed

#### Main Application
- **Source**: `src/core_daemon/main.py`
- **Target**: `backend/main.py`
- **Dependencies**: All components
- **Migration Steps**:
  1. Create new main.py after other modules are migrated
  2. Implement cleaner initialization logic
  3. Add support for integration registry
  4. Add feature flag checks for optional routers
  5. Implement robust startup/shutdown procedures

### 11.2. Dependency Resolution Strategy

To handle complex dependencies, the following strategies will be used:

1. **Bottom-Up Migration**: Start with least dependent files
2. **Interface Abstraction**: Create clean interfaces between components
3. **Events Broker**: Implement publish/subscribe patterns for cross-component communication
4. **Service Layer**: Extract business logic into dedicated services
5. **Dependency Injection**: Use FastAPI's dependency system where appropriate
6. **Staged Deployment**: Maintain compatibility during transition period

## 12. Updated Execution Checklist

### 12.1. Preparation Phase (Week 1)
- [ ] Create the new directory structure
- [ ] Create interface definitions in `backend/integrations/interfaces.py`
- [ ] Create events broker in `backend/core/events.py`
- [ ] Set up comprehensive testing plan
- [ ] Document migration strategy for the team
- [ ] Create compatibility layer plan
- [ ] Develop rollback procedures

### 12.2. Foundation Phase (Week 1-2)
- [ ] Migrate core foundational modules:
  - [ ] `src/common/models.py` → `backend/models/common.py`
  - [ ] `src/core_daemon/config.py` → `backend/core/config.py`
  - [ ] `src/core_daemon/metrics.py` → `backend/core/metrics.py`
  - [ ] Create integration interfaces for CAN, IP, and Bluetooth
  - [ ] Create integration factory and registry
  - [ ] Migrate `src/rvc_decoder/*` → `backend/integrations/rvc/*`
  - [ ] Create tests for all migrated modules

### 12.3. Core Components Phase (Week 2-3)
- [x] Split domain-specific models:
  - [x] Create `backend/models/entities.py`, `backend/models/can.py`, etc.
  - [x] Update imports in dependent files
  - [x] Create compatibility imports
- [x] Migrate middleware:
  - [x] `src/core_daemon/middleware.py` → `backend/middleware/http.py`
- [x] Migrate CAN integration:
  - [x] `src/core_daemon/can_manager.py` → `backend/integrations/can/manager.py`
  - [x] Create `backend/integrations/can/interface.py` implementing `IntegrationInterface`
- [x] Create initial service layer:
  - [x] `backend/services/entity_service.py`
  - [x] `backend/services/can_service.py`
- [x] Create enhanced feature management:
  - [x] Create `backend/services/feature_base.py` with improved Feature base class
  - [x] Create `backend/services/feature_manager.py` with FeatureManager service class
  - [x] Add `backend/services/feature_flags.yaml` for config-driven feature definitions
  - [x] Require all feature logic and registration to use the new FeatureManager/Feature/YAML pattern
  - [x] Remove legacy feature flag code and update all imports to use new backend module paths
  - [x] Update documentation and OpenAPI specs to reflect feature-conditional endpoints
  - [x] Add feature dependency resolution logic
- [x] Create tests for all migrated components (to be expanded in later phases)

_Phase 2 complete: All core service skeletons, feature management, and migration to the new backend structure are done. Proceed to Phase 3 for state, API, and integration migration._

### 12.4. State and API Phase (Week 3-4)
- [ ] Migrate state management:
  - [ ] `src/core_daemon/app_state.py` → `backend/core/state.py`
  - [ ] Integrate with events broker
  - [ ] Extract service methods to appropriate services
- [ ] Migrate WebSocket handling:
  - [ ] `src/core_daemon/websocket.py` → `backend/websocket/handlers.py`
  - [ ] Integrate with events broker
- [ ] Migrate API routers:
  - [ ] Extract business logic to services
  - [ ] Create new router files with service dependencies
  - [ ] Ensure backward compatibility
- [ ] Migrate feature management:
  - [ ] `src/core_daemon/feature_manager.py` → `backend/services/feature_manager.py`
- [ ] Create tests for all migrated components

### 12.5. Main Application Phase (Week 4-5)
- [ ] Create new main application:
  - [ ] `backend/main.py` with clean initialization
  - [ ] Configure router registration based on features
  - [ ] Implement integration registration
  - [ ] Setup startup/shutdown procedures
- [ ] Run full integration tests
- [ ] Create comprehensive documentation
- [ ] Validate backward compatibility

### 12.6. New Features Phase (Week 5+)
- [ ] Develop coach maintenance tracking:
  - [ ] Create models, services, and API endpoints
  - [ ] Integrate with existing state management
  - [ ] Add feature flag for enabling/disabling
- [ ] Implement IP device integration:
  - [ ] Create concrete implementation of `IntegrationInterface`
  - [ ] Develop device discovery and messaging
- [ ] Implement Bluetooth integration:
  - [ ] Create concrete implementation of `IntegrationInterface`
  - [ ] Develop device scanning and communication

### 12.7. Transition and Cleanup (Ongoing)
- [ ] Update imports across codebase to use new modules
- [ ] Remove compatibility layers once no longer needed
- [ ] Deprecate old code paths with clear warnings
- [ ] Update testing infrastructure
- [ ] Update CI/CD pipelines
- [ ] Update documentation to reflect new architecture

## 13. Conclusion and Technical Benefits

This refactoring will lead to several key technical improvements:

1. **Modularity**: Clear separation of concerns makes the codebase easier to understand and modify
2. **Extensibility**: New integrations and features can be added without modifying existing code
3. **Testability**: Clearer interfaces make it easier to write isolated unit tests
4. **Maintainability**: Business logic in services is easier to understand and maintain
5. **Scalability**: Components can be improved independently as needs evolve
6. **Developer Experience**: Clearer structure makes onboarding and development more efficient

By focusing on clean interfaces, dependency injection, and service-oriented patterns, this refactoring lays the groundwork for future feature development while improving the quality and maintainability of the codebase.

## 14. Feature Management Best Practices

Based on research into modern FastAPI feature management patterns, the refactoring will incorporate the following best practices:

### 14.1. Feature Flag Architecture

- **Service-Based Pattern**: Implement feature management as a dedicated service with dependency injection
- **Feature Classes**: Use an enhanced base class with clear lifecycle methods and health reporting
- **Dependency Management**: Explicitly declare dependencies between features
- **Async Support**: Ensure non-blocking, async-aware implementation throughout

### 14.2. Feature Flag Implementation

```python
# Example of the enhanced feature manager service
from typing import Dict, Any, Optional, List

class Feature:
    def __init__(
        self,
        name: str,
        enabled: bool = False,
        core: bool = False,
        config: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self.core = core
        self.config = config or {}
        self.dependencies = dependencies or []

    async def startup(self) -> None:
        """Called when the feature is started."""
        pass

    async def shutdown(self) -> None:
        """Called when the feature is stopped."""
        pass

    @property
    def health(self) -> str:
        """Report health status."""
        return "unknown"

class FeatureManager:
    def __init__(self):
        self._features = {}

    def register_feature(self, feature: Feature) -> None:
        self._features[feature.name] = feature

    def is_enabled(self, feature_name: str) -> bool:
        feature = self._features.get(feature_name)
        return feature is not None and feature.enabled

    async def startup(self) -> None:
        """Start all enabled features in dependency order."""
        for feature in self._get_ordered_features():
            if feature.enabled:
                await feature.startup()
```

### 14.3. Usage in FastAPI Endpoints

Best practices for using feature flags in the API layer:

```python
# Example router with feature flag check
from fastapi import APIRouter, Depends, HTTPException

from backend.services.feature_manager import FeatureManager, get_feature_manager

router = APIRouter()

@router.get("/maintenance/status")
async def get_maintenance_status(
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Get maintenance system status."""
    if not feature_manager.is_enabled("maintenance_tracking"):
        raise HTTPException(status_code=404, detail="Maintenance tracking not enabled")

    # Continue with maintenance status logic
    return {"status": "operational"}
```

### 14.4. Integration with Settings and Configuration

The feature manager will integrate with the application's settings system to allow:
- Environment variable-based feature enabling/disabling
- Configuration file-based feature settings
- Per-environment feature profiles

### 14.5. Feature Health Monitoring

Features will report health status through the enhanced health check endpoint:
- Each feature provides its own health status
- System aggregates feature health for overall status
- Unhealthy features are highlighted in monitoring

## 15. References

- [FastAPI Project Structure](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [Python Application Layouts](https://realpython.com/python-application-layouts/)
- [Clean Architecture in Python](https://www.thedigitalcatonline.com/blog/2016/11/14/clean-architectures-in-python-a-step-by-step-example/)
- [Dependency Injection in FastAPI](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [Feature Flag Best Practices](https://launchdarkly.com/blog/best-practices-feature-flags/)
- [Feature-Driven FastAPI Services](https://www.gridlinesapp.com/blog/building-maintainable-fastapi-services-a-feature-driven-approach)
- Current `docs/architecture/backend.md` documentation
- [Event-Driven Architecture Patterns](https://www.oreilly.com/library/view/software-architecture-patterns/9781491971437/ch02.html)
