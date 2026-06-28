# CoachIQ — Implementation Plan / Build Log

The durable build log for CoachIQ. This is the canonical, git-tracked home for
plans and decisions that graduate out of the `coachiq` basic-memory channel.
basic-memory holds work *in flight*; this file (and the ADRs under `docs/adr/`)
holds what has *landed* and why.

**How this file is maintained.** When a spec hand-off (`handoff/HOF-NNN` in the
`coachiq` basic-memory project) is implemented, its durable content graduates
here **in the same commit as the implementation** — then the basic-memory note
is archived (see the `handoff/README` graduation rule and lesson L-05). Each
entry below records what shipped, the HOF that drove it, and the commit, so the
log stays traceable back to the discussion that produced it.

For the architecture orientation (what the system is, the ADR set, the
load-bearing patterns and gotchas), see `PROJECT_CONTEXT.md`. For how agents
coordinate, see the `handoff/README` note in the `coachiq` basic-memory project.

---

## Conventions

- **Newest entries at the top** of the Build Log.
- Each entry: `### HOF-NNN — <title>` followed by `[shipped]` (commit SHA +
  date), a one-paragraph **what changed**, and a **why** that points at the ADR
  or decision behind it. Link the `[references-file]` paths touched.
- A change that establishes or revises a load-bearing decision should also land
  (or update) a formal ADR under `docs/adr/`; this log then points at it rather
  than duplicating it.
- Keep prose tight. This is a log, not a narrative — the discussion lives in the
  archived basic-memory notes.

---

## Direction — v2-only convergence

Per [ADR-0003](docs/adr/ADR-0003-api-v2-only-no-legacy.md), the API surface and
frontend consumer code converge on `/api/v2` only. Legacy `/api/*` routers and
frontend v1 clients/hooks are retired incrementally; each deletion is gated on a
proven-equivalent v2 contract and migrated callers.

The end state is deletion-heavy: no v1 `useEntities` hook stack, no legacy
`frontend/src/api/endpoints.ts` functions, no `withDomainAPIFallback` or `useV2`
machinery, and the remaining mounted legacy router modules inventoried in
HOF-016 removed. The dual `detail` plus `error.{code,message}` envelope can be
revisited once legacy is gone.

The path is router-by-router and caller-by-caller. The HOF-016 inventory below
is the retirement map; each row remains individually gated.

Remaining contract gaps blocking completion:

1. v2 `EntityCommand` lacks `lock`/`unlock`, which blocks full entity v1 removal
   until the command contract is widened and tested.
2. Diagnostics legacy-router retirement is closed by HOF-026; remaining
  `SystemHealthResponse` generated names belong to other v2/security-dashboard
  contracts, not `/api/diagnostics/health`.

Work hanging off this direction: HOF-017 removed the fake entity fallback and
adopted generated result types; HOF-023 is the candidate for migrating the 22
entity UI callers plus widening v2 for lock/unlock; per-router retirements
follow the HOF-016 plan.

Pace caveat: interleave risk-reduction work such as HOF-015 guardrail coverage
rather than pursuing pure surface shrink monotonically. Coverage addresses real
risk; retirement addresses cleanliness.

---

## Build Log

### HOF-026 — v2 Diagnostics Health Widget And Legacy Router Retirement

- [shipped] same commit as this entry · 2026-06-27
- [component] both
- [adr] docs/adr/ADR-0003-api-v2-only-no-legacy.md

**What changed.** The frontend diagnostics health path now reads real v2
diagnostics data from `/api/v2/diagnostics/system-status` and
`/api/v2/diagnostics/faults`, using generated OpenAPI types for the status and
fault summary shapes. `SystemHealthScore`, `useDiagnostics`, and the performance
page were migrated off the old hand-written `SystemHealthResponse` contract.
The legacy backend `GET /api/diagnostics/health` router was deleted and removed
from router registration, and OpenAPI plus generated frontend API types were
regenerated.

**Why.** HOF-022 made v2 diagnostics real, so the UI can now cut over without
displaying the fake health/fault data that blocked HOF-016. This is the first
actual legacy-router deletion in the ADR-0003 retirement inventory.

**Files.** backend/api/router_config.py, backend/api/routers/diagnostics.py,
docs/api/openapi.json, docs/api/openapi.yaml, frontend/src/api/endpoints.ts,
frontend/src/api/generated/openapi-types.ts, frontend/src/api/types.ts,
frontend/src/api/types/domains.ts,
frontend/src/components/diagnostics/SystemHealthScore.tsx,
frontend/src/components/diagnostics/index.ts, frontend/src/hooks/useDiagnostics.ts,
frontend/src/pages/performance.tsx

### HOF-022 — Real v2 Diagnostics Backend

- [shipped] same commit as this entry · 2026-06-27
- [component] backend

**What changed.** The dormant advanced diagnostics handler is now available as a
registered `diagnostic_handler` service and is injected into `CANBusService`.
The CAN receive path can decode live source-address-specific DM_RV/J1939 DM1
frames by PGN fallback, ignores the RECON-003 clean heartbeat sentinel
(`SPN=0x7FFFF`, `FMI=31`, lamps clear, occurrence count `127`), and ingests
active DM_RV DTCs into the handler keyed by source address, SPN, and FMI. The
v2 diagnostics `/faults`, `/dtcs`, `/statistics`, and `/system-status` endpoints
now read registered handler/CAN health data instead of the previous `None`
service fallback.

