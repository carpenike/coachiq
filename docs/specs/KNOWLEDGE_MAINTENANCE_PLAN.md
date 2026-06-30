# Knowledge & Maintenance Subsystem — Plan (approved umbrella)

**Status:** approved umbrella architecture, reconciled to current HEAD after
HOF-033 and HOF-036 (tracked as HOF-035 in the `coachiq` basic-memory channel)
**Author:** Claude (HQ)
**Date:** 2026-06-28
**Approved:** 2026-06-29
**Component:** both (backend + frontend), plus a new MCP adapter

This is the durable umbrella plan for the bounded-context boundary. ADR-0012 is
reserved for the Knowledge & Maintenance subsystem boundary and lands with the
Phase 0 implementation HOF, where the storage substrate proof is performed.

---

## 1. Motivation & framing

CoachIQ is **coach intelligence, not just bus intelligence**. The reference
install is a **2021 Entegra Aspire 44R** — which is also the dev reference coach,
so this subsystem targets real hardware we already model.

The device is a Raspberry Pi inside the coach with **intermittent connectivity**
(Starlink-dependent). The defining requirement is that an operator can get
answers **on the road, offline**:

- Lookups against manuals and specs — *"how big is my black tank so I don't
  overfill during a flush?"*, fluid capacities, torque values, fuse maps.
- Maintenance tracking — what's due, what was done, condition-based reminders
  driven by live coach data (engine hours, odometer, DTCs).

These are durable, operator-facing capabilities. They are a **different concern**
from real-time bus management, but they belong on the **same device** because the
offline requirement forbids a phone-home design.

## 2. As-built reality (honest accounting)

Treat the existing code as **reference, not constraint** — it was an exploratory
"is this even possible?" spike and may be discarded freely. ADR-0010 (pre-1.0,
no backward-compat) explicitly permits decisive removal.

- **`dev_tools/` FAISS pipeline** (`enhanced_document_processor.py`,
  `document_loader.py`, `query_faiss.py`) — a real PDF chunking + FAISS indexing
  toolchain. Querying defaults to **cloud** OpenAI `text-embedding-3-large`
  embeddings when `OPENAI_API_KEY` exists, with a local HuggingFace
  `all-MiniLM-L6-v2` fallback in `query_faiss.py`. Index generation in
  `enhanced_document_processor.py` is still OpenAI-only and errors when no
  OpenAI API key is configured. PoC quality.
- **Runtime substrate is initialized but empty.** HOF-038 replaced the
  `backend/services/knowledge/vector_service.py` /
  `backend/repositories/vector_repository.py` stub with a sqlite-vec empty store:
  `initialize_index()` creates the SQLite database and `vec0` table,
  `is_available()` reflects the loaded substrate, and `search()` returns `[]`
  until Phase 1 adds ingestion.
- **Original intent was different.** `docs/specs/faiss-integration-plan.md` scoped
  FAISS to *RV-C decoder validation* (DGN/spec checks), not operator
  manual/maintenance lookup. Conversational + offline operation appear there only
  as "future work."
- **A legacy maintenance surface already exists.**
  `backend/api/routers/predictive_maintenance.py` (legacy `/api/predictive-maintenance`)
  plus its service/model provide component health, maintenance log/history, and
  recommendations. Its repository is in-memory/sample-data backed today, so the
  new subsystem should **absorb the useful concepts and migrate durable data** to
  `/api/v1` with real persistence, then retire the legacy router (decisive
  retirement is sanctioned by ADR-0010), rather than run two maintenance surfaces
  in parallel.

**Net position:** local *retrieval infrastructure* exists (FAISS + a viable local
embedder) but is cloud-leaning, stubbed, and built for the wrong use case. There
is **no on-device generative model** anywhere. Retrieval and generation are
separate decisions (see §3.2).

## 3. Architecture decisions

### 3.1 A new bounded context — not folded into the CAN stack

The offline argument puts this *on the device and in the repo*; it does **not**
put it inside the bus domain. This is a new domain subsystem alongside CAN/RVC,
respecting the ADR set:

