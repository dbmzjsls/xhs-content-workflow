from __future__ import annotations

from sqlmodel import Session

from app.repositories import runs as repo
from app.schemas import ReviewRequest, RunCreate
from app.services import content_pipeline, content_rules, export_service
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
    child = content_pipeline.create_revision(
        session,
        latest,
        run.brief,
        payload.instructions or "Improve clarity while preserving the original meaning.",
    )
    repo.update_run(session, run_id, status="review_required", current_step="human_review")
    return {"draft_id": child.id, "status": "review_required"}
