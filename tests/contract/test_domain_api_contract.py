"""
Tests for Domain API v2 contract (OpenAPI schema conformance).

This module is intentionally a skip stub.

The previous test body validated that ``/api/v2/...`` endpoints conformed
to the OpenAPI v3 contract documented at the time of the v2 migration
(see deleted ``OPENAPI_V3_SPECIFICATION.md`` reference in the original
docstring). The fixtures relied on ``backend.services.feature_manager``
to gate v2-route registration; that module no longer exists, so every
test fails at collection time with ``ModuleNotFoundError``.

Migration status as of 2026-05-12:

- v2 routes are alive and unconditionally registered (no feature flag).
- Legacy ``/api/...`` routes coexist as first-class siblings.
- The OpenAPI schema is generated dynamically by FastAPI; the
  hand-written spec doc the contract test asserted against is no longer
  the source of truth.

If you want OpenAPI contract testing back, the right approach is to:

1. Export the live OpenAPI schema (``poetry run python scripts/export_openapi.py``).
2. Diff it against a checked-in golden file in CI.
3. Make the golden file the source of truth, not a separate
   ``OPENAPI_V3_SPECIFICATION.md`` document.

Until that exists, this stub is the honest signal.

Tracked in issue #105 (test-restoration sweep #2). Tied off via PR #120.
"""

import pytest

pytest.skip(
    "Domain API v2 contract validation is obsolete: it depends on the "
    "removed backend.services.feature_manager module to toggle v2 routes "
    "(now unconditionally registered) and asserts against a hand-written "
    "OpenAPI doc that's no longer the source of truth. See PR #120.",
    allow_module_level=True,
)
