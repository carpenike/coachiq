# Development Environment Setup for CoachIQ

This document outlines multiple approaches for setting up development environments for the CoachIQ project.

## Option 1: Using Nix Development Shell (Recommended)

The project includes a Nix flake that provides a fully configured development environment with all dependencies.

### Prerequisites

- [Nix package manager](https://nixos.org/download.html) with flakes enabled

### Setup

1. Enter the development shell:

   ```bash
   nix develop
   ```

2. This provides:

   - Python 3.12 with all project dependencies
   - Node.js for the frontend
   - Poetry for Python package management
   - All necessary development tools (ruff, pyright, pytest, can-utils on Linux)

3. Start developing:
   - Backend: `poetry run python run_server.py` (or `./dev_start.sh`, which exports development defaults such as a virtual CAN bus before starting the server)
   - Frontend: `cd frontend && npm run dev`

There is also a CI-oriented shell with virtual CAN (vcan) setup: `nix develop .#ci`.

### Benefits

- Reproducible environment across all developers
- Exact versions of all dependencies are locked
- Works on any system where Nix is installed
- No global pollution of your system

## Option 2: Using Poetry Directly

If you don't want to use Nix, you can use Poetry directly to manage the Python environment.

### Prerequisites

- [Python](https://www.python.org/downloads/) 3.12 or later
- [Poetry](https://python-poetry.org/docs/#installation)
- [Node.js](https://nodejs.org/) (for frontend development)

### Setup

1. Install Python dependencies:

   ```bash
   poetry install
   ```

2. Install frontend dependencies:

   ```bash
   cd frontend && npm install
   ```

3. Start the backend server:

   ```bash
   poetry run python run_server.py
   ```

4. Start the frontend development server:

   ```bash
   cd frontend && npm run dev
   ```

## VS Code Integration

The repository includes VS Code configuration files to make development easier:

- Tasks for common operations
- Launch configurations for debugging
- Recommended extensions

To use these features:

1. Open the project in VS Code
2. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS) and search for "Tasks: Run Task"
3. Choose from available tasks like:
   - Start Backend Server
   - Start Frontend Dev Server
   - Run Tests
   - Format Code (Ruff)
   - Lint (Ruff)

## Environment Variables

All configuration uses `COACHIQ_`-prefixed environment variables (nested settings use
a double underscore, e.g. `COACHIQ_SERVER__HOST`). The `dev_start.sh` script exports a
working set of development defaults; the variables you are most likely to set by hand
are listed below. See [Configuration Management](configuration.md) for the full
structure.

### Basic Configuration

- `COACHIQ_ENVIRONMENT`: Application environment (default: `development`)
- `COACHIQ_LOGGING__LEVEL`: Logging level (default: `INFO`)
- `COACHIQ_SERVER__HOST` / `COACHIQ_SERVER__PORT`: Bind address (default: `127.0.0.1:8000`)
- `COACHIQ_SERVER__RELOAD`: Enable auto-reload during development
- `COACHIQ_SERVER__ROOT_PATH`: Root path for API URLs (default: `""`)

### CAN Bus Configuration

- `COACHIQ_CAN__INTERFACES`: Comma-separated list of CAN interfaces (default: `can0`; `dev_start.sh` uses `virtual0`)
- `COACHIQ_CAN__BUSTYPE`: python-can bus type (default: `socketcan`; use `virtual` for hardware-free development)
- `COACHIQ_CAN__BITRATE`: CAN bus bitrate (default: `500000`)
- `COACHIQ_CAN__INTERFACE_MAPPINGS`: Logical-to-physical mapping, e.g. `'{"house": "can0", "chassis": "can1"}'`

### File Paths

- `COACHIQ_RVC__SPEC_PATH`: Override path to the RV-C specification file (`rvc.json`)
- `COACHIQ_RVC__COACH_MAPPING_PATH`: Override path to the coach mapping file
- `COACHIQ_RVC__COACH_MODEL`: Select a bundled coach mapping by model (e.g. `2021_Entegra_Aspire_44R`)
- `COACHIQ_PERSISTENCE__DATA_DIR`: Persistent data directory (`dev_start.sh` uses `backend/data`)

### Integrations

- `COACHIQ_NOTIFICATIONS__ENABLED`: Enable the notification system (default: `false`)
- `COACHIQ_NOTIFICATIONS__PUSHOVER__ENABLED`: Enable Pushover notifications
- `COACHIQ_NOTIFICATIONS__PUSHOVER__USER_KEY` / `COACHIQ_NOTIFICATIONS__PUSHOVER__TOKEN`: Pushover credentials
- `COACHIQ_NOTIFICATIONS__PUSHOVER__DEVICE`: Pushover device name (optional)
- `COACHIQ_FEATURES__ENABLE_UPTIMEROBOT`: Enable UptimeRobot integration

## Model Context Protocol Tools

For enhanced code exploration and understanding, the project is configured to work with Model Context Protocol (MCP) tools:

- See [MCP Tools Setup](mcp-tools-setup.md) for more information.
