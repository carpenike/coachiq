# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚨 CRITICAL: Target Architecture (Pre-Release Development)

**IMPORTANT**: We are in pre-release development. Make breaking changes to reach the ideal architecture. Do NOT maintain backward compatibility.

**TARGET PATTERNS ONLY**:
- ✅ `backend.core.dependencies` for all service access
- ✅ FastAPI `Depends()` with `Annotated[Type, Depends()]` pattern
- ✅ ServiceRegistry for service lifecycle management
- ✅ Repository injection ONLY (no app_state parameters)
- ✅ Facades PREFERRED for safety-critical coordination
- ✅ Direct repository usage in simple services

**REMOVE ON SIGHT**:
- ❌ ALL `app_state` parameters in constructors
- ❌ ALL migration adapters (EntityServiceMigrationAdapter, etc.)
- ❌ ALL V1 service implementations
- ❌ ALL compatibility facades (for backward compatibility only)
- ❌ ALL backward compatibility code
- ❌ ALL feature flags for V1/V2 selection
- ❌ ALL FeatureManager usage and references

**KEEP AND PREFER THESE**:
- ✅ **Safety-critical facades** (RVCProtocolFacade, SafetyOperationsFacade, EntityControlFacade)
- ✅ **Multi-service coordination facades** (audit trails, real-time operations)
- ✅ **Complex subsystem facades** (DatabaseManager, AuthManager)
- ✅ **Facades that enforce safety boundaries** and centralized validation

**WHEN YOU ENCOUNTER LEGACY CODE**:
- DELETE the old implementation
- REPLACE with clean V2 implementation
- DO NOT add deprecation warnings
- DO NOT maintain compatibility
- DO NOT create adapters
- Just make it work the right way

## Modular Claude Instructions

This project uses modular Claude instruction files stored in `.claude/instructions/` and custom commands in `.claude/commands/`.
Each file contains targeted guidance for specific development workflows and contexts.

**Key instruction files:**

- [`backend.md`](.claude/instructions/backend.md): Python backend architecture, FastAPI patterns, service patterns
- [`frontend.md`](.claude/instructions/frontend.md): React frontend standards, TypeScript patterns, UI components
- [`testing.md`](.claude/instructions/testing.md): Testing patterns and requirements for both backend and frontend
- [`code-quality.md`](.claude/instructions/code-quality.md): Linting, formatting, and type checking standards
- [`api-patterns.md`](.claude/instructions/api-patterns.md): Entity control, WebSocket, and REST API patterns
- [`domain-api.md`](.claude/instructions/domain-api.md): Domain API v2 development patterns, bulk operations, and migration strategies
- 🆕 [`service-patterns.md`](.claude/instructions/service-patterns.md): **CRITICAL - Modern service access patterns, ServiceRegistry, and dependency injection**
- 🆕 [`safety-system-patterns.md`](.claude/instructions/safety-system-patterns.md): **CRITICAL - ISO 26262-compliant safety patterns, SafetyServiceRegistry, and emergency stop coordination**
- 🆕 [`security-patterns.md`](.claude/instructions/security-patterns.md): **CRITICAL - Security best practices, authentication, rate limiting, and sensitive data protection**

**Available commands:**

- `/fix-type-errors` - Run type checking and fix common issues
- `/run-full-dev` - Start complete development environment
- `/code-quality-check` - Run all linting, formatting, and type checks
- `/build-and-test` - Full build and test cycle
- `/setup-can-testing` - Set up virtual CAN environment and run comprehensive message tests
- `/manage-db` - Database development workflow including migrations, testing, and data management
- `/vector-search-dev` - Set up and develop FAISS-based vector search functionality
- `/deploy-docs` - Build and deploy documentation with OpenAPI schemas and PDF processing
- `/sync-deps` - Synchronize dependencies across Poetry, Nix, and frontend package managers
- `/sync-config` - Synchronize configuration files after adding features or dependencies
- `/rvc-debug` - Debug RV-C protocol encoding/decoding and real-time message monitoring
- `/domain-api-dev` - Develop Domain API v2 endpoints with bulk operations, caching, and monitoring
- `/api-migration` - Migrate legacy API endpoints to Domain API v2 with progressive rollout

