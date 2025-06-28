# MkDocs Configuration Update (May 18, 2025)

This document summarizes the changes made to the MkDocs configuration structure to improve documentation building and organization, including the addition of Mermaid diagram support and documentation reorganization.

## Changes Implemented

1. **Moved `mkdocs.yml` from `/docs` directory to project root**:

   - This is a standard best practice for MkDocs projects
   - It resolves issues with the docs directory being both the configuration location and source directory

2. **Updated path configurations in mkdocs.yml**:

   - Changed `docs_dir` from `.` to `docs` (pointing to the docs directory from project root)
   - Changed `site_dir` from `../site` to `site` (site output in project root)

3. **Added missing dependency**:

   - Added `mkdocs-autorefs = "^0.5.0"` to `pyproject.toml`
   - This dependency was needed for proper reference linking in documentation

4. **Updated VS Code tasks to reference the new mkdocs.yml location**:

   - Updated "Server: Serve Documentation" task
   - Updated "Build: Documentation" task
   - Updated "API: Update Documentation" task
   - All tasks now run from project root directory

5. **Fixed YAML lint errors**:

   - Updated the `!!python/name:` tag format in the superfences configuration
   - Changed from `format: !!python/name:pymdownx.superfences.fence_code_format` to `format: "pymdownx.superfences.fence_code_format"`
   - This preserves functionality while resolving VS Code YAML lint warnings

6. **Added Mermaid Diagram Support**:

   - Added `mkdocs-mermaid2-plugin` to the project dependencies
   - Configured the mermaid plugin in the plugins section of mkdocs.yml
   - Created comprehensive diagram guidelines in the documentation instructions
   - Added sample diagrams to demonstrate proper usage in test-mermaid.md

7. **Reorganized Documentation Structure**:
   - Clearly separated documentation into User Guide and Developer Guide sections
   - Created a documentation-organization.md file explaining the structure
   - Updated navigation in mkdocs.yml to reflect the new organization
   - Added cross-linking between related documentation pages

## Key Added Diagrams

Several important diagrams have been added throughout the documentation:

1. **System Architecture**: Comprehensive component diagram in `architecture/overview.md`
2. **Backend Architecture**: Component flow chart in `architecture/backend.md`
3. **WebSocket Communication**: Sequence diagram in `api/websocket.md`
4. **Frontend API Integration**: Sequence diagram in `api/frontend-integration.md`
5. **Environment Variables**: Configuration flow diagram in `environment-variable-integration.md`
6. **Frontend Architecture**: Component diagram in `architecture/frontend.md`
7. **Pull Request Workflow**: Process diagram in `contributing/pull-requests.md`

## Diagram Styling Standards

To ensure consistency across all diagrams, a standard color scheme was established:

| Component Type   | Fill Color | Stroke Color |
| ---------------- | ---------- | ------------ |
| Frontend/UI      | #bbdefb    | #1976d2      |
| API/Backend      | #c8e6c9    | #388e3c      |
| Business Logic   | #fff9c4    | #fbc02d      |
| Infrastructure   | #e1f5fe    | #0288d1      |
| Hardware/Devices | #ffccbc    | #e64a19      |
| User/External    | #f5f5f5    | #bdbdbd      |

## Benefits

1. **Standard MkDocs Structure**: Following MkDocs best practices for configuration location
2. **Simplified Commands**: Documentation commands can now run from project root
3. **Fixed Build Issues**: Resolved issues with docs_dir configuration
4. **Improved Dependency Management**: All documentation dependencies now properly specified in pyproject.toml
5. **Enhanced Visual Communication**: Complex architecture and processes illustrated with diagrams
6. **Clearer Organization**: Distinct separation between user and developer documentation
7. **Consistent Visual Language**: Standardized diagram styling across all documentation

## How to Use

### Serving Documentation Locally

Use the VS Code task "Server: Serve Documentation" or run:

```bash
cd /Users/ryan/src/rvc2api
poetry run mkdocs serve
```

Then visit http://localhost:8000 in your browser.

### Building Documentation

Use the VS Code task "Build: Documentation" or run:

```bash
cd /Users/ryan/src/rvc2api
poetry run mkdocs build
```

Output will be in the `/Users/ryan/src/rvc2api/site` directory.

### Updating API Documentation

Use the VS Code task "API: Update Documentation" or run:

```bash
cd /Users/ryan/src/rvc2api
poetry run python scripts/export_openapi.py
poetry run mkdocs build
```

This will export the OpenAPI schema and rebuild the documentation.
