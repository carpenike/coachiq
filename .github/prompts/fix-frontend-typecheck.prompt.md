# Subagent task: fix `npm run typecheck` failures on `main`

You are working on [carpenike/coachiq](https://github.com/carpenike/coachiq).
The frontend `tsc --noEmit` step is failing on `main`. The
copilot-instructions explicitly mark this as a non-negotiable quality
gate, but it isn't currently CI-blocking, so the failures landed
silently.

## Read first

1. `/memories/repo/coachiq-architecture.md` — what CoachIQ is/isn't.
2. `/memories/repo/audit-2026-05-12.md` — current state, including the
   specific TS errors flagged.

## Known failures (from audit)

```
src/components/admin/DatabaseManagementTab.tsx(735,8):
  TS2375 — `exactOptionalPropertyTypes: true` violation. Component is
  passed `databaseStatus: DatabaseStatus | undefined` and
  `safetyStatus: SafetyStatus | undefined`, but the child's prop type
  is `databaseStatus?: DatabaseStatus` (no explicit `| undefined`).

src/pages/can-sniffer.tsx(421,5):
  TS2322 — `(message: CANMessage) => void` is not assignable to
  `(message: unknown) => void`. Likely a generic param missing
  somewhere upstream of this callback registration.
```

There may be more once the first batch is fixed — run
`cd frontend && npm run typecheck` to see the full list.

## The job

1. Get the full failure list with `cd frontend && npm run typecheck`.
2. For each error:
   - **Prefer narrowing over widening.** Don't add `| undefined` to
     prop types just to make `exactOptionalPropertyTypes` happy —
     instead, narrow at the parent (early return if undefined, or
     pass a default).
   - **Don't use `any`.** Add a proper type or use `unknown` + a
     type guard.
   - **Don't disable the rule.** No `// @ts-expect-error` or
     `// @ts-ignore` without a linked issue.
3. After fixing, run:
   ```bash
   cd frontend
   npm run typecheck   # must exit 0
   npm run lint        # baseline must not regress (currently 649/1496)
   npm run build       # must succeed
   ```
4. **Add CI enforcement.** Update `scripts/ci-quality-gate.sh` (or the
   appropriate CI step) to fail the build if `npm run typecheck` exits
   non-zero. This is the core fix — without enforcement the gate will
   re-break next week.

## Acceptance

- [ ] `npm run typecheck` exits 0 on the resulting branch.
- [ ] CI step added that fails on typecheck regression.
- [ ] No new `// @ts-ignore` / `// @ts-expect-error` / `: any`.
- [ ] `npm run lint` and `npm run build` both succeed.

## Out of scope

- Don't try to fix the 649 ESLint errors in this PR — separate effort.
- Don't refactor the components beyond what's needed for the type fix.