**🆕 Code Quality & Safety Commands:**
- `/check-service-patterns` - Check for legacy service access patterns that need migration
- `/check-service-health` - Verify all services have proper health checks and dependencies
- `/check-memory-safety` - Ensure memory management patterns for real-time CAN operations
- `/check-safety-patterns` - Verify safety-critical patterns for RV-C vehicle control
- `/check-security-patterns` - Audit code for security best practices and vulnerabilities
- `/check-async-patterns` - Validate proper async/await usage and identify blocking operations
- `/check-tech-debt` - Find and categorize TODOs, FIXMEs, and technical debt
- `/dev-health-check` - Comprehensive development environment health diagnostics
- `/show-service-deps` - Visualize service dependencies and startup order

> **For any code generation or development tasks involving these topics, refer to the relevant instruction file in `.claude/instructions/` for detailed guidance.**

## Critical Development Requirements

- **All Python scripts must be run using Poetry.** Use `poetry run python <script>.py` or `poetry run <command>`, never `python <script>.py` directly.
- **MANDATORY CODE QUALITY GATES**: ALL code changes must pass linting, type checking, and build verification BEFORE proceeding to the next task. Run quality checks incrementally throughout development, not just at the end.
- **SAFETY-CRITICAL VALIDATION**: This is an RV-C vehicle control system. Code quality failures can result in dangerous malfunctions. ALL safety-critical validation MUST pass.
- **SECURITY-FIRST DEVELOPMENT**: Security vulnerabilities can lead to vehicle compromise. Follow security patterns in `.claude/instructions/security-patterns.md` without exception. No hardcoded secrets, no fallback values, proper rate limiting, and sensitive data protection are MANDATORY.
- **Use Domain API v2 for new development**: All new API integrations should use `/api/v2/{domain}` endpoints (e.g., `/api/v2/entities`) with domain-driven architecture patterns.
- **Legacy API compatibility**: Legacy `/api/entities` endpoints remain available but prefer Domain API v2 for enhanced features, bulk operations, and better performance.
- **All API endpoints require comprehensive documentation** with examples, descriptions, and response schemas to maintain the OpenAPI specification.
- **Domain API command structure**: Use structured command objects: `{"command": "set|toggle|brightness_up|brightness_down", "state": true/false, "brightness": 0-100, "parameters": {}}`
- **BRANDED TYPES**: Use branded types from `@/types/branded` for all safety-critical data (temperatures, pressures, speeds) to prevent type confusion.

### Command Execution Best Practices (BIAS TOWARDS ACTION)

**IMPORTANT**: Claude should take a bias towards action and ensure commands execute successfully on the first attempt:

1. **Before executing any terminal command**:
   - Review the command syntax carefully to avoid syntax errors
   - Verify all file paths and arguments are correctly formatted
   - Use proper quoting for paths with spaces or special characters
   - Ensure you're in the correct directory for the command

2. **If a command is not found**:
   - First check if you're using the correct command prefix (e.g., `poetry run` for Python commands)
   - Check if the command exists in the current PATH
   - Verify you're in the correct directory (frontend vs backend)
   - Check if dependencies need to be installed first (`poetry install` or `npm install`)

3. **Common command patterns to remember**:
   - Backend Python: Always use `poetry run python` not just `python`
   - Backend tools: `poetry run pytest`, `poetry run ruff`, `poetry run pyright`
   - Frontend: Navigate to `frontend/` directory first, then use `npm run`
   - Scripts: Make sure scripts are executable with `chmod +x` if needed

4. **Path verification before file operations**:
   - Use `pwd` to confirm current directory
   - Use `ls` to verify file/directory exists before operating on it
   - Use absolute paths when uncertain about relative paths

