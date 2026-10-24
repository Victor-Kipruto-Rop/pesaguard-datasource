# PesaGuard Datasource: Premium & Production Readiness Roadmap

## Execution rules
- Execute one phase at a time in the order below. A phase is not complete until its acceptance criteria are verified with evidence.
- Start every phase by inspecting the current branch, existing implementations, tests, migrations, workflows, and open pull requests. Do not duplicate features already implemented.
- Preserve the existing FastAPI/SQLAlchemy/PostgreSQL architecture, PesaGuard identity boundaries, frontend behavior, and deployment contracts unless a reviewed change requires otherwise.
- Never invent integrations, credentials, verification results, data, job progress, test outcomes, or production state.
- Never expose, copy into the frontend, or log secrets, access tokens, financial records, or sensitive personal data.
- Do not run destructive migrations, mutate production data, rotate production secrets, change production settings, merge, or deploy without explicit authorized approval.
- Every behavior change must include regression tests. Do not suppress CI failures or use `continue-on-error` to make checks appear green.
- Keep implementation changes reviewable. Record what changed, exact validation commands and results, known blockers, and rollback considerations.
- External-provider capabilities remain unavailable until contracts, credentials, permissions, and sandbox tests are actually confirmed.
- Do not mark a checkbox complete from code inspection alone if runtime evidence is required.

## Phase 0 — Baseline audit and execution plan
- [ ] Map all frontend routes, components, CSS imports, and user-visible actions.
- [ ] Map backend routers, endpoint contracts, database models, Alembic migrations, workers, queue/storage dependencies, and external provider adapters.
- [ ] Inspect open PRs and branches to avoid duplicate/conflicting work.
- [ ] Run or obtain actionable logs for backend tests, lint, frontend tests/build, PostgreSQL tests, dependency audits, and Docker/Compose validation.
- [ ] Classify each requirement as verified, partially implemented, missing, blocked by external access, or requiring production operator action.
- [ ] Record baseline commit, commands, results, and known failures.

Exit gate: evidence-based gap report exists; no claim of green CI without a successful run.

## Phase 1 — Frontend foundation and premium UX
- [ ] Audit every route for working actions, real API wiring, and accurate status language.
- [ ] Apply the shared dark emerald glass design system consistently, using official PesaGuard logo and favicon.
- [ ] Standardize navigation, typography, spacing, icons, forms, tables, dialogs, notifications, empty/loading/error/success states.
- [ ] Verify mobile/tablet/desktop behavior, keyboard navigation, focus, contrast, reduced motion, and WCAG 2.2 AA targets.
- [ ] Remove dead controls, duplicate CSS, contradictory themes, and fabricated/demo state presented as live data.
- [ ] Add or update component, accessibility, and responsive regression tests.

Exit gate: frontend tests and production build pass; critical routes have evidence-backed visual and interaction checks.

## Phase 2 — Identity, security, and tenant isolation
- [ ] Verify the real PesaGuard identity-provider token contract, issuer/audience, claims, expiry, key rotation, and revocation behavior.
- [ ] Keep production API-key issuance fail-closed until organization verification is obtained from an authoritative backend source.
- [ ] Test authentication, authorization, IDOR, cross-tenant reads/writes, role escalation, key lifecycle, and sandbox/production separation.
- [ ] Enforce scope, expiry, rate limits, request-size limits, CSRF where applicable, and secure cookie/session settings.
- [ ] Protect user-configurable connections against SSRF, private/internal destinations, unsafe redirects, and DNS rebinding risks.
- [ ] Redact secrets and sensitive data from logs, traces, errors, and audit payloads.
- [ ] Design PostgreSQL RLS with the required privileged credential-hash lookup path; verify runtime role grants before enabling policies.
- [ ] Add dependency, secret, container, and static security scanning.

Exit gate: critical security tests pass and any remaining limitation is explicit; no production authorization relies only on frontend flags.

## Phase 3 — Datasource and ingestion correctness
- [ ] Verify create/read/update/disable/archive/delete and connection-test flows against actual persisted backend state.
- [ ] Use connector-specific schemas and truthful capability states; distinguish unavailable, planned, configured, healthy, and degraded.
- [ ] Ensure durable queue/job state, bounded retries with jitter, idempotency, deduplication, checkpoints, cancellation, and safe replay.
- [ ] Add dead-letter inspection/redrive with tenant authorization and restricted diagnostics.
- [ ] Add schema validation, malformed-record quarantine, incremental ingestion, data lineage, and source-level control totals.
- [ ] Test partial batch failure, worker restart, duplicate submissions, provider timeout, stale jobs, and queue outage.
- [ ] Add job-level and tenant-level concurrency, quota, and resource limits.

