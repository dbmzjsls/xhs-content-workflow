from __future__ import annotations

import json
import zipfile
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from threading import Event, Thread

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_engine, reset_engine_for_tests
from app.main import app
from app.migrate import migrate_database
from app.models import (
    ContentRun,
    IdempotencyRecord,
    ImageAsset,
    ReviewAction,
    RunStep,
    UploadAsset,
)
from app.repositories import runs as repo
from app.schemas import RunCreate
from app.security import redact_internal_error
from app.services import content_pipeline, execution_service, image_rules, state_service
from app.services.worker import get_worker
from app.time_utils import utc_now

PNG = b"\x89PNG\r\n\x1a\n" + b"test-image"


def _prepare(tmp_path: Path, monkeypatch) -> TestClient:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "uploads"))
    cover_dir = tmp_path / "covers" / "备忘录聊天框风"
    product_dir = tmp_path / "product" / "screenshots"
    cover_dir.mkdir(parents=True)
    product_dir.mkdir(parents=True)
    (cover_dir / "cover.png").write_bytes(PNG)
    (product_dir / "ui.png").write_bytes(PNG)
    monkeypatch.setenv("CATHOVEN_COVER_REFERENCE_DIR", str(tmp_path / "covers"))
    monkeypatch.setenv("CATHOVEN_PRODUCT_REFERENCE_DIR", str(tmp_path / "product"))
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
    assert text_ready["current_step"] == "copy_review"
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
    assert assets_ready["current_step"] == "asset_review"
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


