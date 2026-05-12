# GitHub Copilot Instructions for CoachIQ

## CRITICAL CODE QUALITY REQUIREMENTS

**MANDATORY**: ALL code changes must pass linting, type checking, and build verification BEFORE proceeding to the next task. Run quality checks incrementally throughout development, not just at the end.

**Quality Gates (NON-NEGOTIABLE):**
```bash
# Frontend (run after ANY code change)
cd frontend
npm run typecheck && npm run lint && npm run build

# Backend (run after ANY code change)
poetry run pyright backend && poetry run ruff check . && poetry run ruff format backend
```

## Core Requirements

- All build, cache, and output files (e.g., dist, dist-ssr, .vite, .vite-temp, node_modules, _.tsbuildinfo, .cache, _.log) are excluded from linting and type checking in both root and frontend ESLint configs.
- All API calls are made via /api/entities endpoints, not /api/lights, /api/locks, etc. to ensure a unified and extensible API design.
- All API endpoints require comprehensive documentation with examples, descriptions, and response schemas to maintain the OpenAPI specification.
- **All Python scripts must be run using Poetry.** Use `poetry run python <script>.py` or `poetry run <command>`, never `python <script>.py` directly.

This document provides key information for GitHub Copilot to understand the `CoachIQ` project architecture and coding patterns.

## Modular Copilot Instructions

This project uses modular Copilot instruction files stored in `.github/instructions/`.
Each `.instructions.md` file contains targeted guidance for specific languages, frameworks, or workflows.

**Key instruction files:**

- [`project-overview.instructions.md`](.github/instructions/project-overview.instructions.md): Project architecture and structure
- [`python-code-style.instructions.md`](.github/instructions/python-code-style.instructions.md): Python coding standards
- [`typescript-code-style.instructions.md`](.github/instructions/typescript-code-style.instructions.md): TypeScript/React coding standards
- [`eslint-typescript-config.instructions.md`](.github/instructions/eslint-typescript-config.instructions.md): ESLint and TypeScript config details
- [`dev-environment.instructions.md`](.github/instructions/dev-environment.instructions.md): Development environment setup and tooling
- [`testing.instructions.md`](.github/instructions/testing.instructions.md): Test patterns and requirements
- [`pull-requests.instructions.md`](.github/instructions/pull-requests.instructions.md): PR guidelines and expectations
- [`documentation.instructions.md`](.github/instructions/documentation.instructions.md): API documentation and MkDocs configuration
- [`mcp-tools.instructions.md`](.github/instructions/mcp-tools.instructions.md): Using Copilot Chat tools and context commands
- [`env-vars.instructions.md`](.github/instructions/env-vars.instructions.md): Configuration and environment setup

> **For any code generation or chat involving these topics, refer to the relevant `.instructions.md` file in `.github/instructions/` for detailed guidance.**

## Project Summary

`CoachIQ` is a Python-based API and WebSocket service for RV-C (Recreational Vehicle Controller Area Network) systems:

- **FastAPI backend** with WebSocket support (migrated to `backend/` structure)
- **React frontend** with TypeScript and Vite
- **RV-C decoder** for CANbus messages
- **Service-oriented architecture** with clear separation of concerns
- **Typed code** with Pydantic models and full type hints
- **API Documentation** with MkDocs, Material theme, and OpenAPI integration

## System role (READ THIS FIRST)

CoachIQ is **NOT** a direct hardware controller. In the reference RV install
it talks to a **Firefly MIRA** multiplex panel over RV-C / J1939. Firefly
owns the physical-safety case and decides what commands to act on.
CoachIQ's role is the same as a wall-switch panel or HMI: it emits well-formed
CAN frames; Firefly chooses to act on them or not.

Implications for code generation in this repo:

- **Do NOT frame requirements as DO-178C / aerospace / life-critical.**
  This is convenience automation, not certified safety equipment. See
  `docs/safety.md` for the operational-safety policy.
- **Realistic threats are API-side**: bus flooding, malformed frames,
  unauth'd API access, credential compromise. NOT "the brakes release".
- **In-process "safety" code (`backend/services/safety_service.py`,
  `brake_safety_monitor.py`, etc.) is defense-in-depth API guardrail**,
  not the actual safety system. It exists to keep CoachIQ from being
  a stupid CAN-bus citizen, not to enforce vehicle-level safety.
- **Aim for "good consumer-grade backend"** quality, not aerospace:
  ~70-80% coverage on the API guardrail paths, strict types, fast tests,
  proper auth/CSRF, no bus flooding. Don't propose mutation testing,
  100% MC/DC coverage, formal methods, etc.