5. **Recovery from failures**:
   - If a command fails, diagnose the issue immediately
   - Check error messages for missing dependencies or incorrect paths
   - Don't repeat the same failed command without fixing the underlying issue

### Code Quality Requirements (MANDATORY)

**CRITICAL**: After ANY code change, you MUST run quality checks before proceeding:

**Frontend Quality Gates:**
```bash
cd frontend
npm run typecheck       # TypeScript compilation MUST pass (strict mode)
npm run lint           # ESLint MUST pass (SonarJS + security rules)
npm run security:audit # Dependency vulnerabilities MUST be resolved
npm run build          # Production build MUST succeed
```

**Backend Quality Gates:**
```bash
cd backend
poetry run pyright backend    # Type checking MUST pass (strict mode)
poetry run ruff check .        # Linting MUST pass (safety-critical rules)
poetry run ruff format .       # Code formatting MUST be applied
poetry run bandit -c pyproject.toml -r backend  # Security scanning MUST pass
poetry run pip-audit           # Dependency vulnerabilities MUST be resolved
```

**When to Run Quality Checks:**
- After every significant code change (>10 lines)
- Before moving to the next development task
- Before any git commit
- After implementing any new feature or component
- During refactoring operations

**Development Workflow Pattern:**
1. Make code changes
2. Run appropriate quality checks immediately
3. Fix any issues before proceeding
4. Only then move to the next task

**Use Available Quality Commands:**
- `/fix-type-errors` - Automated type error resolution
- `/code-quality-check` - Comprehensive quality validation
- `/build-and-test` - Full build and test verification
- `./scripts/code_quality_check.sh` - Complete safety-critical validation suite

## Domain API v2 Architecture Patterns

**IMPORTANT**: All new development should follow Domain API v2 patterns. The project now uses domain-driven architecture for better scalability, performance, and maintainability.

### Backend Domain API Patterns

**Domain Structure**:
```
backend/api/domains/          # Domain-specific API routers
backend/services/domains/     # Domain business logic
backend/schemas/             # Pydantic schemas with Zod export
backend/middleware/          # Domain-specific middleware
backend/monitoring/          # Domain observability
```

**Key Patterns**:
1. **Domain Routers**: Use `/api/v2/{domain}` endpoints (e.g. `/api/v2/entities`)
2. **Bulk Operations**: Implement efficient bulk operations with partial success handling
3. **Type Safety**: Use Pydantic schemas with TypeScript export capability
4. **Caching & Rate Limiting**: Domain-specific performance optimizations
5. **Monitoring**: Built-in metrics, logging, and health checks

### Frontend Domain API Patterns

**Frontend Structure**:
```
frontend/src/api/domains/     # Domain-specific API clients
frontend/src/api/types/       # TypeScript types from backend schemas
frontend/src/hooks/domains/   # Domain-specific React hooks
frontend/src/components/      # Enhanced UI components for bulk ops
```

**Key Patterns**:
1. **Domain API Clients**: Use `fetchEntitiesV2()`, `controlEntityV2()` functions
2. **React Hooks**: Use `useEntitiesV2()`, `useControlEntityV2()` with optimistic updates
3. **Bulk Operations**: Use `useBulkControlEntitiesV2()` and selection management hooks
4. **Progressive Migration**: Use `withDomainAPIFallback()` for gradual migration from legacy APIs
5. **Type Safety**: Import types from `@/api/types/domains` for full type safety

### Migration Strategy

**For New Features**: Always use Domain API v2 patterns
**For Existing Code**: Use progressive migration with fallback support
**Authentication**: Support JWT, API Key, and Legacy session authentication
**Error Handling**: Use structured error responses with proper HTTP status codes

### Example Usage Patterns

**Backend Domain Router**:
```python
from backend.api.domains.entities import create_entities_router
router = create_entities_router()  # Auto-includes bulk ops, caching, monitoring
```

