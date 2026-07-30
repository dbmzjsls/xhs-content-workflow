from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import ContentRun, Draft, ImageAsset, ReferenceAsset, ReviewAction, RunStep
from app.time_utils import utc_now


def create_run(session: Session, payload: dict[str, Any]) -> ContentRun:
    run = ContentRun(**payload)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_run(session: Session, run_id: int) -> ContentRun | None:
    return session.get(ContentRun, run_id)


def update_run(
    session: Session,
    run_id: int,
    *,
    status: str | None = None,
    current_step: str | None = None,
    brief: dict[str, Any] | None = None,
    final_package: dict[str, Any] | None = None,
    error: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> ContentRun:
    run = session.get(ContentRun, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    if status is not None:
        run.status = status
    if current_step is not None:
        run.current_step = current_step
    if brief is not None:
        run.brief = brief
    if final_package is not None:
        run.final_package = final_package
    if error is not None:
        run.error = error
    if provider is not None:
        run.provider = provider
    if model is not None:
        run.model = model
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def record_step(
    session: Session,
    run_id: int,
    name: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    *,
    status: str = "completed",
) -> RunStep:
    run = session.get(ContentRun, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    step = RunStep(
        run_id=run_id,
        name=name,
        status=status,
        input_payload=input_payload,
        output_payload=output_payload,
    )
    run.current_step = name
    run.updated_at = utc_now()
    session.add(step)
    session.add(run)
    session.commit()
    session.refresh(step)
    return step


def add_draft(
    session: Session,
    run_id: int,
    *,
    title: str,
    body: str,
    tags: list[str],
    first_comment: str | None,
    narrative_plan: dict[str, Any],
    quality_report: dict[str, Any],
    is_final: bool = False,
    round: int = 1,
    candidate: int = 1,
    parent_draft_id: int | None = None,
    angle: str | None = None,
    source: str | None = None,
    score: float | None = None,
    selected: bool = False,
) -> Draft:
    if selected:
        for existing in session.exec(select(Draft).where(Draft.run_id == run_id, Draft.selected)).all():
            existing.selected = False
            session.add(existing)
    next_version = (
        session.exec(
            select(func.coalesce(func.max(Draft.version), 0) + 1)
            .where(Draft.run_id == run_id)
            .with_for_update()
        ).one()
        or 1
    )
    draft = Draft(
        run_id=run_id,
        version=next_version,
        title=title,
        body=body,
        tags=tags,
        first_comment=first_comment,
        narrative_plan=narrative_plan,
        quality_report=quality_report,
        is_final=is_final,
        round=round,
        candidate=candidate,
        parent_draft_id=parent_draft_id,
        angle=angle,
        source=source,
        score=score,
        selected=selected,
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def get_selected_or_recommended_draft(session: Session, run_id: int) -> Draft | None:
    drafts = session.exec(
        select(Draft).where(Draft.run_id == run_id).order_by(Draft.version)
    ).all()
    if not drafts:
        return None
    selected = [draft for draft in drafts if draft.selected]
    if selected:
        return max(selected, key=lambda draft: draft.version)
    candidates = [
        draft
        for draft in drafts
        if draft.parent_draft_id is None and draft.quality_report.get("hard", {}).get("passed")
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda draft: (-(draft.score if draft.score is not None else -1), draft.candidate, draft.version),
    )


def mark_selected_or_recommended_draft_final(session: Session, run_id: int) -> Draft | None:
    selected_draft = get_selected_or_recommended_draft(session, run_id)
    if selected_draft is None:
        return None
    drafts = session.exec(select(Draft).where(Draft.run_id == run_id)).all()
    for draft in drafts:
        draft.is_final = draft.id == selected_draft.id
        session.add(draft)
    session.commit()
    session.refresh(selected_draft)
    return selected_draft


def mark_latest_draft_final(session: Session, run_id: int) -> Draft | None:
    """Compatibility alias retained for callers before candidate selection existed."""
    return mark_selected_or_recommended_draft_final(session, run_id)


def add_image_asset(
    session: Session,
    run_id: int,
    *,
    kind: str,
    status: str,
    title: str,
    prompt: str,
    reference_reason: str,
    file_path: str | None,
    qc_report: dict[str, Any],
) -> ImageAsset:
    asset = ImageAsset(
        run_id=run_id,
        kind=kind,
        status=status,
        title=title,
        prompt=prompt,
        reference_reason=reference_reason,
        file_path=file_path,
        qc_report=qc_report,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def add_reference(
    session: Session,
    run_id: int,
    *,
    source: str,
    role: str,
    path: str,
    reason: str,
) -> ReferenceAsset:
    ref = ReferenceAsset(run_id=run_id, source=source, role=role, path=path, reason=reason)
    session.add(ref)
    session.commit()
    session.refresh(ref)
    return ref


def add_review_action(
    session: Session,
    run_id: int,
    *,
    action: str,
    instructions: str | None,
    replacement: dict[str, Any] | None,
) -> ReviewAction:
    row = ReviewAction(
        run_id=run_id,
        action=action,
        instructions=instructions,
        replacement=replacement,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_steps(session: Session, run_id: int) -> list[RunStep]:
    return session.exec(select(RunStep).where(RunStep.run_id == run_id)).all()


def list_drafts(session: Session, run_id: int) -> list[Draft]:
    return session.exec(select(Draft).where(Draft.run_id == run_id).order_by(Draft.version)).all()


def list_images(session: Session, run_id: int) -> list[ImageAsset]:
    return session.exec(select(ImageAsset).where(ImageAsset.run_id == run_id)).all()


def list_references(session: Session, run_id: int) -> list[ReferenceAsset]:
    return session.exec(select(ReferenceAsset).where(ReferenceAsset.run_id == run_id)).all()
