from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from threading import Lock
from typing import Any

from sqlalchemy import delete, update
from sqlmodel import Session, select

from app.models import Draft, IdempotencyRecord, ImageAsset, UploadAsset
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
    child = content_pipeline.create_revision(
        session, parent, run.brief, payload.instructions, commit=False
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
    else:
        raise StateConflict("failed run has no recoverable phase")
    repo.update_run(
        session,
        run_id,
        status=status,
        current_step=status,
        clear_error=True,
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
    repo.update_run(
        session,
        run_id,
        status="canceled",
        current_step="canceled",
        commit=False,
    )
    session.exec(delete(ImageAsset).where(ImageAsset.run_id == run_id))
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
        except Exception:
            session.rollback()
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
