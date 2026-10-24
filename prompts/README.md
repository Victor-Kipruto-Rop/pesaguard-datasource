# PesaGuard Datasource execution prompts

Use these prompts in order. Each prompt is a contract for a coding agent; it is not evidence that the work has been completed.

1. `phase-00-baseline-audit.md` — map the actual repository and evidence.
2. `phase-01-frontend-foundation.md` — premium UI and frontend quality.
3. `phase-02-security-isolation.md` — identity, keys, tenant isolation, and SSRF.
4. `phase-03-ingestion-reliability.md` — source lifecycle and durable ingestion.
5. `phase-04-observability-performance.md` — metrics, alerts, load and recovery.
6. `phase-05-enterprise-capabilities.md` — developer and enterprise features.
7. `phase-06-deployment-supply-chain.md` — CI/CD, containers, migrations and release safety.
8. `phase-07-production-acceptance.md` — evidence-based release sign-off.

## Mandatory rules
- Read `AGENTS.md`, `README.md`, `docs/production-hardening-roadmap.md`, and `docs/premium-production-roadmap.md` before changing code.
- Inspect the current branch, open PRs, existing implementations, test files, migrations, and CI. Do not duplicate or conflict with ongoing work.
- Implement only the current phase, except for a tiny prerequisite fix that must be documented.
- Preserve API contracts unless a migration/change is necessary and reviewed.
- No mock results or fabricated progress in live/production surfaces.
- No secrets in source, browser bundles, chat, logs, fixtures, or screenshots.
- Do not change production infrastructure, migrate/alter production data, merge, or deploy without explicit authorization.
- Every bug fix gets a regression test. Never hide failing tests with skips or `continue-on-error`.
- Run the exact applicable commands and report exit codes and output summaries honestly. If the environment or CI runner is unavailable, mark validation blocked, not passed.
- Update the roadmap checklist and a phase report with commit SHA, changed files, tests run, results, risks, and next phase.
- Stop if the task requires credentials, external provider approval, production access, or an architectural decision that cannot be safely inferred. Document the blocker instead of inventing behavior.

## Required final report for every phase
1. Implemented changes and files.
2. Tests/commands executed and actual results.
3. Security/data migration impact.
4. Unverified items and blockers.
5. Acceptance criteria checked with evidence.
6. Commit/PR link and the next phase.

A phase is complete only when its exit gate in the roadmap is supported by evidence.