Exit gate: end-to-end local or sandbox flow proves source configuration -> ingestion -> persisted job/result -> truthful UI, with recovery tests.

## Phase 4 — Reliability, observability, and performance
- [ ] Verify liveness/readiness and safe dependency health for database, queue/cache, workers, object storage, and configured providers.
- [ ] Emit structured logs with request/correlation/job IDs and redact sensitive fields.
- [ ] Measure HTTP latency, DB latency, queue wait/depth, ingestion throughput, retries, dead letters, and connector errors.
- [ ] Add actionable alerts, runbooks, incident levels, external uptime checks, and truthful status reporting.
- [ ] Load, stress, spike, and soak test representative workloads; set p50/p95/p99 and throughput targets from measured requirements.
- [ ] Verify worker recovery, graceful shutdown, resource limits, database pool behavior, and tenant fairness.
- [ ] Define and test backup/restore, RTO, RPO, and migration rollback/recovery.

Exit gate: measurements and recovery evidence exist; do not claim SLA or capacity without test results.

## Phase 5 — Developer and enterprise capabilities
- [ ] Publish versioned API contracts, stable errors, pagination rules, rate-limit behavior, idempotency, and request IDs.
- [ ] Add webhook signing, replay protection, delivery attempts, retries, and controlled replay if supported by actual endpoints.
- [ ] Add scoped key management, expiry, usage metadata, and auditable administrative operations.
- [ ] Complete organization/membership/role workflows only where backed by the existing authoritative identity and organization model.
- [ ] Add data-quality trends, freshness/schema-drift signals, alert rules, exports, and operational reporting.
- [ ] Add AI-assisted explanations or mapping suggestions only as optional, explainable, human-approved features.
- [ ] Add connector integrations only after provider access, terms, permissions, and sandbox behavior are verified.

Exit gate: each capability has API contracts, permission checks, tests, docs, and accurate availability status.

## Phase 6 — Deployment and supply-chain hardening
- [ ] Use reproducible Docker builds, least-privilege non-root runtime, pinned dependencies, and maintained base images.
- [ ] Validate environment configuration at startup without printing secret values.
- [ ] Separate development/staging/production and document configuration ownership.
- [ ] Require tests, lint, migration checks, dependency/secret scans, frontend build, and container builds in CI.
- [ ] Test migrations on a clean database and a representative upgrade fixture before any production rollout.
- [ ] Add deployment smoke tests, rollback instructions, artifact provenance, and controlled release approvals.
- [ ] Verify TLS, DNS, CORS, security headers, cookie flags, storage permissions, and external health checks.

Exit gate: CI passes on the intended commit and a staging deployment has been smoke-tested.

## Phase 7 — Final production acceptance
- [ ] Execute full end-to-end, security, accessibility, load, failure-recovery, backup/restore, and rollback suites.
- [ ] Review all critical/high findings and record accepted residual risks with owners and dates.
- [ ] Verify provider contracts/credentials, database grants, alerts, backups, support contacts, and operational ownership.
- [ ] Publish accurate docs, retention/privacy notices, incident communication, and service limitations.
- [ ] Record release approval and tested rollback path.

Exit gate: all mandatory release gates have evidence and an authorized operator approves production deployment.

## Status vocabulary
- **Verified**: observed by a reproducible test or live check with recorded evidence.
- **Implemented, unverified**: code exists but required test/runtime evidence is missing.
- **Blocked**: needs provider access, credentials, platform/runner availability, or authorized operator action.
- **Not implemented**: required behavior is absent.
- **Accepted risk**: explicitly documented, approved, owned, and time-bound.

## Release blockers that cannot be solved by repository edits alone
- GitHub Actions runner/infrastructure availability when jobs fail before starting.
- Provider contracts, credentials, approved permissions, and provider sandbox access.
- Production environment variables, DNS/TLS, database grants, backups, and monitoring configuration.
- Production deployment, data migration, security sign-off, and release approval.