**Why.** HOF-022 unblocks the frontend diagnostics rebuild by making the v2
backend source real first. The nixpi bridge means mirrored `can0`/`can1` DM_RV
frames are expected, so DTC counting must dedupe by diagnostic identity rather
than interface.

**Files.** backend/api/domains/diagnostics.py,
backend/services/can_bus_service.py, backend/core/registrations/phase4.py,
backend/integrations/diagnostics/feature.py,
backend/integrations/diagnostics/tests/test_advanced_diagnostics.py,
tests/api/test_diagnostics_v2_real.py

### HOF-028 — RV-C Decode Quality Harness

- [shipped] same commit as this entry · 2026-06-27
- [component] backend

**What changed.** The RV-C decoder now supports explicit per-signal
`unavailable_raw_values` metadata, returning unavailable live values as `None`
in the core decoder and `"n/a"` through `decode_payload_safe`. `rvc.json` masks
live-proven no-data fields and corrects scale/offset for load-bearing signals
validated against the RECON-004 corpus, including ATS current/frequency,
thermostat setpoints, tank level capacity fields, AC load status, and AC command
percent/dead-band fields. The PDF-confirmed `WATERHEATER_STATUS` (`1FFF7`) and
`CHARGER_CONFIGURATION_COMMAND_2` (`1FF95`) DGNs were added; unconfirmed
observed PGNs remain classified as gaps instead of invented layouts.

**Why.** RECON-004 showed that structural decoding was not enough: raw sentinel
and Table 5.3 encoded values surfaced as plausible physical readings such as
`65535`, `32000`, and raw thermostat setpoints. HOF-028 turns that into a
repeatable check by committing a trimmed live-corpus fixture and validating it in
CI with `scripts/validate_rvc_spec.py` / `nix run .#rvc-spec-validation`.
The coach mapping files are incomplete by design: mapped DGNs are confirmed
user-facing entities and must exist in `rvc.json`, but live bus DGNs that are not
yet mapped are roadmap candidates rather than validation failures.

**Files.** .github/workflows/nix-ci.yml, flake.nix, config/rvc.json,
backend/integrations/rvc/decoder_core.py, backend/integrations/rvc/decode.py,
scripts/validate_rvc_spec.py, recordings/recon004_decode_sanity.candump,
tests/test_rvc_decoder_comprehensive.py, PROJECT_CONTEXT.md

### HOF-015 — Guardrail Coverage Ratchet
- [shipped] same commit as this entry · 2026-06-27
- [component] backend
- [adr] docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md

**What changed.** Focused behavior tests now cover the approved guardrail
modules: CANFacade delegation/e-stop paths, SafetyService interlocks/PIN/e-stop
decisions, AuthManager/AuthService token/MFA/lockout decisions, secure auth
middleware happy/deny paths, and WebSocket auth happy/deny/permission paths.
The global pytest `--cov-fail-under` floor was removed and replaced with
`scripts/check_module_coverage.py`, a per-module ratchet over fresh
`coverage.xml`. `nix run .#guardrail-coverage` runs the guardrail marker suite
and enforces the ratchet; CI runs that app after the diff-aware quality gate.

**Why.** HOF-015 moves coverage onto the realistic API-side risk paths from
ADR-0004 without making narrow marker runs fail on unrelated long-tail modules.
The ratchet floors were seeded at the reviewed first milestones, then raised to
lock in the HOF-015 measured gains with buffer: CANFacade 65%, SafetyService
42%, AuthService 80%, AuthManager 32%, SecureAuthenticationMiddleware 60%, and
WebSocketAuthHandler 85%.

**Files.** .github/workflows/nix-ci.yml, flake.nix, pytest.ini,
scripts/check_module_coverage.py, PROJECT_CONTEXT.md,
tests/services/test_can_facade_guardrails.py,
tests/services/test_safety_service_guardrails.py,
tests/services/test_auth_guardrails.py, tests/middleware/test_secure_auth.py,
tests/websocket/test_auth_handler_guardrails.py

### HOF-017 — Remove Fake Entity Domain Fallback
- [shipped] same commit as this entry · 2026-06-27
- [component] frontend
- [adr] docs/adr/ADR-0003-api-v2-only-no-legacy.md

**What changed.** The frontend entity v2 client no longer uses
`withDomainAPIFallback`; entity control and bulk-control call the v2 endpoints
directly and surface v2 errors instead of routing through a fake fallback path.
`frontend/src/api/types/domains.ts` now aliases entity control result types to
the generated HOF-021 `SafetyOperationResultV2` and
`BulkSafetyOperationResultV2` schemas. `frontend/src/hooks/useEntities.ts`
remains as a legacy-shaped UI adapter for existing callers, but the `useV2`
switch and silent fallback behavior were removed. The bridge `as any` casts in
`frontend/src/api` were eliminated.

**Why.** HOF-017 review proved the fallback was not a real v1 safety net: the
"legacy" fallback path also POSTed to `/api/v2/entities/{id}/control`, then
converted through untyped casts. Removing it makes entity failures visible and
keeps the frontend on the finalized v2 contract from HOF-021 while deferring
full `useEntities.ts` removal until each UI caller migrates.

