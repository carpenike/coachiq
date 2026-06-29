# CoachIQ

Intelligent RV-C network management system with advanced analytics and control.
This project provides a backend daemon, a web UI for monitoring and control,
and a console client for direct interaction.

## Overview

`CoachIQ` is designed to intelligently bridge RV-C networks with modern applications by providing a structured API and real-time data streaming. It decodes RV-C messages, manages device states, and allows for sending commands to the RV-C bus.

## System role and architecture (important)

CoachIQ is **not** a direct hardware controller. In a typical RV install
(this project's reference build is a 2021 Entegra Aspire 44R with a
**Firefly MIRA** multiplex panel) the architecture looks like:

```
  CoachIQ                          Firefly MIRA panel              Hardware
  (this project)                   (the OEM controller)            (lights,
        │                                  │                       slides,
        │  RV-C / J1939 over CAN bus       │  proprietary backplane locks,
        │  (acts like a smart sensor /     │  + RV-C output bus     fans,
        ├───remote panel emitting frames)──►Firefly────────────────────►…)
        │                                  │
        │  reads bus traffic               │  enforces real safety
        │  for state / telemetry           │  interlocks (slides,
        │                                  │  brake, leveling, etc.)
        ▼                                  ▼
   FastAPI + WebSocket UI            (owns the safety case)
```

What this means in practice:

- **Firefly owns physical safety.** It will refuse, ignore, or fail-safe any
  command it considers unsafe. CoachIQ cannot bypass it.
- **CoachIQ is a polite citizen on the CAN bus.** It emits well-formed
  RV-C/J1939 frames the same way a wall switch or HMI panel would. Firefly
  decides whether to act on them.
- **The realistic threat model is API-side, not hardware-side.** The risks
  CoachIQ must guard against are: bus flooding, malformed frames, unauth'd
  API access, and credential compromise — not "the brakes get released".
- **CoachIQ is convenience automation, not certified safety equipment.**
  See [docs/safety.md](docs/safety.md) for the full operational-safety policy.
  Quality-engineering choices (test coverage, type checking, linting)
  should be calibrated to "good consumer-grade backend" — not aerospace.

## Key Components

- **Backend (`backend/`):** FastAPI application with a service-oriented architecture.
  - `backend/main.py`: FastAPI application entry point and service registration.
  - `backend/core/`: Core application infrastructure (config, dependencies, ServiceRegistry, exceptions).
  - `backend/services/`: Business logic services (entity, auth, persistence, etc.) accessed via dependency injection.
  - `backend/repositories/`: Repository pattern for data access; replaces the previous monolithic `AppState`.
  - `backend/api/routers/`: REST API endpoints organized by domain.
  - `backend/api/domains/`: Domain API v1 endpoints (`/api/v1/...`) with bulk operations and caching.
  - `backend/websocket/`: WebSocket handlers for real-time entity, log, and CAN sniffer streams.
  - `backend/integrations/`: Protocol integrations
    - `backend/integrations/can/`: CAN bus interface management.
    - `backend/integrations/rvc/`: RV-C message decoding (PGN/SPN), Firefly extensions.
    - `backend/integrations/j1939/`: J1939 protocol decoding and Spartan K2 chassis extensions.
  - `backend/middleware/`: HTTP middleware (auth, CSRF, structured logging).
  - `backend/alembic/`: Database migrations (SQLAlchemy 2.0 async).
  - `backend/models/`, `backend/schemas/`: Pydantic models and schemas.
- **Configuration (`config/`):**
  - `config/rvc.json`: RV-C specification (PGNs, SPNs, signal definitions).
  - `config/coach_mapping.default.yml`: Default coach-to-entity mapping.
  - `config/2021_Entegra_Aspire_44R.yml`: Example coach-specific mapping.
  - `config/Caddyfile.example`: Production Caddy reverse-proxy template.
- **Frontend (`frontend/`):**
  - React 19 SPA built with Vite, TypeScript (strict), Tailwind CSS, and shadcn/ui.
  - Communicates with the backend via REST (`/api/...` and `/api/v1/...`) and WebSockets.
  - State managed with React Query and React Context.
