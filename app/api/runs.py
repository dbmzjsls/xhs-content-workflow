import logging
from collections.abc import Mapping
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.repositories import runs as repo
from app.schemas import DraftRead, ImageRead, ReviewRequest, RunCreate, RunRead, StepRead
from app.security import require_api_token
from app.services import workflow_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(require_api_token)])


@router.post("", response_model=RunRead)
def create_run(payload: RunCreate, session: Session = Depends(get_session)) -> RunRead:
    try:
        run = workflow_service.create_and_run(session, payload)
    except Exception:
        logger.exception("workflow creation failed")
        raise HTTPException(status_code=500, detail="workflow creation failed")
    if run is None:
        raise HTTPException(status_code=500, detail="run vanished")
    return _read_run(session, run.id)


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: int, session: Session = Depends(get_session)) -> RunRead:
    if repo.get_run(session, run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _read_run(session, run_id)


@router.post("/{run_id}/review")
def review_run(
    run_id: int,
    payload: ReviewRequest,
    session: Session = Depends(get_session),
) -> dict:
    if repo.get_run(session, run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        result = workflow_service.review_run(session, run_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("review action failed", extra={"run_id": run_id})
        raise HTTPException(status_code=500, detail="review action failed")
    return {"ok": True, "result": result}


@router.get("/{run_id}/export")
def export_run(run_id: int, session: Session = Depends(get_session)) -> FileResponse:
    run = repo.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    package = run.final_package
    if not package:
        raise HTTPException(status_code=409, detail="run has not been approved for export")
    zip_path = _safe_export_zip_path(run_id, package)
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="export missing")
    return FileResponse(zip_path, filename=zip_path.name, media_type="application/zip")


def _safe_export_zip_path(run_id: int, package: Mapping[str, object]) -> Path:
    zip_value = package.get("zip")
    if not isinstance(zip_value, str) or not zip_value:
        raise HTTPException(status_code=404, detail="export missing")

    zip_path = Path(zip_value).resolve()
    export_root = (get_settings().export_dir / str(run_id)).resolve()
    try:
        zip_path.relative_to(export_root)
    except ValueError:
        logger.warning("rejected export path outside export root", extra={"run_id": run_id})
        raise HTTPException(status_code=400, detail="invalid export path")
    if zip_path.suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="invalid export path")
    return zip_path


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
        brief=run.brief,
        final_package=run.final_package,
        error=run.error,
        created_at=run.created_at,
        updated_at=run.updated_at,
        steps=[
            StepRead(name=s.name, status=s.status, output_payload=s.output_payload, created_at=s.created_at)
            for s in repo.list_steps(session, run_id)
        ],
        drafts=[
            DraftRead(
                title=d.title,
                body=d.body,
                tags=d.tags,
                first_comment=d.first_comment,
                narrative_plan=d.narrative_plan,
                quality_report=d.quality_report,
                is_final=d.is_final,
            )
            for d in repo.list_drafts(session, run_id)
        ],
        images=[
            ImageRead(
                kind=i.kind,
                status=i.status,
                title=i.title,
                prompt=i.prompt,
                reference_reason=i.reference_reason,
                file_path=i.file_path,
                qc_report=i.qc_report,
            )
            for i in repo.list_images(session, run_id)
        ],
    )
