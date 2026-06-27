# CoachIQ — Project Context

Curated, non-derivable orientation for agents working on CoachIQ. This is the
"what the system is and why" companion to the cross-agent comms doctrine (the
`handoff/README` note in the `coachiq` basic-memory project, which covers _how
agents coordinate_). Read both at the start of a session that touches this repo.

This file is hand-curated. It deliberately captures the things you cannot
recover by reading the code in a hurry: the load-bearing decisions, the
"don't revert this" constraints, and the gotchas that have already cost
someone an afternoon. When a decision here graduates into a formal ADR or a
plan doc, trim it to a pointer.

---

## 1. System overview

CoachIQ is an RV-C / J1939 CANbus network-management system for recreational
vehicles. It runs on a small Linux box (a Raspberry Pi in the reference
install) inside the coach, decodes the RV-C messages on the bus into
addressable **entities** (lights, locks, tanks, climate, etc.), exposes their
state and control over a **FastAPI** REST + WebSocket API, and serves a
**React** SPA for monitoring and control. The repo is historically named
`rvc2api`; the product is CoachIQ.

**The single most important framing — read ADR-0004.** CoachIQ is **not** a
vehicle safety system. In the reference install (a 2021 Entegra Aspire 44R) it
talks to a **Firefly MIRA** multiplex panel over RV-C / J1939. **Firefly owns
the physical-safety case** and decides which commands to act on. CoachIQ's role
is that of a wall-switch panel or HMI: it emits well-formed CAN frames; Firefly
chooses whether to act on them. Consequences for how you write code and specs:

- Do **not** frame requirements as DO-178C / aerospace / life-critical. This is
  convenience automation. The realistic threat model is **API-side**: bus
  flooding, malformed frames, unauthenticated API access, credential
  compromise — _not_ "the brakes release."
- The in-process "safety" code (`backend/services/safety_service.py`,
  `backend/core/safety_*.py`) is **defense-in-depth API guardrail**, not the
  actual safety system. It exists to keep CoachIQ from being a bad CAN-bus
  citizen, not to enforce vehicle-level safety.
- Quality bar is "good consumer-grade backend": ~70–80% coverage on the
  guardrail paths, strict types, proper auth/CSRF, no bus flooding. Don't
  propose mutation testing, 100% MC/DC coverage, or formal methods.

**Deployment shape:** Python 3.12 backend run under Poetry; React SPA built
with Vite and served by **Caddy**, which also terminates TLS and does
IP-based rate-limiting and proxies `/api` + `/ws` to FastAPI. Reproducible
builds and an optional NixOS module are provided via the Nix flake.

---

## 2. Repository map

One repo, two halves. A single feature commonly spans both.

### `backend/` — FastAPI application

- **Entrypoints:** `run_server.py` (dev/prod launcher, e.g.
  `poetry run python run_server.py --reload --debug`) → `backend/main.py`
  (service startup, router wiring, lifespan).
- **`backend/core/`** — application infrastructure: `config.py` (the canonical
  Pydantic `Settings`), `service_registry.py` (the `ServiceRegistry` +
  startup-stage orchestration), `dependencies.py` (the public DI entry points),
  `entity_manager.py`, the `safety_*` modules (`safety_registry.py`,
  `safety_state_engine.py`, `safety_interfaces.py`), structured logging,
  exception handlers, input validation, and the `registrations/` startup
  modules.
- **`backend/services/`** — domain + management services (see §3). This is the
  largest surface; most business logic lives here.
- **`backend/repositories/`** — repository pattern for data access. Replaces the
  old monolithic `AppState` (removed in the ServiceRegistry refactor).
- **`backend/integrations/`** — protocol integrations, each self-registering
  with the feature system: `can/`, `rvc/` (incl. Firefly extensions),
  `j1939/` (incl. Spartan K2 chassis extensions), `diagnostics/`,
  `notifications/`, `analytics/`, `analytics_dashboard/`, `device_discovery/`,
  `auth/`, `ip/`, `bluetooth/`.