**Frontend Hook Usage**:
```typescript
import { useEntitiesV2, useControlEntityV2 } from '@/hooks/domains/useEntitiesV2';

// Enhanced entity management with optimistic updates
const { data: entities } = useEntitiesV2({ device_type: 'light' });
const controlEntity = useControlEntityV2();
```

**Bulk Operations**:
```typescript
import { useBulkControlEntitiesV2, useEntitySelection } from '@/hooks/domains/useEntitiesV2';

// Advanced bulk operations with selection management
const { executeBulkOperation } = useEntitySelection();
const result = await executeBulkOperation({ command: { command: 'set', state: false } });
```

## Configuration File Synchronization Requirements

**CRITICAL**: When adding new features, dependencies, or configuration options, you MUST update ALL relevant configuration files to maintain consistency across the project:

### When Adding New Python Dependencies:
1. **`pyproject.toml`** - Add to `[tool.poetry.dependencies]` or appropriate group
2. **`flake.nix`** - Add to `propagatedBuildInputs`, `devShell buildInputs`, and `ciShell buildInputs`
3. **Verify** - Run `nix flake check` to ensure Nix build compatibility

### When Adding New Features or Protocols:
1. **`flake.nix`** - Add NixOS module options in the `settings` section
2. **`flake.nix`** - Add environment variable mapping in the `systemd.services.coachiq.environment` section
3. **`.env.example`** - Add example environment variables with documentation
4. **Documentation** - Update relevant files in `docs/` if applicable

### Configuration File Checklist:
```bash
# When adding features, verify these files are updated:
□ flake.nix (settings section)           # NixOS module options
□ flake.nix (environment section)        # Environment variable mapping
□ .env.example                           # Environment variable examples
□ pyproject.toml                         # Python dependencies (if needed)
□ flake.nix (buildInputs)                # Nix dependencies (if needed)
```

### Environment Variable Naming Convention:
- **Top-level settings**: `COACHIQ_SETTING` (e.g., `COACHIQ_APP_NAME`)
- **Nested settings**: `COACHIQ_SECTION__SETTING` (e.g., `COACHIQ_SERVER__HOST`)
- **Feature flags**: `COACHIQ_FEATURES__ENABLE_FEATURE_NAME`
- **Protocol settings**: `COACHIQ_PROTOCOL__SETTING` (e.g., `COACHIQ_RVC__ENABLE_ENCODER`)

### Example: Adding a New Protocol

```nix
# 1. flake.nix - Add to settings section
newProtocol = {
  enabled = lib.mkOption {
    type = lib.types.bool;
    default = false;
    description = "Enable new protocol integration";
  };
  customSetting = lib.mkOption {
    type = lib.types.bool;
    default = true;
    description = "Enable custom setting for new protocol";
  };
};

# 2. flake.nix - Add to environment section
COACHIQ_NEW_PROTOCOL__ENABLED = lib.mkIf config.coachiq.settings.newProtocol.enabled "true";
COACHIQ_NEW_PROTOCOL__CUSTOM_SETTING = lib.mkIf (!config.coachiq.settings.newProtocol.customSetting) "false";
```

```bash
# 3. .env.example - Add documentation
# =============================================================================
# NEW PROTOCOL CONFIGURATION
# =============================================================================
COACHIQ_NEW_PROTOCOL__ENABLED=false
COACHIQ_NEW_PROTOCOL__CUSTOM_SETTING=true
```

**Failure to update configuration files will result in deployment issues and inconsistent behavior across development/production environments.**

### Critical Configuration Files (Always Check These):

| File | Purpose | Update When |
|------|---------|-------------|
| `flake.nix` (settings section) | NixOS module configuration options | Adding configurable parameters |
| `flake.nix` (environment section) | Environment variable mapping for systemd | Adding any new setting |
| `.env.example` | Environment variable documentation | Adding any new environment variable |
| `pyproject.toml` | Python dependencies | Adding Python packages |
| `flake.nix` (buildInputs) | Nix dependencies | Adding system or Python dependencies |

**Pro Tip**: Use the `/sync-config` command after making changes to automatically detect and update missing configuration entries.

