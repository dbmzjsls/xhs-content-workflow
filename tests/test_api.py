import json

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import get_settings
from app.db import get_engine, init_db, reset_engine_for_tests
from app.main import app
from app.repositories import runs as repo


def _prepare_test_app(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    export_dir = tmp_path / "exports"
    cover_dir = tmp_path / "covers" / "备忘录聊天框风"
    product_dir = tmp_path / "product" / "screenshots"
    cover_dir.mkdir(parents=True)
    product_dir.mkdir(parents=True)
    (cover_dir / "cover.png").write_bytes(b"fake")
    (product_dir / "ui.png").write_bytes(b"fake")
    monkeypatch.setenv("EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("CATHOVEN_COVER_REFERENCE_DIR", str(tmp_path / "covers"))
    monkeypatch.setenv("CATHOVEN_PRODUCT_REFERENCE_DIR", str(tmp_path / "product"))
    monkeypatch.delenv("API_TOKEN", raising=False)
    reset_engine_for_tests(f"sqlite:///{db_path}")
    get_settings.cache_clear()
    init_db()
    return export_dir


def test_create_review_and_export(tmp_path, monkeypatch):
    export_dir = _prepare_test_app(tmp_path, monkeypatch)

    client = TestClient(app)
    response = client.post("/api/runs", json={
        "topic": "睡前20分钟改作文",
        "audience": "雅思 5.5 考生",
        "product_function": "Writing Checker",
        "pain_point": "作文改了很多遍还是不知道卡在哪",
        "style_preference": "备忘录聊天框风",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "review_required"
    assert body["drafts"]
    assert body["images"]
    run_id = body["id"]

    pre_export = client.get(f"/api/runs/{run_id}/export")
    assert pre_export.status_code == 409
    assert not (export_dir / str(run_id) / "发布包.zip").exists()

    review = client.post(f"/api/runs/{run_id}/review", json={"action": "approve"})
    assert review.status_code == 200, review.text
    assert review.json()["result"]["zip"].endswith("发布包.zip")

    exported = client.get(f"/api/runs/{run_id}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")

    package_json = export_dir / str(run_id) / "package.json"
    package_md = export_dir / str(run_id) / "发布包.md"
    payload = json.loads(package_json.read_text(encoding="utf-8"))
    assert payload["references"]
    assert "参考图选择" in package_md.read_text(encoding="utf-8")


def test_export_rejects_package_path_outside_run_dir(tmp_path, monkeypatch):
    _prepare_test_app(tmp_path, monkeypatch)
    client = TestClient(app)
    response = client.post("/api/runs", json={
        "topic": "睡前20分钟改作文",
        "audience": "雅思 5.5 考生",
        "product_function": "Writing Checker",
        "pain_point": "作文改了很多遍还是不知道卡在哪",
        "style_preference": "备忘录聊天框风",
    })
    run_id = response.json()["id"]
    secret_zip = tmp_path / "secret.zip"
    secret_zip.write_bytes(b"not really a zip")
    with Session(get_engine()) as session:
        repo.update_run(session, run_id, final_package={"zip": str(secret_zip)})

    exported = client.get(f"/api/runs/{run_id}/export")
    assert exported.status_code == 400


def test_replace_review_requires_valid_replacement(tmp_path, monkeypatch):
    _prepare_test_app(tmp_path, monkeypatch)
    client = TestClient(app)
    response = client.post("/api/runs", json={
        "topic": "睡前20分钟改作文",
        "audience": "雅思 5.5 考生",
        "product_function": "Writing Checker",
        "pain_point": "作文改了很多遍还是不知道卡在哪",
        "style_preference": "备忘录聊天框风",
    })
    run_id = response.json()["id"]

    missing = client.post(f"/api/runs/{run_id}/review", json={"action": "replace"})
    assert missing.status_code == 422

    too_short = client.post(
        f"/api/runs/{run_id}/review",
        json={"action": "replace", "replacement": {"title": "替换稿", "body": "太短"}},
    )
    assert too_short.status_code == 422


def test_api_token_is_required_when_configured(tmp_path, monkeypatch):
    _prepare_test_app(tmp_path, monkeypatch)
    monkeypatch.setenv("API_TOKEN", "secret-token")
    get_settings.cache_clear()
    client = TestClient(app)

    blocked = client.get("/api/runs/1")
    assert blocked.status_code == 401

    allowed = client.get("/api/runs/1", headers={"authorization": "Bearer secret-token"})
    assert allowed.status_code == 404
