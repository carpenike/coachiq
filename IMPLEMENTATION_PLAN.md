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

## Build Log

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
