# ADR-0012: Keep Knowledge and Maintenance as an offline-first bounded context

## Status

**Accepted**, 2026-06-29. Applies before the Phase 1 deterministic-tier work.

## Context

CoachIQ is growing from bus observability and control into coach intelligence:
manual lookups, structured coach facts, maintenance schedules, and future
question-answering over local documents. These capabilities belong on the device
because the reference coach has intermittent connectivity, but they are not part
of the CAN/RV-C control stack.

The approved Knowledge & Maintenance plan requires two offline tiers:
structured facts plus FTS5 that always work without a model, and a best-effort
retrieval/RAG tier over prebuilt vectors. HOF-035 reserved this ADR for the
bounded-context decision and left Phase 0 to prove the vector substrate.

Phase 0 proved `sqlite-vec` on the actual platforms that matter. On the Darwin
dev box, the repo's Nix Python 3.12.13 exposes `enable_load_extension`; the
nixpkgs `sqlite-vec` package loads successfully with `vec_version() = v0.1.6`,
and the Poetry/PyPI wheel locks at v0.1.9 and also loads successfully. On the
deploy target (`nixpi`, aarch64 NixOS), the host-run proof showed Python 3.11.15
with SQLite 3.50.4 and `enable_load_extension OK`. The broader nixpkgs concern
about Python builds without loadable SQLite extension support does not apply to
the interpreters this repo is actually using.

## Decision

Create a new Knowledge & Maintenance bounded context alongside the existing
CAN/RV-C/J1939 domains.

The subsystem owns coach manuals, extracted text, structured facts, maintenance
tasks, maintenance logs, and retrieval metadata. It will expose future HTTP
endpoints under `/api/v1` domain routers and will use normal service/repository
wiring through the ServiceRegistry and FastAPI dependencies. It must not reach
`CANFacade` or lower CAN services directly; live readouts needed for maintenance
come from read-only domain surfaces.

Use `sqlite-vec` as the runtime vector substrate for this bounded context.
Vector data lives in SQLite so it aligns with CoachIQ's existing SQLite data root
and backup story. Index generation can happen at build/provisioning time and may
use cloud embeddings; the device runtime path remains offline and serves the
persisted result.

Phase 0 wires only the substrate seam: `VectorRepository`/`VectorService` can
initialize an empty sqlite-vec store, report real availability, and return empty
search results until ingestion exists. It does not add ingestion, knowledge
endpoints, maintenance endpoints, MCP tools, or SPA views.

## Consequences

### Becomes easier

- Manual search, structured facts, and maintenance data have a clear ownership
  boundary separate from the bus-control stack.
- The vector store shares CoachIQ's SQLite-oriented persistence and backup model.
- Future MCP and local-model consumers can call the same backend domain surface
  the SPA uses instead of becoming the storage foundation.
- The runtime substrate choice is proven before Phase 1 builds feature code on
  top of it.

### Becomes harder

- `sqlite-vec` is a loadable SQLite extension, so runtime packaging must include
  the Python package and must keep using Python/SQLite builds that support
  extension loading.
- The first implementation phases need explicit tests for extension loading and
  empty-store behavior, not only import checks.
- The older FAISS dev-tools pipeline remains historical/provenance code until it
  is either retired or adapted for build-time corpus generation.

### Cannot do anymore

- Treat the knowledge and maintenance work as an extension of the CAN facade or
  RV-C configuration facade.
- Add new knowledge or maintenance endpoints under legacy `/api/*` routes.
- Commit feature code that depends on an unproven vector substrate.
- Require a network or cloud model for deterministic structured-fact lookup.

## Alternatives considered

- **FAISS packaged index artifact**: already works in the current dev tooling and
  was the fallback. Rejected for runtime because `sqlite-vec` is now proven on
  both target platforms and better fits the one-data-root SQLite backup story.
  FAISS remains useful provenance for older RV-C documentation experiments.
- **`pysqlite3-binary` workaround**: considered as a way around Python builds
  without loadable SQLite extension support. Rejected for this repo because the
  actual stdlib SQLite path is green on both platforms, and `pysqlite3-binary`
  was not available for the current macOS arm64/Python 3.12 dev environment.
- **Rebuild/override Python for loadable extensions**: considered as a Nix
  workaround. Rejected because no override is needed for the current Darwin or
  deploy-target interpreters.
- **Keep everything in the existing FAISS spike**: rejected because the spike was
  scoped to RV-C documentation/spec validation, not operator-facing coach manual
  and maintenance workflows.

## Revisit conditions

- A future Nixpkgs update removes loadable SQLite extension support from the
  interpreters used by CoachIQ.
- `sqlite-vec` becomes unavailable or unstable on the Raspberry Pi deployment
  architecture.
- The document corpus grows enough that sqlite-vec query performance no longer
  meets the local device budget.
- A public 1.0 API contract requires formal deprecation policy for knowledge or
  maintenance endpoints.

## See also

- `docs/specs/KNOWLEDGE_MAINTENANCE_PLAN.md`
- `backend/repositories/vector_repository.py`
- `backend/services/knowledge/vector_service.py`
- HOF-035, HOF-038, RECON-005, and RECON-006 in the CoachIQ handoff channel.
- [ADR-0002](ADR-0002-can-facade-pattern.md) -- CAN facade boundary.
- [ADR-0003](ADR-0003-api-v2-only-no-legacy.md) and
  [ADR-0011](ADR-0011-public-api-v1-naming.md) -- `/api/v1` domain routing.
- [ADR-0008](ADR-0008-rvc-config-facade-naming.md) -- config tier separation.
- [ADR-0010](ADR-0010-pre-1.0-no-backward-compat.md) -- decisive pre-1.0 cleanup.