**Files.** frontend/src/api/domains/entities.ts,
frontend/src/api/domains/index.ts, frontend/src/api/types/domains.ts,
frontend/src/hooks/useEntities.ts,
frontend/src/hooks/domains/__tests__/useEntitiesV2.test.tsx,
frontend/src/hooks/domains/__tests__/useEntitiesV2Validation.test.tsx,
PROJECT_CONTEXT.md

### HOF-021 — Typed v2 Response Models For Generated Frontend Contracts
- [shipped] same commit as this entry · 2026-06-27
- [component] both
- [adr] docs/adr/ADR-0003-api-v2-only-no-legacy.md

**What changed.** The remaining loose top-level response schemas identified by
HOF-014 now have concrete v2 response models: entity control and bulk-control
reuse the existing service-layer safety result models, diagnostics health/DTC
collection/statistics use typed Pydantic envelopes with documented dynamic DTC
item details, system health is typed, and system status documents both default
and IETF health+json response shapes. OpenAPI artifacts and generated frontend
types were regenerated, with contract tests covering component refs, the system
status `anyOf`, and representative sample responses.

**Why.** HOF-021 closes the root OpenAPI weakness behind the HOF-014 manual
type remainder without changing endpoint semantics or adding legacy routes.
The diagnostics v2 health endpoint remains a service-health contract, not a
replacement for legacy `/api/diagnostics/health`; retiring that legacy route
still requires a separate v2 home for `SystemHealthResponse` or frontend
migration.

**Files.** backend/api/domains/entities.py,
backend/api/domains/diagnostics.py, backend/api/domains/system.py,
backend/schemas/domain_api.py, docs/api/openapi.json, docs/api/openapi.yaml,
frontend/src/api/generated/openapi-types.ts,
frontend/src/api/types/domains.ts, tests/api/test_domain_response_models.py

### HOF-016 — ADR-0003 Legacy Router Retirement Inventory
- [shipped] same commit as this entry · 2026-06-27
- [component] backend
- [adr] docs/adr/ADR-0003-api-v2-only-no-legacy.md

**What changed.** No routers were removed. This pass converted the reviewed
HOF-016 scope into an inventory-only migration checkpoint: the mounted legacy
router surface, v2 coverage status, and frontend caller evidence are now
recorded below as the gate for future ADR-0003 cutover work.

**Why.** Review disproved the apparent diagnostics duplicate. Legacy
`GET /api/diagnostics/health` returns the typed `SystemHealthResponse` consumed
by `frontend/src/api/endpoints.ts::fetchSystemHealth()`, while
`GET /api/v2/diagnostics/health` is a loose diagnostics-service health object
and `GET /api/v2/diagnostics/system-status` has a different `SystemStatus`
shape. Deleting the legacy router would break the UI. Future removals must be
per-router, contract-proven, and paired with frontend migration when callers
remain.

**Inventory method.** The route list was generated from `backend.main.app.routes`
under `nix develop --command poetry run python`, then cross-checked against
`docs/api/openapi.json` and string references in `frontend/src` excluding
generated OpenAPI types. "Frontend callers" means direct string references were
found in current frontend source; "none found" is not proof of no external or
test clients.

**Summary.** There are 29 mounted legacy router modules with 263 registered
routes, plus 4 unmounted files in `backend/api/routers/`. The v2 domains expose
40 routes across entities, diagnostics, networks, and system. No mounted legacy
router is proven fully covered by v2 in this pass.

**Retirement priorities.**

1. **Contract blockers before deletion:** diagnostics, health, and dashboard
   compatibility responses need v2 equivalents or caller migration first.
2. **Partial-overlap clusters:** CAN/network, config/system, multi-network,
   safety, and schemas should be split into read-only v2 replacement work and
   remaining legacy-only capability work.
3. **Frontend-owned migrations:** routes with current frontend callers must move
   under HOF-017-style client consolidation before backend removal.
4. **Unmounted files:** unmounted router files can be retired separately after
   import/test checks because they are not exposed by the current app.

**Registered legacy routers.**

- `analytics_dashboard` — routes: `GET /api/analytics/aggregation`,
  `GET /api/analytics/health`, `GET /api/analytics/historical`,
  `GET /api/analytics/insights`, `POST /api/analytics/metrics`,
  `GET /api/analytics/status`, `GET /api/analytics/trends`; v2 coverage: none;
  frontend callers: `frontend/src/hooks/useAnalyticsDashboard.ts`; gate: design
  an analytics v2 domain or retire the dashboard feature.
