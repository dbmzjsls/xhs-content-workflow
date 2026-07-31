from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from threading import Lock
from typing import Any

from sqlalchemy import delete, update
from sqlmodel import Session, select

from app.models import ContentRun, Draft, IdempotencyRecord, ImageAsset, RunStep, UploadAsset
from app.repositories import runs as repo
from app.schemas import DraftRevision, DraftSelection, RunCreate
from app.services import content_pipeline, export_service
from app.services.worker import get_worker
from app.time_utils import utc_now

ACTIVE_STATUSES = {
    "queued",
    "running",
    "copy_review_required",
    "image_queued",
    "image_running",
    "asset_review_required",
}
_idempotency_lock = Lock()


class StateConflict(ValueError):
    pass


class RevisionProviderFailure(RuntimeError):
    def __init__(self, error: Exception, *, started_at, attempt: int):
        super().__init__(str(error))
        self.started_at = started_at
        self.attempt = attempt
        self.error_type = type(error).__name__


def create_run(session: Session, payload: RunCreate):
    upload_ids = list(dict.fromkeys(payload.upload_asset_ids))
    if len(upload_ids) != len(payload.upload_asset_ids):
        raise StateConflict("upload asset IDs must be unique")
    uploads = []
    for upload_id in upload_ids:
        upload = repo.get_upload(session, upload_id)
        if upload is None:
            raise ValueError(f"upload asset {upload_id} not found")
        if upload.run_id is not None:
            raise StateConflict(f"upload asset {upload_id} is already assigned")
        uploads.append(upload)
    brief = payload.model_dump(exclude={"upload_asset_ids"})
    try:
        run = repo.create_run(
            session,
            {
                **brief,
                "status": "queued",
                "current_step": "queued",
                "reference_path": None,
                "brief": brief,
                "workflow_name": "xhs-workbench",
                "workflow_version": "1",
            },
            commit=False,
        )
        for upload in uploads:
            claimed = session.exec(
                update(UploadAsset)
                .where(UploadAsset.id == upload.id, UploadAsset.run_id.is_(None))
                .values(run_id=run.id, updated_at=utc_now())
            )
            if claimed.rowcount != 1:
                raise StateConflict(f"upload asset {upload.id} is already assigned")
        session.commit()
        session.refresh(run)
    except Exception:
        session.rollback()
        raise
    get_worker().wake()
    return run


def select_draft(
    session: Session, run_id: int, payload: DraftSelection, *, commit: bool = True
) -> dict[str, Any]:
    _require_state(session, run_id, "copy_review_required")
    draft = session.exec(
        select(Draft).where(Draft.id == payload.draft_id, Draft.run_id == run_id)
    ).first()
    if draft is None:
        raise ValueError("draft not found for run")
    if not _is_hard_pass(draft):
        raise StateConflict("hard-rule-failing drafts cannot be selected")
    for row in repo.list_drafts(session, run_id):
        row.selected = row.id == draft.id
        session.add(row)
    repo.add_review_action(
        session,
        run_id,
        action="select",
        instructions=None,
        replacement={"draft_id": draft.id},
        commit=False,
    )
    _maybe_commit(session, commit)
    return {"run_id": run_id, "draft_id": draft.id, "status": "copy_review_required"}


def revise_draft(
    session: Session, run_id: int, payload: DraftRevision, *, commit: bool = True
) -> dict[str, Any]:
    run = _require_state(session, run_id, "copy_review_required")
    parent = repo.get_selected_or_recommended_draft(session, run_id)
    if parent is None:
        raise ValueError("no draft to revise")
    started_at = utc_now()
    attempt = repo.next_step_attempt(session, run_id, "draft_revision")
    try:
        child = content_pipeline.create_revision(
            session,
            parent,
            run.brief,
            payload.instructions,
            commit=False,
            record_step=False,
        )
    except Exception as exc:
        raise RevisionProviderFailure(
            exc, started_at=started_at, attempt=attempt
        ) from exc
    repo.record_step(
        session,
        run_id,
        "draft_revision",
        {"parent_draft_id": parent.id, "instructions": payload.instructions},
        {"child_draft_id": child.id},
        status="completed",
        attempt=attempt,
        started_at=started_at,
        commit=False,
    )
    repo.update_run(
        session, run_id, current_step="copy_review", commit=False
    )
    repo.add_review_action(
        session,
        run_id,
        action="revise",
        instructions=payload.instructions,
        replacement=None,
        commit=False,
    )
    _maybe_commit(session, commit)
    return {"run_id": run_id, "draft_id": child.id, "status": "copy_review_required"}


def approve_copy(session: Session, run_id: int, *, commit: bool = True) -> dict[str, Any]:
    _require_state(session, run_id, "copy_review_required")
    eligible = repo.get_selected_or_recommended_draft(session, run_id)
    if eligible is None or not _is_hard_pass(eligible):
        raise StateConflict("no eligible draft selected")
    repo.add_review_action(
        session,
        run_id,
        action="approve_copy",
        instructions=None,
        replacement=None,
        commit=False,
    )
    repo.update_run(
        session,
        run_id,
        status="image_queued",
        current_step="image_queued",
        clear_error=True,
        clear_failed_phase=True,
        commit=False,
    )
    _maybe_commit(session, commit, wake=True)
    return {"run_id": run_id, "status": "image_queued"}


