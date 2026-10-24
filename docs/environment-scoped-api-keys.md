# Environment-scoped API keys

## Security contract

- Every user-issued key belongs to exactly one organization and one environment: `sandbox` or `production`.
- Sandbox keys are accepted only by an API deployment configured with `API_ENVIRONMENT=sandbox`. A sandbox key used against production is rejected with HTTP 403 and error code `API_KEY_ENVIRONMENT_MISMATCH`; the attempt is persisted as an audit/security event and logged without the secret.
- Production keys are accepted only by a deployment configured with `API_ENVIRONMENT=production`.
- A request header, query parameter, or client-supplied environment label never overrides the server's `API_ENVIRONMENT`.
- Key secrets are generated with a cryptographically secure random generator, stored only as SHA-256 hashes, shown once, and never returned by list endpoints.
- Key management requires a short-lived PesaGuard `type=access` HS256 JWT with `sub`, `tenant_id`, `exp`, `iat`, `nbf`, `jti`, `iss`, `aud`, and a trusted JWT key ID where configured. The datasource accepts the PesaGuard `organization_id`/`org_id` claim, or uses `tenant_id` as a narrower partition if no organization claim is present. Issuer and audience are required in production. Refresh tokens are rejected.
- Production key creation requires the JWT to state that the organization is verified and the user has an `owner` or `admin` role. The identity provider must set these claims based on its authoritative records, not client-submitted form fields.
- Key management routes are organization-scoped. Users cannot list, rotate, or revoke another organization's keys by changing an ID.
- Rotation revokes the old key and returns a new secret once. Revocation is immediate for subsequent requests.

## Deployment configuration

Set these server-side variables (never in Vite/browser variables):

- `API_ENVIRONMENT=production` on the live API service.
- `API_ENVIRONMENT=sandbox` on a separate sandbox service with a separate sandbox database, storage bucket/prefix, credentials, and hostname.
- `API_KEY_AUTH_JWT_KEYS_JSON` and `API_KEY_AUTH_JWT_ACTIVE_KID`: preferred rotating key ring copied from the trusted PesaGuard identity configuration. `API_KEY_AUTH_JWT_SECRET` is single-key compatibility mode only. Never expose any of these values to the frontend.
- `API_KEY_AUTH_JWT_ISSUER` and `API_KEY_AUTH_JWT_AUDIENCE`: configure to the exact identity provider issuer and audience.
- Continue using `REGISTRY_API_KEYS` only for existing trusted internal service-to-service callers during migration. Never expose it to browser JavaScript or customer API consumers.

Production and sandbox should be separate deployments. Setting a frontend dropdown or sending `X-Environment: production` is not environment isolation. The API environment comes from deployment configuration. Do not point the sandbox deployment at production PostgreSQL or production object storage.

## Migration / rollout

1. Apply the repository's Alembic migrations through `head` (`cd backend && python -m alembic -c alembic.ini upgrade head`). The API-key tables are introduced by `0006_api_key_tables`; this repository does not contain a `009_environment_scoped_api_keys.sql` migration.
2. Configure the JWT secret and matching issuer/audience on the API deployment and identity issuer.
3. Set `API_ENVIRONMENT=production` on production and provision an isolated sandbox deployment/database/storage.
4. Configure the datasource to trust the PesaGuard auth_rbac JWT key ring, issuer and audience. The current PesaGuard access-token implementation must provide authoritative organization-verification state before production key issuance can be enabled; absent `organization_verified: true`, production key creation intentionally fails closed.
5. Test sandbox key on production (403 and audit event), production key on sandbox (403 and audit event), expired/revoked keys (401), cross-organization management (404), unverified organization production-key creation (403), and one-time secret display.
6. Only then expose key management in the customer dashboard.

The legacy static `REGISTRY_API_KEYS` remain internal service credentials and are not managed by this feature. Rotate/migrate them separately; do not treat them as customer-issued keys.

## Customer key scope model (updated)

Customer-issued keys are **read-only lookup credentials**. The only scopes that can be granted are
`registry:read` (lookup, search and organization listing) and `sources:read` (source catalogue).

Customer keys can never reach ingestion, uploads, bulk export, metrics, warehouse telemetry or source
writes, whatever scopes a legacy key row carries: those endpoints return `403 API_KEY_ENDPOINT_NOT_AVAILABLE`.
Ingestion writes into the shared canonical registry and job data is not tenant-scoped, so it stays internal.
Responses to customer keys mask tax PINs (last two characters only) and redact PIN/tax fields in
`registry_payload`.

Rotation is atomic: the old key is revoked and the replacement issued in one transaction. If the
replacement is refused (for example the organization is no longer verified) the old key keeps working.
Rotation drops any legacy scope outside the allowed set.


## Tenant and database boundary notes

API-key rows and API-key audit-event queries are filtered by the authenticated organization/tenant partition, and rotate/revoke lookups include both the key ID and authenticated partition. These application predicates are covered by regression tests. They are not database Row-Level Security: the current schema has no RLS policies for these tables, and the operator workspace remains a system-wide administrative view. Verify PostgreSQL grants and implement/test RLS separately before claiming database-enforced tenant isolation.
