import time

import pytest
from fastapi.testclient import TestClient

from src import admin_auth
from src.config import settings
from src.database import Base, engine
from src.main import app

Base.metadata.create_all(engine)
PASSWORD = 'correct horse battery staple'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, 'admin_password_hash', admin_auth.hash_password(PASSWORD, iterations=1000))
    monkeypatch.setattr(settings, 'session_secret', 's' * 48)
    monkeypatch.setattr(settings, 'session_cookie_secure', False)
    monkeypatch.setattr(settings, 'admin_login_max_attempts_per_minute', 5)
    monkeypatch.setattr(settings, 'redis_url', '')
    monkeypatch.setattr(settings, 'app_env', 'test')
    admin_auth._attempts.clear()
    return TestClient(app)


def _login(client, password=PASSWORD):
    return client.post('/api/v1/admin/login', json={'password': password})


def test_password_hash_roundtrip_and_rejects_garbage():
    encoded = admin_auth.hash_password('a-long-password', iterations=1000)
    assert admin_auth.verify_password('a-long-password', encoded)
    assert not admin_auth.verify_password('wrong', encoded)
    assert not admin_auth.verify_password('a-long-password', 'not-a-hash')


def test_login_requires_configuration_and_correct_password(client, monkeypatch):
    assert _login(client, 'wrong').status_code == 401
    monkeypatch.setattr(settings, 'admin_password_hash', '')
    assert _login(client).status_code == 503


def test_session_cookie_is_httponly_samesite_strict_and_grants_dashboard_access(client):
    response = _login(client)
    assert response.status_code == 200 and response.json()['csrf_token']
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie
    assert 'pg_admin_session' not in response.text  # the token is never exposed to page JavaScript
    assert client.get('/api/v1/organizations').status_code == 200
    assert client.get('/api/v1/admin/session').json()['authenticated'] is True


def test_cookie_authenticated_writes_require_the_csrf_token(client):
    csrf = _login(client).json()['csrf_token']
    body = {'source_key': 'csrf-' + str(int(time.time() * 1000)), 'display_name': 'CSRF test'}
    assert client.post('/api/v1/sources', json=body).status_code == 403
    assert client.post('/api/v1/sources', json=body, headers={'X-CSRF-Token': 'wrong'}).status_code == 403
    assert client.post('/api/v1/sources', json=body, headers={'X-CSRF-Token': csrf}).status_code == 201


def test_tampered_expired_and_logged_out_sessions_are_rejected(client):
    _login(client)
    token = client.cookies.get('pg_admin_session')
    for bad in (token[:-2] + 'xx', 'garbage', ''):
        fresh = TestClient(app)
        fresh.cookies.set('pg_admin_session', bad)
        assert fresh.get('/api/v1/organizations').status_code == 401
    expired, _ = admin_auth.issue_session_token(now=time.time() - 10 * settings.session_ttl_seconds)
    fresh = TestClient(app)
    fresh.cookies.set('pg_admin_session', expired)
    assert fresh.get('/api/v1/organizations').status_code == 401
    assert client.post('/api/v1/admin/logout').status_code == 403  # logout is a cookie-authenticated state change
    csrf = client.get('/api/v1/admin/session').json()['csrf_token']
    assert client.post('/api/v1/admin/logout', headers={'X-CSRF-Token': csrf}).status_code == 204
    assert client.get('/api/v1/organizations').status_code == 401


def test_login_is_rate_limited(client):
    codes = [_login(client, 'wrong').status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_session_secret_must_be_long_when_login_is_enabled(monkeypatch):
    from src.config import validate_runtime_config
    monkeypatch.setattr(settings, 'admin_password_hash', 'x')
    monkeypatch.setattr(settings, 'session_secret', 'short')
    with pytest.raises(RuntimeError):
        validate_runtime_config()


def test_production_login_fails_closed_when_redis_is_unavailable(client, monkeypatch):
    import redis
    monkeypatch.setattr(settings, 'app_env', 'production')
    monkeypatch.setattr(settings, 'redis_url', 'redis://unavailable.invalid:6379/0')
    def unavailable(*args, **kwargs):
        raise redis.ConnectionError('simulated redis outage')
    monkeypatch.setattr(redis.Redis, 'from_url', unavailable)
    response = _login(client)
    assert response.status_code == 503
    assert 'rate limiter' in response.json()['detail'].lower()
