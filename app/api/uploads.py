from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.api.runs import _contained_file
from app.config import get_settings
from app.db import get_session
from app.repositories import runs as repo
from app.schemas import UploadRead
from app.security import require_api_token
from app.services import upload_service

router = APIRouter(prefix="/api/uploads", tags=["uploads"], dependencies=[Depends(require_api_token)])


@router.post("", response_model=UploadRead, status_code=201)
async def create_upload(file: UploadFile, session: Session = Depends(get_session)) -> UploadRead:
    try:
        row = await upload_service.store_upload(session, file)
    except upload_service.UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except upload_service.UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadRead(
        id=row.id,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        url=f"/api/uploads/{row.id}",
    )


@router.get("/{upload_id}")
def read_unassigned_upload(
    upload_id: int, session: Session = Depends(get_session)
) -> FileResponse:
    row = repo.get_upload(session, upload_id)
    if row is None or row.run_id is not None:
        raise HTTPException(status_code=404, detail="upload not found")
    path = _contained_file(row.file_path, get_settings().upload_root.resolve())
    return FileResponse(path, media_type=row.mime_type)
