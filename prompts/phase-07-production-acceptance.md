# Phase 7 — Production acceptance and release sign-off

## Objective
Decide readiness from evidence, not from feature count or UI appearance.

## Tasks
- Run complete unit, integration, PostgreSQL, API contract, security, frontend, accessibility, end-to-end, load and failure-recovery suites.
- Verify backup restoration, RTO/RPO, migration recovery, deployment rollback, alerts and runbooks.
- Confirm identity-provider claims, provider contracts/credentials, production DB grants, secrets, DNS/TLS, monitoring and support ownership with authorized operators.
- Review every critical/high security finding; assign owners and dates to accepted risks.
- Check retention/deletion/export, privacy notices, auditability and applicable Kenyan data-protection/financial-sector obligations with appropriate review.
- Verify documentation and status pages accurately describe current service availability and limitations.
- Produce release report containing exact commit SHA, CI links, test commands/results, performance measurements, blockers, accepted risks and rollback path.
- Do not merge or deploy until authorized release approval is explicitly given.

## Acceptance
- All mandatory release gates have reproducible evidence.
- No unresolved critical blocker is hidden or waived silently.
- Production approval and rollback ownership are recorded.
- If any external or infrastructure requirement is unavailable, release is marked blocked.
