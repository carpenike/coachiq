# Code Quality Tools

This document outlines the code quality tools used in the `CoachIQ` project.

## Python Code Quality Tools

### Ruff

[Ruff](https://github.com/astral-sh/ruff) is our primary Python linting tool. It's a fast, comprehensive linter written in Rust that replaces Flake8 and many of its plugins.

#### Key features

- 10-100x faster than Flake8
- Includes functionality from multiple Flake8 plugins
- Can automatically fix many issues
- Import sorting (replacing isort)
- Configurable through `pyproject.toml`

#### Usage

```bash
# Check your code
poetry run ruff check .

# Apply auto-fixes
poetry run ruff check --fix .
```

### Ruff Format

[Ruff Format](https://docs.astral.sh/ruff/formatter/) is our Python code formatter. It enforces a consistent style by reformatting your code to conform to its rules, similar to Black but integrated with the Ruff toolchain.

#### Key features

- Deterministic formatting
- Fast performance
- Integrated with Ruff linting
- Compatible with Black-style formatting

#### Usage

```bash
# Format your code
poetry run ruff format src tests
```

### Pyright/Pylance

[Pyright](https://github.com/microsoft/pyright) is our standardized static type checker for Python, used in VS Code via the Pylance extension. We've standardized on Pyright as our sole type checker due to its superior performance and integration with modern Python tools.

#### Key features

- Fast, incremental type checking
- Excellent IDE integration
- Strong support for modern Python typing features
- Better performance for larger codebases
- Native support for FastAPI and Pydantic type annotations

#### Usage

```bash
# Type check your code
npx pyright src

# Or in VS Code:
# Use the built-in type checking with Pylance
```

## Frontend Code Quality Tools

### ESLint

[ESLint](https://eslint.org/) is the standard linter for the React + TypeScript frontend. The configuration lives in `frontend/eslint.config.js` (flat config) and is imported from the repo-root `eslint.config.js` so monorepo-wide tooling stays consistent.

#### Usage

```bash
# Check the frontend
cd frontend && npm run lint

# Apply auto-fixes
cd frontend && npm run lint:fix
```

### TypeScript Compiler (`tsc --noEmit`)

```bash
# Type-check the frontend (strict mode)
cd frontend && npm run typecheck
```

The CI quality gate runs `npm run typecheck` and fails if any error is found (baseline ratcheted to 0 in PR #110).

## Diff-Aware Quality Gates ("Pragmatic Mode")

Both Python and frontend toolchains have *pragmatic-mode* gates: pre-existing legacy debt on lines you didn't touch is allowed, but any **new** violation on a line you DID touch fails the gate. This lets the project ratchet down legacy debt over time without each PR drowning in it.

The gates are implemented as paired diff-check scripts that mirror each other's UX:

| Concern | Script | Invocation |
|---------|--------|------------|
| Python lint (ruff) | `scripts/ruff_diff_check.py` | `poetry run python scripts/ruff_diff_check.py [BASE_REF]` |
| Frontend lint (ESLint) | `scripts/eslint_diff_check.py` | `poetry run python scripts/eslint_diff_check.py [BASE_REF] [--warnings-fail]` |

Both scripts:

1. Find files changed since `BASE_REF` (default `origin/main`, three-dot range to match GitHub PR diffs).
2. Run the underlying tool with JSON output on those files.
3. Cross-reference each diagnostic's line against the diff's added/changed line set.
4. Exit 0 if no NEW issues; exit 1 with a focused report if any new issues; exit 2 on tooling failure.
5. Print a "(N legacy issues on unchanged lines were ignored.)" footer so it's obvious what was suppressed.

Both scripts are wired into Stage 1 of `scripts/ci-quality-gate.sh`, which is what GitHub Actions runs via `nix run .#ci`. The pre-commit hook for each tool runs only the autofix half (`ruff format`, `eslint --fix`) and ignores legacy errors; the diff-aware blocking is CI's job.

### Updating baselines

Three tools have project-wide baselines in `scripts/ci-quality-gate.sh` that act as one-way ratchets:

| Tool | Variable | Stage | Current |
|------|----------|-------|---------|
| pyright | `EXPECTED_PYRIGHT_ERRORS` | Stage 3 | 1484 (PR #117) |
| TypeScript (`tsc --noEmit`) | `EXPECTED_FRONTEND_TS_ERRORS` | Stage 4 | 0 (PR #110) |
| ESLint (whole project) | `EXPECTED_FRONTEND_ESLINT_ERRORS` | Stage 5 | 648 (PR #117) |

Behavior:

- **Count goes UP** → CI fails. A regression was introduced; either fix it or (rare and discouraged) raise the baseline with a clear PR explanation.
- **Count goes DOWN without baseline update** → CI also fails. This forces the author to lower the baseline in the same PR, locking in the improvement so a later regression can't silently restore the old count.
- **Count equals baseline** → CI passes silently.

The "fail on improvement" behavior is intentional. The first PR that reduces a baseline does the work twice (write the fix, lower the number); every subsequent PR benefits because the project has now committed to the new ceiling.

For ESLint and ruff specifically, Stage 1's diff-aware checks (`scripts/eslint_diff_check.py`, `scripts/ruff_diff_check.py`) run *before* the whole-project ratchets and produce focused per-line error reports. The whole-project ratchets exist as a backstop in case the diff-check ever undercounts (e.g., issue #116, the shallow-clone false-positive bug).

## Pre-commit Integration

These tools are integrated into our [pre-commit](https://pre-commit.com/) configuration, ensuring code quality checks run automatically before each commit.

To set up pre-commit:

```bash
# Install pre-commit hooks
poetry run pre-commit install
```

## Custom Type Stubs

The project includes custom type stubs in the `typings/` directory to enhance type checking and IDE support, particularly for third-party libraries.

### FastAPI Type Stubs

We maintain custom type stubs for FastAPI to provide better typing for WebSocket components and other FastAPI features.

#### Organization

- `typings/fastapi/__init__.py` - Implementation file with detailed docstrings
- `typings/fastapi/__init__.pyi` - Type stub file with concise type definitions

#### Special Configuration

These files have specific lint exceptions in `pyproject.toml`:

```toml
[tool.ruff.lint.per-file-ignores]
# Allow function names that don't follow snake_case for FastAPI compatibility
# Also allow exception names without Error suffix to match FastAPI's conventions
"typings/fastapi/__init__.py" = ["N802", "N818"]
"typings/fastapi/__init__.pyi" = ["N802", "N818"]
# Allow relative imports in the typings directory for proper type stub organization
"typings/**/*.py" = ["TID252"]
"typings/**/*.pyi" = ["TID252"]
```

These exceptions allow:

- Non-snake_case function names (like `Body()`) to match FastAPI's API
- Exception names without the "Error" suffix (like `WebSocketDisconnect`) to match FastAPI's conventions
- Relative imports in type stub files for proper organization

For more details, see `typings/fastapi/README.md`.

## Why We Chose These Tools

- **Ruff over Flake8**: Ruff is significantly faster and includes all the functionality of Flake8 plus much more. It also has better integration with modern Python tooling.
- **Ruff Format over Black**: Ruff Format provides the same deterministic formatting as Black but is integrated with the Ruff toolchain, offering better performance and consistency with linting rules.
- **Pyright over mypy for type checking**: We've standardized on Pyright because it offers excellent performance, strong IDE integration via VS Code's Pylance extension, and better support for modern Python typing features, especially with FastAPI and Pydantic. It also provides faster type checking for large codebases.
- **Custom Type Stubs**: For better IDE support and type checking with libraries like FastAPI.

## VS Code Integration

VS Code tasks are configured for these tools:

- **Format Code (Ruff)**: Formats Python code
- **Lint (Ruff)**: Runs Ruff linting with fix capability
- **Type Check (Pyright)**: Performs static type checking
