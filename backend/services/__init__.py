"""
Services package for CoachIQ.

This package contains business logic services that implement core functionality
and features of the application.

NOTE: This package intentionally does NOT eagerly re-export individual
service classes. Doing so used to trigger `backend.services.entity_service`
(and through it `backend.websocket.handlers` and
`backend.websocket.routes`) to load whenever ANY service was imported,
which produced a hard-to-diagnose circular import when
`backend.core.dependencies` started importing service classes directly
for the typed-DI pattern in ADR-0006 (audit cycle 2026-05-13 PRs
A7.0--A7.3).

Use the fully-qualified module path instead:
    from backend.services.entity_service import EntityService
    from backend.services.rvc_config_facade import RVCConfigFacade
"""