- `auth` — routes: `GET /api/auth/admin/credentials`,
  `GET /api/auth/admin/invitations`,
  `DELETE /api/auth/admin/invitations/{invitation_id}`,
  `POST /api/auth/admin/mfa/disable`, `GET /api/auth/admin/mfa/status`,
  `GET /api/auth/admin/stats`, `GET /api/auth/admin/users`,
  `GET /api/auth/invitation/accept`, `POST /api/auth/invitation/send`,
  `GET /api/auth/lockout/status`, `GET /api/auth/lockout/status/{username}`,
  `POST /api/auth/lockout/unlock`, `POST /api/auth/login`,
  `POST /api/auth/login-mfa`, `POST /api/auth/login-step`,
  `POST /api/auth/logout`, `GET /api/auth/magic`, `POST /api/auth/magic-link`,
  `GET /api/auth/me`, `GET /api/auth/mfa/backup-codes`,
  `DELETE /api/auth/mfa/disable`, `POST /api/auth/mfa/regenerate-backup-codes`,
  `POST /api/auth/mfa/setup`, `GET /api/auth/mfa/status`,
  `POST /api/auth/mfa/verify`, `POST /api/auth/mfa/verify-setup`,
  `POST /api/auth/refresh`, `POST /api/auth/revoke`,
  `POST /api/auth/secure/login`, `POST /api/auth/secure/logout`,
  `POST /api/auth/secure/refresh`, `GET /api/auth/status`; v2 coverage: none;
  frontend callers: auth context, endpoint client, settings, and MFA
  components; gate: separate auth-domain design, not a router retirement.
- `can` — routes: `POST /api/can/emergency-stop`, `GET /api/can/health`,
  `GET /api/can/health/comprehensive`, `GET /api/can/interfaces`,
  `GET /api/can/interfaces/details`, `GET /api/can/metrics/computed`,
  `GET /api/can/queue/status`, `GET /api/can/recent`, `POST /api/can/send`,
  `GET /api/can/statistics`, `GET /api/can/statistics/enhanced`,
  `GET /api/can/status`, websocket `/api/can/ws/scan`; v2 coverage: partial via
  `networks` read-only status/statistics/interfaces only; frontend callers:
  `frontend/src/api/endpoints.ts`; gate: keep TX, recent frames, queue, health,
  and websocket capability until explicit v2 replacements exist.
- `can_analyzer` — routes: `POST /api/can-analyzer/analyze`,
  `DELETE /api/can-analyzer/clear`, `GET /api/can-analyzer/live`,
  `GET /api/can-analyzer/messages`, `GET /api/can-analyzer/patterns`,
  `GET /api/can-analyzer/protocols`, `GET /api/can-analyzer/report`,
  `GET /api/can-analyzer/statistics`; v2 coverage: none; frontend callers:
  `frontend/src/api/can-analyzer.ts`; gate: analyzer v2 design or feature
  retirement.
- `can_filter` — routes: `DELETE /api/can-filter/capture`,
  `GET /api/can-filter/capture`, `GET /api/can-filter/export`,
  `POST /api/can-filter/import`, `GET /api/can-filter/rules`,
  `POST /api/can-filter/rules`, `DELETE /api/can-filter/rules/{rule_id}`,
  `GET /api/can-filter/rules/{rule_id}`, `PUT /api/can-filter/rules/{rule_id}`,
  `GET /api/can-filter/statistics`, `POST /api/can-filter/statistics/reset`,
  `GET /api/can-filter/status`; v2 coverage: none; frontend callers:
  `frontend/src/api/can-filter.ts`; gate: filter v2 design or feature
  retirement.
- `can_recorder` — routes: `GET /api/can-recorder/download/{filename}`,
  `GET /api/can-recorder/list`, `POST /api/can-recorder/pause`,
  `POST /api/can-recorder/replay/start`, `POST /api/can-recorder/replay/stop`,
  `POST /api/can-recorder/resume`, `POST /api/can-recorder/start`,
  `GET /api/can-recorder/status`, `POST /api/can-recorder/stop`,
  `DELETE /api/can-recorder/{filename}`; v2 coverage: none; frontend callers:
  recorder API, CAN tools page, and recorder websocket hook; gate: recorder v2
  design or feature retirement.
- `can_tools` — routes: `POST /api/can-tools/inject`,
  `POST /api/can-tools/inject/j1939`, `DELETE /api/can-tools/inject/stop`,
  `GET /api/can-tools/pgn-info/{pgn}`, `PUT /api/can-tools/safety`,
  `GET /api/can-tools/status`, `GET /api/can-tools/templates`; v2 coverage:
  none; frontend callers: `frontend/src/pages/can-tools.tsx`; gate: explicit
  developer-tools v2 surface.
- `config` — routes: `GET /api/config/can/interfaces`,
  `POST /api/config/can/interfaces/validate`,
  `PUT /api/config/can/interfaces/{logical_name}`,
  `GET /api/config/coach/interface-requirements`,
  `GET /api/config/coach/metadata`, `GET /api/config/database`,
  `GET /api/config/device_mapping`, `GET /api/config/features`,
  `GET /api/config/settings`, `GET /api/config/spec`,
  `GET /api/status/application`, `GET /api/status/features`,
  `POST /api/status/force_update_check`, `GET /api/status/latest_release`,
  `GET /api/status/server`; v2 coverage: partial through system/networks for
  read-only status only; frontend callers: endpoint client, API types,
  documentation page, RV-C spec page; gate: split app status, coach metadata,
  settings, and release checks into typed v2 surfaces.
- `dashboard` — routes: `GET /api/dashboard/activity`,
  `POST /api/dashboard/alerts/{alert_id}/acknowledge`,
  `GET /api/dashboard/analytics`, `POST /api/dashboard/bulk-control`,
  `GET /api/dashboard/can-bus`, `GET /api/dashboard/entities`,
  `GET /api/dashboard/summary`, `GET /api/dashboard/system`; v2 coverage:
  partial through entities/networks/system primitives, not dashboard aggregate
  contracts; frontend callers: `frontend/src/api/endpoints.ts`; gate: migrate
  dashboard composition to v2 primitives or add typed dashboard v2.
