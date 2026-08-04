from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlmodel import Session

from app.config import get_settings
from app.models import UploadAsset

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED = {
    ".png": ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".webp": (
        "image/webp",
        lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    ),
}


class UploadValidationError(ValueError):
    pass


class UploadTooLarge(UploadValidationError):
    pass


async def store_upload(session: Session, upload: UploadFile) -> UploadAsset:
    extension = Path(upload.filename or "").suffix.casefold()
    rule = ALLOWED.get(extension)
    if rule is None:
        raise UploadValidationError("only PNG, JPEG, and WebP files are allowed")
    expected_mime, magic_check = rule
    if upload.content_type != expected_mime:
        raise UploadValidationError("file extension and MIME type do not match")
    root = get_settings().upload_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    final_path = root / f"{uuid4().hex}{extension}"
    descriptor, temporary_name = tempfile.mkstemp(dir=root, prefix=".upload-")
    size = 0
    digest = hashlib.sha256()
    head = b""
    try:
        with os.fdopen(descriptor, "wb") as handle:
            while chunk := await upload.read(64 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise UploadTooLarge("upload exceeds 10 MiB")
                if len(head) < 16:
                    head += chunk[: 16 - len(head)]
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if not magic_check(head):
            raise UploadValidationError("file signature does not match its image type")
        os.replace(temporary_name, final_path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    row = UploadAsset(
        run_id=None,
        kind="reference",
        status="uploaded",
        file_path=str(final_path),
        mime_type=expected_mime,
        checksum=digest.hexdigest(),
        size_bytes=size,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
