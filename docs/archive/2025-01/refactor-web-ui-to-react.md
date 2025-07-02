# Refactor Web UI to Standalone React App

## 1. Refactoring Objective

### 1.1. Purpose
- Decouple the web UI from the FastAPI backend, enabling independent development and deployment.
- Modernize the frontend using React (with Vite for tooling), improving maintainability, scalability, and developer experience.
- Prepare for future enhancements (e.g., richer UI, real-time features, easier testing).

### 1.2. Scope
- Affected: `src/core_daemon/frontend/` (all templates, static assets, and related backend integration), API endpoints serving UI assets.
- Unchanged: Backend API logic, WebSocket endpoints, business logic, and backend models/services.
- Boundaries: Only the UI layer and its integration with the backend; no changes to core API or backend state management.

## 2. Current State Analysis

### 2.1. Code Structure
- Check in with context7 before starting to refactor to ensure we use the latest recommended practices for use with the languages being proposed.
- UI is implemented as Jinja2 templates in `src/core_daemon/frontend/templates/` and static files in `src/core_daemon/frontend/static/`.
- Served directly by FastAPI backend.
- Tightly coupled: UI changes require backend restarts; limited frontend tooling.
- Pain points: Difficult to modernize, limited interactivity, slow iteration, hard to test UI in isolation.

### 2.2. Code Quality Concerns
- Technical debt: Outdated template-based UI, minimal JS/CSS modularity.
- Patterns: No componentization, limited state management, no frontend build pipeline.
- Inconsistencies: UI/UX drift, hard to maintain styles/scripts.

### 2.3. Test Coverage
- Minimal automated UI testing; backend tests focus on API.
- No frontend unit/integration tests.
- Refactoring will require new test strategy for React components.

## 3. Refactoring Plan

### 3.1. Architectural Changes
- Scaffold a new React app (using Vite) in a new `frontend/` directory at the project root.
- UI will communicate with backend via REST/WebSocket APIs (no backend modernization or FastAPI changes in this phase).
- Decouple static asset serving from FastAPI completely - FastAPI will provide API services only.
- The React frontend will be served directly by Caddy (which already reverse-proxies the FastAPI service).
- Design goal: Create a beautiful, modern UI using curved lines, contemporary themes, and visually appealing layouts. Leverage modern CSS frameworks (e.g., Tailwind CSS, Material UI) to ensure a polished, user-friendly experience.
- Ignore authentication and backend modernization for this phase; these will be handled separately.

### 3.2. Code Structure Changes
- Create `frontend/` at project root: contains all React source, assets, and build config.
- Remove or archive `src/core_daemon/frontend/`.
- Update backend to serve built frontend (optional: only in production; no backend code changes in this phase).
- Update all relevant `.nix` files in the project root (e.g., `flake.nix`, `devshell.nix`) to include Node.js, frontend build tools, and React app development dependencies for a unified dev environment.
- Update `pyproject.toml` as appropriate to reflect any changes in backend/frontend integration or developer workflow (but do not change backend logic).
- Use modern naming conventions (PascalCase for components, camelCase for variables).

### 3.3. Interface Changes
- Public API endpoints remain unchanged.
- UI endpoints (HTML pages) will be replaced by static file serving.
- Backward compatibility: maintain API contract; document UI migration.
- Deprecate old template routes with clear warnings (no backend code changes in this phase).

### 3.4. Testing Strategy
- Add unit and integration tests for React components (Jest, React Testing Library).
- Manual and automated E2E tests for critical UI flows.
- Backend tests and authentication will be addressed in a separate phase.

## 4. Implementation Strategy

### 4.1. Phased Approach
- Phase 1: Scaffold React app, set up Vite, basic routing, and API integration.
- Phase 2: Migrate core UI features (dashboard, device views, etc.).
- Phase 3: Remove/disable old templates; update backend static serving.
- Phase 4: Add tests, update docs, finalize migration.

### 4.2. Risk Mitigation
- Risks: API drift, deployment misconfiguration, user confusion.
- Mitigation: Maintain API contract, dual-serve old/new UI during transition, clear migration docs.
- Fallback: Re-enable old templates if needed.

### 4.3. Validation Checkpoints
- Each phase: run backend and frontend tests, verify UI functionality, check API compatibility.
- Metrics: UI feature parity, test pass rate, user feedback.

## 5. Code Migration Guide

### 5.1. Old vs. New Patterns
- BEFORE: Jinja2 templates, static JS/CSS, backend-coupled rendering.
- AFTER: React components, modular JS/CSS, API-driven UI, independent dev server.

### 5.2. Deprecation Path
- Mark old template routes as deprecated in backend.
- Timeline: Remove after 1-2 releases.
- Provide migration guide in docs.

## 6. Documentation Updates

### 6.1. Code Documentation
- Update backend docstrings for UI endpoints.
- Add README to `frontend/` with setup/dev instructions.
- Update architecture docs to reflect new UI structure.

### 6.2. User Documentation
- Update user-facing docs to reference new UI.
- Communicate API stability and UI migration path.
- Provide troubleshooting and migration guides.

## 7. Execution Checklist

### 7.1. Preparation
- [x] Analyze current code structure
- [x] Create test cases for critical functionality
- [x] Document current behavior
- [x] Create backup branch

### 7.2. Implementation
- [ ] Create new React app structure
- [ ] Implement core UI features
- [ ] Update backend static serving
- [ ] Update tests
- [ ] Update documentation
- [ ] Create deprecation notices

### 7.3. Validation
- [ ] Run all tests
- [ ] Verify UI feature parity
- [ ] Validate API compatibility
- [ ] Review code quality

### 7.4. Deployment
- [ ] Create release plan
- [ ] Update changelog
- [ ] Communicate changes to users
- [ ] Monitor for issues

## 8. References

### 8.1. Design Patterns
- React component architecture
- API-driven UI
- Vite for fast frontend tooling
- See: https://vitejs.dev/guide/

### 8.2. Best Practices
- Python/JS code separation
- REST/WebSocket API contracts
- Modern frontend testing (Jest, React Testing Library)
- See: https://react.dev/learn, https://testing-library.com/docs/react-testing-library/intro/
