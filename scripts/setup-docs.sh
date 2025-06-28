#!/bin/bash
# setup-docs.sh - Set up simplified documentation structure

set -e

echo "Setting up CoachIQ documentation..."

# 1. Create directory structure
echo "Creating directory structure..."
mkdir -p docs/api
mkdir -p docs/archive

# 2. Archive old docs if they haven't been moved yet
if [ -f "docs/test-mermaid.md" ] || [ -f "docs/mkdocs-versioning.md" ]; then
    echo "Archiving old documentation..."
    mkdir -p docs/archive/2025-01

    # Move files marked for removal
    for file in \
        "verifying-versioned-documentation.md" \
        "docs-versioning-fixes.md" \
        "test-mermaid.md" \
        "install-vcan-test-task.md" \
        "react-migration-summary.md" \
        "shadcn-ui-migration-summary.md" \
        "theme-improvements-summary.md" \
        "frontend-theming-assessment.md" \
        "documentation-updates-summary.md" \
        "mkdocs-versioning-integration.md" \
        "mkdocs-versioning.md" \
        "versioning-with-release-please.md" \
        "mkdocs-config-update.md" \
        "documentation-versioning-update.md" \
        "theme-system-verification-report.md" \
        "vcan-setup-changes.md" \
        "eslint-typescript-config.md" \
        "test-framework-modernization.md"
    do
        [ -f "docs/$file" ] && mv "docs/$file" "docs/archive/2025-01/" 2>/dev/null || true
    done
fi

# 3. Check if core docs exist, create if not
if [ ! -f "docs/README.md" ]; then
    echo "Creating README.md..."
    cat > docs/README.md << 'EOF'
# CoachIQ - RV Control System

Control your RV systems from a web interface running on Raspberry Pi.

## Quick Start

1. Connect Raspberry Pi to RV CAN bus
2. Access web UI at http://raspberrypi.local:8080
3. Control lights, HVAC, tanks, etc.

See [setup.md](setup.md) for installation instructions.
EOF
fi

# 4. Generate API documentation
echo "Generating API documentation..."
if [ -f "scripts/generate_simple_api_docs.py" ]; then
    poetry run python scripts/generate_simple_api_docs.py
else
    echo "Note: scripts/generate_simple_api_docs.py not found, skipping API doc generation"
fi

# 5. Create a simple index if it doesn't exist
if [ ! -f "docs/index.md" ]; then
    echo "Creating index.md..."
    cp docs/README.md docs/index.md
fi

echo "✓ Documentation setup complete!"
echo ""
echo "Next steps:"
echo "1. Run 'poetry run mkdocs serve' to preview the documentation"
echo "2. Run 'poetry run python scripts/generate_simple_api_docs.py' to update API docs"
echo "3. Edit the markdown files in docs/ to customize content"
