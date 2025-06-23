# Pragmatic Quality Policy

## Overview

This project uses a **pragmatic quality policy** that balances code quality enforcement with development velocity, especially important given our existing technical debt.

## Core Principles

1. **Prevent Regression, Not Perfection**: Block NEW issues in CHANGED files only
2. **Security First**: ALWAYS block on medium+ security vulnerabilities
3. **CI as Safety Net**: Comprehensive project-wide checks run in CI before merge
4. **Developer Experience**: Fast local feedback, slow checks are optional

## Quality Gate Architecture

```
Local (Pre-commit) → Fast, Changed Files Only
     ↓
CI (GitHub Actions) → Comprehensive, Project-Wide
     ↓
Merge Protection → Must Pass All CI Checks
```

## Configuration Management

### Pre-commit Modes

We maintain two pre-commit configurations:

1. **Pragmatic Mode** (`.pre-commit-config.yaml`) - DEFAULT
   - Fast checks on changed files only
   - Type checking moved to manual stage
   - Enables development velocity

2. **Strict Mode** (`.pre-commit-config.strict.yaml`)
   - Full checks including pre-push hooks
   - Type checking on every push
   - Use before releases or during cleanup sprints

### Switching Modes

```bash
# Check current mode
./scripts/switch-precommit-mode.sh status

# Switch to pragmatic (recommended for daily work)
./scripts/switch-precommit-mode.sh pragmatic

# Switch to strict (for releases/cleanup)
./scripts/switch-precommit-mode.sh strict
```

## Developer Workflows

### Normal Development Flow

```bash
# 1. Ensure you're in pragmatic mode
./scripts/switch-precommit-mode.sh pragmatic

# 2. Make changes and commit normally
git add -A
git commit -m "feat: add new feature"

# 3. Push - CI will run comprehensive checks
git push
```

### When Blocked by Pre-commit

If pre-commit blocks your commit, you have options:

1. **Fix the issues** (preferred if they're in your changed files)
2. **Use --no-verify** (acceptable for critical fixes)
   ```bash
   git commit --no-verify -m "fix: critical security issue"
   ```
3. **Switch to pragmatic mode** if accidentally in strict mode

### Running Manual Checks

```bash
# Quick security scan (should always pass)
poetry run bandit -c pyproject.toml --severity-level medium -r backend

# Type checking (when you want to check)
pre-commit run pyright --all-files

# Full CI simulation locally
./scripts/ci-quality-gate.sh
```

## Quality Standards by Category

### Always Blocking (Fast)
- Trailing whitespace
- End of file fixes
- YAML/JSON/TOML syntax
- Merge conflicts
- Debug statements
- Security vulnerabilities (Medium+)

### Diff-Aware Blocking (Changed Files)
- Ruff formatting
- Ruff linting (with auto-fix)
- ESLint on staged files

### Manual/CI Only (Slow)
- Pyright type checking
- Frontend TypeScript checking
- Frontend build verification
- Poetry lock verification

## Baseline Management

The CI quality gate uses baselines to allow existing debt while preventing new issues:

```bash
# Current baselines (in scripts/ci-quality-gate.sh)
EXPECTED_PYRIGHT_ERRORS=962      # Python type errors
EXPECTED_FRONTEND_TS_ERRORS=3    # TypeScript errors
```

When you fix issues and reduce these numbers:
1. Update the baseline in the script
2. Include the update in your PR
3. Celebrate the improvement! 🎉

## When to Use --no-verify

Using `--no-verify` is acceptable for:

- **Critical security fixes** blocked by unrelated issues
- **Production hotfixes** that need immediate deployment
- **Switching between branches** with different quality states
- **Documentation-only changes** blocked by code issues

Always document why you used --no-verify in the commit message.

## CI Quality Gate Stages

The CI runs a 4-stage quality gate:

1. **Stage 1: Linting on Changed Files**
   - Uses `pre-commit run --from-ref origin/main --to-ref HEAD`
   - Zero tolerance for new issues

2. **Stage 2: Security Scan**
   - Full project Bandit scan
   - Blocks on Medium+ severity

3. **Stage 3: Type Checking**
   - Full project Pyright analysis
   - Baseline counting (no increases allowed)

4. **Stage 4: Frontend Validation**
   - TypeScript compilation
   - Baseline counting for existing errors

## Gradual Improvement Strategy

1. **Prevent New Debt**: Diff-aware checks block new issues
2. **Track Existing Debt**: Baselines make debt visible
3. **Celebrate Reductions**: Update baselines when improved
4. **Scheduled Cleanup**: Regular "quality sprints" to reduce debt

## Common Scenarios

### Scenario: "I need to commit a critical fix but pre-commit is blocking"
```bash
# Option 1: Fix only the issues in your changed files
poetry run ruff format backend/my_changed_file.py
poetry run ruff check backend/my_changed_file.py --fix

# Option 2: Bypass for critical fix
git commit --no-verify -m "fix: critical security vulnerability

Used --no-verify due to unrelated linting issues in codebase.
Follow-up task created: JIRA-1234"
```

### Scenario: "I want to clean up technical debt"
```bash
# Switch to strict mode
./scripts/switch-precommit-mode.sh strict

# Run full checks
pre-commit run --all-files

# Fix issues incrementally
# Update baselines as you improve
```

### Scenario: "CI is failing but my local commit worked"
```bash
# Reproduce CI locally
./scripts/ci-quality-gate.sh

# This will show exactly what CI sees
# Fix any issues and push again
```

## Integration with Claude

When Claude works on this codebase, it should:

1. Default to pragmatic mode for development tasks
2. Run security scans for any security-related changes
3. Use --no-verify only when explicitly fixing critical issues
4. Update baselines when improvements are made
5. Document any quality bypasses in commit messages

## The Philosophy

> "Perfect is the enemy of good. A pragmatic quality system that developers
> actually use is far better than a strict one they constantly bypass."

This approach acknowledges that:
- We have 4,436 existing linting issues
- We have 962 existing type errors
- Blocking all commits until these are fixed would halt development
- We can prevent NEW issues while gradually fixing old ones
- Security issues are never acceptable, regardless of age

By following this pragmatic approach, we maintain forward progress while continuously improving code quality.
