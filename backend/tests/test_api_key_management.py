import time
import json

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import api_keys
from src.api_keys import CreateApiKey, _create_key, require_user_claims, rotate_api_key, list_api_keys, list_key_audit, current_identity, revoke_api_key
from src.config import settings
from src.database import Base
from src.models import ApiKey, ApiKeyAuditEvent

SECRET = 'k' * 48


@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


def _claims(**overrides):
    claims = {'sub': 'user-1', 'org_id': 'org-1', 'roles': ['owner'], 'organization_verified': True, 'exp': time.time() + 600}
    claims.update(overrides)
    return claims


def test_rotation_is_atomic_when_the_replacement_is_refused(db):
    created = _create_key(db, _claims(), CreateApiKey(name='Live', environment='production', expires_in_days=30))
    with pytest.raises(HTTPException) as refused:
        rotate_api_key(created['id'], claims=_claims(organization_verified=False), db=db)
    assert refused.value.status_code == 403
    db.expire_all()
    assert db.get(ApiKey, created['id']).status == 'active', 'the old key must keep working when rotation fails'
    assert db.scalar(select(ApiKeyAuditEvent).where(ApiKeyAuditEvent.action == 'api_key.rotated_revoked')) is None


def test_successful_rotation_revokes_old_key_and_issues_a_new_one(db):
    created = _create_key(db, _claims(), CreateApiKey(name='Sandbox', environment='sandbox', scopes=['registry:read', 'sources:read']))
    rotated = rotate_api_key(created['id'], claims=_claims(), db=db)
    assert rotated['id'] != created['id'] and rotated['secret'].startswith('pg_sandbox_')
    assert rotated['scopes'] == ['registry:read', 'sources:read'] and rotated['expires_at'] is None
    db.expire_all()
    assert db.get(ApiKey, created['id']).status == 'revoked' and db.get(ApiKey, rotated['id']).status == 'active'


def test_rotation_drops_legacy_ingestion_scopes(db):
    legacy = ApiKey(id='legacy', organization_id='org-1', created_by_user_id='u', name='old', environment='sandbox', key_prefix='pg_sandbox_legacy',
                    secret_hash='0' * 64, scopes=['registry:read', 'ingestion:write'], status='active')
    db.add(legacy); db.commit()
    assert rotate_api_key('legacy', claims=_claims(), db=db)['scopes'] == ['registry:read']


@pytest.mark.parametrize('scope', ['ingestion:write', 'ingestion:read', 'admin'])
def test_customers_cannot_request_ingestion_scopes(db, scope):
    with pytest.raises(HTTPException) as refused:
        _create_key(db, _claims(), CreateApiKey(name='Nope', environment='sandbox', scopes=[scope]))
    assert refused.value.status_code == 422

@pytest.mark.parametrize('roles', [['member'], [], None, {'unexpected': 'shape'}])
def test_non_admin_or_malformed_role_claims_cannot_create_api_keys(db, roles):
    with pytest.raises(HTTPException) as refused:
        _create_key(db, _claims(roles=roles), CreateApiKey(name='No privilege', environment='sandbox'))
    assert refused.value.status_code == 403
    assert db.scalar(select(func.count()).select_from(ApiKey)) == 0


def test_api_key_creation_accepts_normalized_owner_role(db):
    created = _create_key(db, _claims(roles=['OWNER']), CreateApiKey(name='Owner key', environment='sandbox'))
    assert created['environment'] == 'sandbox'


def test_unverified_organization_cannot_create_production_key(db):
    with pytest.raises(HTTPException) as refused:
        _create_key(db, _claims(organization_verified=False), CreateApiKey(name='Unverified', environment='production', expires_in_days=30))
    assert refused.value.status_code == 403
    assert db.scalar(select(func.count()).select_from(ApiKey)) == 0


# --- JWT validation
@pytest.fixture
def jwt_settings(monkeypatch):
    monkeypatch.setattr(settings, 'api_key_auth_jwt_secret', SECRET)
    monkeypatch.setattr(settings, 'api_key_auth_jwt_keys_json', '')
    monkeypatch.setattr(settings, 'api_key_auth_jwt_active_kid', 'current')
    monkeypatch.setattr(settings, 'api_key_auth_jwt_issuer', 'pesaguard')
    monkeypatch.setattr(settings, 'api_key_auth_jwt_audience', 'datasource')


def _token(secret=SECRET, algorithm='HS256', **overrides):
    now = int(time.time())
    claims = {'sub': 'u1', 'org_id': 'o1', 'tenant_id': 'tenant-o1', 'type': 'access', 'jti': 'token-1', 'iat': now, 'nbf': now - 1, 'auth_version': 1, 'scope': 'registry:read', 'iss': 'pesaguard', 'aud': 'datasource', 'exp': now + 300}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    headers = {'kid': 'current'} if algorithm == 'HS256' else None
    return 'Bearer ' + jwt.encode(claims, None if algorithm == 'none' else secret, algorithm=algorithm, headers=headers)


def test_valid_token_is_accepted(jwt_settings):
    assert require_user_claims(_token())['org_id'] == 'o1'


