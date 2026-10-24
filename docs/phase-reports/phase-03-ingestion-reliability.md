# Phase 3 — Datasource and ingestion reliability report

**Status:** Targeted retry reliability improvement implemented; phase remains incomplete and unverified.  
**Candidate PR:** #47  
**Date:** 2026-10-24

## Changes
- Added `WORKER_RETRY_MAX_SECONDS` / `worker_retry_max_seconds` with a safe default of 900 seconds.
- Added a retry-delay helper that caps exponential backoff and applies equal jitter, reducing synchronized retry storms while ensuring retry delays remain bounded.
- Replaced unbounded deterministic exponential retry scheduling in the ingestion worker with the helper.
- Added focused tests for exponential growth, cap behavior, jitter lower bound and non-positive configuration handling.

## Validation
- Source and test definitions were inspected through the repository API.
- Pytest has not run successfully in this environment. The most recent actionable CI attempt still failed before any steps started; no pass/fail conclusion can be drawn about these new tests.
- Local end-to-end source-to-job ingestion, worker restart, provider outage, dead-letter and replay behavior remain unverified.
- No queued production job or production data was processed.

## Remaining acceptance items
- Run the new retry tests and the complete backend suite.
- Confirm all worker settings are validated for staging/production configuration.
- Test retry scheduling with the actual worker/database stack, including stale lease recovery and worker restarts.
- Verify dead-letter authorization, redaction, controlled redrive and idempotency end to end.
- Prove source configuration -> ingestion -> persisted output -> UI using safe local or approved sandbox data.

## Decision
Only bounded retry backoff and jitter are implemented in this phase. The complete ingestion reliability exit gate remains open.
