from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

from sqlmodel import Session

from app.config import get_settings
from app.repositories import runs as repo
from app.security import redact_internal_error


def export_package(session: Session, run_id: int, *, commit: bool = True) -> dict:
    run = repo.get_run(session, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    draft = repo.mark_selected_or_recommended_draft_final(session, run_id, commit=commit)
    if draft is None:
        raise ValueError("no draft to export")
    images = repo.list_images(session, run_id)
    references = repo.list_references(session, run_id)
    steps = repo.list_steps(session, run_id)
    out_dir = get_settings().export_dir / str(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    markdown = _render_markdown(run, draft, images, references)
    md_path = out_dir / "发布包.md"
    json_path = out_dir / "package.json"
    zip_path = out_dir / "发布包.zip"
    _atomic_write(md_path, markdown.encode("utf-8"))
    payload = {
        "run_id": run_id,
        "topic": run.topic,
        "draft": draft.model_dump(mode="json"),
        "images": [
            {
                "id": img.id,
                "kind": img.kind,
                "status": img.status,
                "title": img.title,
                "url": f"/api/runs/{run_id}/assets/{img.id}",
                "qc_report": img.qc_report,
            }
            for img in images
        ],
        "references": [
            {"source": ref.source, "role": ref.role, "reason": ref.reason}
            for ref in references
        ],
        "steps": [
            {
                "name": step.name,
                "status": step.status,
                "attempt": step.attempt,
                "started_at": step.started_at.isoformat() if step.started_at else None,
                "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                "duration_ms": step.duration_ms,
                "error": redact_internal_error(step.error),
            }
            for step in steps
        ],
    }
    _atomic_write(json_path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    descriptor, temporary_zip = tempfile.mkstemp(dir=out_dir, prefix=".package-", suffix=".zip")
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(md_path, md_path.name)
            zf.write(json_path, json_path.name)
            asset_root = (out_dir / "assets").resolve()
            for img in images:
                if not img.file_path:
                    continue
                image_path = Path(img.file_path).resolve()
                try:
                    image_path.relative_to(asset_root)
                except ValueError as exc:
                    raise ValueError("image asset path escapes run asset root") from exc
                if image_path.is_file():
                    zf.write(image_path, f"assets/{image_path.name}")
        os.replace(temporary_zip, zip_path)
    except BaseException:
        Path(temporary_zip).unlink(missing_ok=True)
        raise
    final_package = {
        "markdown_url": f"/api/runs/{run_id}/exports/markdown",
        "json_url": f"/api/runs/{run_id}/exports/json",
        "zip_url": f"/api/runs/{run_id}/exports/zip",
    }
    repo.update_run(
        session,
        run_id,
        status="completed",
        current_step="export_package",
        final_package=final_package,
        commit=commit,
    )
    return final_package


def _render_markdown(run, draft, images, references) -> str:
    tag_line = " ".join(draft.tags)
    reference_lines = "\n".join(
        f"{idx}. {ref.role} / {ref.source}\n   - 理由：{ref.reason}"
        for idx, ref in enumerate(references, start=1)
    ) or "无外部参考图。"
    image_lines = "\n".join(
        (
            f"{idx}. {img.kind}：{img.title}\n"
            f"   - 资源：/api/runs/{run.id}/assets/{img.id}\n"
            f"   - 参考理由：{img.reference_reason}\n"
            f"   - 图片质检：{json.dumps(img.qc_report, ensure_ascii=False)}\n"
            f"   - Prompt：{img.prompt[:600]}"
        )
        for idx, img in enumerate(images, start=1)
    )
    return f"""# {draft.title}

## 正文

{draft.body}

## 标签

{tag_line}

## 首评

{draft.first_comment or ""}

## 叙事结构

```json
{json.dumps(draft.narrative_plan, ensure_ascii=False, indent=2)}
```

## 质检报告

```json
{json.dumps(draft.quality_report, ensure_ascii=False, indent=2)}
```

## 参考图选择

{reference_lines}

## 图片方案

{image_lines}

## 项目信息

- Run ID: {run.id}
- Topic: {run.topic}
- Audience: {run.audience}
- Product Function: {run.product_function}
"""


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
