# Code Quality Check

Run code quality checks using our pragmatic quality policy that balances safety with development velocity.

## Quick Check (Pragmatic Mode - DEFAULT)

For daily development, only check changed files:

```bash
# Ensure pragmatic mode is active
./scripts/switch-precommit-mode.sh pragmatic

# Run checks on staged files only
git add -A
pre-commit run

# Or check specific changed files
poetry run ruff check --diff
poetry run ruff format --check --diff
```

## Full Quality Check Workflow

For comprehensive validation before PRs or releases:

### 1. Python Backend Quality
```bash
# Formatting check
poetry run ruff format backend --check

# Linting
poetry run ruff check .

# Type checking
poetry run pyright backend
```

### 2. Frontend Quality
```bash
cd frontend

# Linting and formatting
npm run lint

# Type checking
npm run typecheck
```

### 3. Pre-commit Hooks
```bash
poetry run pre-commit run --all-files
```

### 4. Test Suite
```bash
# Backend tests
poetry run pytest

# Frontend tests
cd frontend && npm test
```

## Fix Mode

Add `--fix` argument to automatically fix issues where possible:

### Backend Fixes
```bash
poetry run ruff format backend
poetry run ruff check . --fix
```

### Frontend Fixes
```bash
cd frontend && npm run lint:fix
```

## Quality Standards

### Python Requirements
- **Line Length**: 100 characters
- **Import Order**: stdlib → third-party → local
- **Type Hints**: Required for all functions
- **Docstrings**: Required for public APIs

### TypeScript Requirements
- **Strict Mode**: Enabled
- **No Trailing Commas**: `comma-dangle: ["error", "never"]`
- **Double Quotes**: `quotes: ["error", "double"]`
- **Semicolons**: Required

## Arguments

$ARGUMENTS can specify:
- `--fix` - Automatically fix issues where possible
- `backend` - Run only Python backend checks
- `frontend` - Run only TypeScript frontend checks
- `tests` - Include test suite execution
- `--strict` - Fail on any warnings (CI mode)

## CI/CD Integration

Use the CI quality gate for the most accurate validation:

```bash
# Run the same checks CI will run
./scripts/ci-quality-gate.sh
```

This uses diff-aware checking and baseline management to allow existing debt while preventing new issues.

## Security Checks (ALWAYS BLOCKING)

Security scans always run on the full project:

```bash
# Must always pass - no exceptions
poetry run bandit -c pyproject.toml --severity-level medium -r backend
```

## Mode Management

```bash
# Check current mode
./scripts/switch-precommit-mode.sh status

# Switch between modes
./scripts/switch-precommit-mode.sh pragmatic  # For development
./scripts/switch-precommit-mode.sh strict     # For cleanup/releases
```
