---
mode: "agent"
description: "A12 \u2014 Frontend router idiom consolidation (app/ vs pages/ vs components/)"
---

# A12 \u2014 Frontend router idiom consolidation

Audit cycle: 2026-05-13 architectural audit.

## Why

`frontend/src/` mixes idioms:

- `frontend/src/app/` \u2014 looks like an experimental Next.js-style App
  Router scaffold.
- `frontend/src/pages/` \u2014 classic SPA "pages" directory.
- `frontend/src/components/` \u2014 standalone components.

`/memories/repo/handoff-2026-05-11.md` notes that `frontend/src/root.tsx`
and `frontend/src/dashboard.tsx` were deleted in the 2026-05-11 cleanup
but `frontend/src/app/dashboard/page.tsx` was kept (with `data.json`
used by demo-dashboard). That's the residue \u2014 the App Router
experiment was partly cleaned but not all the way.

This is a Vite SPA (`frontend/vite.config.ts`), not Next.js. The
`app/` idiom doesn't pull its weight here.

## The job

1. **Audit `frontend/src/app/` end-to-end**:
   - List every file. For each, identify the live consumer.
   - Distinguish "demo only" (e.g. `dashboard/data.json`) from
     "production".
2. **Decide one idiom**:
   - **Recommended**: collapse to `pages/` + `components/` + `hooks/`
     + `lib/` + `api/` + `contexts/`. Move anything in `app/` that
     has a real consumer into `pages/` or `components/`.
   - **Alternative**: if `app/` IS the future, finish the migration
     by moving `pages/` into `app/` and deleting `pages/`. (Probably
     not the right call for a Vite SPA, but document if chosen.)
3. **Delete dead files** in `app/` (especially demo-only assets if
   the demo-dashboard isn't used in production).
4. **Update routing config** (likely `frontend/src/main.tsx` or
   wherever the React Router routes are declared) to match.

## Verification

```bash
# After consolidation
ls frontend/src/
# Expect: api components contexts hooks lib pages test types main.tsx global.css vite-env.d.ts

# Routes render
cd frontend && npm run dev
# Manually visit each route and confirm

# Build still works
npm run build && npm run typecheck
```

## Acceptance criteria

- One router idiom (recommended: `pages/`).
- `app/` either gone or fully populated and `pages/` deleted.
- No broken imports.
- Frontend build, typecheck, lint baselines all pass or improve.

## Stop-and-ask if

- A demo-dashboard or sales-demo consumer of `app/dashboard/page.tsx`
  is found. The cleanup should preserve it (move + rename) rather
  than delete.
- The repo actually intends to migrate to Next.js eventually. Then
  this PR is wrong; document and close.

## Risk

Medium. Frontend-only. Test by clicking through every route in dev
mode.

## Coordination with A11

If A11 lands first and changes the API surface, the frontend will
need updates anyway \u2014 fold them into A12.
