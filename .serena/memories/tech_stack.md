# Tech Stack

## Backend
- **Language**: Python 3.12+
- **Framework**: FastAPI (>=0.115)
- **Server**: Uvicorn with standard extras
- **Package Management**: Poetry
- **Database**: SQLAlchemy 2.0+ with AsyncIO support
  - SQLite (aiosqlite) for development
  - PostgreSQL (asyncpg) for production
- **Authentication**: JWT (PyJWT), Passlib with bcrypt
- **CAN Bus**: python-can (>=4.0), cantools
- **WebSocket**: Built into FastAPI
- **Monitoring**: Prometheus client
- **Notifications**: Apprise
- **Documentation**: MkDocs with Mike versioning

## Frontend
- **Language**: TypeScript (strict mode)
- **Framework**: React 19 with Vite
- **UI Components**: shadcn/ui with Radix UI primitives
- **Styling**: TailwindCSS
- **State Management**:
  - React Query (TanStack Query) for server state
  - React Context for UI state
- **Forms**: React Hook Form with Zod validation
- **Routing**: React Router v6
- **Icons**: Lucide React, Tabler Icons
- **Charts**: Recharts
- **Build Tool**: Vite

## Development Tools
- **Python Linting**: Ruff (replaces Black, Flake8)
- **Python Type Checking**: Pyright
- **JS/TS Linting**: ESLint 9 with TypeScript plugin
- **Formatting**: Prettier (frontend), Ruff (backend)
- **Pre-commit**: Hooks for quality enforcement
- **Testing**:
  - Backend: pytest with asyncio
  - Frontend: Vitest with React Testing Library
- **Security**: Bandit for Python security scanning
