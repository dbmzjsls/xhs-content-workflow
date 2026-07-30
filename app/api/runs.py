from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.repositories import runs as repo
from app.schemas import (
    DraftRead,
    DraftRevision,
    DraftSelection,
    ImageRead,
    RunCreate,
    RunList,
    RunRead,
    RunSummary,
    StepRead,
)
from app.security import require_api_token
from app.services import state_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(require_api_token)])
RunStatus = Literal[
    "queued",
    "running",
    "copy_review_required",
    "image_queued",
    "image_running",
    "asset_review_required",
    "completed",
    "failed",
    "canceled",
]


@router.post("", response_model=RunRead, status_code=202)
def create_run(payload: RunCreate, session: Session = Depends(get_session)) -> RunRead:
    try:
        run = state_service.create_run(session, payload)
    except state_service.StateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _read_run(session, run.id)


@router.get("", response_model=RunList)
def list_runs(
    status: RunStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> RunList:
    rows, total = repo.list_runs(session, status=status, limit=limit, offset=offset)
    return RunList(
        items=[
            RunSummary(
                id=row.id,
                status=row.status,
                current_step=row.current_step,
                topic=row.topic,
                error=row.error,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: int, session: Session = Depends(get_session)) -> RunRead:
    return _read_run(session, run_id)


@router.post("/{run_id}/selection")
def select_draft(
    run_id: int,
    payload: DraftSelection,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _mutation(
        session,
        key=idempotency_key,
        scope="selection",
        run_id=run_id,
        payload=payload.model_dump(),
        action=lambda: state_service.select_draft(session, run_id, payload),
    )


@router.post("/{run_id}/revisions")
def revise_draft(
    run_id: int,
    payload: DraftRevision,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _mutation(
        session,
        key=idempotency_key,
        scope="revision",
        run_id=run_id,
        payload=payload.model_dump(),
        action=lambda: state_service.revise_draft(session, run_id, payload),
    )


@router.post("/{run_id}/copy-approval")
def approve_copy(
    run_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _mutation(
        session,
        key=idempotency_key,
        scope="copy-approval",
        run_id=run_id,
        payload={},
        action=lambda: state_service.approve_copy(session, run_id),
    )


@router.post("/{run_id}/asset-approval")
def approve_assets(
    run_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _mutation(
        session,
        key=idempotency_key,
        scope="asset-approval",
        run_id=run_id,
        payload={},
        action=lambda: state_service.approve_assets(session, run_id),
    )


@router.post("/{run_id}/retry")
def retry_run(
    run_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _mutation(
        session,
        key=idempotency_key,
        scope="retry",
        run_id=run_id,
        payload={},
        action=lambda: state_service.retry(session, run_id),
    )


@router.post("/{run_id}/cancel")
def cancel_run(
    run_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _mutation(
        session,
        key=idempotency_key,
        scope="cancel",
        run_id=run_id,
        payload={},
        action=lambda: state_service.cancel(session, run_id),
    )


@router.get("/{run_id}/assets/{asset_id}")
def read_asset(run_id: int, asset_id: int, session: Session = Depends(get_session)) -> FileResponse:
    asset = repo.get_image(session, run_id, asset_id)
    if asset is None or not asset.file_path:
        raise HTTPException(status_code=404, detail="asset not found")
    root = (get_settings().export_dir / str(run_id) / "assets").resolve()
    path = _contained_file(asset.file_path, root)
    return FileResponse(path)


@router.get("/{run_id}/uploads/{upload_id}")
def read_run_upload(
    run_id: int, upload_id: int, session: Session = Depends(get_session)
) -> FileResponse:
    upload = repo.get_run_upload(session, run_id, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="upload not found")
    path = _contained_file(upload.file_path, get_settings().upload_root.resolve())
    return FileResponse(path, media_type=upload.mime_type)


@router.get("/{run_id}/exports/{kind}")
def read_export(
    run_id: int,
    kind: Literal["markdown", "json", "zip"],
    session: Session = Depends(get_session),
) -> FileResponse:
    run = repo.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status != "completed" or not run.final_package:
        raise HTTPException(status_code=409, detail="run has not completed export")
    filenames = {"markdown": "发布包.md", "json": "package.json", "zip": "发布包.zip"}
    media = {"markdown": "text/markdown", "json": "application/json", "zip": "application/zip"}
    root = (get_settings().export_dir / str(run_id)).resolve()
    path = _contained_file(root / filenames[kind], root)
    return FileResponse(path, filename=path.name, media_type=media[kind])


def _mutation(
    session: Session,
    *,
    key: str | None,
    scope: str,
    run_id: int,
    payload: dict[str, Any],
    action,
) -> dict[str, Any]:
    try:
        return state_service.idempotent(
            session,
            key=key,
            scope=scope,
            run_id=run_id,
            payload=payload,
            action=action,
        )
    except state_service.StateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        if repo.get_run(session, run_id) is None:
            raise HTTPException(status_code=404, detail="run not found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _read_run(session: Session, run_id: int) -> RunRead:
    run = repo.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return RunRead(
        id=run.id,
        status=run.status,
        current_step=run.current_step,
        topic=run.topic,
        audience=run.audience,
        product_function=run.product_function,
        pain_point=run.pain_point,
        style_preference=run.style_preference,
        brief=_public_payload(run.brief),
        final_package=_public_payload(run.final_package),
        error=run.error,
        created_at=run.created_at,
        updated_at=run.updated_at,
        steps=[
            StepRead(
                name=step.name,
                status=step.status,
                output_payload=_public_payload(step.output_payload),
                created_at=step.created_at,
                attempt=step.attempt,
                started_at=step.started_at,
                completed_at=step.completed_at,
                duration_ms=step.duration_ms,
                error=step.error,
            )
            for step in repo.list_steps(session, run_id)
        ],
        drafts=[
            DraftRead(
                id=draft.id,
                title=draft.title,
                body=draft.body,
                tags=draft.tags,
                first_comment=draft.first_comment,
                narrative_plan=draft.narrative_plan,
                quality_report=draft.quality_report,
                is_final=draft.is_final,
                selected=draft.selected,
                candidate=draft.candidate,
                parent_draft_id=draft.parent_draft_id,
            )
            for draft in repo.list_drafts(session, run_id)
        ],
        images=[
            ImageRead(
                id=image.id,
                kind=image.kind,
                status=image.status,
                title=image.title,
                prompt=image.prompt,
                reference_reason=image.reference_reason,
                url=f"/api/runs/{run_id}/assets/{image.id}" if image.file_path else None,
                qc_report=image.qc_report,
            )
            for image in repo.list_images(session, run_id)
        ],
    )


def _public_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _public_payload(item)
            for key, item in value.items()
            if key not in {"path", "file_path", "reference_path"}
        }
    if isinstance(value, list):
        return [_public_payload(item) for item in value]
    return value


def _contained_file(value: str | Path, root: Path) -> Path:
    path = Path(value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        logger.warning("rejected resource path outside configured root")
        raise HTTPException(status_code=400, detail="invalid resource path") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="resource missing")
    return path
