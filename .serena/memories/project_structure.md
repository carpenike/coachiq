# Project Structure

## Root Directory
```
/Users/ryan/src/rvc2api/
├── backend/               # FastAPI backend application
├── frontend/             # React frontend application
├── config/               # Configuration files (RV-C specs, mappings)
├── tests/                # Backend test suite
├── scripts/              # Development and build scripts
├── docs/                 # Project documentation (MkDocs)
├── .claude/              # Claude-specific instructions and commands
├── resources/            # Static resources (PDFs, vector stores)
├── data/                 # Runtime data directory
├── deployment/           # Deployment configurations
├── typings/              # Python type stubs
└── templates/            # Template files

## Backend Structure
```
backend/
├── api/
│   ├── routers/          # FastAPI route handlers
│   ├── domains/          # Domain API v2 routers
│   └── middleware/       # API middleware
├── core/
│   ├── config.py         # Settings and configuration
│   ├── dependencies.py   # Dependency injection
│   ├── service_registry.py # Service lifecycle management
│   └── state.py          # Application state
├── services/             # Business logic services
│   ├── domains/          # Domain-specific services
│   └── facades/          # Safety-critical facades
├── models/               # Pydantic models
├── schemas/              # API schemas
├── repositories/         # Data persistence layer
├── integrations/         # External integrations
│   ├── can/             # CAN bus interfaces
│   └── rvc/             # RV-C protocol handling
├── websocket/           # WebSocket handlers
└── monitoring/          # Metrics and monitoring

## Frontend Structure
```
frontend/
├── src/
│   ├── api/             # API client functions
│   │   ├── domains/     # Domain API v2 clients
│   │   └── endpoints.ts # Legacy endpoints
│   ├── components/      # React components
│   │   └── ui/         # shadcn/ui components
│   ├── pages/          # Route page components
│   ├── hooks/          # Custom React hooks
│   │   └── domains/    # Domain-specific hooks
│   ├── contexts/       # React contexts
│   ├── types/          # TypeScript types
│   │   └── branded/    # Safety-critical branded types
│   ├── lib/            # Utility functions
│   └── test/           # Test setup and utilities
├── public/             # Static assets
└── dist/               # Build output

## Key Configuration Files
- `pyproject.toml` - Python dependencies and tool config
- `package.json` - Frontend dependencies
- `.env.example` - Environment variable documentation
- `flake.nix` - Nix build configuration
- `.pre-commit-config.yaml` - Git hooks configuration
- `pytest.ini` - Test configuration
- `tsconfig.json` - TypeScript configuration
- `vite.config.ts` - Vite build configuration

## Important Patterns
- Services use repository injection (no app_state)
- API endpoints follow `/api/entities` pattern
- Domain API v2 uses `/api/v2/{domain}` pattern
- Frontend uses React Query for server state
- WebSocket for real-time updates
- ServiceRegistry manages all service lifecycles
