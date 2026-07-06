from __future__ import annotations

import json
import zipfile
from pathlib import Path

from sqlmodel import Session

from app.config import get_settings
from app.repositories import runs as repo


def export_package(session: Session, run_id: int) -> dict:
    run = repo.get_run(session, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    draft = repo.mark_latest_draft_final(session, run_id)
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
    md_path.write_text(markdown, encoding="utf-8")
    payload = {
        "run_id": run_id,
        "topic": run.topic,
        "draft": draft.model_dump(mode="json"),
        "images": [img.model_dump(mode="json") for img in images],
        "references": [ref.model_dump(mode="json") for ref in references],
        "steps": [step.model_dump(mode="json") for step in steps],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(md_path, md_path.name)
        zf.write(json_path, json_path.name)
        for img in images:
            if img.file_path and Path(img.file_path).exists():
                zf.write(img.file_path, f"assets/{Path(img.file_path).name}")
    final_package = {
        "markdown": str(md_path),
        "json": str(json_path),
        "zip": str(zip_path),
    }
    repo.update_run(session, run_id, status="completed", current_step="export_package", final_package=final_package)
    return final_package


def _render_markdown(run, draft, images, references) -> str:
    tag_line = " ".join(draft.tags)
    reference_lines = "\n".join(
        f"{idx}. {ref.role} / {ref.source}\n   - 文件：{ref.path}\n   - 理由：{ref.reason}"
        for idx, ref in enumerate(references, start=1)
    ) or "无外部参考图。"
    image_lines = "\n".join(
        (
            f"{idx}. {img.kind}：{img.title}\n"
            f"   - 文件：{img.file_path}\n"
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
