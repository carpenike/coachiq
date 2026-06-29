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
EXPECTED_PYRIGHT_ERRORS=1371  # Ratcheted 2026-06-29 after HOF-032 path typing cleanup (1375 -> 1371).
EXPECTED_FRONTEND_TS_ERRORS=0  # Ratcheted 2026-05-12 to 0 by PR #110 (DatabaseManagementTab + can-sniffer + useCANScanWebSocket generic). Any new TS error is a hard fail.
EXPECTED_FRONTEND_ESLINT_ERRORS=602  # Ratcheted 2026-06-29 after HOF-032 diff-line cleanup (603 -> 602).

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
ESLINT_OK=true

# Skip pre-commit's `ruff` (linter) hook AND `eslint-staged` hook in Stage 1.
# Their diff-aware counterparts (ruff_diff_check.py, eslint_diff_check.py)
# below handle line-level filtering. We still want pre-commit's `ruff-format`
# hook to run (formatting is correctly a file-level concern: a file is
# either canonically formatted or not).
if ! SKIP=ruff,eslint-staged poetry run pre-commit run --from-ref "$TARGET_BRANCH" --to-ref HEAD; then
    PRECOMMIT_OK=false
fi

if ! poetry run python scripts/ruff_diff_check.py "$TARGET_BRANCH"; then
    RUFF_OK=false
fi

# Frontend ESLint diff-aware gate (mirror of ruff_diff_check.py).
# Only relevant if the PR touches frontend files; the script reports
# "No changed frontend files" and exits 0 in the no-op case.
if [ -d "frontend" ]; then
    if ! poetry run python scripts/eslint_diff_check.py "$TARGET_BRANCH"; then
        ESLINT_OK=false
    fi
fi

if $PRECOMMIT_OK && $RUFF_OK && $ESLINT_OK; then
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
    echo -e "${YELLOW}   Update EXPECTED_PYRIGHT_ERRORS in this script to $ACTUAL_PYRIGHT_ERRORS${RESET}"
    echo -e "${YELLOW}   and include the baseline update in your PR. Failing here so the${RESET}"
    echo -e "${YELLOW}   improvement is locked in (a future regression can't silently restore it).${RESET}"
    rm -f "$PYRIGHT_OUTPUT_FILE"
    exit 1
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
            cd ..
            rm -f /tmp/ts-output.log
            exit 1
        elif [ "$ACTUAL_TS_ERRORS" -lt "$EXPECTED_FRONTEND_TS_ERRORS" ]; then
            echo -e "${GREEN}🎉 EXCELLENT: TypeScript errors reduced from $EXPECTED_FRONTEND_TS_ERRORS to $ACTUAL_TS_ERRORS!${RESET}"
            echo -e "${GREEN}   Please update EXPECTED_FRONTEND_TS_ERRORS in this script to $ACTUAL_TS_ERRORS${RESET}"
            echo -e "${GREEN}   Include this baseline update in your PR${RESET}"
            cd ..
            rm -f /tmp/ts-output.log
            exit 1  # Force the author to ratchet the baseline down so the win is locked in.
        else
            # Failure exit code from npm run typecheck but error count == baseline.
            # When baseline is 0 this branch is unreachable. When baseline > 0
            # this means the same number of pre-existing errors are still there
            # (no regression, no improvement) — still treated as success since
            # the diff didn't make things worse.
            echo -e "${YELLOW}⚠️  TypeScript compilation failed but error count ($ACTUAL_TS_ERRORS) within baseline of $EXPECTED_FRONTEND_TS_ERRORS— ratchet down when fixed.${RESET}"
        fi
    fi

    cd ..
    rm -f /tmp/ts-output.log
fi

# ===== STAGE 5: Whole-Project Frontend ESLint with Baseline =====
# Stage 1's eslint_diff_check.py catches NEW issues on changed lines.
# Stage 5 is the project-wide ratchet: it tracks total error count and
# fails if the count goes UP (regression) OR DOWN without a baseline
# update in the same PR (locking in any improvement).
#
# This mirrors Stage 3 (pyright). When the baseline reaches 0 the
# diff-check in Stage 1 becomes redundant for blocking purposes, but
# we keep both because the diff-check gives MUCH better error messages
# (only the new ones, not the full 602-error wall of text).
if [ -d "frontend" ]; then
    echo -e "\n${BLUE}🎨 Stage 5: Full-project ESLint with baseline...${RESET}"

    cd frontend

    ESLINT_OUTPUT_FILE=$(mktemp)
    npx eslint --format=json --no-error-on-unmatched-pattern -- \
        "src/**/*.{ts,tsx,js,jsx}" > "$ESLINT_OUTPUT_FILE" 2>/dev/null || true

    # Sum severity-2 (error) messages across all files. The python
    # one-liner mirrors what scripts/eslint_diff_check.py uses, keeping
    # the count semantics identical between the two stages.
    ACTUAL_ESLINT_ERRORS=$(python3 -c "
import json, sys
with open('$ESLINT_OUTPUT_FILE') as f:
    data = json.load(f)
print(sum(1 for r in data for m in r.get('messages', []) if m.get('severity') == 2))
")

    rm -f "$ESLINT_OUTPUT_FILE"
    cd ..

    if [ "$ACTUAL_ESLINT_ERRORS" -gt "$EXPECTED_FRONTEND_ESLINT_ERRORS" ]; then
        echo -e "${RED}❌ FAILURE: ESLint found $ACTUAL_ESLINT_ERRORS errors, exceeding baseline of $EXPECTED_FRONTEND_ESLINT_ERRORS${RESET}"
        echo -e "${RED}   Stage 1's eslint_diff_check.py should have caught the specific new error(s).${RESET}"
        echo -e "${RED}   Re-run with the failure context above to find which line is the regression.${RESET}"
        exit 1
    elif [ "$ACTUAL_ESLINT_ERRORS" -lt "$EXPECTED_FRONTEND_ESLINT_ERRORS" ]; then
        echo -e "${GREEN}🎉 EXCELLENT: ESLint errors reduced from $EXPECTED_FRONTEND_ESLINT_ERRORS to $ACTUAL_ESLINT_ERRORS!${RESET}"
        echo -e "${YELLOW}   Update EXPECTED_FRONTEND_ESLINT_ERRORS in this script to $ACTUAL_ESLINT_ERRORS${RESET}"
        echo -e "${YELLOW}   and include the baseline update in your PR. Failing here so the${RESET}"
        echo -e "${YELLOW}   improvement is locked in (a future regression can't silently restore it).${RESET}"
        exit 1
    else
        echo -e "${GREEN}✅ SUCCESS: ESLint error count stable at baseline of $EXPECTED_FRONTEND_ESLINT_ERRORS${RESET}"
    fi
fi

# ===== SUCCESS =====
echo -e "\n${BLUE}============================================================${RESET}"
echo -e "${GREEN}✅ ALL QUALITY GATES PASSED!${RESET}"
echo -e "${GREEN}🚀 Code is ready for merge${RESET}"
echo -e "${GREEN}🛡️  CoachIQ quality standards maintained${RESET}"
echo -e "${BLUE}============================================================${RESET}\n"

exit 0
