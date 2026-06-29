---
applyTo: "**"
---

# Project Overview

`CoachIQ`: Intelligent RV-C network management system with advanced analytics and control:

- FastAPI backend with WebSocket support and feature management
- React frontend with TypeScript, Vite, and shadcn/ui
- RV-C protocol decoder with comprehensive message processing
- Real-time CAN bus monitoring and control
- Comprehensive Nix flake for reproducible development environments
- Hierarchical environment configuration with `COACHIQ_` prefix

## System role and architecture (important context)

CoachIQ is **NOT** a direct hardware controller. The reference RV install
talks to a **Firefly MIRA** multiplex panel over RV-C / J1939. Firefly
owns the physical safety case and physical control authority. CoachIQ
plays the role of a smart wall-switch or HMI panel: it emits well-formed
CAN frames; Firefly decides whether to act on them.

Keep this in mind when designing or modifying code:

- The realistic threat model is **API-side** (bus flooding, malformed
  frames, unauth'd API access, credential compromise) — NOT hardware-side.
- In-process "safety" services (`safety_service.py`,
  `brake_safety_monitor.py`, etc.) are **defense-in-depth API guardrails**,
  not the actual vehicle safety system.
- Code-quality standards target **good consumer-grade backend**, not
  aerospace. Mutation testing, 100% MC/DC coverage, formal methods are
  out of scope. Strict types, ~70-80% coverage on API guardrail paths,
  proper auth/CSRF, and CAN-bus politeness (rate limiting, message
  validation) are in scope.

## Current Structure

- `backend/`: FastAPI app, API routes, services, and business logic
  - `backend/main.py`: FastAPI application entry point
  - `backend/core/`: Core application infrastructure (config, ServiceRegistry, dependency injection, exceptions)
  - `backend/services/`: Business logic services (entity, CAN, RV-C, auth, persistence)
  - `backend/repositories/`: Repository pattern for data access (replaces the removed monolithic `AppState`)
  - `backend/api/routers/`: REST API endpoint routers
  - `backend/websocket/`: WebSocket management
  - `backend/integrations/`: Protocol integrations
  - `backend/models/`: Domain models
- `frontend/`: React frontend with TypeScript, Vite, and Tailwind CSS

## Architecture Features

The current backend structure provides:
- Service-oriented architecture with clear separation of concerns
- YAML-driven feature flag system with dependency resolution
- Multi-interface CAN bus support with automatic reconnection
- Real-time WebSocket updates for entity state changes
- Optional SQLite persistence with repository pattern
- Comprehensive OpenAPI documentation with type generation

## Environment Configuration

### Configuration Pattern
All settings use the `COACHIQ_` prefix with hierarchical naming:
- **Top-level**: `COACHIQ_APP_NAME`, `COACHIQ_ENVIRONMENT`
- **Nested**: `COACHIQ_SERVER__HOST`, `COACHIQ_FEATURES__ENABLE_PERSISTENCE`

### Key Configuration Files
- **`.env.example`**: Comprehensive documentation of all settings
- **`.env`**: Active configuration (not in version control)
- **`backend/core/config.py`**: Pydantic Settings with type validation

### Configuration Access
- **Settings** is the canonical app-config object (`backend.core.config.get_settings()`). Read it directly.
- **RVCConfigFacade**: ONLY for RV-C metadata (PGN names, coach info), not general app config. See ADR-0008.
- **Environment variable priority**: Overrides .env file values
- **Persistence modes**: Memory-only, development, or production
- **Feature flags**: Enable/disable features via `COACHIQ_FEATURES__*`

## Nix Development Environment (Optional)

### Nix Flake Features
The project includes an optional Nix flake that provides:
- **Reproducible environment**: Consistent dependencies across developers
- **CLI apps**: `nix run .#test`, `nix run .#lint`, `nix run .#format`
- **NixOS module**: Production deployment configuration
- **Automatic setup**: Frontend dependencies installed on shell entry
- **Cross-platform**: Works on macOS and Linux

### Nix CLI Apps (if using Nix)
```bash
# Run tests and linters via Nix
nix run .#test
nix run .#lint
nix run .#format
nix run .#ci
```

**Note**: Nix is optional. All standard Poetry and npm commands work without Nix.

# API Endpoint Design Decision

All light-related API operations are consolidated under `/api/v1/entities` endpoints (e.g., `/api/v1/entities?device_type=light`). Legacy per-type and v1 entity endpoints are not used. This ensures a unified, type-safe, and extensible API surface for all entity types.

## Entity Control Command Structure

When controlling entities via the `/api/v1/entities/{id}/control` endpoint, the request body must use the standardized command format:

```json
// Turn light on
{ "command": "set", "state": "on" }

// Set light brightness
{ "command": "set", "state": "on", "brightness": 75 }

// Toggle light state
{ "command": "toggle" }

// Adjust brightness
{ "command": "brightness_up" }
{ "command": "brightness_down" }
```

All frontend code must use this command structure rather than simplified formats like `{ state: true }` which don't match the backend API expectations.
