# GitHub Actions Workflows

This directory contains GitHub Actions workflows for building, testing, and
versioning the CoachIQ project.

## Workflows

### `nix-ci.yml`

Main CI: runs `nix run .#ci` (pre-commit, tests, lints, lock-check) and
`nix flake check` on every push to `main` and PR targeting `main`.

The Cachix step (`cachix-action`) is configured with `continue-on-error: true`
so a missing/revoked auth token will not fail the run — Nix will just rebuild
from source. To restore caching, generate a new token at
<https://app.cachix.org/cache/coachiq> and set it as the `CACHIX_AUTH_TOKEN`
repository secret.

### `test-docs.yml`

Builds the MkDocs documentation on PRs that touch `docs/` or `mkdocs.yml`.
Verifies that the docs still build (and that `scripts/export_openapi.py`
still runs) before merging. Does NOT deploy.

### `release-please.yml`

Runs on push to `main`. Uses [release-please](https://github.com/googleapis/release-please)
to track Conventional Commits and open/update a release PR that bumps
`VERSION`, updates `CHANGELOG.md`, and updates `tool.poetry.version` in
`pyproject.toml` (configured via `release-please-config.json`).
</content>
</invoke>