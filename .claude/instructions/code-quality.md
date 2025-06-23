# Code Quality Instructions

## Overview

Comprehensive code quality standards covering formatting, linting, type checking, and documentation for both Python backend and TypeScript frontend.

## Python Backend Quality

### Formatting with Ruff
```bash
# Format code (required before commits)
poetry run ruff format backend

# Check formatting without applying changes
poetry run ruff format backend --check
```

**Standards:**
- **Line Length**: 100 characters
- **Quote Style**: Double quotes preferred
- **Trailing Commas**: Allowed in multi-line structures
- **Import Formatting**: One import per line, grouped and sorted

### Linting with Ruff
```bash
# Run linting (required before commits)
poetry run ruff check .

# Auto-fix issues where possible
poetry run ruff check . --fix

# Show detailed error explanations
poetry run ruff check . --show-source
```

**Configuration (pyproject.toml):**
```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]

[tool.ruff.lint.isort]
force-single-line = true
known-first-party = ["backend"]
```

**Linting Exceptions:**
Some framework patterns require `# noqa` exceptions:

```python
# FastAPI dependency injection (B008 is safe with Depends)
@router.get("/endpoint")
async def my_endpoint(
    service: Service = Depends(get_service),  # noqa: B008
):
    """Depends() in defaults is the official FastAPI pattern."""
    pass

# Type annotation improvements (UP007, UP038 should be applied automatically)
def example(value: str | None = None) -> list[dict]:  # Use | instead of Union
    if isinstance(value, str | int):  # Use | in isinstance calls
        return [{"result": value}]

# Common linting exceptions for framework patterns:
# - B008: Function call in argument defaults (FastAPI Depends)
# - E501: Line too long (for very long import chains)
# - UP007: Use X | Y for type annotations (should be auto-fixed)
# - UP038: Use X | Y for isinstance() calls (should be auto-fixed)
```

### Type Checking with Pyright
```bash
# Run type checking (required before commits)
poetry run pyright backend

# Check specific files
poetry run pyright backend/services/entity_service.py
```

**Standards:**
- **Type Hints**: Required for all function parameters and return values
- **Generic Types**: Use proper generic typing for collections and protocols
- **Optional Types**: Use `Optional[T]` or `T | None` for nullable values
- **Custom Stubs**: Create type stubs in `typings/` for third-party libraries

**Type Stub Pattern:**
```python
# typings/example_lib/__init__.pyi
from typing import Protocol, TypeVar

T = TypeVar("T")

class AsyncContextManagerProtocol(Protocol[T]):
    async def __aenter__(self) -> T: ...
    async def __aexit__(self, *args) -> None: ...

def some_function(param: str) -> bool: ...
```

### Import Organization
```python
# Standard library imports
import os
import sys
from pathlib import Path

# Third-party imports
import fastapi
from pydantic import BaseModel

# Local imports (absolute only)
from backend.core.config import get_settings
from backend.services.entity_service import EntityService
```

### Documentation Standards
```python
def control_entity(entity_id: str, command: EntityControlCommand) -> EntityControlResult:
    """
    Control an RV-C entity with the specified command.

    Args:
        entity_id: Unique identifier for the entity to control
        command: Control command with action and optional parameters

    Returns:
        Result indicating success/failure and any response data

    Raises:
        EntityNotFoundError: If the entity_id is not found
        CANBusError: If communication with the CAN bus fails

    Example:
        >>> result = control_entity("light_1", EntityControlCommand(command="set", state="on"))
        >>> assert result.success is True
    """
    # Implementation
```

## TypeScript Frontend Quality

### ESLint Configuration
```bash
# Run linting (required before commits)
npm run lint

# Auto-fix issues where possible
npm run lint:fix

# Check specific files
npm run lint src/components/entity-card.tsx
```

**ESLint Rules (eslint.config.js):**
```javascript
export default [
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: "@typescript-eslint/parser",
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true }
      }
    },
    rules: {
      "comma-dangle": ["error", "never"],
      "quotes": ["error", "double"],
      "semi": ["error", "always"],
      "@typescript-eslint/no-unused-vars": "error",
      "react-hooks/exhaustive-deps": "warn"
    }
  }
];
```

### TypeScript Configuration
```bash
# Run type checking (required before commits)
npm run typecheck

# Build check
npm run build
```

**Standards:**
- **Strict Mode**: Enabled in tsconfig.json
- **Interface Requirements**: All standalone interface files must have imports
- **Component Props**: Use proper TypeScript interfaces for component props
- **Event Handlers**: Use proper React event types

**Component Type Pattern:**
```typescript
import type { ReactNode, MouseEvent } from "react";

interface ButtonProps {
  children: ReactNode;
  onClick: (event: MouseEvent<HTMLButtonElement>) => void;
  variant?: "primary" | "secondary";
  disabled?: boolean;
}

export function Button({ children, onClick, variant = "primary", disabled = false }: ButtonProps) {
  return (
    <button
      className={`btn btn-${variant}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