- **Deployment:**
  - Nix flake provides dev shells, CLI apps (`nix run .#test|lint|format|ci`), and a NixOS module for production.
  - Production architecture: Caddy (edge: TLS, IP rate-limiting, CORS) → FastAPI (app: auth, business logic).

## Documentation

- **Deployment & Integration**

  - [NixOS Integration Guide](docs/nixos-integration.md)
  - [NixOS Module Configuration Reference](docs/nixos-module.md)
  - [React Frontend Deployment](docs/react-deployment.md)

- **Development**

  - [Development Environments Setup](docs/development-environments.md)
  - [VS Code Extensions](docs/vscode-extensions.md)
  - [Model Context Protocol Tools Setup](docs/mcp-tools-setup.md)

- **Quality Tools**
  - [Code Quality Tools](docs/code-quality-tools.md)
  - [Pre-commit and GitHub Actions](docs/pre-commit-and-actions.md)

## Features

- **FastAPI Backend:** Robust and modern API framework.
- **WebSocket Streaming:** Real-time updates of RV-C data and entity states to connected clients.
- **RV-C Message Decoding:** Translates raw CAN bus messages into human-readable RV-C data.
- **Entity Management:** Represents RV-C devices and their states as controllable entities.
- **Web-based UI:** Provides a user-friendly interface for monitoring and interaction.
- **Documentation Search:** AI-powered semantic search of RV-C specification using FAISS and OpenAI embeddings.
- **Configuration Driven:** Uses YAML and JSON files for RV-C specifications and device mappings.
- **Poetry for Dependency Management:** Ensures reproducible builds and development environments.

## Prerequisites

