# CoachIQ Frontend Redesign

**Status:** In progress (2026-07)
**Driver:** UX review of iq.holtel.io found the 25-route frontend dishonest and broken at the core journey (see PR description). Direction from Ryan: rebuild the product surface; CoachIQ is a **replacement for the Vegatouch Mira / Firefly panel**, usable away from the coach and more intuitive than the OEM UI.

## Product frame

The owner surface answers three questions, in order:

1. **Is my coach reachable, and is what I'm seeing current?** (connectivity/staleness — never lie)
2. **What state is each zone of the coach in?** (zone-based display: real devices rendered inside the areas they live in)
3. **Can I change it right now?** (controls that work, give feedback, and explain themselves when they can't)

Everything else (CAN tooling, mapping, spec search) is a technician surface, present but subordinate.

## Information architecture

### Owner section (sidebar, top)
| Nav label (== page title) | Route | Content |
|---|---|---|
| Home | `/` | Connectivity hero, zone grid (devices grouped by coach area from coach config), scenes, active alerts |
| Lights | `/lights` | Zone-grouped light controls, per-zone all on/off, brightness where dimmable |
| Devices | `/devices` | All entities table/cards, filter by type/area/protocol (replaces "Multi-Protocol Entities") |
| Diagnostics | `/diagnostics` | DTCs (real v2 data), per-system health — the ONLY fault-code page |
| System | `/system` | App/service status + CAN interface telemetry + performance, tabbed (replaces System Status, Health Dashboard, Performance Analytics, Analytics Dashboard) |

### Technician section (sidebar, "Advanced", collapsed by default)
| Nav label | Route | Notes |
|---|---|---|
| CAN Sniffer | `/advanced/can-sniffer` | Explicit "waiting for CAN traffic / disconnected" states instead of skeleton-forever |
| CAN Tools | `/advanced/can-tools` | Kept as-is, fix truncated Safety Level control |
| Network Map | `/advanced/network-map` | Fix epoch "Last Seen" bug |
| Unknown PGNs | `/advanced/unknown-pgns` | Honest empty states ("No CAN traffic observed" ≠ "everything recognized") |
| Unmapped Entries | `/advanced/unmapped-entries` | same |
| Device Mapping | `/advanced/device-mapping` | now reachable; area truthfulness fixed |
| RV-C Spec | `/advanced/rvc-spec` | unchanged |

### Account/system (sidebar footer + user menu)
- Settings `/settings` (app prefs + profile + security, merged; delete empty stubs)
- Admin `/admin` (admin-only; remove "Coming Soon" button until real)
- Login `/login`, OIDC callback (kept)

### Deleted outright
`/health` (page renamed into `/system`; URL conflicts with backend health endpoint), `/performance`, `/analytics-dashboard`, `/security` (security events fold into System if endpoint is real; else cut), `/maintenance` (stub), `/documentation` (broken search; RV-C spec page covers reference needs), `/system-status`, dashboard's fake activity feed, NavDocuments dead links, GitHub header link, Vite favicon.

## Connectivity model (the honesty layer)

Single derived state, computed in one provider (`CoachConnectionProvider`) and consumed everywhere:

```
websocket: connected | connecting | down        (WS lifecycle)
canbus:    active | silent                      (any CAN rx in last N sec, from real telemetry)
entities:  fresh | stale (max last-updated age)
──────────────────────────────────────────────
coach:     LIVE      (ws connected, can active)
           STALE     (ws connected, can silent — showing last known state from HH:MM)
           OFFLINE   (ws down — app cannot see the coach)
```

Rules:
- STALE/OFFLINE ⇒ persistent banner with the timestamp of last real data; every device card shows its own last-updated time.
- Controls in STALE/OFFLINE are disabled with a tooltip/inline reason — never a dead button that silently fails.
- No page may render a "healthy/all good" verdict from a component other than this provider. Green requires LIVE + no active DTCs.
- Every command mutation gets toast feedback: optimistic pending → confirmed on state echo, error toast with cause on failure (incl. 4xx text).

## Zone model

Source of truth: coach mapping config (`config/2021_Entegra_Aspire_44R.yml`) — `areas:` hierarchy (interior/exterior, zones with display names) and per-entity `area:` assignments; scenes from `lighting_scenes`, groups from `lighting_groups`. Backend must expose these (entity.area today returns "Unknown" — bug to fix). Frontend fallback: derive zone from entity_id prefix when area is missing, flag derived zones in Device Mapping as needing config.

Home zone grid: one card per zone that has entities; card shows zone name, device count + summary state (e.g. "3 lights on"), expands/links to devices. Exterior zones grouped under an Exterior section. Scenes rendered as buttons (Evening, Security, Travel Prep, All Off) — only if backend exposes scene execution; otherwise omit (no dead buttons).

## Non-negotiable app-shell requirements
- Route-level error boundary + friendly 404 with nav back to Home.
- Layout route (single `AppLayout` with sidebar/header) instead of per-route `AuthGuard` wrapping.
- Nav label, page `<h1>`, and header title come from ONE route registry (no more "Application" fallbacks / triple naming).
- No number rendered without a real source. "—" or explicit "no data" over fabricated 0%/98%.
- Empty states must distinguish "no data because bus is silent" from "genuinely none observed".
- Footer version from build metadata, correct year, real favicon.

## Endpoint bindings

Binding rule: `/api/v1/*` + `/ws*` + auth endpoints only. No `/api/dashboard/*` (legacy, being retired per ADR-0003/HOF-016). No number rendered that the backend doesn't provide.

| UI need | Endpoint | Key fields |
|---|---|---|
| Entity list / zone grid | `GET /api/v1/entities` | entity_id, name, device_type, protocol, state, area, last_updated, available |
| Zones, scenes, groups | `GET /api/v1/entities/config/coach` (new) | areas{interior/exterior→zones→display_name}, lighting_scenes, lighting_groups, coach_info |
| Entity control | `POST /api/v1/entities/{id}/control` | ControlCommandV2 → SafetyOperationResultV2 (status, error_message, execution_time_ms) |
| Bulk control | `POST /api/v1/entities/bulk-control` | BulkControlRequestV2 → per-entity results |
| CAN liveness (banner) | `GET /api/v1/networks/status` | per-interface: last_activity (ISO), message_rate, bus_load_percent, state, error counters |
| DTCs | `GET /api/v1/diagnostics/dtcs` | code, severity, protocol, system_type, description, resolved |
| Health verdict | `GET /api/v1/diagnostics/system-status` | overall_health, health_score, active/degraded systems |
| Service health (System page) | `GET /api/v1/system/services`, `GET /api/v1/system/components/health` | per-service/component status |
| System info | `GET /api/v1/system/info` | hostname, platform, uptime_seconds |
| Unmapped/unknown | `GET /api/v1/entities/debug/unmapped`, `/debug/unknown-pgns` | — |
| Realtime entity state | `WS /ws` | entity update envelope |
| Logs stream | `WS /ws/logs` | log entries |
| CAN sniffer | `WS /ws/can-sniffer` | raw frames |
| Auth | `/api/auth/*` (login/me/refresh/logout/magic-link), `/api/v1/auth/oidc/*` | unchanged |

Known-fake endpoints that must NOT be bound: `/api/v1/system/events` (sample data), predictive-maintenance endpoints (sample repository data), `/ws/security` (closes 1011, unmigrated). Frontend-computed fakes to delete: lights "efficiency %", protocol-health percentages, device trend arrows.

## Mira panel reference (photos, 2026-07-03)

Observations from the physical Vegatouch Mira screens in the coach, as roadmap input:

**Device inventory the coach actually has (G6 outputs screen)** — far beyond the 29
currently-mapped entities. Channel names verbatim: satellite dome, entry door
lock/unlock, generator start/stop, water pump, RR/FR awning ext/ret/stop, bed ceiling
A/B, bed accent/vanity/ovhd, bath ceiling/lav/accent, stool ceiling/accent, entry
ceiling, livrm edge/ceiling/accent A+B/misc A–D, courtesy, dinette, sink, midship,
hutch accent, entry door awning ret/ext, awning D/S+P/S lights, cargo, under-slide,
closet, security D/S+P/S+motion, porch. When the bus is live these will surface in
Unmapped Entries; use these names when assigning them in the coach mapping.

**Climate model (Climate Control screen)** — zones Front/Mid/Rear each with current
temp, setpoint, and mode (Cool / Heat Pump / Aqua-Hot / Auto) + fan High/Low; plus
Bay (Aqua-Hot) and Floor (floor heat) zones and global Aqua-Hot Burner / Electric
toggles. This is the blueprint for a CoachIQ Climate page once thermostat/HVAC DGNs
are mapped — zone cards with setpoint steppers and mode selection, same pattern as
the lighting zone cards.

**Tanks** — Mira's fault list shows fresh/grey/black tank sensors (currently not
reporting on the panel either). TANK_STATUS mapping → Home tank-level card.

**Slides/awnings screen** — EXT/RET momentary pairs per slide (Vanity/Super/Bed/
Kitchen) and awning, alongside a floorplan diagram with each slide color-highlighted.
Slide control stays OUT of CoachIQ scope (ADR-0004: Firefly owns the safety case;
same posture as lock/unlock RECON-002). The floorplan-with-highlighted-zones visual
is worth stealing eventually for Home (SVG 44R floorplan, zones light up by state).

**Misc** — panel runs GUI/Logic 11.6; its Settings screen reports Floorplan "33R"
(coach is a 44R — possibly a panel misconfiguration, worth checking with Entegra).

## Command feedback contract

`useControlEntity` mutation wraps every control POST:
- pending → button spinner state
- HTTP error → destructive toast with backend `detail`/`error_message` (e.g. "Command blocked: guardrail active"), never silent
- success + `status != success` (timeout/safety_abort) → warning toast with reason
- true state confirmation arrives via WS entity update (or refetch fallback when WS down — but controls are disabled when OFFLINE anyway)
