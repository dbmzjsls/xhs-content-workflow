from __future__ import annotations

from sqlmodel import Session

from app.repositories import runs as repo
from app.schemas import ReviewRequest, RunCreate
from app.services import content_rules, export_service
from app.workflow.graph import run_workflow


def create_and_run(session: Session, payload: RunCreate):
    run = repo.create_run(
        session,
        {
            "topic": payload.topic,
            "audience": payload.audience,
            "product_function": payload.product_function,
            "pain_point": payload.pain_point,
            "style_preference": payload.style_preference,
            "reference_path": payload.reference_path,
            "brief": payload.model_dump(),
        },
    )
    try:
        run_workflow(session, run.id, payload.model_dump())
    except Exception as exc:
        repo.update_run(session, run.id, status="failed", current_step="failed", error=str(exc))
        raise
    return repo.get_run(session, run.id)


def review_run(session: Session, run_id: int, payload: ReviewRequest):
    run = repo.get_run(session, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    repo.add_review_action(
        session,
        run_id,
        action=payload.action,
        instructions=payload.instructions,
        replacement=payload.replacement,
    )
    if payload.action == "approve":
        return export_service.export_package(session, run_id)
    if payload.action == "replace":
        if payload.replacement is None:
            raise ValueError("replacement is required for replace action")
        replacement = payload.replacement.model_dump()
        draft = repo.add_draft(
            session,
            run_id,
            title=replacement["title"],
            body=replacement["body"],
            tags=replacement["tags"] or content_rules.REQUIRED_TAGS,
            first_comment=replacement.get("first_comment"),
            narrative_plan={"source": "human replacement"},
            quality_report=content_rules.xhs_quality_check(replacement),
        )
        repo.update_run(session, run_id, status="review_required", current_step="human_review")
        return {"draft_id": draft.id, "status": "review_required"}
    drafts = repo.list_drafts(session, run_id)
    if not drafts:
        raise ValueError("no draft to revise")
    latest = drafts[-1]
    revised_body = _append_revision_note(latest.body, payload.instructions)
    revised = {
        "title": latest.title,
        "body": revised_body,
        "tags": latest.tags,
        "first_comment": latest.first_comment,
    }
    quality = content_rules.xhs_quality_check(revised)
    repo.add_draft(
        session,
        run_id,
        title=revised["title"],
        body=revised["body"],
        tags=revised["tags"],
        first_comment=revised["first_comment"],
        narrative_plan=latest.narrative_plan,
        quality_report={"manual_revision": payload.instructions, "post_revision": quality},
    )
    repo.update_run(session, run_id, status="review_required", current_step="human_review")
    return {"status": "review_required"}


def _append_revision_note(body: str, instructions: str | None) -> str:
    body = body.rstrip()
    if not instructions:
        return body[: content_rules.MAX_BODY_CHARS]

    note = f"人工返修备注：{instructions.strip()[:80]}"
    separator = "\n\n"
    max_body_chars = content_rules.MAX_BODY_CHARS - len(separator) - len(note)
    if max_body_chars <= 0:
        return note[: content_rules.MAX_BODY_CHARS]
    if len(body) > max_body_chars:
        body = body[: max_body_chars - 1].rstrip(content_rules.BODY_STRIP_CHARS) + "。"
    return f"{body}{separator}{note}"
