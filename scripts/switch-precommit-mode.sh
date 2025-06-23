#!/bin/bash
# Switch between strict and pragmatic pre-commit configurations

set -euo pipefail

# ANSI color codes
GREEN="\033[92m"
YELLOW="\033[93m"
BLUE="\033[94m"
RESET="\033[0m"

show_usage() {
    echo "Usage: $0 [pragmatic|strict|status]"
    echo ""
    echo "Modes:"
    echo "  pragmatic - Use pragmatic config (blocks only new issues in changed files)"
    echo "  strict    - Use strict config (includes heavy pre-push hooks)"
    echo "  status    - Show current configuration mode"
    echo ""
    echo "Examples:"
    echo "  $0 pragmatic   # Switch to pragmatic mode for daily development"
    echo "  $0 strict      # Switch to strict mode before major releases"
    echo "  $0 status      # Check which mode is active"
}

get_current_mode() {
    if [ -L ".pre-commit-config.yaml" ]; then
        link_target=$(readlink ".pre-commit-config.yaml")
        if [[ "$link_target" == *"pragmatic"* ]]; then
            echo "pragmatic"
        else
            echo "strict"
        fi
    elif [ -f ".pre-commit-config.yaml" ]; then
        # Check if pyright is in manual stage
        if grep -q "stages: \[manual\]" .pre-commit-config.yaml 2>/dev/null; then
            echo "pragmatic"
        else
            echo "strict"
        fi
    else
        echo "unknown"
    fi
}

switch_to_pragmatic() {
    echo -e "${BLUE}Switching to pragmatic pre-commit mode...${RESET}"

    # Backup current config if it's not already a backup
    if [ -f ".pre-commit-config.yaml" ] && [ ! -f ".pre-commit-config.strict.yaml" ]; then
        cp .pre-commit-config.yaml .pre-commit-config.strict.yaml
        echo -e "${GREEN}✓ Backed up current config to .pre-commit-config.strict.yaml${RESET}"
    fi

    # Use pragmatic config
    cp .pre-commit-config.pragmatic.yaml .pre-commit-config.yaml
    echo -e "${GREEN}✓ Switched to pragmatic mode${RESET}"
    echo -e "${YELLOW}ℹ️  Pre-commit will now:${RESET}"
    echo "  - Run fast checks on changed files only"
    echo "  - Skip heavy type checking (run manually with: pre-commit run pyright --all-files)"
    echo "  - Allow commits with existing technical debt"
}

switch_to_strict() {
    echo -e "${BLUE}Switching to strict pre-commit mode...${RESET}"

    # Restore strict config
    if [ -f ".pre-commit-config.strict.yaml" ]; then
        cp .pre-commit-config.strict.yaml .pre-commit-config.yaml
        echo -e "${GREEN}✓ Switched to strict mode${RESET}"
    else
        echo -e "${YELLOW}⚠️  No strict config backup found${RESET}"
        echo "The current config will be used as-is"
    fi

    echo -e "${YELLOW}ℹ️  Pre-commit will now:${RESET}"
    echo "  - Run all checks including heavy type checking on push"
    echo "  - Enforce stricter quality standards"
    echo "  - May block commits if existing issues are present"
}

show_status() {
    current_mode=$(get_current_mode)
    echo -e "${BLUE}Current pre-commit mode: ${GREEN}$current_mode${RESET}"

    if [ "$current_mode" == "pragmatic" ]; then
        echo -e "${YELLOW}ℹ️  Using pragmatic configuration:${RESET}"
        echo "  - Fast checks on changed files only"
        echo "  - Type checking is manual-only"
        echo "  - Optimized for development velocity"
    elif [ "$current_mode" == "strict" ]; then
        echo -e "${YELLOW}ℹ️  Using strict configuration:${RESET}"
        echo "  - Full checks including pre-push hooks"
        echo "  - Type checking runs on push"
        echo "  - Enforces highest quality standards"
    fi
}

# Main script logic
case "${1:-status}" in
    pragmatic)
        switch_to_pragmatic
        ;;
    strict)
        switch_to_strict
        ;;
    status)
        show_status
        ;;
    -h|--help|help)
        show_usage
        exit 0
        ;;
    *)
        echo -e "${YELLOW}Invalid mode: $1${RESET}"
        show_usage
        exit 1
        ;;
esac