## Project Overview

CoachIQ is an intelligent RV-C network management system with advanced analytics and control. It provides a FastAPI backend for CAN bus monitoring/control, a React frontend for user interaction, and comprehensive documentation search capabilities.

**Key Architecture:**

- **Backend**: FastAPI-based service-oriented architecture with ServiceRegistry
- **Frontend**: Modern React SPA with Vite, TypeScript, TailwindCSS, and shadcn/ui
- **Configuration**: Pydantic-based settings with environment variable support
- **CAN Integration**: Multiple CAN interface support with RV-C protocol decoding

## Development Commands

### IMPORTANT: Always Use Poetry

**All Python commands in this project MUST be run through Poetry:**
```bash
# First, ensure dependencies are installed
poetry install

# ALWAYS prefix Python commands with 'poetry run'
poetry run python <any_script>.py
poetry run pytest
poetry run ruff check .
poetry run pyright backend
```

### Backend Development

```bash
# Install dependencies (always do this first)
poetry install

# Start development server
poetry run python run_server.py --reload --debug

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=backend --cov-report=term

# Code quality
poetry run ruff check .
poetry run ruff format backend
poetry run pyright backend

# Pre-commit hooks
poetry run pre-commit run --all-files
```

### Frontend Development

```bash
cd frontend

# Development server
npm run dev

# Build for production
npm run build

# Testing
npm run test
npm run test:coverage

# Code quality
npm run lint
npm run lint:fix
npm run typecheck
```

### Integrated Build Tools

```bash
# Frontend build script (supports --dev, --install, --lint, --clean)
./scripts/build-frontend.sh

# Full development environment (both backend and frontend)
# Use VS Code tasks: "Server: Start Full Dev Environment"
```

### Nix Environment (Optional)

```bash
# Nix is optional - all commands work with standard Poetry/npm
nix run .#test          # Run tests
nix run .#lint          # Run linters
nix run .#format        # Format code
nix run .#ci            # Full CI suite
```

## Architecture & Code Patterns

### Backend Structure

- **ServiceRegistry**: Centralized service lifecycle management with dependency resolution
- **Services**: Service classes in `backend/services/` handle business logic
- **Models**: Pydantic models in `backend/models/` for data validation
- **API Routers**: FastAPI routers in `backend/api/routers/` organized by domain
- **Configuration**: Centralized in `backend/core/config.py` using Pydantic Settings
- **Dependencies**: Modern dependency injection via `backend/core/dependencies.py`

### Frontend Structure

- **Components**: React components in `frontend/src/components/` with shadcn/ui design system
- **Pages**: Route components in `frontend/src/pages/`
- **API Client**: Centralized API calls in `frontend/src/api/`
- **State Management**: React Query for server state, React Context for UI state
- **WebSocket**: Real-time updates via `frontend/src/contexts/websocket-context.ts`

### Key Integrations

- **RV-C Protocol**: Decoding logic in `backend/integrations/rvc/`
- **CAN Bus**: Interface management in `backend/integrations/can/`
- **WebSocket**: Real-time communication in `backend/websocket/`
- **Vector Search**: FAISS-based document search (optional feature)

## Configuration

### Environment Variables

Use `COACHIQ_` prefix with double underscore for nested settings:

```bash
COACHIQ_SERVER__HOST=0.0.0.0
COACHIQ_SERVER__PORT=8080
COACHIQ_CAN__INTERFACES=can0,can1
COACHIQ_FEATURES__ENABLE_VECTOR_SEARCH=true
```

### Configuration Files

- **RV-C Spec**: `config/rvc.json` (bundled resources prioritized for Nix compatibility)
- **Coach Mapping**: `config/coach_mapping.default.yml` or `config/{model}.yml`

## Testing

### Backend Testing

- **Framework**: pytest with asyncio support
- **Location**: `tests/` directory
- **Factories**: Test factories in `tests/factories.py`
- **Configuration**: `pytest.ini` with custom python path

### Frontend Testing

