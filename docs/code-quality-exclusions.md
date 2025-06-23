# Code Quality Tool Exclusions

## Overview

This document maintains the canonical list of directories and files excluded from linting and type checking in the CoachIQ monorepo.

**Important**: When adding new directories to the project, update ALL of the configuration locations listed below to maintain consistency.

## Configuration Locations

When adding new exclusions, update these files:

1. **`pyproject.toml`**: `[tool.ruff]` → `exclude`
2. **`pyproject.toml`**: `[tool.pyright]` → `exclude`
3. **`pyproject.toml`**: `[tool.bandit]` → `exclude_dirs`
4. **`frontend/eslint.config.js`**: `ignores` array
5. **`.eslintignore`** (root level)

## Standard Exclusions

### Version Control
```
.git, .hg, .svn
```

### Python
```
__pycache__, *.pyc, .venv, venv, env, .env, __pypackages__
```

### Testing & Coverage
```
.pytest_cache, .coverage, htmlcov, coverage.xml, .tox, .nox
```

### Type Checking
```
.mypy_cache, .pytype, .pyre
```

### Build Artifacts
```
build, dist, _build, *.egg-info, *.egg
```

### Caches
```
.ruff_cache, .cache, .vite
```

### Documentation
```
docs/_build, site
```

### IDE & Editor
```
.vscode, .idea, *.swp, *.swo
```

### OS Files
```
.DS_Store, Thumbs.db
```

### Frontend
```
node_modules, frontend/dist, frontend/coverage, frontend/htmlcov
```

### Project Specific
```
_deprecated, result, result-*
```

### Databases & Temporary Files
```
*.db, *.sqlite, *.sqlite3, *.tmp, *.temp, tmp/, temp/
```

## Maintenance Process

1. **Quarterly Review**: Check if tools have added shared configuration features
2. **When Adding Directories**: Update all 5 configuration locations
3. **Validation**: Run `python scripts/validate_exclusions.py` to verify consistency
4. **Testing**: Run `poetry run pre-commit run --all-files` after changes

## Rationale

We maintain separate exclusion lists for each tool because:
- Tools don't automatically share exclusion configurations
- Each tool may have slightly different pattern matching syntax
- This approach ensures consistent behavior whether tools are run via pre-commit or manually

## Performance Notes

- `force-exclude = true` in Ruff ensures exclusions work even when pre-commit passes files explicitly
- `pass_filenames: false` for Pyright lets it analyze the full project context
- Frontend tools use `.eslintignore` at root to prevent scanning Python directories