- **`backend/api/routers/`** — legacy `/api/*` REST endpoints (being retired,
  ADR-0003).
- **`backend/api/domains/`** — **Domain API v2** (`/api/v2/*`): `entities.py`,
  `diagnostics.py`, `networks.py`, `system.py`. This is the primary development
  path.
- **`backend/websocket/`** — WebSocket handlers/routes (entity updates, logs,
  CAN sniffer, network map, features, recorder/analyzer/filter).
- **`backend/middleware/`** — auth, CSRF, structured logging, rate-limiting,
  validation.
- **`backend/models/`** (SQLAlchemy ORM), **`backend/schemas/`** (Pydantic
  request/response), **`backend/alembic/`** (async migrations).

### `frontend/` — React SPA

- **React 19 + Vite 6 + TypeScript (strict) + Tailwind 4 + shadcn/ui.**
- **Server state via React Query**; client state via React Context (auth,
  websocket, health, theme). No Redux.
- `src/` is organized by `pages/`, `components/` (with `ui/` for shadcn),
  `hooks/`, `contexts/`, `api/`, `types/`. OpenAPI-strong frontend REST
  types are generated into `src/api/generated/openapi-types.ts`; WebSocket
  envelopes, runtime validators, legacy-shaped UI adapters, and analytics
  responses remain manual where they are not direct OpenAPI REST contracts.
  Entity control/bulk-control uses the generated HOF-021 safety result schemas;
  `frontend/src/hooks/useEntities.ts` is only a legacy-shape adapter for current
  UI callers, not a v1/v2 fallback switch.
- Talks to the backend over REST (`/api/v2/*`) + WebSocket (`/ws*`). Vite dev
  server proxies both to the backend.

### Supporting trees

- **`config/`** — `rvc.json` (the RV-C spec: PGNs/SPNs/signals),
  `coach_mapping.default.yml` (generic device→entity map),
  `2021_Entegra_Aspire_44R.yml` (reference coach), `security.yml`,
  `Caddyfile.example`.
- **`docs/`** — `docs/adr/` (the 9 formal ADRs — see §4), `docs/architecture/`,
  `docs/api/`, `docs/safety.md` (the operational-safety policy), MkDocs site.
- **`.github/`** — `copilot-instructions.md` + the modular
  `.github/instructions/*.instructions.md` set + `.github/prompts/` (audit /
  feature prompts) + CI workflows.
- **`nix/`, `flake.nix`** — Nix package/module support. `flake.nix` stays a thin
  output shell; `nix/package.nix` owns the CoachIQ/backend + frontend package
  derivations, `nix/module.nix` owns the `services.coachiq` hybrid NixOS module,
  and `nix/test-module.nix` is wired into Linux flake checks for module eval
  coverage.
- **`dev_tools/`, `scripts/`** — dev utilities; `scripts/export_openapi.py`
  exports the OpenAPI schema; `frontend/scripts/generate-api-types.mjs` and
  `frontend/scripts/check-api-types.mjs` generate/check the committed frontend
  OpenAPI types; `scripts/ci-quality-gate.sh` is the CI gate.

---

## 3. Backend architecture — the load-bearing patterns

These are the patterns you must work _with_, not around. Each is backed by an
ADR; the ADR is the durable source of truth.

**ServiceRegistry + FastAPI `Depends` (ADR-0001, ADR-0006).** There is no
external DI framework. `backend/core/service_registry.py` owns service
lifecycle and resolves a topological startup order across startup stages
(registered in `backend/core/registrations/`). HTTP code obtains services
**only** through the typed aliases in `backend/core/dependencies.py` using the
`Annotated[Type, Depends(get_x)]` pattern. The old `AppState` /
`backend/core/state.py` global is **removed** — do not reach for `app.state`,
`get_app_state`, `get_entity_manager`, or module-level service singletons.