- **Framework**: Vitest with jsdom environment
- **Testing Library**: React Testing Library
- **Setup**: `frontend/src/test/setup.ts`
- **Location**: Tests co-located with components or in `__tests__` directories

## Code Quality

### Backend Standards

- **Formatting**: Ruff formatter (replaces Black)
- **Linting**: Ruff linter (replaces Flake8)
- **Type Checking**: Pyright with custom stubs in `typings/`
- **Import Style**: Absolute imports only (`from backend.services...`)
- **Line Length**: 100 characters

### Frontend Standards

- **TypeScript**: Strict mode enabled
- **Linting**: ESLint with TypeScript and React plugins
- **Formatting**: Built into ESLint configuration
- **Imports**: Path aliases (`@/` for `src/`)

## Special Considerations

### WebSocket Integration

- Backend provides real-time entity updates via WebSocket
- Frontend uses optimistic updates with WebSocket synchronization
- WebSocket logging integration updates log display in real-time

### CAN Bus & RV-C

- Multi-interface CAN support with automatic reconnection
- RV-C message decoding based on PGN/SPN specifications
- Entity state management with change tracking and persistence

### Performance Optimizations

- Frontend uses React Query for efficient data fetching and caching
- Virtualized components for large data sets
- Bundle splitting and tree-shaking configured in Vite
- Backend feature system allows disabling unused functionality

### Nix Integration

- Full Nix flake with development shell
- NixOS module for system integration
- Bundled resource handling for configuration files

## Documentation

### API Documentation

- **Swagger UI**: Available at `/docs` when server running
- **ReDoc**: Available at `/redoc`
- **OpenAPI Export**: `poetry run python scripts/export_openapi.py`

### Project Documentation

- **MkDocs**: `poetry run mkdocs serve` for local development
- **Versioning**: Mike-based versioning with `./scripts/docs_version.sh`
- **GitHub Pages**: Auto-deployment from main branch

### Vector Search (Optional)

- **Setup**: Place RV-C spec PDF in `resources/` and run `poetry run python scripts/setup_faiss.py --setup`
- **Query**: `poetry run python dev_tools/query_faiss.py "search term"`
- **API**: `/api/docs/search?query=term`

## Important Development Guidelines

### Service Access Patterns (CRITICAL - NEW)

**MANDATORY**: All new code MUST use the modern service access patterns:
1. Import from `backend.core.dependencies`
2. Use `Annotated[Type, Depends(get_service)]` for type-safe dependency injection
3. Never access `app.state` directly - always use ServiceRegistry through DI
4. Run `/check-service-patterns` to verify your code follows modern patterns
5. See `.claude/instructions/service-patterns.md` for comprehensive guidelines

### Python Command Execution

**CRITICAL**: Always use `poetry run` for all Python commands and scripts in this project. This ensures proper dependency isolation and virtual environment usage.

**Step 1: Install dependencies**
```bash
poetry install
```

**Step 2: Run all Python commands with `poetry run`**
- `poetry run python run_server.py` (not `python run_server.py`)
- `poetry run pytest` (not `pytest`)
- `poetry run python dev_tools/query_faiss.py` (not `python dev_tools/query_faiss.py`)
- `poetry run ruff check .` (not `ruff check .`)
- `poetry run pyright backend` (not `pyright backend`)
- `poetry run pre-commit run --all-files` (not `pre-commit run --all-files`)

This applies to **ALL** Python scripts, development tools, tests, and any other Python-based operations.

### Using Playwright for Development

When building React pages, use Playwright MCP tools to verify your work interactively:

```bash
# Start your dev environment first
cd frontend && npm run dev  # Frontend on http://localhost:5173
poetry run python run_server.py --reload  # Backend on http://localhost:8080
```

Then use these MCP commands to interact with the UI:
- `browser_navigate(url="http://localhost:5173")` - Open the app
- `browser_snapshot()` - See current page structure and accessibility tree
- `browser_click(element="Button text", ref="button")` - Test buttons and links
- `browser_type(element="Input label", ref="input", text="test")` - Fill forms
- `browser_take_screenshot()` - Visual verification
- `browser_console_messages()` - Check for JavaScript errors