@pytest.mark.parametrize('header,status', [
    (lambda: _token(secret='z' * 48), 401),
    (lambda: _token(exp=int(time.time()) - 5), 401),
    (lambda: _token(exp=None), 401),
    (lambda: _token(aud='someone-else'), 401),
    (lambda: _token(iss='attacker'), 401),
    (lambda: _token(org_id=None, tenant_id=None), 401),
    (lambda: _token(type='refresh'), 401),
    (lambda: _token(tenant_id=None), 401),
    (lambda: 'Bearer ' + jwt.encode({'sub': 'u', 'org_id': 'o', 'exp': int(time.time()) + 60}, None, algorithm='none'), 401),
    (lambda: 'Bearer not.a.jwt', 401),
    (lambda: None, 401),
])
def test_invalid_tokens_are_rejected(jwt_settings, header, status):
    with pytest.raises(HTTPException) as refused:
        require_user_claims(header())
    assert refused.value.status_code == status


def test_production_requires_issuer_and_audience(monkeypatch):
    monkeypatch.setattr(settings, 'api_key_auth_jwt_secret', SECRET)
    monkeypatch.setattr(settings, 'api_key_auth_jwt_issuer', '')
    monkeypatch.setattr(settings, 'api_key_auth_jwt_audience', '')
    monkeypatch.setattr(settings, 'app_env', 'production')
    with pytest.raises(HTTPException) as refused:
        require_user_claims(_token())
    assert refused.value.status_code == 503
    assert api_keys.ALLOWED_SCOPES == {'registry:read', 'sources:read'}


def test_pesaguard_rotating_jwt_key_id_is_honoured(monkeypatch):
    active = 'a' * 48
    previous = 'b' * 48
    monkeypatch.setattr(settings, 'api_key_auth_jwt_secret', '')
    monkeypatch.setattr(settings, 'api_key_auth_jwt_keys_json', json.dumps({'active-2026': active, 'previous-2025': previous}))
    monkeypatch.setattr(settings, 'api_key_auth_jwt_active_kid', 'active-2026')
    monkeypatch.setattr(settings, 'api_key_auth_jwt_issuer', 'pesaguard')
    monkeypatch.setattr(settings, 'api_key_auth_jwt_audience', 'datasource')
    now = int(time.time())
    claims = {'sub':'u1','organization_id':'org-rotated','tenant_id':'tenant-rotated','type':'access',
              'jti':'rotated-token','iat':now,'nbf':now-1,'auth_version':1,'scope':'registry:read',
              'iss':'pesaguard','aud':'datasource','exp':now+300}
    token = 'Bearer ' + jwt.encode(claims, previous, algorithm='HS256', headers={'kid':'previous-2025'})
    assert require_user_claims(token)['org_id'] == 'org-rotated'


def test_refresh_token_is_not_accepted_as_customer_identity(jwt_settings):
    with pytest.raises(HTTPException) as refused:
        require_user_claims(_token(type='refresh'))
    assert refused.value.status_code == 401


def test_key_and_audit_lists_are_scoped_to_authenticated_tenant(db):
    first = _create_key(db, _claims(org_id='tenant-a'), CreateApiKey(name='Tenant A', environment='sandbox'))
    _create_key(db, _claims(org_id='tenant-b', sub='user-b'), CreateApiKey(name='Tenant B', environment='sandbox'))
    assert [item['id'] for item in list_api_keys(claims=_claims(org_id='tenant-a'), db=db)['items']] == [first['id']]
    audit = list_key_audit(claims=_claims(org_id='tenant-a'), db=db, limit=100)
    assert audit['items'] and all(item.get('action') == 'api_key.created' for item in audit['items'])
    assert current_identity(claims=_claims(org_id='tenant-a', tenant_id='tenant-a'))['organization_id'] == 'tenant-a'


def test_pesaguard_organization_id_claim_is_used_as_key_partition(jwt_settings):
    token = _token(org_id=None, organization_id='org-from-pesaguard')
    assert require_user_claims(token)['org_id'] == 'org-from-pesaguard'


def test_access_token_without_organization_or_tenant_is_rejected(jwt_settings):
    with pytest.raises(HTTPException) as refused:
        require_user_claims(_token(org_id=None, tenant_id=None))
    assert refused.value.status_code == 401


def test_cross_tenant_rotate_and_revoke_are_not_found(db):
    created = _create_key(db, _claims(org_id='tenant-a'), CreateApiKey(name='Tenant A key', environment='sandbox'))
    with pytest.raises(HTTPException) as rotate_refused:
        rotate_api_key(created['id'], claims=_claims(org_id='tenant-b', sub='user-b'), db=db)
    assert rotate_refused.value.status_code == 404
    with pytest.raises(HTTPException) as revoke_refused:
        revoke_api_key(created['id'], claims=_claims(org_id='tenant-b', sub='user-b'), db=db)
    assert revoke_refused.value.status_code == 404
    db.expire_all()
    assert db.get(ApiKey, created['id']).status == 'active'