```

### Import Organization
```typescript
// React and React-related imports
import { useState, useEffect, type ReactNode } from "react";

// Third-party library imports
import { useQuery } from "@tanstack/react-query";

// UI component imports
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

// Local component and utility imports
import { EntityCard } from "@/components/entity-card";
import { apiClient } from "@/api/client";
import { cn } from "@/lib/utils";
```

## Pre-commit Hooks

### Configuration (.pre-commit-config.yaml)
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v8.50.0
    hooks:
      - id: eslint
        files: \.(js|ts|tsx)$
        additional_dependencies:
          - eslint@8.50.0
          - "@typescript-eslint/parser@6.7.4"
```

### Running Pre-commit
```bash
# Install pre-commit hooks
poetry run pre-commit install

# Run on all files manually
poetry run pre-commit run --all-files

# Run on specific files
poetry run pre-commit run --files backend/services/entity_service.py
```

## Quality Checklist

### Before Every Commit
```bash
# Backend quality check
poetry run ruff format backend
poetry run ruff check .
poetry run pyright backend

# Frontend quality check
cd frontend
npm run lint:fix
npm run typecheck

# Run tests
poetry run pytest
npm test
```

### Before Pull Requests
```bash
# Comprehensive quality check
poetry run pre-commit run --all-files

# Full test suite
poetry run pytest --cov=backend --cov-report=term
cd frontend && npm run test:coverage

# Build verification
cd frontend && npm run build
```

## Editor Configuration

### VS Code Settings (.vscode/settings.json)
```json
{
  "python.defaultInterpreterPath": "python",
  "python.analysis.typeCheckingMode": "basic",
  "python.analysis.stubPath": "${workspaceFolder}/typings",
  "python.formatting.provider": "none",
  "editor.formatOnSave": false,
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": true,
    "source.organizeImports": true
  },
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": true,
      "source.organizeImports.ruff": true
    }
  },
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[typescriptreact]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  }
}
```

## Error Resolution Patterns

### Common Python Issues

#### Service Access Anti-Patterns (DELETE ON SIGHT)
```python
# ❌ DELETE: Direct app.state access
def bad_endpoint(request: Request):
    service = request.app.state.entity_service  # DELETE THIS FUNCTION

# ✅ TARGET: Dependency injection only
def good_endpoint(
    service: Annotated[EntityService, Depends(get_entity_service)]
):
    # Service is properly injected

# ❌ DELETE: Any service with app_state
class BadService:
    def __init__(self, app_state: AppState):  # DELETE THIS CLASS
        self.app_state = app_state

# ✅ TARGET: Repository injection only
class GoodService:
    def __init__(
        self,
        repository: MyRepository,
        # NO app_state parameter!
    ):
        self.repository = repository

# ❌ DELETE: Migration adapters
class ServiceMigrationAdapter:  # DELETE ENTIRE FILE
    def __init__(self, use_v2: bool, ...):
        if use_v2: ...
```

#### Type Annotation Issues
```python
# ❌ Missing type hints
def process_data(data):
    return data

def process_data(data: dict[str, Any]) -> dict[str, Any]:  # ✅ Proper types
    return data

# Import order violation
from backend.services import EntityService  # ❌ Wrong order
import os  # ❌ Should be first

import os  # ✅ Standard library first
from backend.services import EntityService  # ✅ Local imports last
```

### Common TypeScript Issues
```typescript
// Missing interface import
export interface Props {  // ❌ Standalone interface without import
  children: ReactNode;
}

import type { ReactNode } from "react";  // ✅ Required import
export interface Props {
  children: ReactNode;
}

// Trailing comma violation
const config = {
  apiUrl: "http://localhost:8000",  // ❌ Trailing comma
};

const config = {
  apiUrl: "http://localhost:8000"  // ✅ No trailing comma
};
```

## Performance Considerations

### Python Performance
- Use `ruff` instead of multiple tools (Black, isort, flake8) for speed
- Run type checking only on changed files during development
- Use `.ruff_cache/` for faster subsequent runs

### Frontend Performance
- Use ESLint flat config for better performance
- Enable TypeScript incremental compilation
- Use `npm run lint -- --cache` for faster linting

## Continuous Integration

### GitHub Actions Quality Checks
```yaml
name: Code Quality
on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Python quality
        run: |
          poetry run ruff check .
          poetry run ruff format --check backend
          poetry run pyright backend

      - name: Frontend quality
        run: |
          cd frontend
          npm run lint
          npm run typecheck
          npm run build
```

All quality checks must pass before code can be merged to main branch.

## Real-time System Troubleshooting Guide

Based on debugging session learnings, here are common issues and solutions for real-time CAN systems:

### CAN Interface Issues

#### "No CAN Activity" Dashboard Alert
**Symptoms**: Dashboard shows "No CAN Activity" despite traffic on interfaces
**Root Cause**: CAN service not calculating message rates correctly
**Debugging**:
```bash
# 1. Check actual CAN traffic exists
candump can1

# 2. Verify backend logs show listener startup
grep "CAN listener started" backend.log

# 3. Check interface configuration
echo $COACHIQ_CAN__INTERFACES
```
**Solution**: Implement `_calculate_message_rate()` in CAN service using recent sniffer log