This helps verify that components work correctly during development without manual testing. Always take a snapshot first to understand the current page state before performing actions.

## MCP Tools Integration

**IMPORTANT**: Use the appropriate MCP server for each task to ensure efficient and accurate development. Each MCP server has specific strengths and should be used according to the decision matrix below.

### Available MCP Servers

1. **@context7** - Library & Framework Documentation
   - **Use for**: FastAPI, React, TypeScript, Python libraries, framework-specific patterns
   - **Strengths**: Up-to-date API documentation, correct usage examples, best practices
   - **Example**: `@context7 FastAPI dependency injection with Annotated`

2. **@perplexity** - Web Research & General Concepts
   - **Use for**: Protocols, general concepts, industry standards, external research
   - **Strengths**: Real-time information, broad knowledge base, cited sources
   - **Example**: `@perplexity RV-C J1939 protocol specifications`

3. **@github** - Repository & Code Exploration
   - **Use for**: Issue tracking, repository history, code search across GitHub
   - **Strengths**: Repository insights, issue patterns, community solutions
   - **Example**: `@github search similar WebSocket reconnection issues`

4. **@zen** - Code Analysis & Refactoring
   - **Use for**: Deep code analysis, refactoring suggestions, architecture reviews, debugging
   - **Strengths**: Multi-model consensus, comprehensive analysis, refactoring patterns
   - **Available tools**: `thinkdeep`, `codereview`, `debug`, `analyze`, `refactor`, `testgen`
   - **Example**: `@zen codereview` for comprehensive code quality analysis

5. **@playwright** - Browser Automation & UI Testing
   - **Use for**: UI verification during development, E2E testing, visual regression
   - **Strengths**: Real browser interaction, accessibility testing, screenshot capture
   - **Example**: Use `browser_snapshot()` to verify React component rendering

6. **@serena** - Semantic Code Navigation
   - **Use for**: Project-specific code exploration, symbol analysis, file navigation
   - **Strengths**: Context-aware code understanding, efficient file traversal
   - **Example**: `find_symbol` for precise code location and editing

### MCP Server Selection Matrix

| Task Type | Primary MCP Server | Secondary/Alternative |
|-----------|-------------------|----------------------|
| Library/Framework API questions | @context7 | @perplexity (if not in docs) |
| Bug investigation | @zen debug | @serena (for code navigation) |
| Code quality review | @zen codereview | @serena (for symbol analysis) |
| UI component testing | @playwright | - |
| Protocol/Standard research | @perplexity | @context7 (for implementation) |
| Repository exploration | @github | @serena (for local code) |
| Refactoring suggestions | @zen refactor | @serena (for impact analysis) |
| Test generation | @zen testgen | @context7 (for testing patterns) |
| Architecture analysis | @zen analyze | @perplexity (for patterns) |
| Code navigation | @serena | - |

### Best Practices

1. **Context-First Approach**: Always check @context7 for library-specific questions before using general research
2. **Leverage Specialization**: Use each server for its intended purpose to get the best results
3. **Combine for Complex Tasks**:
   - Use @serena to navigate to code, then @zen for analysis
   - Use @context7 for API docs, then @zen testgen for test creation
4. **Validate with Multiple Sources**: For critical decisions, cross-reference between servers
5. **Document Server Usage**: When sharing solutions, indicate which MCP server provided the information

### Common Workflows

**Debugging a Complex Issue:**
```
1. @serena find_symbol - Locate the problematic code
2. @zen debug - Systematic root cause analysis
3. @context7 - Check correct API usage
4. @zen codereview - Verify the fix
```

**Implementing New Feature:**
```
1. @context7 - Research framework patterns
2. @perplexity - Understand domain concepts
3. @serena - Navigate existing code structure
4. @zen analyze - Understand current architecture
5. @playwright - Verify UI implementation
```

