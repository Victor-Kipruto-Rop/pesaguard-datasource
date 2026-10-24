# Phase 0 Baseline Audit — Initial Evidence Snapshot

**Audit date:** 2026-10-24  
**Audit branch:** `feat/datasource-premium-production-phases`  
**Starting commit:** `a41f1779175a2f4e16c78b7935fa4d685ec321ac`  
**Scope:** Repository/API evidence only. No production environment or live database was accessed.

## Executive summary

The repository already contains a substantial FastAPI/SQLAlchemy/PostgreSQL datasource platform, a React/Vite frontend, ingestion workers, API-key management, operator sessions, metrics, health endpoints, Docker builds and CI workflow definitions. It also has prior merged hardening work and several open or draft pull requests. The correct next step is not a rewrite; it is to consolidate overlapping changes, verify runtime behavior, and close evidence-backed gaps.

This snapshot is **not** a full route-by-route source-code audit and does not certify production readiness. Code presence is not proof that a workflow works at runtime.

## Repository areas observed

- Frontend: `frontend/package.json`, `frontend/src/main.jsx`, `frontend/src/App.jsx`, `frontend/src/LoginPage.jsx`, `frontend/src/DataSourcesPanel.jsx`, `frontend/src/WorkspaceModulePage.jsx`, `frontend/src/ApiKeysPanel.jsx`, shared and page-specific CSS.
- Backend: `backend/src/main.py`, `backend/src/api_keys.py`, `backend/src/preflight.py`, API/admin modules, models, tests, Alembic configuration and migrations.
- CI: `.github/workflows/ci.yml` contains backend, PostgreSQL, frontend and local Compose jobs.
- Existing docs: `docs/production-hardening-roadmap.md`, `docs/audit-remediation.md`, API-key documentation and provider/integration guidance.
- Recent work: PR #47 is a draft security/UI feature PR; PRs #44, #45 and #38 are also open in the observed recent PR listing. Their scopes may overlap. Reconcile these before combining or duplicating code.

## Findings and status

| Area | Initial status | Evidence / next action |
|---|---|---|
| Glassmorphism and branding | Implemented, unverified | Shared `glass-theme.css`, logo/favicon, and sign-in/sidebar branding exist on the PR #47 head. Must test each route visually and check broad CSS selector side effects. |
| Frontend tests/build | Blocked/unverified | Workflow defines npm tests/build, but the latest observed CI run failed before steps started. No successful build/browser test was available in this audit. |
| Backend test/lint | Blocked/unverified | Workflow defines compile, Ruff, imports, migration smoke test and pytest. No successful run was available to establish pass status. |
| PostgreSQL coverage | Implemented in CI config, unverified | Dedicated PostgreSQL service job exists. Actual green run and runtime role grants are not verified. |
| API-key token verification | Implemented, incomplete trust lifecycle | API-key module validates local JWT claims/key IDs. Identity introspection and persisted revocation checking are not implemented/verified. |
| Production API-key eligibility | Intentionally blocked | PR #47 states the current identity issuer does not provide an authoritative `organization_verified` claim. Do not enable production key creation based on a UI flag. |
| Tenant isolation | Partially implemented | API-key/audit queries use application-level partition predicates. Global PostgreSQL RLS is not established for all workspace tables. Verify every endpoint and worker. |
| PostgreSQL runtime role | Check implemented, environment unverified | `backend/src/preflight.py` checks elevated role flags; it has not been run against the deployed production DB. |
| Datasource and ingestion workflows | Implemented in parts, end-to-end unverified | UI/API/worker code exists. Must prove a real local or approved sandbox flow, persistence, retries, idempotency and recovery. |
| Observability | Partially implemented | Main app defines structured logs, request IDs, Prometheus metrics, HTTP/DB latency, health and readiness endpoints. Verify labels, privacy, dependency coverage, alert delivery and metric access. |
| CI workflow | Defined, infrastructure failure observed | Latest known run failed before any step started with runner ID 0 and zero steps. Treat as runner/platform blocker until a run produces actionable job logs; do not claim code passed or failed based on a job that never started. |
| Production deploy, DB, providers | Blocked pending operator evidence | No production DB grants, provider contracts/credentials, live DNS/TLS, backups, monitoring configuration, or deployment state were verified here. |

## Priority gaps

### P0 — Required before production
1. Get actionable CI execution; distinguish runner availability from actual code failures.
2. Run backend/frontend/PostgreSQL/Compose checks on the exact candidate commit.
3. Verify authoritative identity claim and revocation behavior; keep production key issuance fail-closed until authoritative verification exists.
4. Test cross-tenant isolation across all endpoints, background workers, files, audit events and API keys.
5. Verify production database role/grants and design RLS only with a correct credential lookup path.
6. Prove an end-to-end datasource -> ingestion job -> persisted result -> frontend workflow using local or approved sandbox data.
7. Test backup restoration, migrations, rollback, secrets handling and security boundaries before release.

### P1 — Quality and reliability
1. Review glass theme selector scope, contrast, keyboard/focus behavior, reduced motion and mobile overflow on every route.
2. Add/verify failure recovery, idempotency, dead-letter, retry and worker-restart tests.
3. Verify metrics, logs, tracing, alerts, dependency readiness and sensitive-data redaction.
4. Consolidate open PR scopes before merging; avoid conflicting changes to the same backend, CSS or workflows.

### P2 — Advanced capabilities
1. Add schema-drift/freshness analytics, webhook management, usage analytics and optional AI-assisted troubleshooting only after their data contracts are stable.
2. Add connector types only when the provider contract, credentials and sandbox are confirmed.
3. Add load/soak testing and measured capacity targets before stating throughput or SLA claims.

## Validation performed for this snapshot

- Retrieved repository metadata and recent pull request metadata via the connected GitHub integration.
- Read the PR #47 head versions of the frontend package manifest, main frontend entry point, backend main app, API-key module, preflight, CI workflow, and existing production roadmap.
- Did not run tests, build containers, browse the live app, access production secrets, connect to a live database, apply migrations, or deploy.
- Latest observed CI status was a runner/infrastructure failure before any job steps; no successful test result is claimed.

## Next action

Proceed to Phase 1 on the stacked feature branch: review the global glass CSS against all existing component styles, fix demonstrable defects with regression tests, and establish build/test evidence once CI execution is available. Then execute the security phase before expanding new enterprise features.
