# Suggested Commands for Development

## Starting Development

### Backend Server
```bash
# Install dependencies first
poetry install

# Start development server (with reload and debug)
poetry run python run_server.py --reload --debug

# Or use the convenience script
./dev_start.sh
```

### Frontend Development
```bash
cd frontend
npm install
npm run dev   # Starts on http://localhost:5173
```

### Full Environment
```bash
# Use VS Code task: "Server: Start Full Dev Environment"
# Or run both servers in separate terminals
```

## Code Quality Commands

### Backend
```bash
# Linting (check only)
poetry run ruff check .

# Linting (with fixes)
poetry run ruff check . --fix

# Formatting
poetry run ruff format backend

# Type checking
poetry run pyright backend

# Security scan
poetry run bandit -c pyproject.toml --severity-level medium -r backend

# All pre-commit hooks
poetry run pre-commit run --all-files
```

### Frontend
```bash
cd frontend

# Linting
npm run lint
npm run lint:fix

# Type checking
npm run typecheck

# All quality checks
npm run quality:all
```

## Testing Commands

### Backend
```bash
# Run all tests
poetry run pytest

# With coverage
poetry run pytest --cov=backend --cov-report=term

# Specific test file
poetry run pytest tests/test_entity_service.py

# With verbose output
poetry run pytest -v
```

### Frontend
```bash
cd frontend

# Run tests
npm run test

# Run once (CI mode)
npm run test:run

# With coverage
npm run test:coverage

# Interactive UI
npm run test:ui
```

## Utility Commands

### Pre-commit Mode Switching
```bash
# Check current mode
./scripts/switch-precommit-mode.sh status

# Switch to pragmatic (development)
./scripts/switch-precommit-mode.sh pragmatic

# Switch to strict (releases)
./scripts/switch-precommit-mode.sh strict
```

### Documentation
```bash
# Start docs server
poetry run mkdocs serve

# Export OpenAPI schema
poetry run python scripts/export_openapi.py
```

### Build Commands
```bash
# Build frontend
cd frontend && npm run build

# Or use build script
./scripts/build-frontend.sh --install --lint
```

### Git Commands
```bash
# Status
git status

# Add all changes
git add -A

# Commit with conventional format
git commit -m "feat: add new feature"
git commit -m "fix: resolve bug"
git commit -m "docs: update README"

# Create PR (after pushing)
gh pr create --title "feat: new feature" --body "Description"
```

### System Commands (Darwin/macOS)
```bash
# List files
ls -la

# Change directory
cd path/to/dir

# Find files
find . -name "*.py" -type f

# Search in files (use ripgrep)
rg "search term" --type py

# Check running processes
ps aux | grep python

# Check ports
lsof -i :8000
```

## Development Workflows

### Adding New API Endpoint
1. Create router in `backend/api/routers/`
2. Add service in `backend/services/`
3. Register in ServiceRegistry
4. Add dependency function in `backend/core/dependencies.py`
5. Update OpenAPI docs

### Creating New React Component
1. Create in `frontend/src/components/`
2. Use shadcn/ui primitives
3. Add TypeScript props interface
4. Include in page component
5. Add tests

### Database Migration
```bash
# Create migration
poetry run alembic revision --autogenerate -m "description"

# Apply migrations
poetry run alembic upgrade head

# Rollback
poetry run alembic downgrade -1
```

## Important Reminders
- **ALWAYS use `poetry run`** prefix for Python commands
- **Navigate to frontend/** before running npm commands
- **Check pre-commit mode** before committing
- **Run quality checks** incrementally during development
- **Use conventional commits** for clear history