- `database_management` — routes: `GET /api/database/history`,
  `POST /api/database/migrate`, `GET /api/database/migrate/{job_id}/status`,
  `GET /api/database/safety-check`, `GET /api/database/status`; v2 coverage:
  none; frontend callers: `frontend/src/components/admin/DatabaseManagementTab.tsx`;
  gate: admin/database v2 design.
- `dbc` — routes: `POST /api/dbc/active/{name}`,
  `POST /api/dbc/convert/dbc-to-rvc`, `POST /api/dbc/convert/rvc-to-dbc`,
  `GET /api/dbc/export/{name}`, `GET /api/dbc/list`,
  `GET /api/dbc/messages/{name}`, `GET /api/dbc/search/{signal_name}`,
  `POST /api/dbc/upload`; v2 coverage: none; frontend callers: none found;
  gate: verify external/test clients before retirement or move to tools v2.
- `device_discovery` — routes: `GET /api/discovery/availability`,
  `POST /api/discovery/discover`, `GET /api/discovery/network-map`,
  `POST /api/discovery/poll`, `GET /api/discovery/protocols`,
  `GET /api/discovery/status`, `GET /api/discovery/topology`,
  `POST /api/discovery/wizard/auto-discover`,
  `GET /api/discovery/wizard/device-profile/{device_address}`,
  `POST /api/discovery/wizard/setup-device`,
  `GET /api/discovery/wizard/setup-recommendations`; v2 coverage: none beyond
  adjacent network concepts; frontend callers: `frontend/src/api/endpoints.ts`;
  gate: discovery v2 domain or feature consolidation.
- `diagnostics` — retired in HOF-026. Former route:
  `GET /api/diagnostics/health`; replacement: real v2 diagnostics
  `GET /api/v2/diagnostics/system-status` plus
  `GET /api/v2/diagnostics/faults`; frontend callers migrated off
  `fetchSystemHealth()`; OpenAPI no longer advertises the legacy path.
- `docs` — routes: `GET /api/docs/openapi`, `GET /api/docs/search`,
  `GET /api/docs/status`; v2 coverage: none; frontend callers:
  `frontend/src/pages/documentation.tsx`; gate: documentation/search v2 design
  or keep as tooling API.
- `health` — routes: `GET /api/health`, `GET /api/health/ready`,
  `GET /api/health/services`, `GET /api/health/startup`; v2 coverage: partial
  through system health/status but not readiness/startup/service contracts;
  frontend callers: none found; gate: compare with deployment probes before
  touching.
- `logs` — routes: `GET /api/logs/history`; v2 coverage: none; frontend
  callers: none found; gate: decide whether logs belong under system v2.
- `multi_network` — routes: `GET /api/multi-network/bridge-status`,
  `GET /api/multi-network/health`, `GET /api/multi-network/networks`,
  `GET /api/multi-network/status`; v2 coverage: partial via networks status,
  not bridge/multi-network-specific contracts; frontend callers:
  `frontend/src/api/endpoints.ts`; gate: fold remaining bridge concepts into
  networks v2 or retain legacy.
- `notification_analytics` — routes: `GET /api/notification-analytics/channels`,
  `GET /api/notification-analytics/dashboard`,
  `POST /api/notification-analytics/engagement/{notification_id}`,
  `GET /api/notification-analytics/errors`,
  `GET /api/notification-analytics/metrics`,
  `GET /api/notification-analytics/queue/health`,
  `GET /api/notification-analytics/reports`,
  `POST /api/notification-analytics/reports/generate`,
  `POST /api/notification-analytics/reports/schedule`,
  `DELETE /api/notification-analytics/reports/schedule/{schedule_id}`,
  `GET /api/notification-analytics/reports/{report_id}`,
  `GET /api/notification-analytics/reports/{report_id}/download`; v2 coverage:
  none; frontend callers: none found; gate: notification v2 or feature removal.
- `notification_dashboard` — routes:
  `GET /api/notifications/dashboard/alerts/config`,
  `PUT /api/notifications/dashboard/alerts/config`,
  `GET /api/notifications/dashboard/channels/health`,
  `GET /api/notifications/dashboard/export/metrics`,
  `GET /api/notifications/dashboard/health`,
  `GET /api/notifications/dashboard/metrics`,
  `GET /api/notifications/dashboard/queue-stats`,
  `GET /api/notifications/dashboard/rate-limiting`,
  `POST /api/notifications/dashboard/test`; v2 coverage: none; frontend
  callers: none found; gate: notification v2 or feature removal.
- `pattern_analysis` — routes:
  `GET /api/pattern-analysis/bit-analysis/{arbitration_id}`,
  `GET /api/pattern-analysis/correlations/{arbitration_id}`,
  `GET /api/pattern-analysis/export/provisional-dbc`,
  `GET /api/pattern-analysis/message-hex/{arbitration_id_hex}`,
  `GET /api/pattern-analysis/message/{arbitration_id}`,
  `GET /api/pattern-analysis/messages`, `POST /api/pattern-analysis/reset`,
  `GET /api/pattern-analysis/summary`; v2 coverage: none; frontend callers:
  none found; gate: analyzer/tools v2 decision.