**Code Quality Improvement:**
```
1. @zen codereview - Identify issues
2. @zen refactor - Get refactoring suggestions
3. @serena - Navigate to affected code
4. @zen testgen - Generate missing tests
```

### Project-Specific MCP Queries

- `@context7 Domain API v2 patterns` - Modern API development patterns
- `@zen analyze backend/services` - Service architecture review
- `@serena find_symbol EntityService` - Navigate to entity management code
- `@playwright browser_snapshot` - Verify UI component state
- `@perplexity RV-C CAN bus best practices` - Protocol implementation guidance
- `@github CoachIQ WebSocket issues` - Historical issue patterns

### MCP Usage Examples & Anti-Patterns

#### ✅ Good MCP Usage Patterns

**Library Research - Use @context7 First:**
```
# GOOD: Check documentation first
@context7 FastAPI WebSocket authentication with JWT

# GOOD: Fall back to @perplexity only if needed
@perplexity WebSocket subprotocol negotiation RFC 6455
```

**Debugging Complex Issues - Combine Tools:**
```
# GOOD: Use @serena to navigate, then @zen to analyze
1. @serena find_symbol RVCService handle_message
2. @zen debug - investigate message parsing issue
3. @context7 asyncio exception handling patterns
```

**Code Quality - Use Specialized Tools:**
```
# GOOD: Use @zen for comprehensive reviews
@zen codereview backend/services/rvc_service.py

# GOOD: Generate tests with context
@zen testgen backend/services/entity_service.py
```

#### ❌ Common Anti-Patterns to Avoid

**Don't Use General Research for Library Questions:**
```
# BAD: Using @perplexity for library-specific questions
@perplexity how to use FastAPI Depends

# GOOD: Use @context7 for framework specifics
@context7 FastAPI Depends with Annotated pattern
```

**Don't Skip Code Navigation:**
```
# BAD: Guessing file locations
"I think the EntityService is in backend/services/entity_service.py"

# GOOD: Use @serena to find exact locations
@serena find_symbol EntityService
```

**Don't Use Wrong Tool for Task:**
```
# BAD: Using @github for local code search
@github search this repository for WebSocket handlers

# GOOD: Use @serena for local code
@serena search_for_pattern "class.*WebSocket.*Handler"
```

**Don't Ignore Tool Specialization:**
```
# BAD: Manual debugging without tools
"Let me read through this code to find the bug"

# GOOD: Use @zen debug for systematic investigation
@zen debug - WebSocket connection drops after 30 seconds
```

### MCP Integration with Project Workflows

**Service Migration Pattern:**
```
1. @serena find_symbol OldService - Locate legacy code
2. @zen analyze - Understand current implementation
3. @context7 FastAPI dependency injection patterns
4. @zen refactor - Get migration suggestions
5. @zen codereview - Validate new implementation
```

**Feature Implementation Pattern:**
```
1. @context7 React hooks best practices
2. @serena get_symbols_overview frontend/src/hooks
3. @zen analyze - Review existing patterns
4. @playwright browser_snapshot - Verify UI behavior
```

**Performance Investigation Pattern:**
```
1. @zen analyze backend/services - Find bottlenecks
2. @perplexity Python asyncio performance patterns
3. @zen refactor - Optimize critical paths
4. @zen codereview - Verify improvements
```

## important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

**MANDATORY CODE QUALITY ENFORCEMENT**: ALWAYS run quality checks (lint, typecheck, build) after ANY code change before proceeding to the next task. This is NON-NEGOTIABLE. Use incremental quality validation throughout development, not just at completion.

**CONFIGURATION SYNCHRONIZATION REQUIREMENT**: When implementing new features, protocols, or dependencies, you MUST update ALL relevant configuration files (feature_flags.yaml, flake.nix settings and environment mappings, .env.example) to maintain consistency. Use `/sync-config` command when available or manually verify the configuration file checklist in the "Configuration File Synchronization Requirements" section.
