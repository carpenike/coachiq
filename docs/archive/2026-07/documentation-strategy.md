# CoachIQ Documentation Strategy - Personal RV Project

*A simple documentation approach for a Raspberry Pi-based RV control system*

> **Last Updated**: January 2025
> **Version**: 4.0 - Personal project for <5 users
> **Context**: Hobby RV project running on Raspberry Pi 4

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#current-state-analysis)
3. [Documentation Architecture](#documentation-architecture)
4. [Implementation Plan](#implementation-plan)
5. [Tooling & Automation](#tooling--automation)
6. [Maintenance Workflow](#maintenance-workflow)
7. [Safety-Critical Requirements](#safety-critical-requirements)
8. [Quick Wins](#quick-wins)
9. [Success Metrics](#success-metrics)

## Executive Summary

This is a personal RV control project that runs on a Raspberry Pi 4 in my motorhome. Documentation needs to be simple, practical, and focused on:
- How to use the system
- How to troubleshoot common issues
- Basic safety information for RV systems
- Simple API reference for future tinkering

### Key Principles
- **Keep it simple** - README files and basic MkDocs site
- **Document what matters** - Focus on actual usage, not compliance
- **Version control** - Git is sufficient for everything
- **Practical safety** - Document what could actually cause problems
- **Maintenance-free** - Set up once, update rarely

## Current State Analysis

### What We Have
- Lots of outdated documentation files from various experiments
- Good technical documentation in `.claude/instructions/`
- Working API that exports OpenAPI specs
- Existing MkDocs setup

### What We Actually Need
- Simple "how to use this" guide
- Basic troubleshooting steps
- API reference (auto-generated from OpenAPI)
- Safety notes (don't electrocute yourself, don't crash the RV)

### Documentation Cleanup List

#### Files to Remove (Outdated)
```
docs/verifying-versioned-documentation.md
docs/docs-versioning-fixes.md
docs/test-mermaid.md
docs/install-vcan-test-task.md
docs/react-migration-summary.md
docs/shadcn-ui-migration-summary.md
docs/theme-improvements-summary.md
docs/frontend-theming-assessment.md
docs/documentation-updates-summary.md
docs/mkdocs-versioning-integration.md
docs/mkdocs-versioning.md
docs/versioning-with-release-please.md
docs/mkdocs-config-update.md
docs/documentation-versioning-update.md
docs/theme-system-verification-report.md
docs/vcan-setup-changes.md
docs/eslint-typescript-config.md
docs/test-framework-modernization.md
```

#### Files to Archive
```
docs/specs/refactor-web-ui-to-react.md
docs/specs/config-mgmt-consolidation.md
docs/specs/shadcn-ui-v4-layout-migration.md
docs/specs/refactor-backend-structure.md
docs/migration/app-state-to-repository.md
docs/github-pages-deployment.md
docs/poetry2nix-integration.md
docs/nix-minimal-config-example.md
docs/environment-variable-integration.md
docs/pdf-processing-guide.md
docs/enabling-github-pages.md
docs/version-management.md
```

## Documentation Architecture

### Simple Directory Structure

```
docs/
├── README.md                      # Quick start guide
├── setup.md                       # Raspberry Pi setup instructions
├── usage.md                       # How to use the system
├── troubleshooting.md            # Common problems and solutions
├── safety.md                     # Important safety information
├── api/
│   └── reference.md              # Auto-generated API docs
└── archive/                      # Old stuff I might need later
```

That's it. No complex hierarchies, no compliance folders, no process documents.

## Implementation Plan

### Weekend Project Setup

#### Step 1: Clean Up Old Docs (30 minutes)
```bash
# Archive all the old stuff
mkdir -p docs/archive/2025-01
mv docs/*.md docs/archive/2025-01/

# Keep only what matters
git mv docs/archive/2025-01/README.md docs/
```

#### Step 2: Write Basic Docs (2 hours)
```bash
# Create the essential files
cat > docs/README.md << 'EOF'
# CoachIQ - RV Control System

Control your RV systems from a web interface running on Raspberry Pi.

## Quick Start
1. Connect Raspberry Pi to RV CAN bus
2. Access web UI at http://raspberrypi.local:8080
3. Control lights, HVAC, tanks, etc.

See setup.md for installation instructions.
EOF

cat > docs/safety.md << 'EOF'
# Safety Information

## Electrical Safety
- This connects to your RV's 12V system
- Turn off battery disconnect before wiring
- Use proper gauge wire for CAN connections

## System Safety
- Test controls work before relying on them
- Keep manual overrides accessible
- System is for convenience, not safety-critical operations
EOF
```

#### Step 3: Set Up Simple MkDocs (1 hour)
```yaml
# Simplified mkdocs.yml
site_name: CoachIQ - Personal RV Control
site_description: Raspberry Pi based RV control system

nav:
  - Home: README.md
  - Setup: setup.md
  - Usage: usage.md
  - Troubleshooting: troubleshooting.md
  - Safety: safety.md
  - API: api/reference.md

theme:
  name: material
  features:
    - navigation.instant
    - content.code.copy

plugins:
  - search
  - mkdocs-swagger-ui-tag:
      spec_path: /api/openapi.json
```

#### Step 4: Auto-generate API Docs (30 minutes)
```python
# Simple script to generate API reference
cat > scripts/generate_simple_api_docs.py << 'EOF'
#!/usr/bin/env python3
"""Generate simple API documentation."""
import json
import subprocess
from pathlib import Path

# Use existing OpenAPI export
subprocess.run(["poetry", "run", "python", "scripts/export_openapi.py"])

# Read the spec
with open("docs/api/openapi.json") as f:
    spec = json.load(f)

# Generate simple markdown
content = ["# API Reference

"]
content.append("Base URL: `http://raspberrypi.local:8080`

")

for path, methods in spec.get("paths", {}).items():
    for method, details in methods.items():
        content.append(f"## {method.upper()} {path}
")
        content.append(f"{details.get('summary', '')}

")

Path("docs/api/reference.md").write_text("".join(content))
print("✓ API docs generated")
EOF
```

## Tooling & Automation

### Simple Tools for Personal Project

| Tool | Purpose |
|------|---------|
| **Git** | Version control |
| **MkDocs** | Simple static site |
| **Python** | API doc generation |

That's it. No Vale, no pre-commit hooks, no CI/CD complexity.

### Required Dependencies

Just add MkDocs to your project:

```toml
[tool.poetry.group.docs]
optional = true

[tool.poetry.group.docs.dependencies]
mkdocs = "^1.5.3"
mkdocs-material = "^9.5.0"
mkdocs-swagger-ui-tag = "^0.6.8"
```

## Maintenance Workflow

### Personal Project Reality

1. **Update docs when something breaks** - Add to troubleshooting.md
2. **Update setup when Pi config changes** - Keep setup.md current
3. **Regenerate API docs after changes** - Run the script
4. **That's it** - This is a hobby project, not a job

## What About Safety?

### Common Sense Safety for RV Projects

1. **Electrical Safety**
   - Document which wires connect where
   - Note the fuse ratings you're using
   - Remind yourself to disconnect battery before wiring

2. **System Behavior**
   - Document what happens if the Pi crashes (hint: manual controls still work)
   - Note which systems you're controlling (lights = safe, brakes = don't)
   - Keep a list of "things that surprised me" for future reference

3. **Testing Notes**
   - "I tested this with..." notes are helpful
   - "Don't do X because Y happened" is very helpful
   - Pictures of your wiring are extremely helpful

## Quick Weekend Implementation

### Simple Setup Script

```bash
#!/bin/bash
# setup-docs.sh - Set up documentation

# 1. Create simple structure
mkdir -p docs/api
mkdir -p docs/archive

# 2. Create basic docs
cat > docs/README.md << 'EOF'
# CoachIQ - RV Control System

Control your RV systems from a Raspberry Pi.

## Quick Start
1. Wire up your Pi to the RV CAN bus
2. Install the software (see setup.md)
3. Access at http://raspberrypi.local:8080
EOF

cat > docs/setup.md << 'EOF'
# Setup Instructions

## Hardware
- Raspberry Pi 4
- CAN HAT (I use PiCAN2)
- 12V to 5V converter
- Some wire

## Software
1. Flash Raspberry Pi OS
2. Enable CAN: `sudo nano /boot/config.txt`
3. Clone this repo
4. Run `make install`
EOF

cat > docs/troubleshooting.md << 'EOF'
# Troubleshooting

## CAN bus not working
- Check termination resistors (120Ω)
- Verify wiring (CAN-H to CAN-H, CAN-L to CAN-L)
- Try `candump can0` to see raw messages

## Web UI not loading
- Check if backend is running: `systemctl status coachiq`
- Check logs: `journalctl -u coachiq -f`
EOF

# 3. Generate API docs
poetry run python scripts/generate_simple_api_docs.py

echo "✓ Documentation setup complete!"
echo "Run 'mkdocs serve' to preview"
```

### Simple Makefile Targets

```makefile
# Add to existing Makefile
docs-setup:
	@bash scripts/setup-docs.sh

docs-serve:
	@poetry run mkdocs serve

docs-api:
	@poetry run python scripts/generate_simple_api_docs.py
```

## Summary

This personal project documentation approach is designed for reality:

1. **Keep it simple** - Basic markdown files for everything
2. **Document what matters** - Setup, usage, troubleshooting, safety
3. **Automate the boring stuff** - API docs generated from code
4. **No compliance theater** - This is for my RV, not for certification
5. **Maintain when needed** - Update docs when things change or break

## Next Steps

1. **Today (30 minutes)**:
   ```bash
   # Run the setup script
   bash scripts/setup-docs.sh
   ```

2. **This Weekend**:
   - Write actual content in the doc files
   - Take photos of the wiring setup
   - Test the MkDocs site locally

3. **Ongoing**:
   - Update troubleshooting.md when you figure out new issues
   - Keep setup.md current with what actually works
   - That's it - this is a hobby, not a second job

Remember: The best documentation is the documentation that actually exists. Keep it simple, keep it current, and focus on what helps you (and maybe a friend) use the system safely.