- `performance_analytics` — routes:
  `GET /api/performance/api-performance-computed`,
  `GET /api/performance/baseline-deviations`,
  `GET /api/performance/health-computed`, `GET /api/performance/metrics`,
  `GET /api/performance/optimization-recommendations`,
  `GET /api/performance/protocol-throughput`, `POST /api/performance/report`,
  `DELETE /api/performance/reset-baselines`,
  `GET /api/performance/resource-utilization`,
  `GET /api/performance/resources-computed`, `GET /api/performance/statistics`,
  `GET /api/performance/status`, `POST /api/performance/telemetry/api`,
  `POST /api/performance/telemetry/can-interface`,
  `POST /api/performance/telemetry/protocol`,
  `POST /api/performance/telemetry/websocket`, `GET /api/performance/trends`;
  v2 coverage: none; frontend callers: `frontend/src/api/endpoints.ts`; gate:
  performance v2 design.
- `pin_auth` — routes: `POST /api/pin-auth/admin/rotate-pins`,
  `GET /api/pin-auth/admin/system-status`,
  `POST /api/pin-auth/admin/unlock-user/{user_id}`,
  `GET /api/pin-auth/admin/user-status/{user_id}`,
  `POST /api/pin-auth/authorize`, `GET /api/pin-auth/pins`,
  `GET /api/pin-auth/security-status`, `DELETE /api/pin-auth/sessions`,
  `DELETE /api/pin-auth/sessions/{session_id}`, `GET /api/pin-auth/status`,
  `POST /api/pin-auth/validate`; v2 coverage: none; frontend callers:
  `frontend/src/api/pin-auth.ts`; gate: PIN/security v2 decision.
- `predictive_maintenance` — routes:
  `GET /api/predictive-maintenance/maintenance/history`; v2 coverage: none;
  frontend callers: `frontend/src/hooks/usePredictiveMaintenance.ts`; gate:
  maintenance v2 or feature consolidation.
- `safety` — routes: `GET /api/safety/audit-log`,
  `POST /api/safety/emergency-stop`, `POST /api/safety/emergency-stop/reset`,
  `GET /api/safety/health`, `GET /api/safety/interlocks`,
  `POST /api/safety/interlocks/check`,
  `POST /api/safety/interlocks/clear-override`,
  `GET /api/safety/interlocks/overrides`, `GET /api/safety/operational-mode`,
  `POST /api/safety/pin/diagnostic-mode/enter`,
  `POST /api/safety/pin/diagnostic-mode/exit`,
  `POST /api/safety/pin/emergency-stop`,
  `POST /api/safety/pin/emergency-stop/reset`,
  `POST /api/safety/pin/interlocks/override`,
  `POST /api/safety/pin/maintenance-mode/enter`,
  `POST /api/safety/pin/maintenance-mode/exit`, `GET /api/safety/status`,
  `POST /api/safety/update-state`; v2 coverage: partial through entities
  emergency-stop/safety-status only; frontend callers: none found; gate: typed
  safety v2 design, especially PIN/interlock contracts.
- `schemas` — routes: `GET /api/schemas/`, `GET /api/schemas/docs/openapi`,
  `GET /api/schemas/list`, `GET /api/schemas/validate/integrity`,
  `GET /api/schemas/{schema_name}`; v2 coverage: partial through per-domain
  `/schemas`; frontend callers: none found; gate: decide whether global schema
  discovery survives or folds into OpenAPI generation.
- `security_config` — routes: `GET /api/security/config/`,
  `PUT /api/security/config/`, `GET /api/security/config/caddy/rate-limits`,
  `POST /api/security/config/mode`,
  `GET /api/security/config/policies/authentication`,
  `GET /api/security/config/policies/pin`,
  `GET /api/security/config/policies/rate-limiting`,
  `POST /api/security/config/policies/{policy_type}`,
  `POST /api/security/config/reload`, `GET /api/security/config/summary`,
  `GET /api/security/config/validate`; v2 coverage: none; frontend callers:
  `frontend/src/api/endpoints.ts`; gate: security admin v2 design.
- `security_dashboard` — routes: `GET /api/security/dashboard/data`,
  `GET /api/security/dashboard/events/recent`,
  `GET /api/security/dashboard/health`, `GET /api/security/dashboard/stats`,
  `POST /api/security/dashboard/test/event`,
  `GET /api/security/dashboard/websocket/info`; v2 coverage: none; frontend
  callers: `frontend/src/api/endpoints.ts`; gate: security dashboard v2 design.
- `security_monitoring` — routes: `POST /api/security/acl/policy`,
  `POST /api/security/acl/source`,
  `DELETE /api/security/acl/source/{source_address}`,
  `GET /api/security/acl/sources`, `GET /api/security/alerts`,
  `GET /api/security/alerts/summary`, `GET /api/security/rate-limiting`,
  `POST /api/security/reset`, `GET /api/security/status`,
  `GET /api/security/storm-status`, `GET /api/security/test/simulate-attack`;
  v2 coverage: none; frontend callers: none found; gate: security monitoring
  v2 design or admin-only retirement.
- `startup_monitoring` — routes: `GET /api/startup/baseline-comparison`,
  `GET /api/startup/health`, `GET /api/startup/metrics`,
  `GET /api/startup/report`, `GET /api/startup/services`; v2 coverage: none;
  frontend callers: none found; gate: compare with `/api/v2/system` and
  deployment health probes before changing.

