#!/bin/bash
# CI Quality Gate for the CoachIQ Backend
# This script implements a diff-aware quality gate that:
# 1. Blocks new linting issues in changed files
# 2. Always enforces security standards on the full project
# 3. Uses baseline counting only for whole-project type checking

set -euo pipefail

# ANSI color codes
RED="\033[91m"
GREEN="\033[92m"
YELLOW="\033[93m"
BLUE="\033[94m"
RESET="\033[0m"

# Configuration - Update these numbers only when issues are actually fixed.
# These are debt-acknowledgement baselines, NOT improvement targets. The
# gate's job is to stop the count from going UP (a ratchet); fixing actual
# pyright errors lower the count and the script will print a green message
# nudging you to update the baseline downward.
EXPECTED_PYRIGHT_ERRORS=1533  # Ratcheted 2026-05-11 by PIN-manager fixes (Pydantic Field(default=...) keyword form cleared 10 latent errors).
EXPECTED_FRONTEND_TS_ERRORS=4  # Resynced 2026-05-11; pre-existing TS debt in DatabaseManagementTab + can-sniffer.

# Determine target branch (for GitHub Actions or local testing)
if [ -n "${GITHUB_BASE_REF:-}" ]; then
    TARGET_BRANCH="origin/${GITHUB_BASE_REF}"
    echo -e "${BLUE}🔍 Running CI Quality Gate for PR against: $TARGET_BRANCH${RESET}"
else
    TARGET_BRANCH="origin/main"
    echo -e "${BLUE}🔍 Running Quality Gate against: $TARGET_BRANCH${RESET}"
fi

# Ensure we have the latest target branch
echo -e "${BLUE}📡 Fetching latest changes...${RESET}"
git fetch origin || true

echo -e "\n${BLUE}============================================================${RESET}"
echo -e "${BLUE}CoachIQ CI Quality Gate${RESET}"
echo -e "${BLUE}============================================================${RESET}\n"

# ===== STAGE 1: Fast Linting on Changed Files Only =====
echo -e "${BLUE}🔧 Stage 1: Checking changed files for new linting issues...${RESET}"

# Run pre-commit on the changed-file set (formatting, JSON/YAML/TOML
# checks, ESLint, etc.) AND ruff on the changed-line set. These are the
# two halves of "diff-aware" gating:
#
#   - pre-commit's `--from-ref ... --to-ref` is FILE-level diff-aware,
#     which is the right granularity for whole-file hooks like ruff-format
#     and structural checks (a malformed JSON file is malformed regardless
#     of which lines changed).
#
#   - For ruff lint specifically we want LINE-level diff-awareness so the
#     gate doesn't drown PRs in pre-existing legacy debt every time a PR
#     touches a long-lived production file. ruff_diff_check.py runs
#     `ruff check` on changed files and filters the JSON output to only
#     issues whose line is in the PR's diff.
#
# Run via `poetry run` so this works under `nix run .#ci`, where poetry is
# on PATH but pre-commit and ruff live inside the poetry-managed venv.
PRECOMMIT_OK=true
RUFF_OK=true

# Skip pre-commit's `ruff` (linter) hook in Stage 1 — ruff_diff_check.py
# below covers the ruff lint side with line-level filtering. We still
# want pre-commit's `ruff-format` hook to run (formatting is correctly
# a file-level concern: a file is either canonically formatted or not).
if ! SKIP=ruff poetry run pre-commit run --from-ref "$TARGET_BRANCH" --to-ref HEAD; then
    PRECOMMIT_OK=false
fi

if ! poetry run python scripts/ruff_diff_check.py "$TARGET_BRANCH"; then
    RUFF_OK=false
fi

if $PRECOMMIT_OK && $RUFF_OK; then
    echo -e "${GREEN}✅ SUCCESS: No new linting issues in changed files${RESET}"
else
    echo -e "${RED}❌ FAILURE: New linting issues found in your changes${RESET}"
    echo -e "${RED}   Fix these issues before committing to maintain code quality${RESET}"
    exit 1
fi

# ===== STAGE 2: Critical Security Scan (Full Project) =====
echo -e "\n${BLUE}🔒 Stage 2: Security scan on entire project...${RESET}"

# Security is always a full-project concern
# Our pre-commit config already blocks on medium+ severity
if poetry run pre-commit run bandit --all-files; then
    echo -e "${GREEN}✅ SUCCESS: No critical security issues found${RESET}"
else
    echo -e "${RED}❌ FAILURE: Critical security issues detected${RESET}"
    echo -e "${RED}   All medium and high severity security issues must be fixed${RESET}"
    exit 1
fi

# ===== STAGE 3: Whole-Project Type Checking with Baseline =====
echo -e "\n${BLUE}🔍 Stage 3: Full-project type checking (Pyright)...${RESET}"

