# Phase 3 — Datasource lifecycle and ingestion reliability

## Objective
Prove an end-to-end source-to-job workflow with durable state and safe recovery.

## Tasks
- Trace source CRUD and connection testing from UI through API, model, persistence and connector adapter.
- Standardize connector result states and errors; never treat unconfigured adapters as successful.
- Ensure accepted jobs are durable and idempotent; define deduplication key scope.
- Add bounded exponential retries with jitter, timeouts, backpressure, cancellation semantics and dead-letter handling.
- Verify checkpoint/cursor behavior, incremental extraction, safe replay, partial-batch transactions and duplicate submission behavior.
- Validate schemas and types; quarantine invalid records with safe diagnostics and row/record references.
- Add lineage from source and run to transformed records; report control totals.
- Enforce tenant/resource limits and fair worker scheduling.
- Test worker crash/restart, queue outage, provider timeout, malformed row, duplicate input, stale lease, cancellation and redrive.
- Keep file and payload size bounded; never load unbounded files into memory.

## Acceptance
- A real local/sandbox integration test follows configure -> test -> submit -> process -> persist -> display.
- Job status and counts come from persisted backend state.
- Retry/replay does not create duplicate side effects.
- Dead-letter access is authorized and diagnostics do not leak secrets/PII.
- External provider tests are marked blocked when credentials or approval are absent.