**Unmounted router files.** `notification_health.py`, `performance_metrics.py`,
`persistence.py`, and `protocols.py` exist under `backend/api/routers/` but do
not appear in `router_config.py` or the app route table. They are candidates for
a separate dead-file cleanup after import/test reference checks.

**Files.** IMPLEMENTATION_PLAN.md

### HOF-011 — Rolling CAN Network Telemetry Sampler
- [shipped] same commit as this entry · 2026-06-26
- [component] backend
- [adr] docs/adr/ADR-0002-can-facade-pattern.md

**What changed.** A registry-managed `CANNetworkTelemetryService` now samples
the HOF-002 cumulative CAN interface counters over time and derives nullable
rolling `message_rate`, approximate `bus_load_percent`, and `last_activity`
values. The sampler uses `startup()` / `shutdown()` hooks that the
`ServiceRegistry` actually invokes, depends on `can_interface_service`, and is
exposed through typed DI. `/api/v2/networks` merges the sampler's rolling state
into `NetworkStatus`, and OpenAPI artifacts were regenerated.

**Why.** HOF-011 completes the networks telemetry story that HOF-002
deliberately deferred: derived-over-time values are now stateful and nullable
rather than fabricated from one cumulative snapshot. Bus load is documented as
approximate and uses the Pi-calibrated classic-CAN estimate
`(delta_bytes * 8 + delta_frames * 96) / (bitrate * delta_seconds) * 100`.
Cold start, non-Linux/empty provider, unknown bitrate, missing counters, and
counter resets serialize `null`; no real TX queue depth field is introduced.

**Files.** backend/api/domains/networks.py, backend/core/dependencies.py,
backend/core/registrations/phase4.py,
backend/services/can_network_telemetry_service.py, docs/api/openapi.json,
docs/api/openapi.yaml, tests/api/test_networks_domain.py,
tests/services/test_can_network_telemetry_service.py

### HOF-002 — Networks v2 Real Per-Interface CAN Telemetry
- [shipped] same commit as this entry · 2026-06-26
- [component] backend
- [adr] docs/adr/ADR-0002-can-facade-pattern.md

**What changed.** `CANInterfaceService` now provides the facade-backed
SocketCAN telemetry methods for discovered Linux CAN interfaces, using
`pyroute2` when available and degrading to empty data on unsupported platforms.
The provider exposes cumulative RX/TX packets, bytes, errors, dropped counters,
CAN state/bitrate, and best-effort nullable controller xstats. `CANFacade` now
summarizes real RX/TX packet and error counters instead of obsolete
`message_count` / `error_count` aliases, and `/api/v2/networks` surfaces the
real per-interface telemetry plus bus statistics. OpenAPI artifacts were
regenerated.

**Why.** HOF-002 graduates the RECON-001 hardware truth table into the v2
networks API without fabricating telemetry: rolling rates, `last_activity`, and
real TX queue depth remain deferred because they require a stateful sampler or
are not exposed by the current stack. Controller counters are best-effort only;
raw `pyroute2` xstats blobs are left nullable rather than parsed or invented.
Legacy `backend/api/routers/can.py` remains untouched to keep the blast radius
on v2 networks and the facade provider.

**Files.** backend/api/domains/networks.py, backend/models/can.py,
backend/services/can_facade.py, backend/services/can_interface_service.py,
docs/api/openapi.json, docs/api/openapi.yaml,
tests/api/test_networks_domain.py, tests/services/test_can_facade.py,
tests/services/test_can_interface_service.py

### HOF-006 — Bump GitHub Actions To Node24 Runtimes
- [shipped] same commit as this entry · 2026-06-26
- [component] both

**What changed.** GitHub workflow actions that were still on Node20-based
majors were bumped to current Node24-based majors: `actions/checkout` to v7,
`cachix/cachix-action` to v17, `actions/setup-python` to v6, and
`googleapis/release-please-action` to v5.

**Why.** HOF-006 clears GitHub Actions Node20 deprecation warnings at the
workflow layer only. The Release Please action bump is runtime-only; diagnosing
any remaining Release Please functional failure is explicitly deferred to
HOF-010.

**Files.** .github/workflows/nix-ci.yml, .github/workflows/release-please.yml,
.github/workflows/test-docs.yml

### HOF-009 — Canonical Database Management DI Providers
- [shipped] same commit as this entry · 2026-06-26
- [component] backend
- [adr] docs/adr/ADR-0006-typed-dependency-injection.md

**What changed.** `backend/api/routers/database_management.py` now imports the
canonical typed `get_database_update_service` and
`get_migration_safety_validator` providers from `backend.core.dependencies`
instead of minting local `create_service_dependency(...)` shadows. The router's
existing concrete service annotations remain unchanged.

**Why.** HOF-009 removes the last local duplicate providers that shadowed the
central typed DI layer closed by HOF-004. The registry keys and runtime behavior
are unchanged, but `dependencies.py` is now the single source of truth for these
database-management providers.

**Files.** backend/api/routers/database_management.py

### HOF-005 — Remove Residual Frontend App Directory
- [shipped] same commit as this entry · 2026-06-26
- [component] frontend