def approve_assets(session: Session, run_id: int, *, commit: bool = True) -> dict[str, Any]:
    _require_state(session, run_id, "asset_review_required")
    package = export_service.export_package(session, run_id, commit=False)
    repo.add_review_action(
        session,
        run_id,
        action="approve_assets",
        instructions=None,
        replacement=None,
        commit=False,
    )
    _maybe_commit(session, commit)
    return {"run_id": run_id, "status": "completed", "final_package": package}


def retry(session: Session, run_id: int, *, commit: bool = True) -> dict[str, Any]:
    run = _require_state(session, run_id, "failed")
    if run.failed_phase == "text":
        status = "queued"
    elif run.failed_phase == "image":
        status = "image_queued"
    elif run.failed_phase == "revision":
        status = "copy_review_required"
    else:
        raise StateConflict("failed run has no recoverable phase")
    repo.update_run(
        session,
        run_id,
        status=status,
        current_step="copy_review" if run.failed_phase == "revision" else status,
        clear_error=True,
        clear_failed_phase=run.failed_phase == "revision",
        commit=False,
    )
    _maybe_commit(session, commit, wake=True)
    return {"run_id": run_id, "status": status}


def cancel(session: Session, run_id: int, *, commit: bool = True) -> dict[str, Any]:
    run = repo.get_run(session, run_id)
    if run is None:
        raise ValueError("run not found")
    if run.status not in ACTIVE_STATUSES:
        raise StateConflict(f"cannot cancel run from {run.status}")
    canceling_text_execution = run.status == "running"
    repo.update_run(
        session,
        run_id,
        status="canceled",
        current_step="canceled",
        commit=False,
    )
    session.exec(delete(ImageAsset).where(ImageAsset.run_id == run_id))
    if canceling_text_execution:
        now = utc_now()
        session.exec(delete(Draft).where(Draft.run_id == run_id))
        session.exec(
            delete(RunStep).where(
                RunStep.run_id == run_id, RunStep.name == "candidate_round"
            )
        )
        session.exec(
            update(RunStep)
            .where(
                RunStep.run_id == run_id,
                RunStep.name == "text_generation",
                RunStep.status == "running",
            )
            .values(
                status="failed",
                output_payload={},
                error="canceled",
                heartbeat_at=now,
                completed_at=now,
            )
        )
    _maybe_commit(session, commit)
    return {"run_id": run_id, "status": "canceled"}


def idempotent(
    session: Session,
    *,
    key: str | None,
    scope: str,
    run_id: int,
    payload: dict[str, Any],
    action: Callable[[], dict[str, Any]],
    error_callback: Callable[[Exception], None] | None = None,
) -> dict[str, Any]:
    if key and len(key) > 200:
        raise StateConflict("idempotency key is too long")
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    with _idempotency_lock:
        existing = repo.get_idempotency(session, key) if key else None
        if key and existing is not None:
            if (
                existing.scope != scope
                or existing.run_id != run_id
                or existing.request_hash != digest
                or existing.status != "completed"
            ):
                raise StateConflict("idempotency key was already used for a different request")
            return dict(existing.response_payload or {})
        try:
            response = action()
            if key:
                session.add(
                    IdempotencyRecord(
                        key=key,
                        scope=scope,
                        run_id=run_id,
                        request_hash=digest,
                        response_payload=response,
                        status="completed",
                    )
                )
            hook = globals().get("_before_transaction_commit")
            if hook is not None:
                hook(session)
            session.commit()
        except Exception as exc:
            session.rollback()
            if error_callback is not None:
                error_callback(exc)
            raise
        if response.get("status") in {"queued", "image_queued"}:
            get_worker().wake()
        return response


def _require_state(session: Session, run_id: int, expected: str):
    run = repo.get_run(session, run_id)
    if run is None:
        raise ValueError("run not found")
    if run.status != expected:
        raise StateConflict(f"run is {run.status}; expected {expected}")
    return run


def _is_hard_pass(draft: Draft) -> bool:
    return draft.quality_report.get("hard", {}).get("passed") is True


def _maybe_commit(session: Session, commit: bool, *, wake: bool = False) -> None:
    if commit:
        session.commit()
        if wake:
            get_worker().wake()


def record_revision_failure(
    session: Session, run_id: int, failure: RevisionProviderFailure
) -> None:
    now = utc_now()
    changed = session.exec(
        update(ContentRun)
        .where(
            ContentRun.id == run_id,
            ContentRun.status == "copy_review_required",
        )
        .values(
            status="failed",
            current_step="draft_revision",
            error=str(failure),
            failed_phase="revision",
            updated_at=now,
        )
    )
    if changed.rowcount != 1:
        session.rollback()
        run = repo.get_run(session, run_id)
        if run is not None and run.status == "canceled":
            return
        raise RuntimeError("revision failure could not transition the expected copy-review run")
    repo.record_step(
        session,
        run_id,
        "draft_revision",
        {},
        {},
        status="failed",
        attempt=failure.attempt,
        started_at=failure.started_at,
        error=str(failure),
        error_type=failure.error_type,
        commit=False,
    )
    repo.update_run(
        session,
        run_id,
        status="failed",
        current_step="draft_revision",
        error=str(failure),
        failed_phase="revision",
        commit=False,
    )
    session.commit()
