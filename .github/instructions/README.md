# GitHub Copilot Instructions

This directory contains modular GitHub Copilot instructions for the `CoachIQ` project. Each file includes YAML frontmatter with an `applyTo` pattern indicating which files the instructions apply to.

## Available Instructions

### Core Architecture

| File                                                                 | Applies To     | Description                                       |
| -------------------------------------------------------------------- | -------------- | ------------------------------------------------- |
| [project-overview.instructions.md](project-overview.instructions.md) | All files      | Project architecture and structure (backend + frontend)                |
| [react-frontend.instructions.md](react-frontend.instructions.md)     | React UI files | React, TypeScript, and Vite frontend architecture |
| [documentation.instructions.md](documentation.instructions.md)       | Markdown files | API documentation and MkDocs configuration        |

### Code Style and Quality

| File                                                                                 | Applies To   | Description                                    |
| ------------------------------------------------------------------------------------ | ------------ | ---------------------------------------------- |
| [python-code-style.instructions.md](python-code-style.instructions.md)               | Python files | Python coding standards and style guide        |
| [typescript-code-style.instructions.md](typescript-code-style.instructions.md)       | TS/JS files  | TypeScript/React coding standards and patterns |
| [eslint-typescript-config.instructions.md](eslint-typescript-config.instructions.md) | TS/JS files  | ESLint setup and TypeScript config details     |
| [code-style.instructions.md](code-style.instructions.md)                             | Python files | General coding standards (legacy)              |

### Development Workflow

| File                                                               | Applies To | Description                        |
| ------------------------------------------------------------------ | ---------- | ---------------------------------- |
| [dev-environment.instructions.md](dev-environment.instructions.md) | All files  | Setting up and using dev tools     |
| [vscode-tasks.instructions.md](vscode-tasks.instructions.md)       | All files  | VS Code task definitions and usage |
| [testing.instructions.md](testing.instructions.md)                 | Test files | Test patterns and requirements     |
| [pull-requests.instructions.md](pull-requests.instructions.md)     | All files  | PR guidelines and expectations     |

### Tools and Configuration

| File                                                   | Applies To   | Description                                |
| ------------------------------------------------------ | ------------ | ------------------------------------------ |
| [mcp-tools.instructions.md](mcp-tools.instructions.md) | All files    | Using Copilot Chat tools (@context7, etc.) |
| [env-vars.instructions.md](env-vars.instructions.md)   | Python files | Configuration and environment setup        |

### Legacy Documentation

| File                                           | Applies To    | Description                           |
| ---------------------------------------------- | ------------- | ------------------------------------- |
| [webui.instructions.md](webui.instructions.md) | Legacy Web UI | Legacy HTML template and JS standards |

## Using These Instructions

These files are designed to work with GitHub Copilot in VS Code. When editing a file, GitHub Copilot will automatically apply the relevant instructions based on the file type.

You can also use the prompt templates in the [../prompts](../prompts) directory for more specific guidance on common development tasks.

## API Documentation Integration

The project uses a comprehensive API documentation system:

- **FastAPI Documentation**: All endpoints are documented with metadata, examples, and response schemas
- **OpenAPI Schema**: Automatically exported to JSON/YAML for use in documentation and TypeScript type generation
- **MkDocs**: Material theme-based documentation site with API reference, architecture docs, and usage guides
- **TypeScript Types**: Generated from OpenAPI schema for type-safe frontend API integration

Dedicated VS Code tasks make it easy to update and maintain documentation:

- `API: Export OpenAPI Schema`: Updates the OpenAPI schema JSON/YAML files
- `API: Update Documentation`: Exports the schema and rebuilds the documentation site

See [documentation.instructions.md](documentation.instructions.md) for detailed guidelines on documenting API endpoints.

## MCP Tools Integration

The project uses Model Context Protocol (MCP) tools for AI-assisted development:

- **@context7**: Always use first for library/framework questions - provides accurate, up-to-date API information
- **@perplexity**: For general research on technical topics not found in the codebase
- **@github**: For repository exploration and finding related issues/PRs

See [mcp-tools.instructions.md](mcp-tools.instructions.md) for detailed usage examples.

## VS Code Tasks Integration

Extensive VS Code tasks are available to streamline development. These tasks cover:

- Starting servers (backend, frontend, documentation)
- Code quality checks (linting, formatting, type checking)
- Testing (with and without coverage reports)
- Building (frontend, documentation)
- Development environment management
- API documentation (OpenAPI schema export, documentation generation)

See [vscode-tasks.instructions.md](vscode-tasks.instructions.md) for the complete list of available tasks and how to use them.