- **Public API v1 only (ADR-0003 + ADR-0011):** new domain router(s) under
  `backend/api/domains/` (e.g. `knowledge.py`, `maintenance.py`), served through
  `/api/v1`. No new legacy `/api/*` routes; migrate the legacy
  `predictive_maintenance` surface into v1 and delete it.
- **DI discipline (ADR-0001/0006):** services obtained via `Depends(get_x)` from
  `backend/core/dependencies.py`, registered in `backend/core/registrations/` in
  the correct startup stage. No `app.state`, no module singletons.
- **CAN boundary (ADR-0002):** this subsystem must **not** reach `CANFacade` or
  lower CAN modules directly for control. Active DTCs are already readable
  through the existing **diagnostics v1** surface. Engine hours and odometer are
  decoded by the Spartan K2 integration (`operating_hours`, `mileage_counter`),
  but they are **not** currently exposed by diagnostics v1; Phase 1/2 must add a
  read-only live-readout path before condition-based maintenance can depend on
  them.
- **Config separation (ADR-0008):** its own settings live under `Settings`
  (`COACHIQ_` prefix); do not entangle with `RVCConfigFacade` / `RVCSpecLoader`.
- **Quality bar (ADR-0004):** consumer-grade. This is a notes/lookup app — not
  safety-framed. No safety ceremony.
- **Storage:** own SQLAlchemy models + Alembic migration, own repositories under
  `backend/repositories/`, following the repository pattern.

### 3.2 Two-tier access model — the offline contract

Offline "intelligence" splits into two tiers with very different availability:

**Deterministic tier — always works, no internet, no model.** Structured facts
stored as real fields (tank capacities, service intervals, fluid specs, torque
values, fuse map) plus **SQLite FTS5** full-text search over extracted manual
text. *This tier answers the black-tank question with zero cloud and zero model.*
It is the tier that genuinely earns the offline promise and is the highest-value,
lowest-risk thing to build first.

**LLM tier — best-effort.** Conversational Q&A / RAG over the manuals and
structured data. Cloud Claude when connected; an optional small on-device model
when not. Explicitly **degraded** offline — the smartest layer is the least
available one.

### 3.3 Retrieval layer — local-first

- **Embeddings default to local** (MiniLM or a better small model) so semantic
  search works offline. Cloud embeddings are an *ingest-time* option only, never
  a runtime dependency.
- **Vector store:** use **`sqlite-vec`** so vectors, FTS, and the records DB
  share one SQLite substrate on the Pi (one file to back up, one
  `PersistenceService` path). Phase 0 proved stdlib SQLite extension loading on
  macOS arm64 and the aarch64 NixOS deploy target, so sqlite-vec is the locked
  runtime substrate. FAISS remains historical fallback/provenance for the older
  RV-C documentation search spike, not the Knowledge & Maintenance runtime
  substrate.
- **Index generation is build/provisioning time.** Cloud embeddings are allowed
  while producing the shipped corpus/index artifact. The device's runtime path
  is offline: deterministic FTS5, structured facts, and prebuilt-vector query.
  On-device generation for user-added documents is explicitly deferred to a
  later phase if it becomes a requirement.
- **Replace the stub** `VectorService`/`VectorRepository` with a real
  implementation wired through DI — or delete them and start clean.
- **Ingestion pipeline:** PDF → extract → chunk → **capture structured fields** →
  embed → store. Heavy or cloud-assisted processing runs **when connected**; the
  Pi serves the persisted result. This is where the `dev_tools` pipeline can be
  salvaged or rewritten.

### 3.4 Data model (sketch — to be refined in review)

- `documents` — manual metadata (source, title, coach-applicability,
  version/edition).
- `doc_chunks` — chunk text + embedding + provenance (page/section).
- `structured_facts` — `(key, value, unit, category, source_ref)`; the
  deterministic-tier store (e.g. `black_tank_capacity = 50 gal`).
- `maintenance_tasks` — definition + schedule/interval/trigger (calendar, engine
  hours, mileage, condition).
- `maintenance_log` — performed records (date, hours/odo at service, notes,
  cost). Migrate legacy `MaintenanceHistoryModel` content here.
- `parts` / consumables (optional, later).

Condition-based triggers reference live signals pulled read-only from the
diagnostics/live-readout surface. Active DTCs are available today; engine hours
and odometer require the planned read-only exposure described above.

