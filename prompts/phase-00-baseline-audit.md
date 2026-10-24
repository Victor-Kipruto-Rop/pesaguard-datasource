# Phase 0 — Baseline audit

## Objective
Establish an accurate, reproducible inventory before modifying implementation.

## Tasks
1. Read repository guidance and the production roadmap.
2. Record branch, base commit, open PRs and overlapping branches. Identify the intended implementation branch.
3. Inventory all frontend routes/components/styles, backend routers/endpoints, models, migrations, workers, queue/cache/object storage, provider adapters, environment variables, Docker files, and workflows.
4. Map each user-visible action to its API endpoint and persistence path. Flag dead buttons, preview-only flows, missing endpoints, mock data, and claims that are not backed by runtime state.
5. Inspect CI workflow definitions and the latest run/job/step evidence. Separate runner/infrastructure failures from code failures.
6. Run available safe checks; never access production secrets or mutate production data.
7. Compare inventory with `docs/premium-production-roadmap.md` and record each requirement as verified, implemented-unverified, blocked, or missing.
8. Create a prioritized gap report with P0/P1/P2, affected files, dependency, proposed change, and test evidence needed.

## Acceptance
- No duplicate work is proposed without explaining why existing implementation is insufficient.
- Every major route, endpoint, model/migration, worker, connector and CI job is accounted for.
- Exact commands and actual outcomes are recorded.
- Unknowns and external/operator blockers are explicit.
- No production state is changed.
