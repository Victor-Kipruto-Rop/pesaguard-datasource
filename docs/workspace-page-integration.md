# Datasource workspace page integration

All dashboard endpoints below are protected by the datasource operator session cookie. The browser must not receive the registry service API key. State-changing operator requests use the in-memory CSRF token in `X-CSRF-Token`.

| Page | Backend endpoint(s) | Behavior / truth boundary |
| --- | --- | --- |
| Overview | `GET /api/v1/admin/workspace/metrics`, `/api/v1/admin/registry/overview`, `/api/v1/admin/ingestion/activity`, `/api/v1/admin/ingestion/jobs`, `/api/v1/admin/workspace/stream` | Persisted KPIs and jobs; SSE snapshots plus REST refresh fallback. Source catalogue entries are not represented as live integrations. |
| Data Sources | `GET/POST /api/v1/admin/sources`, `PATCH/DELETE /api/v1/admin/sources/{id}` | CRUD against the datasource registry source table; deletion is blocked when jobs reference the source. |
| Ingestion Jobs | `GET /api/v1/admin/ingestion/jobs` | Persisted job state only; no hard-coded “live” status. |
| Registry Records | `GET /api/v1/admin/organizations` | Persisted registry organizations with pagination and search. Tax PIN is masked by the API. |
| Upload Center | `POST /api/v1/admin/ingestion/uploads`, `/ingestion/uploads/presign`, `/ingestion/uploads/{job_id}/complete` | Authenticated uploads; large direct uploads require configured private object storage and bucket CORS. |
| API Keys | `GET/POST /api/v1/keys`, `POST /api/v1/keys/{id}/rotate`, `DELETE /api/v1/keys/{id}` | Requires a trusted PesaGuard user access token with organization claims. The operator cookie is not a customer identity token. |
| Data Quality | `GET /api/v1/admin/data-quality/overview` | Field presence and ingestion-row error counts from persisted records; not external KRA/BRS verification. |
| Warehouse | `GET /api/v1/admin/warehouse/overview` | Persisted raw import metadata, stored byte totals, warehouse access events and unresolved dead-letter rows. |
| Validation Rules | `GET /api/v1/admin/validation/rules` | Read-only application-defined checks. No user-editable rule table is present in this schema. |
| Audit Logs | `GET /api/v1/admin/audit/logs` | Persisted datasource audit events; sensitive audit detail values are not returned. |
| Settings | `GET /api/v1/admin/settings/overview` | Safe runtime configuration diagnostics. Secret values are never returned. |

## Local verification

1. Configure `backend/.env` with a local database, `SESSION_SECRET` (at least 32 characters), `ADMIN_PASSWORD_HASH`, explicit local CORS origin, and `SESSION_COOKIE_SECURE=false` for localhost only.
2. For distributed login rate limiting, start Redis and set `REDIS_URL`. Production refuses to enable password-protected dashboard sessions without Redis.
3. Set `frontend/.env` to `VITE_API_BASE_URL=http://localhost:8000`.
4. Run the repository's Docker Compose setup or run the backend and Vite frontend separately.
5. From `frontend/`, run `npm ci`, `npm test`, and `npm run build`.
6. From `backend/`, install `requirements-dev.txt` and run `pytest`.
7. Sign in, create a source, upload a small authorized CSV, and verify that a persisted job and registry rows appear across Overview, Jobs, Registry Records, Data Quality and Audit Logs.

Do not treat an enabled source catalogue entry as a successful external integration. Do not mark RLS as active until tenant identity and database policy enforcement are independently verified. Do not merge or deploy based only on a frontend render; the backend tests, frontend build, local ingestion flow, and production worker/storage configuration must all be verified.


## Customer identity, tenant boundary and session security

### PesaGuard-issued customer access tokens

The API-key management routes validate PesaGuard's `auth_rbac` access JWT format, including `type=access`, expiry/not-before, issuer, audience, tenant identity, and the JWT `kid` against a configured HS256 signing-key ring. Refresh tokens are rejected. Use the same trusted values as the PesaGuard identity service:

- `API_KEY_AUTH_JWT_KEYS_JSON`: JSON object mapping the configured JWT key IDs to the same signing secrets used by PesaGuard. Prefer this rotating key ring over a single secret.
- `API_KEY_AUTH_JWT_ACTIVE_KID`: current key ID; tokens with a trusted `kid` from the ring continue to validate during key rotation.
- `API_KEY_AUTH_JWT_ISSUER` and `API_KEY_AUTH_JWT_AUDIENCE`: must exactly match the issuer and audience configured in PesaGuard.
- `API_KEY_AUTH_JWT_SECRET`: compatibility mode only for a single key. Never put a secret in frontend variables or source control.

The browser accepts a short-lived PesaGuard access token in memory only. It is never saved to localStorage or sessionStorage. The API normalizes the trusted `organization_id` / `org_id` claim to the datasource's key partition; when a token only has `tenant_id`, the tenant itself is used as the narrower partition. All key and key-audit listing queries filter by that authenticated partition. Key create, rotate and revoke operations are also scoped to the authenticated partition. Production key creation fails closed unless the token includes `organization_verified: true` and an owner/admin role; the identity service must issue this claim from authoritative verification state before production issuance is enabled.

**Important integration boundary:** this validates the real PesaGuard access-token signature and claims; it does not call an identity introspection endpoint or independently check the provider's persisted session revocation state. Tokens are short-lived, but immediate revocation requires a provider introspection/revocation integration if that guarantee is needed. Never copy the datasource's internal `REGISTRY_API_KEYS` value into the browser.

### Operator session controls

- Dashboard sessions use a signed HttpOnly, SameSite=Strict cookie. JavaScript cannot read the session cookie.
- Cookie-authenticated state changes, including logout, require the session CSRF token in `X-CSRF-Token`.
- Sessions have a signed expiry and slide forward on authenticated activity. Expired or tampered tokens are rejected.
- Production login requires Redis-backed shared token-bucket throttling; missing or unavailable Redis fails closed. The in-process limiter is development/test only.
- Production requires HTTPS cookies, PostgreSQL, strong secrets and Redis. Do not use local fallback configuration in production.

### Tenant-isolation limits

API-key records and API-key audit events are explicitly filtered by the authenticated tenant/organization ID. Customer API keys only receive allowlisted read scopes. This is not equivalent to verified PostgreSQL Row-Level Security for all workspace tables: the operator workspace is currently an administrative, system-wide view, and tenant-scoped RLS for registry/job/source tables has not been established by this change. Do not advertise RLS as enabled until the schema, runtime DB role, RLS policies, and cross-tenant tests have been independently verified against PostgreSQL.

### Manual security verification

1. Configure the datasource with the matching PesaGuard signing-key ring, issuer and audience; issue a real short-lived access token from PesaGuard.
2. Confirm `GET /api/v1/keys/me` returns the expected user, tenant/organization and expiry without returning token material.
3. Confirm expired, refresh-type, wrong-issuer, wrong-audience, unknown-`kid`, tampered and cross-tenant tokens are rejected.
4. Create keys under two test organizations; verify each can list only its own keys and audit events. Verify cross-organization rotate/revoke attempts return 404.
5. Confirm missing/wrong CSRF tokens fail for source mutations and logout; correct CSRF succeeds.
6. In production-like staging, verify Redis login throttling across two app instances, session expiry, cookie Secure/SameSite/HttpOnly flags and fail-closed behavior during Redis outage.
7. Verify PostgreSQL grants and RLS policies using the actual deployed runtime DB role. The app's explicit tenant filters do not prove database-level RLS.
