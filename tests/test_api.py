from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import reset_engine_for_tests
from app.main import app
from app.migrate import migrate_database
from app.services.worker import get_worker


def _prepare_test_app(tmp_path, monkeypatch):
    database = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.delenv("API_TOKEN", raising=False)
    get_settings.cache_clear()
    reset_engine_for_tests(f"sqlite:///{database}")
    migrate_database(f"sqlite:///{database}")
    get_worker().reset_for_tests()


def test_app_startup_does_not_create_unmigrated_schema(tmp_path, monkeypatch):
    database = tmp_path / "unmigrated.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.setenv("WORKER_ENABLED", "true")
    monkeypatch.delenv("API_TOKEN", raising=False)
    get_settings.cache_clear()
    reset_engine_for_tests(f"sqlite:///{database}")

    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"ok": True}

    assert not database.exists()


def test_old_generic_review_endpoint_is_removed(tmp_path, monkeypatch):
    _prepare_test_app(tmp_path, monkeypatch)
    client = TestClient(app)
    response = client.post("/api/runs/1/review", json={"action": "approve"})
    assert response.status_code == 404


def test_api_token_is_required_when_configured(tmp_path, monkeypatch):
    _prepare_test_app(tmp_path, monkeypatch)
    monkeypatch.setenv("API_TOKEN", "secret-token")
    get_settings.cache_clear()
    client = TestClient(app)

    blocked = client.get("/api/runs/1")
    assert blocked.status_code == 401

    allowed = client.get("/api/runs/1", headers={"authorization": "Bearer secret-token"})
    assert allowed.status_code == 404