**What changed.** The last file under `frontend/src/app/` was moved to the
pages idiom: `frontend/src/app/dashboard/data.json` became
`frontend/src/pages/demo-dashboard-data.json`, and `demo-dashboard.tsx` now
imports it from the colocated page directory. The now-empty `frontend/src/app/`
directory was removed while preserving the `/demo-dashboard` route and sidebar
link.

**Why.** HOF-005 / A12 confirmed this Vite SPA already uses React Router with a
`pages/` structure; the leftover `app/` tree was App-Router residue with one
live data artifact. Moving the artifact beside its only consumer consolidates
the frontend to a single pages-based idiom without deleting the demo dashboard.

**Files.** frontend/src/pages/demo-dashboard.tsx,
frontend/src/pages/demo-dashboard-data.json

### HOF-004 — Close Typed Dependency Injection Layer
- [shipped] same commit as this entry · 2026-06-26
- [component] backend
- [adr] docs/adr/ADR-0006-typed-dependency-injection.md

**What changed.** The final non-cycle `Any` providers in
`backend/core/dependencies.py` now expose concrete classes:
`get_database_update_service()` returns `DatabaseUpdateService`,
`get_migration_safety_validator()` returns `MigrationSafetyValidator`, and their
public `Annotated[...]` aliases use those concrete types.

**Why.** This closes the A7.x typed-DI layer under ADR-0006. After this pass,
the only intentionally untyped providers/aliases left in `dependencies.py` are
`get_websocket_manager` / `WebSocketManager` and `get_entity_service` /
`EntityService`, which remain `Any` because of the known EntityService ↔
WebSocket import cycle documented in `PROJECT_CONTEXT.md`.

**Files.** backend/core/dependencies.py

### HOF-003 — Typed Auth/Security Dependency Aliases
- [shipped] same commit as this entry · 2026-06-26
- [component] backend
- [adr] docs/adr/ADR-0006-typed-dependency-injection.md

**What changed.** The auth/security dependency providers and public aliases in
`backend/core/dependencies.py` now expose concrete classes instead of `Any`:
`AuthManager`, `PINManager`, `SecurityAuditService`, `SecurityConfigService`,
and `SecurityEventManager`. The in-file `get_authenticated_user` dependency edge
now also receives a concrete `AuthManager`, and the defensive auth-manager
fallback raises rather than returning an `AuthService` through an
`AuthManager`-typed provider.

**Why.** ADR-0006 requires FastAPI DI aliases to reflect the real service
classes so pyright and IDEs can catch misuse at the call site. HOF-003 keeps the
change scoped to `dependencies.py`, avoids the known `EntityService` /
WebSocket cycle, and leaves consumer call-site cleanup for separate work.

**Files.** backend/core/dependencies.py

### HOF-007 — Explicit Greenlet Dependency For Async SQLAlchemy
- [shipped] same commit as this entry · 2026-06-26
- [component] backend

**What changed.** `greenlet` is now an explicit main Poetry dependency and is
mirrored into the Nix Python dependency sets used by the package, default dev
shell, and CI shell. The Poetry lock was regenerated so `greenlet 3.2.3`
installs on macOS `arm64` instead of being skipped by the transitive lock marker
from `sqlalchemy[asyncio]`.

**Why.** HOF-007 review traced the two WebSocket `database_manager` startup
errors to SQLAlchemy async SQLite requiring `greenlet` during real FastAPI
lifespan startup. The active dev `.venv` was missing `greenlet` on macOS
`arm64`, while the Pi `aarch64` marker path was unaffected. The fix stays at the
dependency/environment layer: no WebSocket skips, no xfails, and no database
startup try/except masking.

**Files.** pyproject.toml, poetry.lock, flake.nix

### HOF-001 — Truthful v2 Networks Data
- [shipped] same commit as this entry · 2026-06-26
- [component] backend
- [adr] docs/adr/ADR-0002-can-facade-pattern.md

**What changed.** The `/api/v2/networks` domain router stopped returning
hardcoded mock `can0` / `virtual0` data. `/interfaces` now reports configured
logical-to-physical CAN mappings via `CANFacade.get_interface_mappings()`,
`/status` reports configured interface count, service-level CAN health, and
facade-reported queue status, `/statistics` returns only
`CANFacade.get_queue_status()`, `/schemas` lists `/statistics`, and `/health`
uses a live UTC timestamp.

**Why.** HOF-001 review found the original bus-statistics path would hit
unimplemented provider methods (`get_interface_stats` / `get_interface_details`)
and fail at runtime. The shipped scope keeps v2 networks on truthful, currently
implemented sources only, preserves ADR-0002 by routing interface mappings
through the CAN facade, and leaves real per-interface / TX-queue telemetry for
HOF-002 recon.

**Files.** backend/api/domains/networks.py, backend/services/can_facade.py,
tests/api/test_networks_domain.py

<!--
Template for a graduated entry:

### HOF-001 — <title>
- [shipped] <commit-sha> · <YYYY-MM-DD>
- [component] backend | frontend | both
- [adr] docs/adr/ADR-000N-*.md   (if it touched a load-bearing decision)

**What changed.** One paragraph: the concrete change that landed.

**Why.** One paragraph: the decision/constraint behind it, pointing at the ADR
or the archived HOF discussion.

**Files.** backend/..., frontend/...
-->
