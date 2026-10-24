# Phase 4 — Observability, reliability and performance

## Objective
Make failures diagnosable and measure capacity using representative workloads.

## Tasks
- Verify liveness vs readiness semantics and safe checks for configured dependencies.
- Add structured logs with request/correlation/job IDs; redact tokens, secrets, full payloads and unnecessary PII.
- Instrument HTTP latency/error rates, DB latency/pool use, queue depth/wait, worker heartbeats, ingestion throughput, retries and dead letters.
- Expose metrics only through the documented protected path; never include sensitive/high-cardinality labels.
- Define actionable alert thresholds and runbooks for stuck jobs, provider failures, queue growth, DB saturation, elevated errors and certificate expiry.
- Test graceful shutdown, worker lease recovery, database/queue outages, external provider timeouts and tenant fairness.
- Add load, stress, spike and soak tests; report concurrency, throughput, p50/p95/p99 latency, error rate and resource use.
- Define RTO/RPO with operators; verify backup restore and rollback in a disposable environment.

## Acceptance
- Metrics/logs/traces correlate a request to its job without leaking sensitive data.
- Load test results include environment and workload assumptions.
- No SLA or capacity claim is made without measured evidence.
- Recovery and alert procedures are tested or explicitly marked blocked.
