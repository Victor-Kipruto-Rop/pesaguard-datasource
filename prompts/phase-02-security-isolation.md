# Phase 2 — Identity, security and tenant isolation

## Objective
Prove that authentication, authorization, key handling, and tenant separation are enforced by the backend.

## Tasks
- Trace the authoritative PesaGuard identity implementation and document exact token claims, issuer, audience, key rotation and revocation semantics.
- Do not assume `organization_verified` is trusted unless the identity provider emits it from an authoritative verification record.
- Keep production key issuance fail-closed until eligibility is authoritative.
- Test missing, malformed, expired, not-yet-valid, wrong-audience, wrong-issuer, refresh, revoked, and unknown-key-ID tokens.
- Test every key/data-source/job/audit endpoint for cross-tenant IDOR and role escalation.
- Verify sandbox keys cannot access production resources and vice versa.
- Review secrets at rest, one-time key display, hash storage, rotation, expiry, revocation and log redaction.
- Review SSRF controls for arbitrary URLs, redirects, DNS changes, private IP ranges, metadata endpoints, and non-HTTP schemes.
- Review CSRF, cookie flags, CORS, request size, rate limiting, webhook replay, and error information leakage.
- Design PostgreSQL RLS only after mapping connection roles and the credential lookup path; add migration and tests only when safe.
- Add tests for each finding and document residual risks.

## Acceptance
- Security tests pass on disposable SQLite and PostgreSQL where applicable.
- No frontend-only authorization is relied on.
- No production migration or secret change is performed.
- RLS and production DB role state are described accurately, not assumed.
- Unavailable identity/provider capabilities remain explicit blockers.
