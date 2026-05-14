---
mode: "agent"
description: "A4 \u2014 Pydantic-Settings test fixture helper to eliminate the three known traps"
---

# A4 \u2014 Pydantic-Settings test fixture helper

Audit cycle: 2026-05-13 architectural audit.

## Why

`backend/core/config.py` defines a 1933-LOC `Settings` model with 19
nested `BaseSettings` sections. The 2026-05-12 audit cycle (PRs #119,
#121, #122) canonized three recurring traps that bit every test author:

1. `MagicMock(spec=BaseSettings)` doesn't materialize Pydantic descriptors
   on the class, so attribute access returns `MagicMock` instead of the
   typed default.
2. `BaseSettings` with `env_file=".env"` auto-loads the developer's
   local `.env` during tests, leaking real config into the test process.
3. `COACHIQ_*` env-var pollution leaks across tests because Pydantic
   only reads env on instantiation and the test process inherits them.

Each new contributor steps on at least one of these. The fix is a
single fixture in `tests/conftest.py`.

## The job

Add `make_test_settings(**overrides) -> Settings` to `tests/conftest.py`
(or `tests/_helpers/settings.py` if a helpers package exists) that:

1. Strips every `COACHIQ_*` env var from `os.environ` for the duration
   of the call (use `pytest.MonkeyPatch.context` if a fixture, or
   manual `os.environ.pop` + `try/finally` if a plain helper).
2. Calls `Settings(_env_file=None, **overrides)` so `.env` does not
   auto-load.
3. Returns the typed `Settings` instance \u2014 not a Mock.

Then provide a `pytest.fixture` wrapper:

```python
@pytest.fixture
def test_settings(monkeypatch):
    """Hermetic Settings instance \u2014 no env-var or .env leakage.

    See `/memories/repo/audit-2026-05-12.md` ("Pydantic-Settings test
    fixture lesson") for the three traps this helper avoids.
    """
    for key in list(os.environ):
        if key.startswith("COACHIQ_"):
            monkeypatch.delenv(key, raising=False)
    return Settings(_env_file=None)
```

Document both APIs in a docstring with the three-trap explanation.

## Migration scope

**Don't migrate every existing test in this PR.** Land the helper +
a few cherry-picked migrations of the most-affected tests:

- `tests/unit/test_configuration_service.py`
- `tests/core/test_config.py`
- one test that previously hit trap #1 (MagicMock-spec).

Leave a TODO header comment in `tests/conftest.py` advising future
test authors to use the helper. New tests must use it; existing tests
migrate opportunistically as they're touched.

## Verification

```bash
# Run the migrated tests
poetry run pytest tests/unit/test_configuration_service.py tests/core/test_config.py -q

# Full suite to confirm no regression
poetry run pytest --no-cov -q --tb=no --continue-on-collection-errors 2>&1 | tail -3
```

## Acceptance criteria

- `make_test_settings` and the `test_settings` fixture exist with
  full docstring referencing the three traps.
- 2\u20133 example migrations land alongside.
- Existing test count is unchanged or up.
- A short note added to `/memories/repo/audit-2026-05-12.md` (or
  `audit-2026-05-13.md`) under "Pydantic-Settings lesson" pointing
  to the new helper.

## Stop-and-ask if

- The repo already has a `tests/_helpers/` or `tests/fixtures/`
  package with a similar helper that just needs hardening. Don't
  duplicate.
- One of the cherry-picked migrations exposes a NEW production bug
  (e.g. `Settings()` actually depends on a leaked env var that wasn't
  documented). That's a discovery; capture in a follow-up issue.

## Risk

Low. Test infra only.
