# GitHub Copilot Instructions for rvc2api

- All build, cache, and output files (e.g., dist, dist-ssr, .vite, .vite-temp, node_modules, *.tsbuildinfo, .cache, *.log) are excluded from linting and type checking in both root and frontend ESLint configs.
- All API calls are made via /api/entities endpoints, not /api/lights, /api/locks, etc. to ensure a unified and extensible API design.
- All API endpoints require comprehensive documentation with examples, descriptions, and response schemas to maintain the OpenAPI specification.
- **All Python scripts must be run using Poetry.** Use `poetry run python <script>.py` or `poetry run <command>`, never `python <script>.py` directly.

This document provides key information for GitHub Copilot to understand the `rvc2api` project architecture and coding patterns.

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

`rvc2api` is a Python-based API and WebSocket service for RV-C (Recreational Vehicle Controller Area Network) systems:

- **FastAPI backend** with WebSocket support (migrated to `backend/` structure)
- **React frontend** with TypeScript and Vite
- **RV-C decoder** for CANbus messages
- **Service-oriented architecture** with clear separation of concerns
- **Typed code** with Pydantic models and full type hints
- **API Documentation** with MkDocs, Material theme, and OpenAPI integration

## Linting & Code Quality Requirements

### Python

- **Version**: 3.12+
- **Formatting**: ruff format (line length: 100)
- **Linting**: ruff (configured in pyproject.toml)
- **Type Checking**: pyright (basic mode, configured in pyrightconfig.json)
- **Import Order**: Group as stdlib → third-party → local
- **Custom Type Stubs**: Created in typings/ directory for external libraries
- **Line Endings**: LF (Unix style)
- **Code Validation**: All code must pass both linting AND type checking

### TypeScript/React

- **ESLint**: Using flat config in eslint.config.js and eslint.config.mjs
- **TypeScript**: Strict mode enabled with project references
- **Formatting**: Follow ESLint configuration rules
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

### Management Services (REQUIRED FOR ALL BACKEND CODE)
All backend development MUST use these management services via dependency injection:

#### Core Management Services
- **FeatureManager** (`backend/services/feature_manager.py`): Feature registration, lifecycle management
- **EntityManager** (`backend/core/entity_manager.py`): Entity operations, state management, device lookups
- **AppState** (`backend/core/state.py`): Application state management, entity tracking
- **DatabaseManager** (`backend/services/database_manager.py`): Database connections, health checks
- **PersistenceService** (`backend/services/persistence_service.py`): Data persistence, backup operations
- **ConfigService** (`backend/services/config_service.py`): Configuration management, environment variables

#### Domain Services (Use via dependency injection)
- **EntityService**: RV-C entity operations, light control, state management
- **CANService**: CAN bus operations, interface monitoring, message sending
- **RVCService**: RV-C protocol operations, message translation
- **DashboardService**: Dashboard data aggregation, activity feeds
- **WebSocketManager**: Client connections, real-time broadcasting

#### Multi-Protocol Services (NEW - Use via dependency injection)
- **J1939Service**: J1939 protocol operations, engine/transmission integration
- **FireflyService**: Firefly RV systems integration with multiplexing support
- **SpartanK2Service**: Spartan K2 chassis system integration with safety interlocks
- **MultiNetworkManager**: Multi-network CAN management with fault isolation
- **DiagnosticsHandler**: Cross-protocol diagnostics with fault correlation
- **PerformanceAnalyticsFeature**: Performance monitoring and optimization recommendations

### Project Structure
- `backend/core/`: Core management services (EntityManager, AppState, dependencies)
- `backend/services/`: Business logic services and FeatureManager
- `backend/api/routers/`: FastAPI routes organized by domain
- `frontend/`: React frontend with TypeScript, Vite, and Tailwind CSS

## Deployment Architecture

- **Backend**: FastAPI application served on configured port
- **Frontend**: React SPA built with Vite and served by Caddy
- **Reverse Proxy**: Caddy serves frontend static files and proxies API/WebSocket requests

## Code Patterns

### Backend Service Access (MANDATORY)
```python
# ALWAYS use dependency injection for services
from backend.core.dependencies import (
    get_feature_manager_from_request, get_entity_service, get_app_state,
    get_database_manager, get_config_service, get_can_service,
    get_can_interface_service, get_websocket_manager, get_persistence_service
)

# Multi-Protocol Service Dependencies (NEW)
from backend.core.dependencies import (
    get_j1939_service, get_firefly_service, get_spartan_k2_service,
    get_multi_network_manager, get_diagnostics_handler, get_performance_analytics
)

@router.get("/entities")
async def get_entities(
    entity_service: EntityService = Depends(get_entity_service),
    feature_manager: FeatureManager = Depends(get_feature_manager_from_request)
):
    """Use EntityService for entity operations, FeatureManager for feature access."""
    entities = await entity_service.get_all_entities()
    return entities

# Multi-Protocol Service Access Pattern (NEW)
@router.get("/protocols/status")
async def get_protocol_status(
    j1939_service: J1939Service = Depends(get_j1939_service),
    diagnostics_handler: DiagnosticsHandler = Depends(get_diagnostics_handler),
    multi_network: MultiNetworkManager = Depends(get_multi_network_manager)
):
    """Access multiple protocol services for unified status across RV-C, J1939, Firefly, Spartan K2."""
    cross_protocol_status = await diagnostics_handler.get_cross_protocol_status()
    network_health = await multi_network.get_network_health_summary()
    return {"protocols": cross_protocol_status, "networks": network_health}

# WRONG: Never access services directly or use incorrect dependency functions
from backend.services.feature_manager import feature_manager  # DON'T DO THIS
from backend.core.dependencies import get_entity_manager  # This function doesn't exist
```

### Development Patterns
- **FastAPI routes**: Organized by domain in `backend/api/routers/` using APIRouter
- **Management Services**: ALWAYS access via dependency injection from `backend.core.dependencies`
- **Feature Registration**: ALL features must extend Feature base class and register with FeatureManager
- **WebSockets**: Use WebSocketManager feature for client connections and broadcasting
- **State management**: Use AppState and EntityManager for application state
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