## Linting & Code Quality Requirements

**INCREMENTAL QUALITY WORKFLOW**:
1. Make code changes
2. Run quality checks immediately (see commands above)
3. Fix all issues before proceeding to next task
4. NEVER accumulate technical debt

### Python

- **Version**: 3.12+
- **Formatting**: ruff format (line length: 100) - **RUN AFTER EVERY CHANGE**
- **Linting**: ruff (configured in pyproject.toml) - **MUST PASS WITH ZERO WARNINGS**
- **Type Checking**: pyright (basic mode, configured in pyrightconfig.json) - **MUST PASS COMPLETELY**
- **Import Order**: Group as stdlib → third-party → local
- **Custom Type Stubs**: Created in typings/ directory for external libraries
- **Line Endings**: LF (Unix style)
- **Code Validation**: All code must pass both linting AND type checking BEFORE proceeding

### TypeScript/React

- **ESLint**: Using flat config in eslint.config.js and eslint.config.mjs. Project runs in **pragmatic mode**: legacy debt on unchanged lines is allowed, but any NEW ESLint **error** on a line you touched fails CI (warnings are advisory). Enforced by `scripts/eslint_diff_check.py` in `scripts/ci-quality-gate.sh` Stage 1.
- **TypeScript**: Strict mode enabled with project references - **COMPILATION MUST SUCCEED** (`npm run typecheck` baseline = 0 errors).
- **Build Verification**: `npm run build` must complete successfully
- **Formatting**: Follow ESLint configuration rules; the `eslint-staged` pre-commit hook applies `--fix` automatically on staged files.
- **Line Endings**: LF (Unix style)
- **Indentation**: 2 spaces
- **TypeScript Interfaces**: Ensure all standalone interface files have imports to avoid parsing errors
- **Trailing Commas**: Not allowed (configured in ESLint)

## Monorepo ESLint & TypeScript Configuration (Frontend)

- **Monorepo Flat Config**: ESLint is configured at the repo root (`eslint.config.js`) and imports the frontend config (`frontend/eslint.config.js`) for monorepo compatibility. Always run ESLint and pre-commit from the repo root.
- **TypeScript Project References**: The frontend uses strict TypeScript project references (`tsconfig.json`, `tsconfig.app.json`, `tsconfig.test.json`, etc.) for modularity and performance. ESLint is pointed to the correct `tsconfig.eslint.json` using absolute paths.
- **Legacy Code Exclusion**: ESLint configuration excludes build artifacts and cache files using robust absolute ignore patterns in ESLint config and pre-commit hooks. This ensures only source code is checked.
- **Pre-commit Integration**: The `.pre-commit-config.yaml` runs ESLint from the repo root, using the root config and correct args. It is set up to ignore legacy files and only check relevant frontend code.
- **Troubleshooting**:
  - If ESLint or pre-commit reports config or parsing errors, check that you are running from the repo root and that ignore patterns are absolute.
  - For TypeScript interface parsing errors, ensure all interface files have at least one import (see `npm run fix:interfaces`).
  - For persistent config issues, see `.github/instructions/eslint-typescript-config.instructions.md` and use MCP tools for targeted queries (e.g., `@context7 ESLint ignore patterns`, `@context7 legacy exclusion`).

See `.github/instructions/eslint-typescript-config.instructions.md` for detailed config, ignore, and troubleshooting patterns.

## Core Architecture

### Service Access (REQUIRED FOR ALL BACKEND CODE)

All backend code MUST access services via FastAPI dependency injection from `backend.core.dependencies`. The legacy `AppState` class and `backend/core/state.py` were removed during the ServiceRegistry refactor; the global state is now decomposed into repositories and services managed by the `ServiceRegistry` (see `backend/core/service_registry.py`).

#### Core Services

- **ServiceRegistry** (`backend/core/service_registry.py`): Central service lifecycle and dependency resolution.
- **FeatureManager** (`backend/services/feature_manager.py`): YAML-driven feature flag system.
- **ConfigService** (`backend/services/config_service.py`): Configuration access (use this rather than reading `Settings` directly).
- **DatabaseManager** (`backend/services/database_manager.py`): Async SQLAlchemy session management.
- **PersistenceService** (`backend/services/persistence_service.py`): Backups and durable storage.
- **AuthManager** / **AuthService** (`backend/services/auth_*.py`): Authentication, tokens, PIN/MFA.

