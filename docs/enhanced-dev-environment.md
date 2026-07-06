# Enhanced Development Environment for CoachIQ

This update introduces several improvements to the development environment for the CoachIQ project:

## 1. VS Code Tasks Integration

A comprehensive set of VS Code tasks has been added to streamline development workflows:

- **Backend Development**

  - Start Backend Server
  - Run Tests
  - Format Code (Ruff)
  - Lint (Ruff)

- **Frontend Development**

  - Start Frontend Dev Server
  - Build Frontend

- **Integrated Development**

  - Start Full Development Environment (backend + frontend)

- **Nix Integration**

  - Enter Nix Development Shell

- **MCP Tools**
  - Restart MCP - context7 Server
  - MCP Tools Status

## 2. poetry2nix Integration (Proposed)

A poetry2nix integration has been proposed to improve the connection between Poetry and Nix:

- Single source of truth for dependencies in `pyproject.toml`
- Improved reproducibility between development and production
- Better handling of Python package dependencies

See the following resources for implementation details:

- Comprehensive guide: `docs/poetry2nix-integration.md`
- Example implementation: `flake.nix.poetry2nix`

## 3. MCP Tools Documentation

Documentation on how to use MCP tools (Model Context Protocol) for AI-assisted development:

- Setup instructions for @context7, @perplexity, and @github tools
- Usage examples for each tool
- Troubleshooting common issues

See `docs/mcp-tools-setup.md` for details.

## 4. VS Code Extensions Integration

A comprehensive set of VS Code extensions has been recommended for the project:

- **Python Development**: Python, Pylance, Black, Ruff, FastAPI snippets, etc.
- **Nix Development**: Nix IDE, environment selector, direnv integration
- **Frontend Development**: ESLint, Prettier, Tailwind CSS, React snippets, etc.
- **General Tools**: GitHub Copilot, YAML, JSON5, etc.

See `docs/vscode-extensions.md` for a detailed list and descriptions.

## Getting Started

1. **Install Recommended VS Code Extensions**

   - Press `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux)
   - Choose "Extensions: Show Recommended Extensions"
   - Install the recommended extensions
   - See `docs/vscode-extensions.md` for details on each extension

2. **Use VS Code Tasks**

   - Press `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux)
   - Choose "Tasks: Run Task"
   - Select a task from the list (e.g., "Start Full Development Environment")

3. **Explore poetry2nix Integration**

   - Review `docs/poetry2nix-integration.md` for implementation guidance
   - Compare your current `flake.nix` with `flake.nix.poetry2nix`

4. **Set Up MCP Tools**
   - Follow the instructions in `docs/mcp-tools-setup.md`
   - Try using the MCP-related tasks to start and check server status

## Next Steps

1. Test the tasks.json configuration and adjust as needed
2. Consider implementing the poetry2nix integration
3. Keep MCP servers updated for the best AI assistance experience

## Detailed Documentation

For GitHub Copilot and development guidance, see the `.github/instructions/` directory:

- **Code Style and Architecture**

  - [Project Overview (Backend Architecture)](../.github/instructions/project-overview.instructions.md)
  - [React Frontend Architecture](../.github/instructions/react-frontend.instructions.md)
  - [Python Code Style Guidelines](../.github/instructions/python-code-style.instructions.md)
  - [TypeScript Code Style Guidelines](../.github/instructions/typescript-code-style.instructions.md)

- **Development Workflow**

  - [VS Code Tasks Documentation](../.github/instructions/vscode-tasks.instructions.md)
  - [Development Environment](../.github/instructions/dev-environment.instructions.md)
  - [Pull Request Expectations](../.github/instructions/pull-requests.instructions.md)

- **Tools and Configuration**
  - [MCP Tools Guide](../.github/instructions/mcp-tools.instructions.md)
  - [ESLint/TypeScript Config](../.github/instructions/eslint-typescript-config.instructions.md)
  - [Environment Variables](../.github/instructions/env-vars.instructions.md)

## Known Issues

- The poetry2nix integration is provided as a proof-of-concept and will need testing
- MCP server management may require additional customization based on your specific setup
- Task configurations may need adjustments depending on your specific environment
