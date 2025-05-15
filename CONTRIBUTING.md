# Contributing to RVC2API

Thank you for your interest in contributing to RVC2API! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please keep interactions respectful and professional. By contributing, you agree to respect fellow contributors and maintain a positive community environment.

## Getting Started

1. **Set up your development environment**:
   ```bash
   # Clone the repository
   git clone https://github.com/carpenike/rvc2api.git
   cd rvc2api

   # Option 1: Using Poetry directly
   poetry install
   poetry shell

   # Option 2: Using Nix (recommended for reproducible builds)
   nix develop
   ```

2. **Familiarize yourself with the codebase**:
   - Review the README.md for a project overview
   - Understand the core components as described in README.md
   - Look at existing code to understand style and patterns

## How to Contribute

### Reporting Bugs

1. **Check existing issues** to avoid duplicates
2. **Use the bug report template** in the GitHub repository
3. **Provide detailed information** about your environment and how to reproduce the bug
4. **Include logs** if possible

### Suggesting Enhancements

1. **Use the feature request template**
2. **Describe your use case** clearly
3. **Consider implementation details** if possible

### Contributing Code

1. **Create an issue first** for major changes to discuss the approach
2. **Fork the repository** and create a branch from `main`
3. **Write clean code** following the project's style (see Coding Standards below)
4. **Add or update tests** for your changes
5. **Ensure all tests pass** by running `poetry run pytest`
6. **Update documentation** if necessary
7. **Submit a pull request** to the `main` branch

## Development Process

### Branching Strategy

- `main`: Main development branch, should always be in a deployable state
- Feature branches: Create branches from `main` for your work, using a descriptive name (e.g., `feat/add-temperature-support`)

### Pull Request Process

1. **Create a focused PR** addressing a single issue or feature
2. **Follow the PR template**
3. **Request reviews** from appropriate code owners
4. **Address feedback** promptly
5. **Ensure CI passes** before merging

## Coding Standards

### Code Style

- Follow the style guide in COPILOT-INSTRUCTIONS.md
- Use Black for formatting: `poetry run black src tests`
- Check linting with Flake8: `poetry run flake8`

### Testing

- Write tests for all new features and bug fixes
- Maintain or improve code coverage
- Test both success and failure cases

### Documentation

- Add docstrings for all functions, classes, and modules
- Keep comments current and relevant
- Update README.md if adding new features or changing functionality

## Licensing

By contributing to RVC2API, you agree that your contributions will be licensed under the same license as the project (see LICENSE file).

## Questions?

If you have questions about contributing, open an issue with the question label or discuss in the GitHub discussions section.