#### Domain Services (access via DI)

- **EntityService** (`backend/services/entity_services.py`): RV-C entity CRUD and control.
- **CANBusService** (`backend/services/can_bus_service.py`): CAN interface monitoring and message sending.
- **RVCService** (`backend/services/rvc_service.py`): RV-C protocol decode/encode.
- **WebSocketService** (`backend/services/websocket_service.py`): Client connections and broadcasting.
- **SafetyService** (`backend/services/safety_service.py`): Safety-aware command validation.

#### Multi-Protocol Integrations

Multi-protocol support is implemented as **integrations**, not standalone services. The relevant code lives under `backend/integrations/`:

- `backend/integrations/can/`: CAN interface management; includes `multi_network_manager.py` (`MultiNetworkManager` for multi-network CAN with fault isolation).
- `backend/integrations/rvc/`: RV-C decoder, including Firefly extensions (`firefly_extensions.py`, `firefly_feature.py`, `firefly_registration.py`).
- `backend/integrations/j1939/`: J1939 decoder (`decoder.py`, `registration.py`) and Spartan K2 chassis extensions (`spartan_k2_extensions.py`, `spartan_k2_registration.py`).
- `backend/integrations/analytics/`: Performance analytics feature (`PerformanceAnalyticsFeature`).
- `backend/integrations/diagnostics/`: Cross-protocol diagnostics.

These integrations register themselves with the `FeatureManager` based on YAML feature flags; access them through the relevant service or repository, not via dedicated `get_*_service()` helpers.

### Project Structure

- `backend/core/`: ServiceRegistry, dependencies, configuration, custom exceptions, structured logging, security validation.
- `backend/services/`: Domain and management services.
- `backend/repositories/`: Repository pattern for data access (replaces the previous monolithic `AppState`).
- `backend/api/routers/`: REST API endpoints (legacy `/api/...`).
- `backend/api/domains/`: Domain API v2 endpoints (`/api/v2/...`) with bulk operations and richer schemas.
- `backend/middleware/`: HTTP middleware (auth, CSRF, structured logging).
- `backend/integrations/`: Protocol integrations (CAN, RV-C, J1939, Firefly, Spartan K2, analytics, diagnostics).
- `backend/websocket/`: WebSocket handlers.
- `frontend/`: React 19 + TypeScript SPA.

## Deployment Architecture

- **Backend**: FastAPI application served on configured port
- **Frontend**: React SPA built with Vite and served by Caddy
- **Reverse Proxy**: Caddy serves frontend static files and proxies API/WebSocket requests

## Code Patterns

### Backend Service Access (MANDATORY)

```python
# ALWAYS use FastAPI dependency injection from backend.core.dependencies.
# Prefer the Annotated[Type, Depends(...)] pattern for type-safe injection.
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.core.dependencies import (
    get_entity_service,
    get_config_service,
    get_can_facade,
    get_safety_service,
    get_rvc_service,
    get_multi_network_manager,
)
from backend.services.entity_services import EntityService

router = APIRouter()


@router.get("/entities")
async def list_entities(
    entity_service: Annotated[EntityService, Depends(get_entity_service)],
):
    return await entity_service.get_all_entities()


# WRONG: do not access app.state, the removed AppState, or import services as module-level globals.
# from backend.services.feature_manager import feature_manager  # ❌ module-level singleton
# from backend.core.state import AppState                       # ❌ removed
# from backend.core.dependencies import get_app_state           # ❌ removed
# from backend.core.dependencies import get_entity_manager      # ❌ removed (use get_entity_service)
```

### Development Patterns

- **FastAPI routes**: Organized by domain in `backend/api/routers/` using APIRouter
- **Management Services**: ALWAYS access via dependency injection from `backend.core.dependencies`
- **Feature Registration**: ALL features must extend Feature base class and register with FeatureManager
- **WebSockets**: Use WebSocketManager feature for client connections and broadcasting
- **State management**: Use repositories and services via DI; do **not** reach for `app.state` or any global `AppState` (both removed).
- **Configuration**: Use ConfigService for all configuration access
- **Database**: Use DatabaseManager and PersistenceService for data operations
- **Error handling**: Structured exceptions with proper logging
- **Testing**: pytest with mocked CANbus interfaces
- **React Components**: Organized by feature in the `frontend/src/` directory
- **API Integration**: REST and WebSocket connections between frontend and backend
- **Documentation**: MkDocs-based documentation with OpenAPI schema integration
  - API endpoints documented with FastAPI's metadata and docstring features
  - OpenAPI schema exported automatically via `scripts/export_openapi.py`
  - Frontend TypeScript types generated from OpenAPI schema
  - Documentation built with MkDocs Material theme
