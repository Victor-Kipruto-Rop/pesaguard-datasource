"""Server-side dashboard authentication.

The browser never receives the service API key. An operator signs in with a dedicated
admin password; the server verifies it against a PBKDF2 hash and issues a signed,
HttpOnly, SameSite=Strict session cookie. State-changing requests that rely on the
cookie must also send the per-session CSRF token in ``X-CSRF-Token``.

Generate a password hash with: ``python -m src.admin_auth hash-password``
"""
import base64
import collections
import getpass
import hashlib
import hmac
import json
import secrets
import sys
import threading
import time
import logging
import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .config import settings
from .database import get_db
from .models import RegistrySource, IngestionJob, Organization, AuditLog, WarehouseRawImport, WarehouseAccessLog, FailedImportDLQ, IngestionRowError
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import Depends, UploadFile
from fastapi.responses import StreamingResponse
from .database import SessionLocal

COOKIE_NAME = 'pg_admin_session'
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}
PBKDF2_ITERATIONS = 600_000
router = APIRouter(prefix='/api/v1/admin', tags=['admin session'])

_attempt_lock = threading.Lock()
_attempts = collections.defaultdict(collections.deque)
_rate_logger = logging.getLogger(__name__)
_REDIS_BUCKET_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])
local state = redis.call('HMGET', key, 'tokens', 'updated')
local tokens = tonumber(state[1]) or capacity
local updated = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - updated) * refill)
local allowed = 0
if tokens >= cost then tokens = tokens - cost; allowed = 1 end
redis.call('HMSET', key, 'tokens', tokens, 'updated', now)
redis.call('EXPIRE', key, ttl)
return {allowed, math.floor(tokens), math.ceil((cost - tokens) / refill)}
"""


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
    return f'pbkdf2_sha256${iterations}${_b64(salt)}${_b64(digest)}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt, expected = encoded.split('$')
        if scheme != 'pbkdf2_sha256':
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), _unb64(salt), int(iterations))
        return hmac.compare_digest(digest, _unb64(expected))
    except Exception:
        return False


def _sign(payload: str) -> str:
    return _b64(hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).digest())


def issue_session_token(now: float | None = None) -> tuple[str, dict]:
    issued = int(now if now is not None else time.time())
    claims = {'sub': 'admin', 'iat': issued, 'exp': issued + max(60, settings.session_ttl_seconds), 'csrf': secrets.token_urlsafe(24)}
    payload = _b64(json.dumps(claims, separators=(',', ':')).encode())
    return f'{payload}.{_sign(payload)}', claims


def decode_session_token(token: str | None) -> dict | None:
    if not token or not settings.session_secret or '.' not in token:
        return None
    payload, _, signature = token.partition('.')
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        claims = json.loads(_unb64(payload))
    except Exception:
        return None
    if not isinstance(claims.get('exp'), (int, float)) or claims['exp'] <= time.time():
        return None
    return claims


def session_from_request(request: Request) -> dict | None:
    return decode_session_token(request.cookies.get(COOKIE_NAME))

def refresh_session_token(claims: dict, now: float | None = None) -> tuple[str, dict]:
    """Issue a sliding-TTL token while preserving the current CSRF secret."""
    issued = int(now if now is not None else time.time())
    renewed = {**claims, 'iat': issued, 'exp': issued + max(60, settings.session_ttl_seconds)}
    payload = _b64(json.dumps(renewed, separators=(',', ':')).encode())
    return f'{payload}.{_sign(payload)}', renewed


def enforce_session_csrf(request: Request, claims: dict) -> None:
    """Cookie-authenticated unsafe requests must prove they came from our dashboard."""
    if request.method.upper() in SAFE_METHODS:
        return
    supplied = request.headers.get('X-CSRF-Token', '')
    if not supplied or not hmac.compare_digest(supplied, str(claims.get('csrf', ''))):
        raise HTTPException(403, 'Missing or invalid CSRF token')


def _check_login_rate(client_host: str) -> None:
    # Redis token bucket is shared across API instances; local fallback is development-only.
    capacity = max(1, settings.admin_login_max_attempts_per_minute)
    if settings.redis_url:
        try:
            import redis
            client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1,
                                          decode_responses=True)
            result = client.eval(_REDIS_BUCKET_LUA, 1,
                'pg:admin-login:' + hashlib.sha256(client_host.encode()).hexdigest(),
                time.time(), capacity, capacity / 60.0, 1, 120)
            allowed, _, retry_after = [int(x) for x in result]
            if allowed != 1:
                raise HTTPException(429, 'Too many sign-in attempts. Try again shortly.',
                                    headers={'Retry-After': str(max(1, retry_after))})
            return
        except HTTPException:
            raise
        except Exception as exc:
            _rate_logger.exception('admin_login_redis_rate_limit_unavailable')
            if settings.app_env.lower() == 'production':
                raise HTTPException(503, 'Sign-in rate limiter is temporarily unavailable') from exc
    elif settings.app_env.lower() == 'production':
        raise HTTPException(503, 'Sign-in rate limiter is not configured')
    now = time.monotonic()
    with _attempt_lock:
        bucket = _attempts[client_host]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= capacity:
            raise HTTPException(429, 'Too many sign-in attempts. Try again in a minute.', headers={'Retry-After': '60'})
        bucket.append(now)


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)


@router.post('/login')
def login(payload: LoginRequest, request: Request, response: Response):
    if not settings.admin_password_hash or not settings.session_secret:
        raise HTTPException(503, 'Dashboard sign-in is not configured')
    _check_login_rate(request.client.host if request.client else 'unknown')
    if not verify_password(payload.password, settings.admin_password_hash):
        raise HTTPException(401, 'Invalid credentials')
    token, claims = issue_session_token()
    response.set_cookie(COOKIE_NAME, token, max_age=max(60, settings.session_ttl_seconds), httponly=True,
                        secure=settings.session_cookie_secure, samesite='strict', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'authenticated': True, 'csrf_token': claims['csrf'], 'expires_at': claims['exp']}


@router.get('/session')
def session(request: Request, response: Response):
    claims = session_from_request(request)
    response.headers['Cache-Control'] = 'no-store'
    if not claims:
        raise HTTPException(401, 'Not signed in')
    return {'authenticated': True, 'csrf_token': claims['csrf'], 'expires_at': claims['exp']}


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response):
    claims = session_from_request(request)
    if claims:
        enforce_session_csrf(request, claims)
    response.delete_cookie(COOKIE_NAME, path='/')
    response.headers['Cache-Control'] = 'no-store'
    return None


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'hash-password':
        first = getpass.getpass('Admin password: ')
        if len(first) < 12:
            sys.exit('Use at least 12 characters.')
        if first != getpass.getpass('Repeat password: '):
            sys.exit('Passwords did not match.')
        print(hash_password(first))
    else:
        sys.exit('usage: python -m src.admin_auth hash-password')


# Session-authenticated dashboard endpoints. The internal service API key stays server-side.
def require_admin(request: Request):
    claims = session_from_request(request)
    if not claims:
        raise HTTPException(401, 'Not signed in')
    enforce_session_csrf(request, claims)
    return claims


def _source_json(source, last_import=None):
    from datetime import datetime, timezone
    if source.freshness_sla_hours is None:
        freshness = 'no_sla'
    elif last_import is None:
        freshness = 'never_imported'
    else:
        imported = last_import if last_import.tzinfo else last_import.replace(tzinfo=timezone.utc)
        freshness = 'stale' if (datetime.now(timezone.utc)-imported).total_seconds() > source.freshness_sla_hours*3600 else 'fresh'
    return {'id':source.id,'source_key':source.source_key,'display_name':source.display_name,'jurisdiction':source.jurisdiction,
        'source_type':source.source_type,'authority_url':source.authority_url,'licence_reference':source.licence_reference,
        'freshness_sla_hours':source.freshness_sla_hours,'precedence':source.precedence,'enabled':source.enabled,'notes':source.notes,
        'last_successful_import_at':last_import.isoformat() if last_import else None,'freshness_status':freshness,
        'created_at':source.created_at.isoformat() if source.created_at else None,
        'updated_at':source.updated_at.isoformat() if source.updated_at else None}


class DashboardSourcePayload(BaseModel):
    source_key: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    jurisdiction: str = Field(default='KE', max_length=100)
    source_type: str = Field(default='IMPORTED_DATASET', max_length=40)
    authority_url: str | None = Field(default=None, max_length=1000)
    licence_reference: str | None = Field(default=None, max_length=500)
    freshness_sla_hours: int | None = Field(default=None, ge=1, le=8760)
    precedence: int = Field(default=100, ge=0, le=10000)
    enabled: bool = True
    notes: str | None = Field(default=None, max_length=10000)


def _validate_source(payload):
    payload.source_key = payload.source_key.strip().lower()
    payload.display_name = payload.display_name.strip()
    if not payload.source_key or not all(c.isalnum() or c in '-_' for c in payload.source_key):
        raise HTTPException(422, 'Source key may contain letters, numbers, hyphens and underscores only')
    if not payload.display_name:
        raise HTTPException(422, 'Display name is required')
    if payload.authority_url and not payload.authority_url.lower().startswith(('https://','http://')):
        raise HTTPException(422, 'Authority URL must use HTTP or HTTPS')


@router.get('/sources')
def dashboard_sources(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    rows = db.scalars(select(RegistrySource).order_by(RegistrySource.precedence, RegistrySource.display_name)).all()
    last_imports = dict(db.execute(select(IngestionJob.source_id, func.max(IngestionJob.completed_at))
        .where(IngestionJob.status.in_(['COMPLETED','COMPLETED_WITH_ERRORS']), IngestionJob.source_id.is_not(None))
        .group_by(IngestionJob.source_id)).all())
    return {'items':[_source_json(s,last_imports.get(s.id)) for s in rows], 'count':len(rows)}


@router.post('/sources', status_code=201)
def dashboard_create_source(payload: DashboardSourcePayload, request: Request, db: Session = Depends(get_db)):
    require_admin(request); _validate_source(payload)
    if db.scalar(select(RegistrySource).where(RegistrySource.source_key == payload.source_key)):
        raise HTTPException(409, 'A source with this key already exists')
    source = RegistrySource(**payload.model_dump())
    db.add(source)
    try:
        db.flush()
        db.add(AuditLog(action='dashboard_source_created', actor='admin', details={'source_id':source.id,'source_key':source.source_key}))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'A source with this key already exists')
    db.refresh(source)
    return _source_json(source)


@router.patch('/sources/{source_id}')
def dashboard_update_source(source_id: str, payload: DashboardSourcePayload, request: Request, db: Session = Depends(get_db)):
    require_admin(request); _validate_source(payload)
    source = db.get(RegistrySource, source_id)
    if not source: raise HTTPException(404, 'Source not found')
    if db.scalar(select(RegistrySource).where(RegistrySource.source_key == payload.source_key, RegistrySource.id != source_id)):
        raise HTTPException(409, 'A source with this key already exists')
    for name, value in payload.model_dump().items(): setattr(source, name, value)
    db.add(AuditLog(action='dashboard_source_updated', actor='admin', details={'source_id':source.id,'source_key':source.source_key}))
    db.commit(); db.refresh(source)
    return _source_json(source)


@router.delete('/sources/{source_id}', status_code=204)
def dashboard_delete_source(source_id: str, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    source = db.get(RegistrySource, source_id)
    if not source: raise HTTPException(404, 'Source not found')
    if db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.source_id == source_id)):
        raise HTTPException(409, 'This source has ingestion history. Disable it instead of deleting it.')
    db.add(AuditLog(action='dashboard_source_deleted', actor='admin', details={'source_id':source.id,'source_key':source.source_key}))
    db.delete(source); db.commit()
    return Response(status_code=204)


@router.get('/ingestion/jobs')
def dashboard_ingestion_jobs(request: Request, page: int = 1, page_size: int = 50, status: str | None = None, q: str | None = None,
                             db: Session = Depends(get_db)):
    require_admin(request)
    page = max(1,page); page_size = max(1,min(page_size,100))
    stmt = select(IngestionJob)
    if status: stmt = stmt.where(IngestionJob.status == status.upper())
    if q and q.strip():
        pattern = '%' + q.strip()[:200] + '%'
        stmt = stmt.where(or_(IngestionJob.file_name.ilike(pattern), IngestionJob.source_name.ilike(pattern), IngestionJob.status.ilike(pattern), IngestionJob.id.ilike(pattern)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(IngestionJob.created_at.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[{'id':j.id,'file_name':j.file_name,'source_id':j.source_id,'source_name':j.source_name,'status':j.status,
        'records_processed':j.records_processed,'records_inserted':j.records_inserted,'records_updated':j.records_updated,
        'records_skipped':j.records_skipped,'attempts':j.attempts,'error_summary':j.error_summary,
        'created_at':j.created_at.isoformat() if j.created_at else None,'started_at':j.started_at.isoformat() if j.started_at else None,
        'completed_at':j.completed_at.isoformat() if j.completed_at else None,'heartbeat_at':j.heartbeat_at.isoformat() if j.heartbeat_at else None} for j in rows],
        'total':total,'page':page,'page_size':page_size}


@router.get('/metrics/summary')
def dashboard_summary(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    total_orgs = db.scalar(select(func.count()).select_from(Organization)) or 0
    total_jobs = db.scalar(select(func.count()).select_from(IngestionJob)) or 0
    completed = db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status.in_(['COMPLETED','COMPLETED_WITH_ERRORS']))) or 0
    failed = db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status.in_(['FAILED','ERROR']))) or 0
    return {'total_organizations':total_orgs,'total_jobs':total_jobs,'completed_jobs':completed,'failed_jobs':failed,
            'data_quality':None,'source':'database','generated_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}


@router.get('/organizations')
def dashboard_organizations(request: Request, page: int = 1, page_size: int = 25, q: str | None = None,
                            db: Session = Depends(get_db)):
    require_admin(request)
    page=max(1,page); page_size=max(1,min(page_size,100))
    stmt=select(Organization)
    if q and q.strip():
        from sqlalchemy import or_
        pattern='%' + q.strip() + '%'
        stmt=stmt.where(Organization.legal_name.ilike(pattern) | Organization.registration_number.ilike(pattern))
    total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows=db.scalars(stmt.order_by(Organization.legal_name).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[{'id':o.id,'legal_name':o.legal_name,'registration_number':o.registration_number,
        'tax_pin':('•'*(max(0,len(o.tax_pin)-2))+o.tax_pin[-2:]) if o.tax_pin else None,
        'status':o.status,'data_quality_status':o.data_quality_status,'source_file':o.source_file,
        'created_at':o.created_at.isoformat() if o.created_at else None,'updated_at':o.updated_at.isoformat() if o.updated_at else None} for o in rows],
        'total':total,'page':page,'page_size':page_size}


@router.post('/ingestion/uploads', status_code=202)
def dashboard_upload(request: Request, file: UploadFile, db: Session = Depends(get_db)):
    require_admin(request)
    from .api import upload as upload_impl
    return upload_impl(request, file, db, request.headers.get('X-Correlation-ID'),
                       request.headers.get('Idempotency-Key'), request.headers.get('X-Registry-Source'))


@router.post('/ingestion/uploads/presign', status_code=201)
def dashboard_presign_upload(payload: dict, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    from .api import DirectUploadRequest, presign_direct_upload
    parsed = DirectUploadRequest.model_validate(payload)
    return presign_direct_upload(parsed, request, db, request.headers.get('X-Correlation-ID'), request.headers.get('Idempotency-Key'))


@router.post('/ingestion/uploads/{job_id}/complete')
def dashboard_complete_upload(job_id: str, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    from .api import complete_direct_upload
    return complete_direct_upload(job_id, db)

# Workspace overview endpoints. All counts are computed from persisted datasource records.
@router.get('/workspace/metrics')
def workspace_metrics(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    total_orgs = db.scalar(select(func.count()).select_from(Organization)) or 0
    total_jobs = db.scalar(select(func.count()).select_from(IngestionJob)) or 0
    completed = db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status.in_(['COMPLETED','COMPLETED_WITH_ERRORS']))) or 0
    failed = db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status.in_(['FAILED','ERROR']))) or 0
    source_count = db.scalar(select(func.count()).select_from(RegistrySource).where(RegistrySource.enabled.is_(True))) or 0
    return {'indexed_organizations':total_orgs,'ingestion_jobs':total_jobs,'completed_jobs':completed,
            'failed_jobs':failed,'enabled_sources_count':source_count,'connected_sources_count':None,'generated_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
            'source':'database'}


@router.get('/ingestion/activity')
def ingestion_activity(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    require_admin(request)
    limit = max(1, min(limit, 200))
    rows = db.scalars(select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(limit)).all()
    events = []
    chronological = list(reversed(rows))
    volumes = [max(0, int(j.records_processed or 0)) for j in chronological]
    for i, job in enumerate(chronological):
        # Compare this job only with preceding observations; flag only with at least five baselines.
        history = volumes[max(0, i - 7):i]
        volume = volumes[i]
        anomaly = None
        if len(history) >= 5:
            mean = sum(history) / len(history)
            variance = sum((v - mean) ** 2 for v in history) / len(history)
            std = variance ** 0.5
            if std > 0 and abs(volume - mean) / std >= 3:
                anomaly = {'type':'volume_spike' if volume > mean else 'volume_drop', 'z_score':round((volume-mean)/std, 2)}
        events.append({'job_id':job.id,'created_at':job.created_at.isoformat() if job.created_at else None,
            'status':job.status,'records_processed':volume,'records_inserted':int(job.records_inserted or 0),
            'anomaly':anomaly})
    events.reverse()
    return {'items':events,'count':len(events),'generated_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
            'source':'database'}


@router.get('/registry/overview')
def registry_overview(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    total = db.scalar(select(func.count()).select_from(Organization)) or 0
    if not total:
        return {'total_records':0,'completeness_percentage':None,'null_assertion_pass_percentage':None,
                'unreviewed_records':0,'source':'database','generated_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
    rows = db.execute(select(Organization.legal_name, Organization.registration_number, Organization.tax_pin,
                             Organization.status, Organization.data_quality_status)).all()
    total_fields = len(rows) * 4
    present_fields = sum(sum(value is not None and str(value).strip() != '' for value in row[:4]) for row in rows)
    completeness = round((present_fields / total_fields) * 100, 2) if total_fields else None
    reviewed = sum(1 for row in rows if str(row[4] or '').upper() not in {'UNREVIEWED', 'UNKNOWN', ''})
    return {'total_records':total,'completeness_percentage':completeness,
            'null_assertion_pass_percentage':round(present_fields / total_fields * 100, 2) if total_fields else None,
            'unreviewed_records':total-reviewed,'source':'database',
            'generated_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}



@router.get('/data-quality/overview')
def admin_data_quality_overview(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    total = db.scalar(select(func.count()).select_from(Organization)) or 0
    rows = db.execute(select(Organization.legal_name, Organization.registration_number,
                             Organization.tax_pin, Organization.status,
                             Organization.data_quality_status)).all()
    required_fields = 4
    field_slots = len(rows) * required_fields
    present = sum(sum(value is not None and str(value).strip() != '' for value in row[:required_fields]) for row in rows)
    complete_rows = sum(all(value is not None and str(value).strip() != '' for value in row[:required_fields]) for row in rows)
    row_errors = db.scalar(select(func.count()).select_from(IngestionRowError)) or 0
    unreviewed = sum(1 for row in rows if str(row[4] or '').upper() in {'UNREVIEWED', 'UNKNOWN', ''})
    return {'total_records': total, 'complete_records': complete_rows,
            'incomplete_records': max(0, total - complete_rows),
            'completeness_percentage': round(present / field_slots * 100, 2) if field_slots else None,
            'complete_record_percentage': round(complete_rows / total * 100, 2) if total else None,
            'unreviewed_records': unreviewed, 'ingestion_row_errors': row_errors,
            'required_fields': ['legal_name', 'registration_number', 'tax_pin', 'status'],
            'source': 'database', 'generated_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}


@router.get('/warehouse/overview')
def admin_warehouse_overview(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    import_count = db.scalar(select(func.count()).select_from(WarehouseRawImport)) or 0
    total_bytes = db.scalar(select(func.coalesce(func.sum(WarehouseRawImport.byte_size), 0))) or 0
    access_count = db.scalar(select(func.count()).select_from(WarehouseAccessLog)) or 0
    dlq_count = db.scalar(select(func.count()).select_from(FailedImportDLQ).where(FailedImportDLQ.resolved_at.is_(None))) or 0
    imports = db.scalars(select(WarehouseRawImport).order_by(WarehouseRawImport.created_at.desc()).limit(50)).all()
    access = db.scalars(select(WarehouseAccessLog).order_by(WarehouseAccessLog.created_at.desc()).limit(20)).all()
    return {'raw_imports': import_count, 'stored_bytes': int(total_bytes), 'warehouse_access_events': access_count,
            'unresolved_dead_letter_rows': dlq_count,
            'imports': [{'id': x.id, 'job_id': x.ingestion_job_id, 'file_name': x.original_filename,
                         'content_type': x.content_type, 'byte_size': int(x.byte_size or 0),
                         'source_name': x.source_name, 'status': x.import_status,
                         'created_at': x.created_at.isoformat() if x.created_at else None} for x in imports],
            'access_events': [{'id': x.id, 'request_id': x.request_id, 'caller_service': x.caller_service,
                               'endpoint': x.endpoint, 'method': x.http_method, 'status_code': x.response_status,
                               'duration_ms': x.duration_ms, 'outcome': x.outcome,
                               'created_at': x.created_at.isoformat() if x.created_at else None} for x in access],
            'source': 'database', 'generated_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}


@router.get('/validation/rules')
def admin_validation_rules(request: Request):
    require_admin(request)
    # These are application-level checks, not user-configurable rules stored in the database.
    rules = [
        {'id': 'legal-name-required', 'name': 'Legal name required', 'field': 'legal_name',
         'severity': 'error', 'status': 'enforced', 'description': 'Every registry organization must have a non-empty legal name.'},
        {'id': 'registration-number-unique', 'name': 'Registration number uniqueness', 'field': 'normalized_registration_number',
         'severity': 'error', 'status': 'enforced', 'description': 'A normalized registration number cannot belong to two registry records.'},
        {'id': 'tax-pin-presence', 'name': 'Tax PIN presence', 'field': 'tax_pin',
         'severity': 'review', 'status': 'measured', 'description': 'Presence is measured for completeness; this does not verify a PIN with KRA.'},
        {'id': 'registration-number-presence', 'name': 'Registration number presence', 'field': 'registration_number',
         'severity': 'review', 'status': 'measured', 'description': 'Presence is measured for completeness; this does not verify BRS registration.'},
        {'id': 'source-provenance', 'name': 'Source provenance', 'field': 'source_name/source_file/source_row',
         'severity': 'review', 'status': 'partially-tracked', 'description': 'Ingestion records retain available source provenance metadata.'},
    ]
    return {'items': rules, 'total': len(rules), 'editable': False, 'source': 'application-defined',
            'note': 'Rules are defined by application behavior. There is no persisted rule-management model in this deployment.',
            'generated_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}


@router.get('/audit/logs')
def admin_audit_logs(request: Request, limit: int = 100, db: Session = Depends(get_db)):
    require_admin(request)
    limit = max(1, min(limit, 200))
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return {'items': [{'id': x.id, 'action': x.action, 'actor': x.actor, 'file_name': x.file_name,
                       'detail_fields': sorted(list((x.details or {}).keys())) if isinstance(x.details, dict) else [],
                       'created_at': x.created_at.isoformat() if x.created_at else None} for x in rows],
            'count': len(rows), 'source': 'database',
            'generated_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}


@router.get('/settings/overview')
def admin_settings_overview(request: Request):
    require_admin(request)
    origins = settings.cors_origin_list
    return {'environment': settings.app_env, 'api_environment': settings.api_environment,
            'database': {'configured': bool(settings.database_url), 'engine': 'postgresql' if 'postgres' in settings.database_url.lower() else ('sqlite/local' if settings.database_url.lower().startswith('sqlite') else 'unknown')},
            'object_storage': {'configured': all([settings.r2_account_id, settings.r2_access_key_id, settings.r2_secret_access_key, settings.r2_bucket_name])},
            'redis': {'configured': bool(settings.redis_url), 'required_for_distributed_admin_rate_limit': bool(settings.admin_password_hash)},
            'operator_session': {'http_only_cookie': True, 'secure_cookie': settings.session_cookie_secure,
                                 'same_site': 'strict', 'ttl_seconds': settings.session_ttl_seconds,
                                 'distributed_rate_limit_configured': bool(settings.redis_url)},
            'cors_origins': origins, 'metrics_token_configured': bool(settings.metrics_token),
            'secrets_exposed': False, 'editable': False,
            'note': 'Read-only diagnostic summary. Secret values are never returned by this endpoint.',
            'source': 'runtime-configuration'}

@router.get('/workspace/stream')
async def workspace_stream(request: Request):
    """Cookie-authenticated SSE snapshots for the live workspace; no credentials in the URL."""
    require_admin(request)

    async def events():
        while not await request.is_disconnected():
            try:
                with SessionLocal() as db:
                    total_orgs = db.scalar(select(func.count()).select_from(Organization)) or 0
                    total_jobs = db.scalar(select(func.count()).select_from(IngestionJob)) or 0
                    completed = db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status.in_(['COMPLETED','COMPLETED_WITH_ERRORS']))) or 0
                    failed = db.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status.in_(['FAILED','ERROR']))) or 0
                    source_count = db.scalar(select(func.count()).select_from(RegistrySource).where(RegistrySource.enabled.is_(True))) or 0
                    jobs = db.scalars(select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(50)).all()
                    payload = {
                        'metrics': {'indexed_organizations': total_orgs, 'ingestion_jobs': total_jobs,
                            'completed_jobs': completed, 'failed_jobs': failed,
                            'enabled_sources_count': source_count, 'connected_sources_count': None, 'source': 'database'},
                        'jobs': [{'id': j.id, 'job_id': j.id, 'file_name': j.file_name, 'status': j.status,
                            'records_processed': int(j.records_processed or 0), 'records_inserted': int(j.records_inserted or 0),
                            'created_at': j.created_at.isoformat() if j.created_at else None,
                            'error_summary': j.error_summary, 'source_name': j.source_name} for j in jobs],
                        'generated_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
                    }
                yield 'event: workspace\ndata: ' + json.dumps(payload, separators=(',', ':')) + '\n\n'
            except Exception:
                _rate_logger.exception('workspace_sse_snapshot_failed')
                yield 'event: error\ndata: {"message":"Workspace snapshot temporarily unavailable"}\n\n'
            await asyncio.sleep(5)

    return StreamingResponse(events(), media_type='text/event-stream',
        headers={'Cache-Control':'no-cache, no-transform', 'X-Accel-Buffering':'no'})
