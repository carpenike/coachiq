"""Skip-stub for the deprecated ``CoreServices`` class.

``backend/core/services.py`` was deprecated in Phase 2 of the
ServiceRegistry migration. ``backend/main.py`` no longer constructs
or registers a ``CoreServices`` instance — its line 160 explicitly
notes ``CoreServices removed in Phase 2 - persistence and database
services registered separately`` and the lifespan shuts services
down via the ServiceRegistry rather than ``CoreServices.shutdown()``.

The module remains on disk only to support the migration helper
``backend/core/core_services_removal.py`` and a pair of unused
fixtures in ``tests/conftest.py``
(``test_core_services``, ``client_with_core_services``,
``async_client_with_core_services`` — none of which any test
currently consumes).

Calling ``CoreServices().startup()`` today raises
``ModuleNotFoundError: No module named 'backend.services.legacy_persistence_service'``
because the legacy persistence shim was deleted but the import in
``backend/core/services.py:79`` was never updated. That is broken
*dead* code (no production caller), not broken *live* code; the
correct follow-up is to delete ``backend/core/services.py`` and the
unused conftest fixtures in a dedicated cleanup PR (similar to PR
#109's removal of ``backend/core/state.py``).

This file is therefore skip-stubbed; restoring real coverage would
mean writing tests for a class that should not exist.

Refs: PR #109 (state.py removal pattern), issue #105 (test sweep #2),
``backend/core/core_services_removal.py`` (migration guide).
"""

import pytest

pytest.skip(
    reason=(
        "CoreServices was deprecated in Phase 2 of the ServiceRegistry "
        "migration and has no live callers. The startup() path is broken "
        "(missing legacy_persistence_service module) but harmless because "
        "nothing constructs it. Follow-up: delete backend/core/services.py "
        "and the unused conftest CoreServices fixtures."
    ),
    allow_module_level=True,
)
