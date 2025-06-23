# Task Completion Checklist

## After Making Code Changes

### Backend Changes
1. **Run Quality Checks** (MANDATORY):
   ```bash
   # Quick checks on changed files only
   poetry run ruff check --diff
   poetry run ruff format --check --diff

   # Security scan (always full)
   poetry run bandit -c pyproject.toml --severity-level medium -r backend
   ```

2. **Type Checking**:
   ```bash
   poetry run pyright backend
   ```

3. **Run Tests**:
   ```bash
   poetry run pytest
   # Or with coverage
   poetry run pytest --cov=backend --cov-report=term
   ```

### Frontend Changes
1. **Navigate to frontend directory first**:
   ```bash
   cd frontend
   ```

2. **Run Quality Checks**:
   ```bash
   npm run lint
   npm run typecheck
   ```

3. **Run Tests**:
   ```bash
   npm run test:run
   ```

### Before Committing
1. **Stage files**:
   ```bash
   git add -A
   ```

2. **Run pre-commit** (catches most issues):
   ```bash
   pre-commit run --all-files
   # Or just commit to trigger automatically
   git commit -m "feat: your change"
   ```

3. **If blocked by pre-commit**:
   - Fix the issues in changed files
   - Or use `--no-verify` for critical fixes (document why)
   - Or switch to pragmatic mode: `./scripts/switch-precommit-mode.sh pragmatic`

### Full Quality Validation (Before PRs)
```bash
# Run comprehensive CI checks locally
./scripts/ci-quality-gate.sh
```

### Configuration Changes
When adding features or dependencies, update:
- `pyproject.toml` for Python dependencies
- `flake.nix` for Nix dependencies
- `.env.example` for new environment variables
- Run `/sync-config` command if available

## Important Notes
- **Always use `poetry run`** for Python commands
- **Never skip security checks** (safety-critical system)
- **Pragmatic mode** blocks new issues in changed files only
- **CI will validate everything** on push
