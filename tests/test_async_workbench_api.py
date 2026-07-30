from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_engine, reset_engine_for_tests
from app.main import app
from app.migrate import migrate_database
from app.models import ContentRun, RunStep, UploadAsset
from app.services import image_rules, state_service
from app.services.worker import get_worker
from app.time_utils import utc_now

PNG = b"\x89PNG\r\n\x1a\n" + b"test-image"


def _prepare(tmp_path: Path, monkeypatch) -> TestClient:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("WORKER_ENABLED", "false")
    monkeypatch.delenv("API_TOKEN", raising=False)
    get_settings.cache_clear()
    reset_engine_for_tests(f"sqlite:///{db_path}")
    migrate_database(f"sqlite:///{db_path}")
    get_worker().reset_for_tests()
    return TestClient(app)


def _create(client: TestClient, *, upload_asset_ids: list[int] | None = None):
    response = client.post(
        "/api/runs",
        json={
            "topic": "睡前20分钟改作文",
            "audience": "雅思 5.5 考生",
            "product_function": "Writing Checker",
            "pain_point": "作文改了很多遍还是不知道卡在哪",
            "style_preference": "备忘录聊天框风",
            "upload_asset_ids": upload_asset_ids or [],
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def _idempotency(value: str) -> dict[str, str]:
    return {"Idempotency-Key": value}


def test_full_mock_flow_has_two_gates_and_durable_steps(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    created = _create(client)
    assert created["status"] == "queued"
    assert created["drafts"] == []

    assert get_worker().run_once() is True
    text_ready = client.get(f"/api/runs/{created['id']}").json()
    assert text_ready["status"] == "copy_review_required"
    assert len(text_ready["drafts"]) == 3
    assert not text_ready["images"]
    assert all(step["attempt"] == 1 for step in text_ready["steps"])
    assert all(step["started_at"] and step["completed_at"] for step in text_ready["steps"])

    selected_id = text_ready["drafts"][1]["id"]
    selected = client.post(
        f"/api/runs/{created['id']}/selection",
        json={"draft_id": selected_id},
        headers=_idempotency("select-1"),
    )
    assert selected.status_code == 200
    revised = client.post(
        f"/api/runs/{created['id']}/revisions",
        json={"instructions": "更口语一点"},
        headers=_idempotency("revise-1"),
    )
    assert revised.status_code == 200
    assert revised.json()["draft_id"] != selected_id

    approved = client.post(
        f"/api/runs/{created['id']}/copy-approval",
        headers=_idempotency("copy-1"),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "image_queued"
    assert get_worker().run_once() is True

    assets_ready = client.get(f"/api/runs/{created['id']}").json()
    assert assets_ready["status"] == "asset_review_required"
    assert assets_ready["images"]
    assert all("file_path" not in item and item["url"] for item in assets_ready["images"])
    asset = client.get(assets_ready["images"][0]["url"])
    assert asset.status_code == 200
    other_run = _create(client)
    assert (
        client.get(
            f"/api/runs/{other_run['id']}/assets/{assets_ready['images'][0]['id']}"
        ).status_code
        == 404
    )

    completed = client.post(
        f"/api/runs/{created['id']}/asset-approval",
        headers=_idempotency("asset-1"),
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    detail = client.get(f"/api/runs/{created['id']}").json()
    assert detail["final_package"] == {
        "markdown_url": f"/api/runs/{created['id']}/exports/markdown",
        "json_url": f"/api/runs/{created['id']}/exports/json",
        "zip_url": f"/api/runs/{created['id']}/exports/zip",
    }
    assert client.get(detail["final_package"]["zip_url"]).status_code == 200


def test_idempotency_replays_original_and_rejects_key_reuse(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    detail = client.get(f"/api/runs/{run['id']}").json()
    first_id, second_id = detail["drafts"][0]["id"], detail["drafts"][1]["id"]

    first = client.post(
        f"/api/runs/{run['id']}/selection",
        json={"draft_id": first_id},
        headers=_idempotency("same-key"),
    )
    replay = client.post(
        f"/api/runs/{run['id']}/selection",
        json={"draft_id": first_id},
        headers=_idempotency("same-key"),
    )
    conflict = client.post(
        f"/api/runs/{run['id']}/selection",
        json={"draft_id": second_id},
        headers=_idempotency("same-key"),
    )
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert conflict.status_code == 409


def test_illegal_transitions_and_cancel_are_conflicts_or_idempotent(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    illegal = client.post(
        f"/api/runs/{run['id']}/copy-approval", headers=_idempotency("too-soon")
    )
    assert illegal.status_code == 409

    canceled = client.post(
        f"/api/runs/{run['id']}/cancel", headers=_idempotency("cancel-1")
    )
    replay = client.post(
        f"/api/runs/{run['id']}/cancel", headers=_idempotency("cancel-1")
    )
    assert canceled.status_code == replay.status_code == 200
    assert canceled.json() == replay.json()
    assert get_worker().run_once() is False
    assert client.post(f"/api/runs/{run['id']}/retry").status_code == 409


def test_cancel_during_provider_work_wins_over_worker_completion(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    client.post(f"/api/runs/{run['id']}/copy-approval")
    original = image_rules.generate_image_assets

    def cancel_then_generate(run_id, prompts):
        with Session(get_engine()) as other_session:
            state_service.cancel(other_session, run_id)
        return original(run_id, prompts)

    monkeypatch.setattr(image_rules, "generate_image_assets", cancel_then_generate)
    get_worker().run_once()
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["status"] == "canceled"
    assert detail["images"] == []


def test_failure_retry_resumes_failed_phase_without_repeating_text(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    text_steps_before = client.get(f"/api/runs/{run['id']}").json()["steps"]
    client.post(f"/api/runs/{run['id']}/copy-approval")

    monkeypatch.setenv("IMAGE_PROVIDER", "broken-provider")
    get_settings.cache_clear()
    assert get_worker().run_once() is True
    failed = client.get(f"/api/runs/{run['id']}").json()
    assert failed["status"] == "failed"
    assert "unsupported image provider" in failed["error"]
    assert not failed["images"]

    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    get_settings.cache_clear()
    retried = client.post(f"/api/runs/{run['id']}/retry", headers=_idempotency("retry-1"))
    assert retried.status_code == 200
    assert retried.json()["status"] == "image_queued"
    get_worker().run_once()
    final = client.get(f"/api/runs/{run['id']}").json()
    assert final["status"] == "asset_review_required"
    assert [s["name"] for s in final["steps"]].count("candidate_round") == 1
    assert len([s for s in final["steps"] if s["name"] == "image_generation"]) == 2
    assert len(text_steps_before) < len(final["steps"])


def test_startup_recovery_requeues_stale_work_and_does_not_repeat_completed(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    first = _create(client)
    second = _create(client)
    with Session(get_engine()) as session:
        run1 = session.get(ContentRun, first["id"])
        run2 = session.get(ContentRun, second["id"])
        assert run1 and run2
        run1.status = "running"
        run1.heartbeat_at = utc_now() - timedelta(hours=1)
        run2.status = "image_running"
        run2.heartbeat_at = utc_now() - timedelta(hours=1)
        session.add(run1)
        session.add(run2)
        session.commit()

    assert get_worker().recover_stale() == 2
    with Session(get_engine()) as session:
        assert session.get(ContentRun, first["id"]).status == "queued"
        assert session.get(ContentRun, second["id"]).status == "image_queued"


def test_upload_validation_assignment_and_cross_run_protection(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    uploaded = client.post(
        "/api/uploads", files={"file": ("reference.png", PNG, "image/png")}
    )
    assert uploaded.status_code == 201, uploaded.text
    upload = uploaded.json()
    assert "file_path" not in upload
    stored_name = Path(upload["url"]).name
    assert stored_name != "reference.png"

    spoof = client.post(
        "/api/uploads", files={"file": ("fake.png", b"not-png", "image/png")}
    )
    bad_extension = client.post(
        "/api/uploads", files={"file": ("fake.txt", PNG, "image/png")}
    )
    bad_mime = client.post(
        "/api/uploads", files={"file": ("fake.png", PNG, "image/jpeg")}
    )
    assert spoof.status_code == bad_extension.status_code == bad_mime.status_code == 400

    run1 = _create(client, upload_asset_ids=[upload["id"]])
    run2 = _create(client)
    assert client.get(f"/api/runs/{run1['id']}/uploads/{upload['id']}").status_code == 200
    assert client.get(f"/api/runs/{run2['id']}/uploads/{upload['id']}").status_code == 404
    duplicate = client.post(
        "/api/runs",
        json={
            "topic": "x", "audience": "x", "product_function": "x", "pain_point": "x",
            "upload_asset_ids": [upload["id"]],
        },
    )
    assert duplicate.status_code == 409
    arbitrary_path = client.post(
        "/api/runs",
        json={
            "topic": "x",
            "audience": "x",
            "product_function": "x",
            "pain_point": "x",
            "reference_path": "../../secret.png",
        },
    )
    assert arbitrary_path.status_code == 422

    with Session(get_engine()) as session:
        row = session.get(UploadAsset, upload["id"])
        assert row and Path(row.file_path).resolve().is_relative_to(
            get_settings().upload_root.resolve()
        )


def test_upload_size_limit_and_containment(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    too_large = client.post(
        "/api/uploads",
        files={"file": ("large.webp", b"RIFF" + b"x" * (10 * 1024 * 1024) + b"WEBP", "image/webp")},
    )
    assert too_large.status_code == 413

    uploaded = client.post(
        "/api/uploads", files={"file": ("ok.png", PNG, "image/png")}
    ).json()
    run = _create(client, upload_asset_ids=[uploaded["id"]])
    with Session(get_engine()) as session:
        row = session.get(UploadAsset, uploaded["id"])
        assert row
        row.file_path = str(tmp_path / "outside.png")
        session.add(row)
        session.commit()
    assert client.get(f"/api/runs/{run['id']}/uploads/{uploaded['id']}").status_code == 400


def test_list_runs_filters_and_paginates_newest_first(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    ids = [_create(client)["id"] for _ in range(4)]
    client.post(f"/api/runs/{ids[0]}/cancel")
    page = client.get("/api/runs", params={"status": "queued", "limit": 2, "offset": 1})
    assert page.status_code == 200
    assert [item["id"] for item in page.json()["items"]] == [ids[2], ids[1]]
    assert page.json()["total"] == 3


def test_step_failure_records_attempt_timing_and_error(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "unknown")
    get_settings.cache_clear()
    run = _create(client)
    get_worker().run_once()
    with Session(get_engine()) as session:
        steps = session.exec(
            select(RunStep).where(RunStep.run_id == run["id"], RunStep.status == "failed")
        ).all()
    assert len(steps) == 1
    assert steps[0].attempt == 1
    assert steps[0].started_at and steps[0].completed_at and steps[0].duration_ms is not None
    assert "unsupported LLM provider" in (steps[0].error or "")
