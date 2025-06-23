# Code Style and Conventions

## Python (Backend)
- **Line Length**: 100 characters
- **Import Style**: Absolute imports only (`from backend.services...`)
- **Target Python**: 3.12+
- **Type Hints**: Required for all public functions and methods
- **Docstrings**: Google style for functions and classes
- **Naming**:
  - Classes: PascalCase
  - Functions/Variables: snake_case
  - Constants: UPPER_SNAKE_CASE
  - Private: prefix with underscore
- **Async**: Use async/await for all I/O operations
- **Logging**: Use module-level logger (`logger = logging.getLogger(__name__)`)

## TypeScript (Frontend)
- **Strict Mode**: Enabled
- **Import Style**: Path aliases (`@/` maps to `src/`)
- **Component Structure**:
  - Function components with hooks
  - Props interfaces named `{Component}Props`
  - Export components as default
- **File Naming**:
  - Components: PascalCase.tsx
  - Utilities: camelCase.ts
  - Types: types.ts or {domain}.types.ts
- **State Management**:
  - Server state: React Query
  - UI state: React Context or local state
- **Error Handling**: Try-catch with proper error boundaries

## Architecture Patterns
- **API Design**: Unified entity endpoints (`/api/entities`, never `/api/lights`)
- **Domain API v2**: New features use `/api/v2/{domain}` pattern
- **Service Access**: Use dependency injection via `backend.core.dependencies`
- **WebSocket**: Real-time updates for entity state changes
- **Safety-Critical**: Use facades for vehicle control operations
- **Health Endpoints**: Root level `/healthz`, not `/api/healthz`

## Git Conventions
- **Commit Messages**: Conventional commits (feat:, fix:, docs:, etc.)
- **Branch Naming**: feature/*, fix/*, chore/*
- **Pre-commit**: Pragmatic mode for development, strict for releases
