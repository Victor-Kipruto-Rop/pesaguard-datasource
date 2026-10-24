# Phase 2 — Identity, security and tenant isolation report

**Status:** Targeted API-key authorization hardening implemented; full phase incomplete.  
**Candidate PR:** #47  
**Date:** 2026-10-24

## Changes
- API-key creation now requires an organization `owner` or `admin` role for both sandbox and production keys. The policy is enforced in the shared backend helper, not just in the frontend.
- Role claims are normalized defensively. Non-string entries and malformed role containers grant no privilege instead of causing an unhandled type error.
- The authorization error now describes API-key management generally rather than only rotation/revocation.
- Added regression tests for member/no-role/malformed-role denial, normalized owner role acceptance, and fail-closed production issuance when organization verification is false.

## Validation
- Source changes and test insertion were inspected via GitHub file reads.
- Pytest has **not** run successfully in this environment.
- GitHub Actions run `40104656666` failed with no job steps reported for backend, PostgreSQL, frontend and Compose. This is not evidence of code test failure or success; runner/infrastructure availability remains a blocker.
- The identity issuer still does not provide an authoritative organization-verification claim according to the existing PR security boundary. Production key issuance must remain blocked until that is fixed at the authoritative identity source.
- Local JWT validation still does not provide persisted session-revocation/introspection guarantees.
- PostgreSQL RLS is not enabled across all workspace tables; the deployed database role/grants have not been verified.

## Remaining P0 security work
- Confirm authoritative identity token claims and revocation semantics with the PesaGuard identity implementation.
- Add/verify negative tests for IDOR and cross-tenant access across all endpoints and background workers.
- Design RLS with a safe credential-hash lookup path and validate runtime role grants before migration.
- Verify SSRF protections for configurable external URLs and provider connections.
- Run all security tests against disposable SQLite and PostgreSQL.
- Document residual risks and do not represent the system as production-ready before the exit gate passes.

## Decision
The targeted API-key authorization change is implemented but unverified. Phase 2 remains open.
