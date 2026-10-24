import time

from fastapi.testclient import TestClient

from src import admin_auth
from src.config import settings
from src.database import Base, engine
from src.main import app

Base.metadata.create_all(engine)


def test_workspace_overview_endpoints_require_operator_session(monkeypatch):
    monkeypatch.setattr(settings, "admin_password_hash", admin_auth.hash_password("workspace-test-password", iterations=1000))
    monkeypatch.setattr(settings, "session_secret", "s" * 48)
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(settings, "app_env", "test")
    admin_auth._attempts.clear()
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/workspace/metrics").status_code == 401
        login = client.post("/api/v1/admin/login", json={"password": "workspace-test-password"})
        assert login.status_code == 200
        assert client.get("/api/v1/admin/workspace/metrics").status_code == 200
        searched_jobs = client.get("/api/v1/admin/ingestion/jobs?page=1&page_size=25&q=definitely-no-matching-job-7d3c").json()
        assert searched_jobs["items"] == [] and searched_jobs["total"] == 0
        metrics = client.get("/api/v1/admin/workspace/metrics").json()
        assert {"indexed_organizations", "ingestion_jobs", "completed_jobs", "failed_jobs", "connected_sources_count"} <= set(metrics)
        activity = client.get("/api/v1/admin/ingestion/activity").json()
        assert isinstance(activity.get("items"), list)
        quality = client.get("/api/v1/admin/registry/overview").json()
        assert "completeness_percentage" in quality
        assert quality["source"] == "database"
        data_quality = client.get("/api/v1/admin/data-quality/overview")
        assert data_quality.status_code == 200
        assert "required_fields" in data_quality.json()
        warehouse = client.get("/api/v1/admin/warehouse/overview")
        assert warehouse.status_code == 200
        assert isinstance(warehouse.json().get("imports"), list)
        rules = client.get("/api/v1/admin/validation/rules")
        assert rules.status_code == 200
        assert rules.json()["editable"] is False
        audit = client.get("/api/v1/admin/audit/logs")
        assert audit.status_code == 200
        assert isinstance(audit.json().get("items"), list)
        settings_response = client.get("/api/v1/admin/settings/overview")
        assert settings_response.status_code == 200
        assert settings_response.json()["secrets_exposed"] is False
        with client.stream("GET", "/api/v1/admin/workspace/stream") as stream:
            assert stream.status_code == 200
            assert "text/event-stream" in stream.headers["content-type"]
            first_event = next(stream.iter_text())
            assert "event: workspace" in first_event
            assert "data: " in first_event


def test_sliding_session_renews_cookie_and_preserves_csrf(monkeypatch):
    monkeypatch.setattr(settings, "admin_password_hash", admin_auth.hash_password("workspace-test-password", iterations=1000))
    monkeypatch.setattr(settings, "session_secret", "s" * 48)
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(settings, "app_env", "test")
    with TestClient(app) as client:
        login = client.post("/api/v1/admin/login", json={"password": "workspace-test-password"})
        csrf = login.json()["csrf_token"]
        before = admin_auth.decode_session_token(client.cookies.get(admin_auth.COOKIE_NAME))
        time.sleep(1)
        response = client.get("/api/v1/admin/workspace/metrics")
        after = admin_auth.decode_session_token(client.cookies.get(admin_auth.COOKIE_NAME))
        assert response.status_code == 200
        assert after["csrf"] == csrf
        assert after["exp"] >= before["exp"]