**The CAN facade (ADR-0002).** All CAN operations go through a single
`CANFacade` (`backend/services/can_facade.py`), which coordinates the
lower-level CAN services (bus service, message injector, filter, recorder,
protocol analyzer, anomaly detector) and enforces TX rate-limiting and
emergency-stop coordination. **Routers must never import `CANBusService` or
the lower-level CAN modules directly** — go through the facade. This is the
chokepoint that keeps CoachIQ a well-behaved bus citizen.

**Domain API v2 only (ADR-0003).** New endpoints land under `/api/v2/*` in
`backend/api/domains/`. Legacy `/api/*` routers are retired as v2 replacements
land — they are **not** maintained in parallel. Entity operations use the
unified `/api/v2/entities` surface, not per-type routes like `/api/lights`.

**Three-tier config, three distinct names (ADR-0008).** Do not conflate these:

- `Settings` (`backend/core/config.py::get_settings`) — the canonical **app
  config** object. Most code reads this directly. Env vars use the
  `COACHIQ_` prefix with `COACHIQ_SECTION__SETTING` nesting.
- `RVCConfigFacade` (`backend/services/rvc_config_facade.py`) — a thin facade
  for **RV-C metadata** lookups (PGN names, coach info) only. Renamed from the
  old `ConfigService`. Not for general app config.
- `RVCSpecLoader` (`backend/integrations/rvc/spec_loader.py`) — a TTL-cached
  loader for the RV-C **spec/mapping files on disk**. Internal to the decoder.
  Renamed from the old `ConfigurationService`.

**Nix module hybrid config (ADR-0009).** The NixOS module lives at
`nix/module.nix`, is exposed as `nixosModules.default`, and configures
`services.coachiq`. Keep only load-bearing deployment knobs first-class
(`host`, `port`, `dataDir`, `environmentFile`, `openFirewall`, `logLevel`,
`tlsTerminationIsExternal`); pass the long-tail non-secret settings through the
freeform `settings` attrset as current `COACHIQ_*` env vars. Secrets belong in
`environmentFile`, not literal Nix options.

**Auth consolidated under `backend/services/auth/` (ADR-0007).** The auth
subsystem is one package: `manager.py` (`AuthManager`, the policy engine) vs
`service.py` (`AuthService`, the request-time facade) are intentionally
distinct, plus `tokens.py`, `sessions.py`, `mfa.py` (TOTP), `lockout.py`,
`repository.py`. Supports single-user, multi-user (JWT + PIN), and magic-link
flows; CSRF protection on mutating endpoints. (OAuth/OIDC is future work, not
yet implemented.)

**Repository pattern.** Repositories under `backend/repositories/` own DB
access; services call repositories rather than issuing raw SQLAlchemy.
`DatabaseManager` provides async sessions; `PersistenceService` handles backups
and durable storage. Persistence has memory-only (default), dev (local files),
and production (system dir) modes.

**HTTP error envelope (ADR-0005).** Error responses carry both FastAPI's
`detail` field and a custom `error.{code, message}` shape for backward compat.
Don't "clean this up" to one or the other.

---

## 4. The ADR set (formal, in `docs/adr/`)

These are the locked "don't revert these" decisions. Read the file before
proposing anything that touches the area.

| ADR      | Title                                 | One-line                                                                                   |
| -------- | ------------------------------------- | ------------------------------------------------------------------------------------------ |
| ADR-0001 | FastAPI `Depends` over a DI framework | ServiceRegistry + native `Depends`; explicit wiring, no punq/dependency-injector           |
| ADR-0002 | CAN facade pattern                    | One `CANFacade` is the sole entry point for all CAN; enforces rate-limit + e-stop          |
| ADR-0003 | API v2 only, no legacy                | New work goes to `/api/v2/*`; legacy `/api/*` deleted as replaced, not parallel-maintained |
| ADR-0004 | CoachIQ is not the safety system      | Firefly owns physical safety; CoachIQ is API guardrails, consumer-grade quality bar        |
| ADR-0005 | HTTP error response envelope          | Dual `detail` + `error.{code,message}` for compatibility                                   |
| ADR-0006 | Typed dependency injection            | Typed aliases in `dependencies.py` map to concrete classes; registry is string-keyed       |
| ADR-0007 | Auth service namespace                | Auth consolidated into `backend/services/auth/`; `AuthManager` ≠ `AuthService` by design   |
| ADR-0008 | RVC config facade naming              | `Settings` (app) vs `RVCConfigFacade` (metadata) vs `RVCSpecLoader` (spec files)           |
| ADR-0009 | Nix module hybrid options             | `services.coachiq` keeps a small typed surface; long-tail config flows through env vars     |

