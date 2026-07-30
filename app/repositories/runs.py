from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import (
    ContentRun,
    Draft,
    IdempotencyRecord,
    ImageAsset,
    ReferenceAsset,
    ReviewAction,
    RunStep,
    UploadAsset,
)
from app.time_utils import utc_now


def create_run(
    session: Session, payload: dict[str, Any], *, commit: bool = True
) -> ContentRun:
    run = ContentRun(**payload)
    session.add(run)
    _save(session, run, commit=commit)
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
    heartbeat_at: datetime | None = None,
    failed_phase: str | None = None,
    clear_error: bool = False,
    clear_failed_phase: bool = False,
    commit: bool = True,
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
    if heartbeat_at is not None:
        run.heartbeat_at = heartbeat_at
    if failed_phase is not None:
        run.failed_phase = failed_phase
    if clear_error:
        run.error = None
    if clear_failed_phase:
        run.failed_phase = None
    run.updated_at = utc_now()
    session.add(run)
    _save(session, run, commit=commit)
    return run


def record_step(
    session: Session,
    run_id: int,
    name: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    *,
    status: str = "completed",
    attempt: int | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
    error_type: str | None = None,
    commit: bool = True,
) -> RunStep:
    run = session.get(ContentRun, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    now = utc_now()
    actual_started = started_at or now
    actual_completed = completed_at or (now if status in {"completed", "failed"} else None)
    if attempt is None:
        attempt = (
            session.exec(
                select(func.coalesce(func.max(RunStep.attempt), 0) + 1).where(
                    RunStep.run_id == run_id, RunStep.name == name
                )
            ).one()
            or 1
        )
    if duration_ms is None and actual_completed is not None:
        duration_ms = max(0, int((actual_completed - actual_started).total_seconds() * 1000))
    step = RunStep(
        run_id=run_id,
        name=name,
        status=status,
        input_payload=input_payload,
        output_payload=output_payload,
        attempt=attempt,
        started_at=actual_started,
        heartbeat_at=now,
        completed_at=actual_completed,
        duration_ms=duration_ms,
        error=error,
        error_type=error_type,
    )
    run.current_step = name
    run.heartbeat_at = now
    run.updated_at = utc_now()
    session.add(step)
    session.add(run)
    _save(session, step, commit=commit)
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
    commit: bool = True,
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
    _save(session, draft, commit=commit)
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


def mark_selected_or_recommended_draft_final(
    session: Session, run_id: int, *, commit: bool = True
) -> Draft | None:
    selected_draft = get_selected_or_recommended_draft(session, run_id)
    if selected_draft is None:
        return None
    drafts = session.exec(select(Draft).where(Draft.run_id == run_id)).all()
    for draft in drafts:
        draft.is_final = draft.id == selected_draft.id
        session.add(draft)
    _save(session, selected_draft, commit=commit)
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
    commit: bool = True,
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
    _save(session, asset, commit=commit)
    return asset


def add_reference(
    session: Session,
    run_id: int,
    *,
    source: str,
    role: str,
    path: str,
    reason: str,
    commit: bool = True,
) -> ReferenceAsset:
    ref = ReferenceAsset(run_id=run_id, source=source, role=role, path=path, reason=reason)
    session.add(ref)
    _save(session, ref, commit=commit)
    return ref


def add_review_action(
    session: Session,
    run_id: int,
    *,
    action: str,
    instructions: str | None,
    replacement: dict[str, Any] | None,
    commit: bool = True,
) -> ReviewAction:
    row = ReviewAction(
        run_id=run_id,
        action=action,
        instructions=instructions,
        replacement=replacement,
    )
    session.add(row)
    _save(session, row, commit=commit)
    return row


def list_steps(session: Session, run_id: int) -> list[RunStep]:
    return session.exec(select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.id)).all()


def list_drafts(session: Session, run_id: int) -> list[Draft]:
    return session.exec(select(Draft).where(Draft.run_id == run_id).order_by(Draft.version)).all()


def list_images(session: Session, run_id: int) -> list[ImageAsset]:
    return session.exec(select(ImageAsset).where(ImageAsset.run_id == run_id)).all()