#### CAN Listener Startup Hanging
**Symptoms**: Server hangs at "CAN listener started for interface: canX"
**Root Cause**: Blocking `bus.recv()` calls in async event loop
**Error Pattern**: Server startup never completes, no further log messages
**Solution**: Use AsyncBufferedReader + Notifier pattern
```python
# WRONG: Blocking call in async context
message = bus.recv(timeout=1.0)  # Blocks event loop!

# CORRECT: Asyncio integration
reader = can.AsyncBufferedReader()
notifier = can.Notifier(bus, [reader], loop=asyncio.get_running_loop())
message = await reader.get_message()  # Non-blocking
```

#### Log Flooding with Data Type Errors
**Symptoms**: "Unexpected data type: <class 'bytearray'>" floods logs
**Root Cause**: AsyncBufferedReader returns bytearray, not bytes
**Solution**: Handle all CAN data types in message processing
```python
# Handle all expected data types
if isinstance(data, str):
    data = bytes.fromhex(data)
elif isinstance(data, bytearray):  # From AsyncBufferedReader
    data = bytes(data)
elif not isinstance(data, bytes):
    logger.warning(f"Unexpected data type: {type(data)}")
    return
```

### API Response Format Issues

#### AttributeError: 'ControlEntityResponse' object has no attribute 'success'
**Symptoms**: Control endpoint throws AttributeError on response.success
**Root Cause**: Response model uses 'status' field, not 'success' boolean
**Error**: `AttributeError: 'ControlEntityResponse' object has no attribute 'success'`
**Solution**: Use correct attribute name
```python
# WRONG: Using non-existent attribute
if result.success:  # AttributeError!

# CORRECT: Use actual response model structure
if result.status == "success":
```

### WebSocket and Frontend Issues

#### Health Endpoint Mismatch
**Symptoms**: Frontend health checks fail with 404
**Root Cause**: Frontend calling `/api/healthz` instead of `/healthz`
**Solution**: Update frontend to use root-level health endpoint
```typescript
// CORRECT: Root level health endpoint
const url = '/healthz';

// WRONG: API prefixed health endpoint
const url = '/api/healthz';  // Returns 404
```

#### Real-time Data Polling vs WebSocket
**Symptoms**: High CPU usage, delayed updates, network congestion
**Root Cause**: Using REST polling for real-time data streams
**Solution**: Convert to WebSocket pattern
```typescript
// WRONG: Polling for real-time data
useEffect(() => {
  const interval = setInterval(async () => {
    const data = await fetchCANMessages(); // Creates load
  }, 100);
}, []);

// CORRECT: WebSocket for real-time streams
const { isConnected } = useCANScanWebSocket({
  onMessage: (message: CANMessage) => {
    setMessages(prev => [...prev, message].slice(-maxMessages))
  }
})
```

### Memory Management Issues

#### Unbounded Buffer Growth
**Symptoms**: Memory usage grows continuously in long-running systems
**Root Cause**: CAN buffers without size limits
**Solution**: Implement FIFO culling with hard limits
```python
# Add entry with size limit
can_command_sniffer_log.append(entry)
if len(can_command_sniffer_log) > 1000:  # Hard limit
    can_command_sniffer_log.pop(0)  # FIFO removal

# Time-based cleanup for short-lived data
pending_commands = [cmd for cmd in pending_commands
                   if time.time() - cmd["timestamp"] < 2.0]
```

#### Entity History Memory Growth
**Symptoms**: Entity history grows without bounds
**Solution**: Apply same FIFO pattern to all real-time buffers
- CAN sniffer log: 1000 entries max
- CAN grouped entries: 500 entries max
- Entity history: 1000 entries per entity max
- Pending commands: 2-second expiration

### Debugging Commands
```bash
# Check CAN interfaces are receiving
candump can0 can1

# Monitor memory usage
poetry run python -c "import psutil; print(f'Memory: {psutil.Process().memory_info().rss / 1024 / 1024:.1f}MB')"

# Check WebSocket connections (Browser DevTools)
# Network tab → WS connections should show active streams

# Verify interface configuration
env | grep COACHIQ_CAN

# Check for blocking event loop issues
# If startup hangs, likely blocking recv() calls in async context
```

### Code Quality Checks for Real-time Systems
Always verify these patterns in code review:
1. **AsyncBufferedReader**: No blocking recv() calls in CAN listeners
2. **Memory Limits**: All buffers have size limits with FIFO culling
3. **Data Types**: Handle str, bytes, and bytearray in CAN processing
4. **Response Format**: Use result.status, never result.success
5. **Health Endpoints**: Root level `/healthz`, not `/api/healthz`
6. **WebSocket Priority**: Real-time data uses WebSocket, not polling