- Python 3.12+
- Poetry (for dependency management and running scripts)
- Node.js 20+ (for the frontend)
- A configured CAN bus interface (e.g., `socketcan` on Linux). For development on macOS, use the Nix devShell which provides a vCAN setup helper.
- Optional: [Nix](https://nixos.org/download.html) with flakes enabled, for a fully reproducible dev environment.

## Installation & Setup

### Option 1: Using NixOS

If you're using NixOS, you can easily integrate `CoachIQ` using the provided NixOS module:

- [NixOS Integration Guide](docs/nixos-integration.md)
- [NixOS Module Configuration Reference](docs/nixos-module.md)

### Option 2: Manual Setup

For detailed instructions on setting up development environments, see:

- [Development Environments Guide](docs/development-environments.md)

For quick start:

1. **Clone the repository:**

   ```bash
   git clone https://github.com/carpenike/coachiq
   cd coachiq
   ```

2. **Install dependencies:**

   ```bash
   # Backend
   poetry install

   # Frontend
   cd frontend && npm install
   ```

3. **Running the application:**

   - **Backend (FastAPI):**

     ```bash
     poetry run python run_server.py --reload --debug
     ```

     The API server starts on `http://localhost:8000` by default. Swagger UI at `/docs`.

   - **Frontend Development Server:**

     ```bash
     cd frontend && npm run dev
     ```

     The frontend dev server is accessible at `http://localhost:5173/` and proxies `/api` and `/ws` to the backend.

## RV-C Documentation Search

The project includes a feature for semantically searching the RV-C specification using AI-powered embeddings:

- **Setup the Documentation Search:**

  ```bash
  # Place the RV-C spec PDF in resources directory
  cp /path/to/your/rv-c-spec.pdf resources/rv-c-spec.pdf

  # Set your OpenAI API key
  export OPENAI_API_KEY="your-api-key-here"

  # Run the setup helper script
  poetry run python scripts/setup_faiss.py --setup
  ```

- **Using the Search Feature:**

  - **Via Web UI:** Navigate to the "Documentation" page in the web interface
  - **Via API:** `GET /api/docs/search?query=your+search+query`
  - **Via Command Line:** `poetry run python dev_tools/query_faiss.py "your search query"`

For detailed instructions, see [RV-C Documentation Search Guide](docs/rv-c-documentation-search.md)

## Processing PDFs and Adding Embeddings

To process a PDF and add its chunks to the FAISS vector store for semantic search, use the following command:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf /path/to/your.pdf \
  --chunking section_overlap \
  --add-to-index resources/vector_store/
```

- Replace `/path/to/your.pdf` with your PDF file.
- Choose the appropriate `--chunking` strategy (e.g., `section_overlap`, `paragraph`, `token`, `sliding_window`).
- The `--add-to-index <path>` argument is required to generate embeddings and store them in the FAISS index. The path should point to your shared FAISS index directory (e.g., `resources/vector_store/`).
- The FAISS index should be shared across all documents for unified search; do not create a separate index per PDF.
- Always use `poetry run python ...` to ensure the correct environment is used.

**Notes:**

- Embeddings are only created and added to the index when `--add-to-index <path>` is specified. Chunking alone does not generate embeddings.
- The argument is `--chunking`, not `--chunking-method`.
- The argument is `--add-to-index <path>`, not just a flag or `true/false`.

For more details, see [docs/pdf-processing-guide.md](docs/pdf-processing-guide.md).

## Development

- **Activate the virtual environment:**

  ```bash
  poetry shell
  ```

- **Running tests:**

  ```bash
  poetry run pytest                       # backend
  cd frontend && npm test                 # frontend
  ```

- **Linting / Formatting / Type Checking:** (See [Code Quality Tools](docs/code-quality-tools.md) for details)

  ```bash
  poetry run ruff format backend          # format
  poetry run ruff check .                 # lint
  poetry run pyright backend              # type-check
  cd frontend && npm run lint && npm run typecheck && npm run build
  ```

- **Reproducible CI environment via Nix (optional):**

  ```bash
  nix run .#test          # tests
  nix run .#lint          # lint
  nix run .#format        # format
  nix run .#ci            # full CI suite
  ```

## API Endpoints

Refer to the FastAPI Swagger UI at `http://localhost:8000/docs` (or ReDoc at `/redoc`) for the full, authoritative API specification.

Key endpoint groups:

- `/api/entities/` and `/api/v1/entities/`: List and control RV-C entities (lights, locks, climate, etc.). All device-type operations are unified under entity endpoints (no `/api/lights`, `/api/locks`, etc.). Use `/api/v1/...` (Domain API v1) for new development — it supports bulk operations, partial-success responses, and richer schemas.
- `/api/can/`: CAN interface status and message tools.
- `/api/auth/`: Authentication, tokens, and PIN/MFA management.
- `/api/health`, `/health`: Liveness and readiness probes.
- `/ws/...`: WebSocket endpoints for real-time entity updates, log streaming, and CAN sniffer feeds.

## Development Tools & Resources

We have enhanced the development environment with several tools to streamline the workflow:

- **VS Code Integration**: Preconfigured settings, tasks, and recommended extensions

  - See [VS Code Extensions](docs/vscode-extensions.md) for recommended extensions
  - See [Enhanced Development Environment](docs/enhanced-dev-environment.md) for comprehensive task documentation
  - Use VS Code tasks for efficient operation of backend, frontend, testing, and code quality tools

- **MCP Tools**: AI-assisted development with Model Context Protocol

  - See [MCP Tools Setup](docs/mcp-tools-setup.md) for information on using @context7, @perplexity, and @github tools
  - Always use @context7 first for accurate, up-to-date library API information
  - Use @perplexity for general research and @github for repository exploration

- **Development Environment**: Comprehensive development setup
  - Structured documentation for both [backend](docs/code-quality-tools.md) and [frontend](docs/frontend-development.md) development
  - Clear code style guidelines for Python and TypeScript
- **Pre-commit and CI/CD**: Quality assurance and automation
  - See [Pre-commit and GitHub Actions](docs/pre-commit-and-actions.md) for configuration details
  - See [Code Quality Tools](docs/code-quality-tools.md) for information about our Python linting and formatting tools
- **Custom Type Stubs**: Enhanced type checking and IDE support
  - Located in `typings/` directory
  - Includes custom type definitions for FastAPI WebSocket components
  - See `typings/fastapi/README.md` for details on organization and usage
- **NixOS Integration**: Using CoachIQ in other NixOS systems
  - See [NixOS Integration](docs/nixos-integration.md) for how to include CoachIQ in other flakes and NixOS configurations

## Contributing

Contributions are welcome! Please follow standard coding practices, ensure tests pass, and consider updating documentation for any new features or changes. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the terms of the [LICENSE](./LICENSE) file.