- **Type Stubs**: Custom type stubs in `typings/` for third-party libraries
  - Use Protocol-based implementations for complex interfaces
  - Only include required parts of the API that are actually used

## Environment Configuration

### Environment Variable Pattern

All configuration uses the `COACHIQ_` prefix with hierarchical naming:

- **Top-level**: `COACHIQ_SETTING` (e.g., `COACHIQ_APP_NAME`)
- **Nested**: `COACHIQ_SECTION__SETTING` (e.g., `COACHIQ_SERVER__HOST`)

### Key Configuration Files

- **`.env.example`**: Comprehensive documentation of all environment variables
- **`.env`**: Active configuration (not committed to git)
- **`backend/core/config.py`**: Pydantic Settings classes with validation

### Configuration Access

```python
# ALWAYS use ConfigService for configuration
from backend.core.dependencies import get_config_service

config_service: ConfigService = Depends(get_config_service)
settings = await config_service.get_config_summary()
```

### Persistence Modes

1. **Memory-only**: `COACHIQ_PERSISTENCE__ENABLED=false` (default)
2. **Development**: Local file storage in `backend/data/`
3. **Production**: System directory (e.g., `/var/lib/coachiq`)

## Nix Development Environment (Optional)

### Nix Flake

The project includes an optional Nix flake providing:

- **Reproducible environment** with all dependencies
- **CLI apps**: `nix run .#test`, `nix run .#lint`, `nix run .#format`
- **NixOS module** for production deployment
- **Automatic Poetry configuration** with correct library paths

### Nix Benefits (if used)

- **Cross-platform consistency**: Same environment on macOS and Linux
- **No Python version conflicts**: Uses Python 3.12
- **Automatic library path configuration**: Poetry works seamlessly
- **Built-in development tools**: pyright, ruff, nodejs included

**Note**: Nix is optional. All standard Poetry and npm commands work without Nix.

## Development Tools

- **VS Code Tasks**: Extensive task configuration for streamlined development:
  - **Server Tasks**: Start backend, frontend, documentation server
  - **Code Quality**: Linting, type checking, formatting for both backend and frontend
  - **Testing**: Run tests with coverage for backend, run frontend tests
  - **Build Tasks**: Build frontend and documentation
  - **Development**: Nix shell, pre-commit checks, dependency management
  - See `.github/instructions/vscode-tasks.instructions.md` for details
- **Model Context Protocol**: MCP tools provide critical context-aware assistance
  - `@context7`: **IMPORTANT** - Always use for up-to-date library documentation and code examples
    - Provides current API specifications and examples that avoid hallucinated APIs
    - Essential for any React, FastAPI, Next.js, or third-party library questions
    - Examples: `@context7 React useState TypeScript`, `@context7 FastAPI WebSocket auth`
  - `@perplexity`: External research for protocols and general concepts
  - `@github`: Repository and issue queries
- **MCP Best Practice**: Always default to `@context7` for library and framework questions before using general LLM knowledge

## Research-Driven Development (NEW PATTERN)

Based on proven success in multi-protocol implementation (35-70x development acceleration):

### Research Workflow Priority

1. **@context7 FIRST**: For framework and library questions (FastAPI, React, TypeScript, Python libraries)
2. **@perplexity for OEM research**: When implementing new manufacturer integrations
   - Example: `@perplexity Firefly RV systems protocol specifications and safety requirements`
   - Example: `@perplexity Spartan K2 chassis J1939 extensions and safety interlocks`
3. **@github for implementation patterns**: Repository exploration and issue research

### Manufacturer Integration Research Pattern

```bash
# 1. Research manufacturer specifications
@perplexity [Manufacturer] RV systems CAN protocol specifications safety requirements

# 2. Validate with library documentation
@context7 [Framework] protocol bridge implementation patterns

# 3. Check existing implementations
@github search code for [Manufacturer] integration patterns
```

### Validated Benefits

- **Development Speed**: Research-first approach eliminates weeks of reverse engineering
- **Implementation Accuracy**: First-time success with comprehensive feature coverage
- **Safety Compliance**: Research-validated safety interlock patterns
- **Quality**: Type-safe, tested, documented implementations
- **Testing**: Use `poetry run pytest` for backend tests and `cd frontend && npm test` for frontend
