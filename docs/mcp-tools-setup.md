# MCP Tools Setup and Management for CoachIQ

This guide explains how to set up and manage [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools for the CoachIQ project. These tools provide context-aware AI assistance through GitHub Copilot Chat.

## Available MCP Tools

The project utilizes three primary MCP tools:

1. **@context7**: Provides project-aware code lookups
2. **@perplexity**: Offers external research capabilities
3. **@github**: Enables repository and issue information queries

## Setting Up MCP Tools

### Prerequisites

- VS Code with GitHub Copilot and GitHub Copilot Chat extensions
- Required MCP server extensions installed

### Installation

Install the necessary VS Code extensions:

- GitHub Copilot
- GitHub Copilot Chat
- Relevant MCP extensions:
  - Context7 Extension (for @context7)
  - GitHub Extension (for @github)
  - Perplexity Extension (for @perplexity)

## Using VS Code Tasks for MCP Tools

The project includes VS Code tasks for managing MCP tools:

### Starting/Restarting MCP Servers

1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS)
2. Select "Tasks: Run Task"
3. Choose "Restart MCP - context7 Server"

### Checking MCP Tool Status

1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS)
2. Select "Tasks: Run Task"
3. Choose "MCP Tools Status"

## Using MCP Tools in Development

### @context7 Examples

```
# Find implementations of WebSocket handling
@context7 WebSocket connection handling

# Learn about CANbus integration
@context7 python-can integration

# Understand API routes
@context7 FastAPI route implementation
```

### @perplexity Examples

```
# Research external technologies
@perplexity RV-C protocol specification

# Find best practices
@perplexity FastAPI dependency injection patterns

# Explore alternative libraries
@perplexity python-can vs socketcan-python
```

### @github Examples

```
# Search for issues
@github issues:coachiq+websocket+reconnection

# Find pull requests
@github pr:coachiq+react+frontend

# Get repository statistics
@github repo:coachiq stats
```

## Best Practices

### When to Prioritize Context7

Always use Context7 for these scenarios:

#### Working with External Libraries

```
@context7 how to use FastAPI dependency injection
@context7 React useState with TypeScript generics
@context7 tailwind responsive design patterns
```

#### Version-Specific Features

```
@context7 Next.js 14 App Router middleware
@context7 React 18 concurrent mode features
@context7 Python 3.12 typing features
```

#### Library API Questions

```
@context7 FastAPI WebSocket authentication
@context7 React useCallback correct dependencies
@context7 tailwind dark mode configuration
```

> **Important**: For any library or framework questions, always use `@context7` first before falling back to LLM-generated answers. This ensures you get current, correct API information rather than outdated or hallucinated answers.

## Troubleshooting

### Common Issues

1. **MCP Server Not Responding**

   - Use the "MCP: Restart Context7 Server" task
   - Check if the server process is running with "Status: Check MCP Tools"
   - Restart VS Code

2. **Limited or Outdated Context**

   - The context server might need to re-index your codebase
   - Try running the indexing command manually or restart the server

3. **External Research Failing**
   - Check your internet connection
   - Verify API keys or authentication if applicable

## Related Documentation

For more information about MCP tools and their integration with specific project areas, see:

- [Project Overview](../.github/instructions/project-overview.instructions.md) - Backend architecture and patterns
- [React Frontend Architecture](../.github/instructions/react-frontend.instructions.md) - Frontend-specific MCP usage
- [MCP Tools Guide](../.github/instructions/mcp-tools.instructions.md) - Complete MCP tools reference
- [VS Code Tasks](../.github/instructions/vscode-tasks.instructions.md) - Tasks for managing MCP tools

## Advanced Configuration

For advanced configuration of MCP tools, refer to the specific documentation for each tool:

- [Context7 Documentation](https://context7.ai/)
- [GitHub Copilot Documentation](https://docs.github.com/en/copilot)
- [Perplexity Documentation](https://www.perplexity.ai/)