---

## 5. Build / test / quality gates

Quality gates are **non-negotiable and incremental** — run them after each
change, not just at the end. This is the bar Copilot is held to and the bar a
spec's `[success-criteria]` should cite.

**Backend:**

```bash
poetry install
poetry run python run_server.py --reload --debug   # dev server (Swagger at /docs)
poetry run pytest                                   # tests; markers: unit, integration, api, can, safety, websocket, rvc, auth, smoke, performance
poetry run python scripts/check_module_coverage.py  # per-module guardrail coverage ratchet after coverage.xml exists
poetry run python scripts/validate_rvc_spec.py      # RV-C spec + live-corpus decode sanity harness
poetry run ruff check .                             # lint (zero warnings)
poetry run ruff format backend                      # format (line length 100)
poetry run pyright backend                          # type-check (basic mode; ratcheting toward strict)
```

**Guardrail coverage ratchet (HOF-015).** Focused marker runs must not fail on
whole-repo coverage, so `pytest.ini` does not set a global `--cov-fail-under`.
Instead, `scripts/check_module_coverage.py` reads fresh `coverage.xml` after
guardrail tests and enforces only the current high-value module floors:
`backend/services/can_facade.py >= 65%`, `backend/services/safety_service.py >= 42%`,
`backend/services/auth/service.py >= 80%`, `backend/services/auth/manager.py >= 32%`,
`backend/middleware/secure_auth.py >= 60%`, and
`backend/websocket/auth_handler.py >= 85%`. Run the ratchet locally with
`nix run .#guardrail-coverage`, which executes `pytest -m "can or auth or safety or websocket"`
then checks those floors. Raise these numbers when coverage improves; never
lower them without a reviewed handoff.

**RV-C decode validation harness (HOF-028).** `scripts/validate_rvc_spec.py`
checks the curated `config/rvc.json` against structural rules, coach-mapping
references, duplicate-PGN variant classification, and the trimmed live fixture
at `recordings/recon004_decode_sanity.candump`. The full RECON-004 Pi capture is
provenance only; CI uses the committed fixture so builds are reproducible.
Per-signal `unavailable_raw_values` metadata is the only mechanism for masking
not-available values; do not add blanket max-value masking.

Treat the RV-C layers as distinct: the spec PDF is the standard, `rvc.json` is
the curated decode subset, the live bus is what is present on this coach, and the
coach mapping YAML is the partial set surfaced as entities so far. The harness
therefore validates mapped DGN references one-way against `rvc.json`; it must not
flag live-but-unmapped bus DGNs as errors because mapping completion is host-led
future work.

**Frontend (from `frontend/`):**

```bash
npm install
npm run dev          # Vite dev server (:5173)
npm run typecheck    # tsc strict; baseline = 0 errors
npm run lint         # ESLint flat config; pragmatic mode (see §6)
npm run build        # must succeed
npm run test         # Vitest
```

**Nix shortcuts:** `nix run .#test` / `.#guardrail-coverage` / `.#lint` /
`.#format` / `.#ci`.
**Pre-commit:** `pre-commit run --all-files` (ruff `--fix`, ruff-format,
bandit, ESLint-staged). `dev_start.sh` sets up a virtual-CAN dev environment.

---

## 6. Gotchas (the afternoon-savers)

