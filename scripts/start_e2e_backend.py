"""Migrate and start the E2E backend with mandatory mock/temp safeguards."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import uvicorn
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.migrate import migrate_database  # noqa: E402


def _require_safe_environment() -> None:
    if os.environ.get("LLM_PROVIDER") != "mock" or os.environ.get("IMAGE_PROVIDER") != "mock":
        raise RuntimeError("E2E requires explicit mock text and image providers")
    runtime_value = os.environ.get("E2E_RUNTIME_ROOT")
    if not runtime_value:
        raise RuntimeError("E2E_RUNTIME_ROOT is required")
    runtime_root = Path(runtime_value).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        runtime_root.relative_to(temp_root)
    except ValueError as exc:
        raise RuntimeError("E2E_RUNTIME_ROOT must be under the OS temporary directory") from exc

    settings = get_settings()
    database_url = make_url(settings.database_url)
    if not database_url.drivername.startswith("sqlite") or not database_url.database:
        raise RuntimeError("E2E requires a file-backed SQLite database")
    guarded_paths = [Path(database_url.database), settings.export_dir, settings.upload_root]
    for guarded_path in guarded_paths:
        try:
            guarded_path.resolve().relative_to(runtime_root)
        except ValueError as exc:
            raise RuntimeError(
                "E2E database/export/upload paths must stay under E2E_RUNTIME_ROOT"
            ) from exc


def main() -> None:
    get_settings.cache_clear()
    _require_safe_environment()
    settings = get_settings()
    migrate_database(settings.database_url)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8090, log_level="warning")


if __name__ == "__main__":
    main()

