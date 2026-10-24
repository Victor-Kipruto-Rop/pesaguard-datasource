# Phase 6 — Deployment and software supply chain

## Objective
Make builds repeatable and releases safe to promote and roll back.

## Tasks
- Review Dockerfiles for multi-stage builds, non-root users, minimal maintained images, pinned dependencies and correct health behavior.
- Validate required environment variables at startup without logging values.
- Separate development, staging and production configuration and access.
- Require backend tests/lint, PostgreSQL tests, frontend tests/build, migrations, dependency audit, secret scan, container scan and Compose validation in CI.
- Investigate runner failures using job and step evidence; do not treat a job that never started as a passing check.
- Test Alembic clean bootstrap and upgrade from a representative schema; never stamp a production database without a reviewed schema comparison.
- Add deployment smoke tests, release artifact identification, staged rollout and rollback procedures.
- Verify TLS, DNS, CORS, cookie flags, security headers, object-storage policy and health checks.
- Document which steps require a human with production credentials.

## Acceptance
- Required CI jobs pass on the exact commit intended for release.
- Container builds and startup/readiness checks pass.
- Migration and rollback strategy has been exercised in a disposable/staging environment.
- No deployment or production migration occurs as part of this phase without explicit authorization.