- **CAN access only via `CANFacade`.** Importing `CANBusService` or a
  lower-level CAN module into a router will pass tests but violates ADR-0002 and
  bypasses the rate-limiter / e-stop. Reviewers reject it.
- **No `AppState` / `app.state` / module-level service singletons.** Removed in
  the ServiceRegistry refactor. Use `Depends(get_x)` from
  `backend/core/dependencies.py` only.
- **`Settings` vs `RVCConfigFacade` vs `RVCSpecLoader`.** Reaching for the
  RV-C facade to read app config (or vice versa) is the classic ADR-0008
  mistake. App config → `get_settings()`; PGN/coach metadata → the facade;
  on-disk spec files → the loader.
- **Startup ordering is topological, validated at boot.** A new service with an
  unsatisfiable or circular dependency fails at startup with a clear error, not
  silently at request time. Register it in `backend/core/registrations/` in the
  right stage. (A known `entity_service` ↔ `websocket.handlers` cycle is the
  reason `EntityService` is intentionally _not_ typed in the DI aliases —
  don't "fix" that by adding the alias.)
- **Frontend ESLint is pragmatic, not clean-slate.** Legacy errors on untouched
  lines are tolerated, but any **new** error on a line you touched fails CI
  (enforced by `scripts/eslint_diff_check.py`). Warnings are advisory. Trailing
  commas are disallowed; 2-space indent; LF line endings.
- **OpenAPI is the contract where the schema is strong.** Generate frontend
  REST types with `cd frontend && npm run gen:api`; verify freshness with
  `npm run check:api-types`. `frontend/src/api/types/domains.ts` aliases the
  generated components for strong v2 schemas and explicitly keeps manual types
  for WebSocket envelopes, Zod/runtime validation helpers, legacy-shaped UI
  adapters, and analytics responses. Entity control and bulk-control result
  types are generated from the HOF-021 safety response models; do not recreate a
  silent fallback bridge for them. If you change a v2 payload, regenerate/export
  and update the generated types in the same change — don't infer the shape by
  hand (see comms lesson L-02).
- **Real bus vs virtual CAN.** Dev/tests use `vcan`/mocked CAN; production is a
  real bus talking to a real Firefly panel. What the coach actually _does_ with
  a frame is knowable only from the live bus, never from CoachIQ's source (see
  comms lesson L-06 and ADR-0004). Treat coach-specific behavior as a fact to
  capture from a trace, not to assert from the spec JSON.
- **All Python runs under Poetry.** `poetry run python …`, never bare `python`.

---

## 7. Current direction

Domain API v2 is the active surface; legacy `/api/*` is being retired endpoint
by endpoint as v2 equivalents land (ADR-0003). The codebase recently went
through an audit cycle (the `A*` prompts under `.github/prompts/`) that produced
ADR-0006 through ADR-0008 — typed DI, the auth-namespace consolidation, and the
RVC-config rename. Type-checking is in pyright "basic" mode and ratcheting
toward strict. Track open structural work as hand-offs in the `coachiq`
basic-memory channel; graduate durable outcomes here, into
`IMPLEMENTATION_PLAN.md`, or into a new ADR.

---

## 8. Cross-agent comms (read alongside this file)

Build coordination between **Claude (HQ — spec/research/plan author)** and
**GitHub Copilot (implementer)** runs through the `coachiq` basic-memory
project (project_id `123da13d-09b8-4297-83ed-a580c3e0401b`), not through this
repo. The doctrine — directory layout, the observation/relation vocabulary, the
mandatory review gate, and the graduation rule — lives in that project's
`handoff/README` note. Claude authors specs and never commits; Copilot reviews
every spec against the real code, pauses for explicit approval, then implements
and commits. Durable outcomes graduate from basic-memory into this repo
(`PROJECT_CONTEXT.md`, `IMPLEMENTATION_PLAN.md`, `docs/adr/`, the
`.github/instructions/*` set) in the same commit as the implementation. See
the "Cross-Agent Comms" section at the top of
`.github/copilot-instructions.md` for Copilot's side of the protocol.
