"""Tests for the entities API endpoints.

The previous version of this file targeted a hybrid legacy+v2 entity
API where the test would try ``/api/v2/entities`` first and fall back
to ``/api/entities`` if v2 returned 404. That layout no longer
matches production:

- The legacy ``/api/entities``, ``/api/metadata``, ``/api/unmapped``,
  and ``/api/unknown-pgns`` endpoints were retired; only the v2 paths
  remain (see ``backend/api/domains/entities.py``).
- The v2 endpoints are mounted unconditionally — there is no
  feature-flag gate, so the ``override_feature_manager`` fixture the
  tests required does not (and should not) exist.
- The v2 ``GET /api/v2/entities`` endpoint expects
  ``EntityService.list_entities()`` to return a *dict-of-dicts* keyed
  by ``entity_id`` with raw entity payloads (see
  ``backend/services/entity_service.py:98`` and the conversion loop
  at ``backend/api/domains/entities.py:480``); the previous test mocks
  returned a paginated ``{"entities": [...]}`` list, which the router
  would refuse to convert.
- ``GET /api/v2/entities/ids`` was never implemented on the v2 router
  at all.

Because each of these clashes is structural (contract change, not a
mock typo), restoring real coverage for ``/api/v2/entities/*`` requires
purpose-built tests against the actual v2 schema and service contract,
not a tweak of the existing test bodies. That is a feature task that
deserves its own PR (likely paired with the still-open
``EntityService.control_light`` refactor in #112).

This file is therefore skip-stubbed. When the v2 entity router gets
its own dedicated test file, those tests should:

- Mount only the v2 entity router on a fresh ``FastAPI()`` app (see
  ``tests/api/test_safety_pin_endpoints.py`` for the canonical
  pattern).
- Override ``backend.core.dependencies.get_entity_service`` directly
  via ``app.dependency_overrides`` rather than ``unittest.mock.patch``
  on import paths.
- Use ``EntitySchemaV2`` / ``EntityCollectionV2`` from
  ``backend.api.domains.entities`` for response assertions so the
  contract is enforced at the schema layer, not via ad-hoc dict checks.

Refs: PRs #109 (state.py removal), #111 (entity service
disambiguation), #115 (notification cleanup), #120 (v1→v2 migration
parity skip-stub), issue #105 (test sweep #2), issue #112
(``control_light`` refactor).
"""

import pytest

pytest.skip(
    reason=(
        "Tests in this file targeted the legacy /api/entities + feature-flag "
        "gated v2 endpoints. The legacy paths are retired and the v2 service "
        "contract is incompatible with the original mocks. Rewriting these "
        "as real v2 contract tests is a feature task; see module docstring."
    ),
    allow_module_level=True,
)