def test_hard_rule_failure_cannot_be_selected_or_approved(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    with Session(get_engine()) as session:
        drafts = repo.list_drafts(session, run["id"])
        failing = drafts[0]
        failing.quality_report = {"hard": {"passed": False, "issues": ["forced"]}}
        failing.selected = False
        session.add(failing)
        session.commit()
        failing_id = failing.id

    rejected = client.post(
        f"/api/runs/{run['id']}/selection",
        json={"draft_id": failing_id},
        headers=_idempotency("reject-hard-fail"),
    )
    assert rejected.status_code == 409

    with Session(get_engine()) as session:
        for draft in repo.list_drafts(session, run["id"]):
            draft.selected = False
            draft.quality_report = {"hard": {"passed": False, "issues": ["forced"]}}
            session.add(draft)
        session.commit()
    bypass = client.post(
        f"/api/runs/{run['id']}/copy-approval",
        headers=_idempotency("reject-approval-bypass"),
    )
    assert bypass.status_code == 409


def test_retry_persisted_round_without_recommendation_stays_failed(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    original = content_pipeline.generate_candidate_round

    def no_recommendation(brief):
        result = original(brief)
        result["recommended_candidate"] = None
        for candidate in result["candidates"]:
            candidate["recommended"] = False
            candidate["hard_report"] = {"passed": False, "issues": ["forced"]}
            candidate["score_report"]["hard_passed"] = False
        return result

    monkeypatch.setattr(content_pipeline, "generate_candidate_round", no_recommendation)
    run = _create(client)
    get_worker().run_once()
    assert client.get(f"/api/runs/{run['id']}").json()["status"] == "failed"

    assert client.post(f"/api/runs/{run['id']}/retry").json()["status"] == "queued"
    get_worker().run_once()
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["status"] == "failed"
    assert [step["name"] for step in detail["steps"]].count("candidate_round") == 1
    attempts = [step for step in detail["steps"] if step["name"] == "text_generation"]
    assert [step["attempt"] for step in attempts] == [1, 2]
    assert all(step["status"] == "failed" for step in attempts)


def test_cancel_wins_when_provider_raises_after_cancellation(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    client.post(f"/api/runs/{run['id']}/copy-approval")
    entered = Event()
    release = Event()

    def failing_provider(run_id, prompts):
        entered.set()
        assert release.wait(5)
        raise RuntimeError("provider failed after cancellation")

    monkeypatch.setattr(image_rules, "generate_image_assets", failing_provider)
    thread = Thread(target=get_worker().run_once)
    thread.start()
    assert entered.wait(5)
    canceled = client.post(f"/api/runs/{run['id']}/cancel")
    assert canceled.status_code == 200
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["status"] == "canceled"
    assert detail["images"] == []


def test_cancel_at_atomic_image_publish_leaves_no_asset_rows(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    client.post(f"/api/runs/{run['id']}/copy-approval")

    def cancel_before_publish(run_id):
        with Session(get_engine()) as other:
            state_service.cancel(other, run_id)

    monkeypatch.setattr(
        execution_service, "_before_image_publish", cancel_before_publish, raising=False
    )
    get_worker().run_once()
    with Session(get_engine()) as session:
        rows = session.exec(select(ImageAsset).where(ImageAsset.run_id == run["id"])).all()
        status = session.get(ContentRun, run["id"]).status
    assert status == "canceled"
    assert rows == []


def test_idempotent_business_action_rolls_back_as_one_unit(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    detail = client.get(f"/api/runs/{run['id']}").json()
    original_id = next(d["id"] for d in detail["drafts"] if d["selected"])
    replacement_id = next(d["id"] for d in detail["drafts"] if d["id"] != original_id)

    def fail_before_commit(session):
        raise RuntimeError("simulated commit boundary failure")

    monkeypatch.setattr(
        state_service, "_before_transaction_commit", fail_before_commit, raising=False
    )
    failing_client = TestClient(app, raise_server_exceptions=False)
    failed = failing_client.post(
        f"/api/runs/{run['id']}/selection",
        json={"draft_id": replacement_id},
        headers=_idempotency("atomic-selection"),
    )
    assert failed.status_code == 500
    with Session(get_engine()) as session:
        selected = repo.get_selected_or_recommended_draft(session, run["id"])
        actions = session.exec(select(ReviewAction).where(ReviewAction.run_id == run["id"])).all()
        idem = session.exec(
            select(IdempotencyRecord).where(IdempotencyRecord.key == "atomic-selection")
        ).first()
    assert selected.id == original_id
    assert actions == []
    assert idem is None

    monkeypatch.delattr(state_service, "_before_transaction_commit", raising=False)
    first = client.post(
        f"/api/runs/{run['id']}/selection",
        json={"draft_id": replacement_id},
        headers=_idempotency("atomic-selection"),
    )
    replay = client.post(
        f"/api/runs/{run['id']}/selection",
        json={"draft_id": replacement_id},
        headers=_idempotency("atomic-selection"),
    )
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    with Session(get_engine()) as session:
        assert len(
            session.exec(select(ReviewAction).where(ReviewAction.run_id == run["id"])).all()
        ) == 1


def test_stale_recovery_interrupts_running_attempt_then_increments(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    stale = utc_now() - timedelta(hours=1)
    with Session(get_engine()) as session:
        row = session.get(ContentRun, run["id"])
        row.status = "running"
        row.heartbeat_at = stale
        session.add(row)
        session.add(
            RunStep(
                run_id=run["id"],
                name="text_generation",
                status="running",
                attempt=1,
                started_at=stale,
                heartbeat_at=stale,
            )
        )
        session.commit()

    assert get_worker().recover_stale() == 1
    with Session(get_engine()) as session:
        interrupted = session.exec(
            select(RunStep).where(
                RunStep.run_id == run["id"], RunStep.name == "text_generation"
            )
        ).one()
        assert interrupted.status == "failed"
        assert interrupted.completed_at is not None
        assert "interrupted" in (interrupted.error or "")
    get_worker().run_once()
    with Session(get_engine()) as session:
        attempts = session.exec(
            select(RunStep)
            .where(RunStep.run_id == run["id"], RunStep.name == "text_generation")
            .order_by(RunStep.attempt)
        ).all()
    assert [step.attempt for step in attempts] == [1, 2]
    assert attempts[1].status == "completed"
    assert attempts[1].heartbeat_at is not None


def test_upload_claim_is_conditional_across_stale_sessions(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    upload_id = client.post(
        "/api/uploads", files={"file": ("reference.png", PNG, "image/png")}
    ).json()["id"]
    first_session = Session(get_engine())
    second_session = Session(get_engine())
    try:
        assert first_session.get(UploadAsset, upload_id).run_id is None
        assert second_session.get(UploadAsset, upload_id).run_id is None
        first = state_service.create_run(
            first_session,
            RunCreate(topic="one", audience="a", product_function="p", pain_point="x", upload_asset_ids=[upload_id]),
        )
        assert first.id is not None
        try:
            state_service.create_run(
                second_session,
                RunCreate(topic="two", audience="a", product_function="p", pain_point="x", upload_asset_ids=[upload_id]),
            )
        except state_service.StateConflict:
            pass
        else:
            raise AssertionError("second stale claimant unexpectedly succeeded")
    finally:
        first_session.close()
        second_session.close()
    with Session(get_engine()) as session:
        runs = repo.list_runs(session, status=None, limit=10, offset=0)[0]
        assert len(runs) == 1
        assert session.get(UploadAsset, upload_id).run_id == runs[0].id


def test_api_redacts_absolute_paths_from_run_and_step_errors(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    internal = r"C:\private\secret.png and /srv/private/key.json"

    def filesystem_failure(brief):
        raise RuntimeError(internal)

    monkeypatch.setattr(content_pipeline, "generate_candidate_round", filesystem_failure)
    run = _create(client)
    get_worker().run_once()
    body = client.get(f"/api/runs/{run['id']}").json()
    assert "C:\\private" not in body["error"]
    assert "/srv/private" not in body["error"]
    failed_step = next(step for step in body["steps"] if step["status"] == "failed")
    assert "C:\\private" not in failed_step["error"]
    assert "/srv/private" not in failed_step["error"]
    listed = client.get("/api/runs").json()["items"][0]
    assert "C:\\private" not in listed["error"]
    assert "/srv/private" not in listed["error"]
    with Session(get_engine()) as session:
        assert internal in session.get(ContentRun, run["id"]).error


def test_error_redaction_detects_quoted_posix_path_only():
    value = "failed opening '/srv/private/key.json', retry later"
    redacted = redact_internal_error(value)
    assert redacted is not None
    assert "/srv/private" not in redacted


def test_error_redaction_detects_windows_path_only():
    value = r"failed opening C:\private\secret.png"
    redacted = redact_internal_error(value)
    assert redacted is not None
    assert r"C:\private" not in redacted


def test_error_redaction_detects_windows_unc_path():
    value = r"failed opening \\fileserver\private\secret.png"
    redacted = redact_internal_error(value)
    assert redacted is not None
    assert r"\\fileserver\private" not in redacted


def test_run_detail_sanitizes_paths_in_arbitrary_strings_and_only_exposes_owned_urls(
    tmp_path, monkeypatch
):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    client.post(f"/api/runs/{run['id']}/copy-approval")
    get_worker().run_once()
    owned_zip = f"/api/runs/{run['id']}/exports/zip"
    with Session(get_engine()) as session:
        stored = session.get(ContentRun, run["id"])
        stored.topic = r"topic loaded from C:\private\brief.json"
        stored.brief = {"note": "source /srv/private/brief.json"}
        stored.final_package = {
            "zip_url": owned_zip,
            "json_url": r"C:\private\package.json",
            "internal_note": "/srv/private/package.json",
        }
        step = repo.list_steps(session, run["id"])[0]
        step.output_payload = {"caption": r"rendered from C:\private\step.json"}
        draft = repo.list_drafts(session, run["id"])[0]
        draft.tags = ["#safe", "/srv/private/tag.txt"]
        draft.narrative_plan = {"source_note": r"C:\private\plan.json"}
        draft.quality_report = {
            **draft.quality_report,
            "audit": "checked at /srv/private/report.json",
        }
        image = repo.list_images(session, run["id"])[0]
        image.prompt = r"Use C:\private\prompt.png as the visual source"
        image.reference_reason = "Selected from /srv/private/reference.png"
        image.qc_report = {"evidence": r"C:\private\qc.json"}
        session.add(stored)
        session.add(step)
        session.add(draft)
        session.add(image)
        session.commit()

    detail = client.get(f"/api/runs/{run['id']}")
    assert detail.status_code == 200, detail.text
    public = json.dumps(detail.json(), ensure_ascii=False)
    assert r"C:\private" not in public
    assert "/srv/private" not in public
    assert detail.json()["final_package"] == {"zip_url": owned_zip}


def test_export_artifacts_sanitize_paths_embedded_in_content(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    client.post(f"/api/runs/{run['id']}/copy-approval")
    get_worker().run_once()
    windows_path = r"C:\private\source.png"
    posix_path = "/srv/private/source.json"
    with Session(get_engine()) as session:
        selected = repo.get_selected_or_recommended_draft(session, run["id"])
        selected.first_comment = f"loaded from {windows_path}"
        selected.narrative_plan = {"private_source": posix_path}
        image = repo.list_images(session, run["id"])[0]
        image.prompt = f"reference {windows_path}"
        image.reference_reason = f"reference {posix_path}"
        image.qc_report = {"private_source": windows_path}
        session.add(selected)
        session.add(image)
        session.commit()

    approved = client.post(f"/api/runs/{run['id']}/asset-approval")
    assert approved.status_code == 200, approved.text
    markdown = client.get(approved.json()["final_package"]["markdown_url"]).text
    package_json = client.get(approved.json()["final_package"]["json_url"]).text
    archive = client.get(approved.json()["final_package"]["zip_url"]).content
    with zipfile.ZipFile(BytesIO(archive)) as bundle:
        archived = "\n".join(
            bundle.read(name).decode("utf-8")
            for name in bundle.namelist()
            if name.endswith((".md", ".json"))
        )
    for content in (markdown, package_json, archived):
        assert windows_path not in content
        assert windows_path.replace("\\", "\\\\") not in content
        assert posix_path not in content
        assert f"/api/runs/{run['id']}/assets/" in content


def test_missing_image_blocks_export_then_retry_regenerates_and_approval_succeeds(
    tmp_path, monkeypatch
):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    client.post(f"/api/runs/{run['id']}/copy-approval")
    get_worker().run_once()
    with Session(get_engine()) as session:
        images = repo.list_images(session, run["id"])
        assert images and all(image.file_path for image in images)
        missing_path = Path(images[0].file_path)
    missing_path.unlink()

    failed = client.post(
        f"/api/runs/{run['id']}/asset-approval",
        headers=_idempotency("missing-asset"),
    )
    assert failed.status_code == 409
    assert failed.json() == {"detail": "image assets are unavailable; retry image generation"}
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["status"] == "failed"
    assert detail["current_step"] == "image_generation"
    assert detail["final_package"] is None
    package_root = tmp_path / "exports" / str(run["id"])
    assert not (package_root / "package.json").exists()
    assert not any(path.suffix == ".zip" for path in package_root.glob("*.zip"))
    with Session(get_engine()) as session:
        assert repo.get_idempotency(session, "missing-asset") is None
        assert session.get(ContentRun, run["id"]).failed_phase == "image"

    retried = client.post(f"/api/runs/{run['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "image_queued"
    assert get_worker().run_once() is True
    ready = client.get(f"/api/runs/{run['id']}").json()
    assert ready["status"] == "asset_review_required"
    assert ready["images"] and all(image["url"] for image in ready["images"])
    completed = client.post(
        f"/api/runs/{run['id']}/asset-approval",
        headers=_idempotency("missing-asset"),
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert client.get(completed.json()["final_package"]["zip_url"]).status_code == 200


def test_upload_backed_flow_never_exposes_filesystem_paths(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    uploaded = client.post(
        "/api/uploads", files={"file": ("reference.png", PNG, "image/png")}
    ).json()
    run = _create(client, upload_asset_ids=[uploaded["id"]])
    get_worker().run_once()
    client.post(f"/api/runs/{run['id']}/copy-approval")
    get_worker().run_once()
    detail = client.get(f"/api/runs/{run['id']}").json()
    public_run = json.dumps(detail, ensure_ascii=False)
    assert f"upload:{uploaded['id']}" in public_run
    assert f"/api/runs/{run['id']}/assets/" in public_run

    approved = client.post(f"/api/runs/{run['id']}/asset-approval").json()
    markdown = client.get(approved["final_package"]["markdown_url"]).text
    package_json = client.get(approved["final_package"]["json_url"]).text
    archive = client.get(approved["final_package"]["zip_url"]).content
    with zipfile.ZipFile(BytesIO(archive)) as bundle:
        zip_markdown = bundle.read("发布包.md").decode("utf-8")
        zip_json = bundle.read("package.json").decode("utf-8")

    with Session(get_engine()) as session:
        stored_upload = session.get(UploadAsset, uploaded["id"])
        absolute_upload = stored_upload.file_path
    forbidden = {
        str(tmp_path),
        tmp_path.as_posix(),
        absolute_upload,
        absolute_upload.replace("\\", "\\\\"),
    }
    for public_content in (public_run, markdown, package_json, zip_markdown, zip_json):
        assert all(path not in public_content for path in forbidden)
    assert f"upload:{uploaded['id']}" in markdown
    assert f"/api/runs/{run['id']}/assets/" in package_json


def test_revision_provider_failure_is_durable_atomic_and_retryable(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    before = client.get(f"/api/runs/{run['id']}").json()
    draft_ids = [draft["id"] for draft in before["drafts"]]
    original = content_pipeline.create_revision

    def failing_revision(*args, **kwargs):
        raise RuntimeError(r"revision provider failed at C:\private\revision.json")

    monkeypatch.setattr(content_pipeline, "create_revision", failing_revision)
    failed = client.post(
        f"/api/runs/{run['id']}/revisions",
        json={"instructions": "make it clearer"},
        headers=_idempotency("revision-provider-failure"),
    )
    assert failed.status_code == 502
    assert failed.json() == {"detail": "revision provider failed"}
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["status"] == "failed"
    assert "C:\\private" not in detail["error"]
    with Session(get_engine()) as session:
        stored = session.get(ContentRun, run["id"])
        assert r"C:\private\revision.json" in stored.error
        assert stored.failed_phase == "revision"
        assert [draft.id for draft in repo.list_drafts(session, run["id"])] == draft_ids
        assert repo.get_idempotency(session, "revision-provider-failure") is None
        assert session.exec(
            select(ReviewAction).where(ReviewAction.run_id == run["id"])
        ).all() == []
        failed_steps = session.exec(
            select(RunStep).where(
                RunStep.run_id == run["id"], RunStep.name == "draft_revision"
            )
        ).all()
        assert len(failed_steps) == 1
        assert failed_steps[0].status == "failed"
        assert failed_steps[0].attempt == 1
        assert failed_steps[0].started_at and failed_steps[0].completed_at
        assert failed_steps[0].heartbeat_at and failed_steps[0].duration_ms is not None
        assert failed_steps[0].error_type == "RuntimeError"
        assert "revision provider failed" in (failed_steps[0].error or "")

    retried = client.post(
        f"/api/runs/{run['id']}/retry", headers=_idempotency("retry-revision")
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "copy_review_required"
    retried_detail = client.get(f"/api/runs/{run['id']}").json()
    assert retried_detail["current_step"] == "copy_review"
    monkeypatch.setattr(content_pipeline, "create_revision", original)
    succeeded = client.post(
        f"/api/runs/{run['id']}/revisions",
        json={"instructions": "make it clearer"},
        headers=_idempotency("revision-provider-failure"),
    )
    assert succeeded.status_code == 200
    with Session(get_engine()) as session:
        attempts = session.exec(
            select(RunStep)
            .where(RunStep.run_id == run["id"], RunStep.name == "draft_revision")
            .order_by(RunStep.attempt)
        ).all()
        assert [step.attempt for step in attempts] == [1, 2]
        assert attempts[1].status == "completed"
        assert attempts[1].started_at and attempts[1].completed_at


def test_revision_failure_commits_before_waiting_approval_can_transition(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    get_worker().run_once()
    entered = Event()
    release = Event()
    approval_started = Event()
    results = {}

    def blocked_failure(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        raise RuntimeError("blocked revision provider failure")

    monkeypatch.setattr(content_pipeline, "create_revision", blocked_failure)

    def revise_request():
        results["revision"] = client.post(
            f"/api/runs/{run['id']}/revisions",
            json={"instructions": "make it clearer"},
            headers=_idempotency("blocked-revision"),
        )

    def approve_request():
        approval_started.set()
        results["approval"] = client.post(
            f"/api/runs/{run['id']}/copy-approval",
            headers=_idempotency("waiting-approval"),
        )

    revision_thread = Thread(target=revise_request)
    approval_thread = Thread(target=approve_request)
    revision_thread.start()
    assert entered.wait(5)
    approval_thread.start()
    assert approval_started.wait(5)
    assert approval_thread.is_alive()
    release.set()
    revision_thread.join(5)
    approval_thread.join(5)
    assert not revision_thread.is_alive() and not approval_thread.is_alive()
    assert results["revision"].status_code == 502
    assert results["approval"].status_code == 409
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["status"] == "failed"
    assert detail["current_step"] == "draft_revision"
    with Session(get_engine()) as session:
        assert len(repo.list_drafts(session, run["id"])) == 3
        assert repo.get_idempotency(session, "blocked-revision") is None
        assert repo.get_idempotency(session, "waiting-approval") is None


def test_cancel_between_text_provider_and_publish_exposes_no_candidates(tmp_path, monkeypatch):
    client = _prepare(tmp_path, monkeypatch)
    run = _create(client)
    original = content_pipeline.generate_candidate_round
    publish_entered = Event()
    publish_release = Event()

    def pause_before_publish(run_id):
        publish_entered.set()
        assert publish_release.wait(5)

    monkeypatch.setattr(
        execution_service, "_before_text_publish", pause_before_publish, raising=False
    )
    monkeypatch.setattr(content_pipeline, "generate_candidate_round", original)
    thread = Thread(target=get_worker().run_once)
    thread.start()
    assert publish_entered.wait(5)
    assert client.post(f"/api/runs/{run['id']}/cancel").status_code == 200
    publish_release.set()
    thread.join(5)
    assert not thread.is_alive()
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["status"] == "canceled"
    assert detail["drafts"] == []
    assert not any(step["name"] == "candidate_round" for step in detail["steps"])