# Run Pyright and capture results
PYRIGHT_OUTPUT_FILE=$(mktemp)
if poetry run pyright --outputjson backend > "$PYRIGHT_OUTPUT_FILE" 2>/dev/null; then
    PYRIGHT_EXIT_CODE=0
else
    PYRIGHT_EXIT_CODE=$?
fi

# Parse error count from JSON output
if [ -s "$PYRIGHT_OUTPUT_FILE" ] && command -v jq >/dev/null 2>&1; then
    ACTUAL_PYRIGHT_ERRORS=$(jq '.summary.errorCount // 0' < "$PYRIGHT_OUTPUT_FILE")
else
    # Fallback if jq is not available or output is empty
    if [ $PYRIGHT_EXIT_CODE -eq 0 ]; then
        ACTUAL_PYRIGHT_ERRORS=0
    else
        echo -e "${YELLOW}⚠️  Warning: Could not parse Pyright output, assuming errors exist${RESET}"
        ACTUAL_PYRIGHT_ERRORS=999999  # Force failure on parse error
    fi
fi

# Baseline enforcement
if [ "$ACTUAL_PYRIGHT_ERRORS" -gt "$EXPECTED_PYRIGHT_ERRORS" ]; then
    echo -e "${RED}❌ FAILURE: Pyright found $ACTUAL_PYRIGHT_ERRORS errors, exceeding baseline of $EXPECTED_PYRIGHT_ERRORS${RESET}"
    echo -e "${RED}   Your changes may have introduced new type errors project-wide${RESET}"
    # Show first few errors for debugging
    if [ -s "$PYRIGHT_OUTPUT_FILE" ] && command -v jq >/dev/null 2>&1; then
        echo -e "${YELLOW}📋 First 5 type errors:${RESET}"
        jq -r '.generalDiagnostics[:5][] | "  \(.file):\(.range.start.line + 1) - \(.message)"' < "$PYRIGHT_OUTPUT_FILE" 2>/dev/null || true
    fi
    rm -f "$PYRIGHT_OUTPUT_FILE"
    exit 1
elif [ "$ACTUAL_PYRIGHT_ERRORS" -lt "$EXPECTED_PYRIGHT_ERRORS" ]; then
    echo -e "${GREEN}🎉 EXCELLENT: Type errors reduced from $EXPECTED_PYRIGHT_ERRORS to $ACTUAL_PYRIGHT_ERRORS!${RESET}"
    echo -e "${GREEN}   Please update EXPECTED_PYRIGHT_ERRORS in this script to $ACTUAL_PYRIGHT_ERRORS${RESET}"
    echo -e "${GREEN}   Include this baseline update in your PR${RESET}"
else
    echo -e "${GREEN}✅ SUCCESS: Pyright error count stable at baseline of $EXPECTED_PYRIGHT_ERRORS${RESET}"
fi

rm -f "$PYRIGHT_OUTPUT_FILE"

# ===== STAGE 4: Frontend Type Checking (if frontend exists) =====
if [ -d "frontend" ]; then
    echo -e "\n${BLUE}🎨 Stage 4: Frontend TypeScript checking...${RESET}"

    cd frontend

    # Count TypeScript errors (this is project-specific, adjust as needed)
    if npm run typecheck 2>&1 | tee /tmp/ts-output.log; then
        echo -e "${GREEN}✅ SUCCESS: No TypeScript compilation errors${RESET}"
    else
        # Count errors from output (this may need adjustment based on your TypeScript config)
        ACTUAL_TS_ERRORS=$(grep -c "error TS" /tmp/ts-output.log 2>/dev/null || echo "0")

        if [ "$ACTUAL_TS_ERRORS" -gt "$EXPECTED_FRONTEND_TS_ERRORS" ]; then
            echo -e "${RED}❌ FAILURE: TypeScript found $ACTUAL_TS_ERRORS errors, exceeding baseline of $EXPECTED_FRONTEND_TS_ERRORS${RESET}"
            exit 1
        elif [ "$ACTUAL_TS_ERRORS" -lt "$EXPECTED_FRONTEND_TS_ERRORS" ]; then
            echo -e "${GREEN}🎉 EXCELLENT: TypeScript errors reduced from $EXPECTED_FRONTEND_TS_ERRORS to $ACTUAL_TS_ERRORS!${RESET}"
            echo -e "${GREEN}   Please update EXPECTED_FRONTEND_TS_ERRORS in this script${RESET}"
        else
            echo -e "${YELLOW}⚠️  TypeScript compilation failed but error count within baseline${RESET}"
        fi
    fi

    cd ..
    rm -f /tmp/ts-output.log
fi

# ===== SUCCESS =====
echo -e "\n${BLUE}============================================================${RESET}"
echo -e "${GREEN}✅ ALL QUALITY GATES PASSED!${RESET}"
echo -e "${GREEN}🚀 Code is ready for merge${RESET}"
echo -e "${GREEN}🛡️  CoachIQ quality standards maintained${RESET}"
echo -e "${BLUE}============================================================${RESET}\n"

exit 0