def list_references(session: Session, run_id: int) -> list[ReferenceAsset]:
    return session.exec(select(ReferenceAsset).where(ReferenceAsset.run_id == run_id)).all()


def list_runs(
    session: Session, *, status: str | None, limit: int, offset: int
) -> tuple[list[ContentRun], int]:
    where = ContentRun.status == status if status else None
    statement = select(ContentRun)
    count_statement = select(func.count(ContentRun.id))
    if where is not None:
        statement = statement.where(where)
        count_statement = count_statement.where(where)
    rows = session.exec(
        statement.order_by(ContentRun.created_at.desc(), ContentRun.id.desc()).offset(offset).limit(limit)
    ).all()
    return list(rows), int(session.exec(count_statement).one())


def get_image(session: Session, run_id: int, asset_id: int) -> ImageAsset | None:
    return session.exec(
        select(ImageAsset).where(ImageAsset.id == asset_id, ImageAsset.run_id == run_id)
    ).first()


def get_upload(session: Session, upload_id: int) -> UploadAsset | None:
    return session.get(UploadAsset, upload_id)


def get_run_upload(session: Session, run_id: int, upload_id: int) -> UploadAsset | None:
    return session.exec(
        select(UploadAsset).where(UploadAsset.id == upload_id, UploadAsset.run_id == run_id)
    ).first()


def list_uploads(session: Session, run_id: int) -> list[UploadAsset]:
    return list(session.exec(select(UploadAsset).where(UploadAsset.run_id == run_id)).all())


def get_idempotency(session: Session, key: str) -> IdempotencyRecord | None:
    return session.exec(select(IdempotencyRecord).where(IdempotencyRecord.key == key)).first()


def next_step_attempt(session: Session, run_id: int, name: str) -> int:
    return int(
        session.exec(
            select(func.coalesce(func.max(RunStep.attempt), 0) + 1).where(
                RunStep.run_id == run_id, RunStep.name == name
            )
        ).one()
        or 1
    )


def start_step(
    session: Session,
    run_id: int,
    name: str,
    input_payload: dict[str, Any],
    *,
    commit: bool = True,
) -> RunStep:
    now = utc_now()
    attempt = (
        session.exec(
            select(func.coalesce(func.max(RunStep.attempt), 0) + 1).where(
                RunStep.run_id == run_id, RunStep.name == name
            )
        ).one()
        or 1
    )
    step = RunStep(
        run_id=run_id,
        name=name,
        status="running",
        input_payload=input_payload,
        output_payload={},
        attempt=attempt,
        started_at=now,
        heartbeat_at=now,
    )
    run = get_run(session, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    run.current_step = name
    run.heartbeat_at = now
    run.updated_at = now
    session.add(run)
    session.add(step)
    _save(session, step, commit=commit)
    return step


def heartbeat_step(session: Session, run_id: int, step_id: int) -> None:
    now = utc_now()
    step = session.get(RunStep, step_id)
    run = get_run(session, run_id)
    if step is None or run is None:
        raise ValueError("run step not found")
    step.heartbeat_at = now
    run.heartbeat_at = now
    run.updated_at = now
    session.add(step)
    session.add(run)
    session.commit()


def finish_step(
    session: Session,
    step_id: int,
    *,
    status: str,
    output_payload: dict[str, Any] | None = None,
    error: str | None = None,
    error_type: str | None = None,
    commit: bool = True,
) -> RunStep:
    step = session.get(RunStep, step_id)
    if step is None:
        raise ValueError(f"run step {step_id} not found")
    now = utc_now()
    step.status = status
    step.output_payload = output_payload or {}
    step.error = error
    step.error_type = error_type
    step.heartbeat_at = now
    step.completed_at = now
    if step.started_at is not None:
        comparable_now = now if step.started_at.tzinfo else now.replace(tzinfo=None)
        step.duration_ms = max(
            0, int((comparable_now - step.started_at).total_seconds() * 1000)
        )
    session.add(step)
    _save(session, step, commit=commit)
    return step


def _save(session: Session, row, *, commit: bool) -> None:
    if commit:
        session.commit()
        session.refresh(row)
    else:
        session.flush()