### 3.5 MCP surface — one tool surface, two consumers

An MCP server exposes the subsystem so **both cloud Claude and a local model use
the same tools** (the host's consistency principle). It is a **thin adapter over
`/api/v1` + the retrieval layer — not the foundation.** Data and logic live in
the subsystem; the MCP server is one consumer; the locally-served React SPA is
the offline consumer.

Minimal tool surface:

- `manual_search(query, source?)` — semantic + FTS over manuals.
- `get_fact(key)` / `list_facts(category)` — deterministic-tier lookups.
- `list_maintenance(due_within?)` / `next_due(task?)` — schedule queries.
- `log_service(task, date, notes, hours?, odo?)` — record work.
- `get_live_readout()` — active DTCs via diagnostics v1; engine hours / odo via
  the planned read-only live-readout path.

**Design constraint — local-model tool reliability.** Small on-device models
(3–8B) are markedly worse at multi-step tool orchestration than frontier Claude.
So: keep the tool surface **flat and deterministic**, provide a
**direct-retrieval fast path** the local model can hit in a single call, and do
**not** assume tool-use parity. Treat local-model tool reliability as an explicit
design constraint, not an afterthought.

## 4. Phasing

- **Phase 0 (substrate proof + ADR):** prove and declare `sqlite-vec` packaging
  in Poetry + Nix on Darwin and Linux, land ADR-0012, and inventory the legacy
  `predictive_maintenance` surface for migration.
- **Phase 1 — deterministic tier (highest offline value, no model):** models +
  Alembic migration, `structured_facts` + FTS5, an ingestion CLI, v1 read
  endpoints, a minimal SPA view. The black-tank question works after this phase.
- **Phase 2 — maintenance tracking:** tasks/log CRUD on v1; condition-based
  triggers reading active DTCs plus the new read-only engine-hours/odometer
  exposure; SPA; migrate + retire the legacy `predictive_maintenance` router.
- **Phase 3 — local retrieval:** local embeddings + vector store wired into
  runtime (replacing the stub `VectorService`); RAG retrieval endpoint.
- **Phase 4 — MCP surface:** MCP server over the v1 + retrieval layer; validate
  with cloud Claude first, then a local model against the constrained surface.
- **Phase 5 — local generation (optional):** evaluate a small on-device LLM for
  the offline conversational tier within the Pi's RAM/thermal budget.

## 5. ADR implications

No existing ADR is violated; this extends scope within ADR-0004's consumer-grade
framing and leans on ADR-0010 to discard the PoC and legacy router decisively.
The bounded-context boundary and storage substrate are recorded in
ADR-0012 — Knowledge & Maintenance subsystem boundary.

## 6. Resolved questions

1. **Offline-first contract:** deterministic FTS5, structured facts, and
  prebuilt-vector query are always offline. Index generation is a
  build/provisioning step and may use cloud embeddings; the device ships a
  prebuilt index.
2. **Storage substrate:** `sqlite-vec` is selected because it fits the unified
  SQLite/persistence/backup story from HOF-032 and Phase 0 proved extension
  loading on Darwin and the aarch64 NixOS deploy target.
3. **Legacy `predictive_maintenance`:** absorb useful concepts and API
  affordances into the `/api/v1` maintenance domain with real persistence, then
  retire the legacy in-memory router.
4. **Engine-hours / odometer:** not on diagnostics v1 today. Maintenance starts
  with manual odometer/hours entry; a read-only live-readout sourced from the
  J1939 signals, not direct `CANFacade`, is a prerequisite for service-interval
  automation.
5. **Corpus/licensing/budget:** manual selection, redistribution rights, and
  final embedding budget are phase-local decisions, not umbrella blockers.

## 7. Success criteria (per L-07 — against the real CI gate)

Per-phase implementation hand-offs must cite, against `scripts/ci-quality-gate.sh`:
touched files clean; `pyright backend` at-or-below baseline (ratchet down if
reduced); ESLint diff-clean on touched lines; relevant `pytest -m` markers pass;
OpenAPI re-exported when v1 shapes change; a new Alembic migration where models
change; and the durable plan-doc/ADR entry graduated in the same commit.
