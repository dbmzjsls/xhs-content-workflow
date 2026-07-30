from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy import update
from sqlmodel import Session

from app.models import ContentRun
from app.repositories import runs as repo
from app.services import content_pipeline, content_rules, image_rules
from app.time_utils import utc_now

logger = logging.getLogger(__name__)


class ExecutionCanceled(RuntimeError):
    pass


def run_text_phase(session: Session, run_id: int) -> None:
    run = repo.get_run(session, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    phase_step = repo.start_step(session, run_id, "text_generation", {"brief": run.brief})
    try:
        _require_active(session, run_id, "running")
        brief = _completed_output(session, run_id, "brief_normalize")
        if brief is None:
            brief = content_rules.normalize_brief(run.brief)
            repo.record_step(session, run_id, "brief_normalize", run.brief, brief)
            repo.update_run(session, run_id, brief=brief)

        route = _completed_output(session, run_id, "style_route")
        if route is None:
            route = content_rules.route_style(brief)
            repo.record_step(session, run_id, "style_route", brief, route)

        plan = _completed_output(session, run_id, "narrative_plan")
        if plan is None:
            plan = content_rules.build_narrative_plan(brief, route)
            repo.record_step(
                session, run_id, "narrative_plan", {"brief": brief, "style_route": route}, plan
            )

        result = _completed_output(session, run_id, "candidate_round")
        persist_round = result is None
        if result is None:
            _heartbeat(session, run_id, phase_step.id)
            result = content_pipeline.generate_candidate_round(brief)
        _publish_candidates_atomically(
            session,
            run_id,
            phase_step.id,
            result,
            persist_round=persist_round,
        )
    except ExecutionCanceled:
        session.rollback()
        repo.finish_step(session, phase_step.id, status="failed", error="canceled")
        return
    except Exception as exc:
        logger.exception("text execution phase failed", extra={"run_id": run_id})
        session.rollback()
        if _run_is_canceled(session, run_id):
            repo.finish_step(session, phase_step.id, status="failed", error="canceled")
            return
        repo.finish_step(session, phase_step.id, status="failed", error=str(exc))
        _mark_failed_if_active(session, run_id, "running", "text", str(exc))


def run_image_phase(session: Session, run_id: int) -> None:
    run = repo.get_run(session, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    phase_step = repo.start_step(
        session, run_id, "image_generation", {"selected_draft": True}
    )
    try:
        _require_active(session, run_id, "image_running")
        _validate_image_provider()
        draft = repo.get_selected_or_recommended_draft(session, run_id)
        if draft is None:
            raise RuntimeError("no selected draft for image generation")
        # Repository helpers commit individual durable steps; capture this before
        # SQLAlchemy expires the selected row on a later commit.
        draft_payload = draft.model_dump(mode="json")
        draft_id = draft.id
        brief = run.brief
        route = _step_value(
            session,
            run_id,
            "image_task_classify",
            lambda: image_rules.classify_image_tasks(brief, content_rules.route_style(brief)),
            brief,
        )

        reference_output = _completed_output(session, run_id, "reference_select")
        if reference_output is None:
            references = image_rules.select_references(run_id, brief, route)
            for upload in repo.list_uploads(session, run_id):
                references.append(
                    {
                        "source": f"user_upload:{upload.id}",
                        "role": "cover_style",
                        "path": upload.file_path,
                        "asset_id": upload.id,
                        "label": f"upload:{upload.id}",
                        "reason": "User-controlled uploaded reference image.",
                    }
                )
            repo.record_step(
                session, run_id, "reference_select", route, {"items": references}
            )
            for reference in references:
                repo.add_reference(
                    session,
                    run_id,
                    source=reference["source"],
                    role=reference["role"],
                    path=reference["path"],
                    reason=reference["reason"],
                )
        else:
            references = list(reference_output.get("items", []))

        prompt_output = _completed_output(session, run_id, "prompt_rewrite")
        if prompt_output is None:
            prompts = image_rules.rewrite_image_prompts(
                brief,
                content_rules.route_style(brief),
                draft_payload,
                route,
                references,
            )
            repo.record_step(session, run_id, "prompt_rewrite", route, {"items": prompts})
        else:
            prompts = list(prompt_output.get("items", []))

        generated_output = _completed_output(session, run_id, "image_generate")
        if generated_output is None:
            _heartbeat(session, run_id, phase_step.id)
            generated = image_rules.generate_image_assets(run_id, prompts)
            _require_active(session, run_id, "image_running")
            repo.record_step(
                session, run_id, "image_generate", {"items": prompts}, {"items": generated}
            )
        else:
            generated = list(generated_output.get("items", []))

        if _completed_output(session, run_id, "image_qc") is None:
            qc = image_rules.image_qc(generated)
            if not qc["passed"]:
                raise RuntimeError("image quality checks failed: " + "; ".join(qc["issues"]))
        else:
            qc = _completed_output(session, run_id, "image_qc") or {}
        _publish_images_atomically(
            session, run_id, phase_step.id, draft_id, generated, qc
        )
    except ExecutionCanceled:
        session.rollback()
        repo.finish_step(session, phase_step.id, status="failed", error="canceled")
        return
    except Exception as exc:
        logger.exception("image execution phase failed", extra={"run_id": run_id})
        session.rollback()
        if _run_is_canceled(session, run_id):
            repo.finish_step(session, phase_step.id, status="failed", error="canceled")
            return
        repo.finish_step(session, phase_step.id, status="failed", error=str(exc))
        _mark_failed_if_active(session, run_id, "image_running", "image", str(exc))


def _step_value(
    session: Session,
    run_id: int,
    name: str,
    factory: Callable[[], dict[str, Any]],
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    existing = _completed_output(session, run_id, name)
    if existing is not None:
        return existing
    output = factory()
    repo.record_step(session, run_id, name, input_payload, output)
    return output


def _completed_output(session: Session, run_id: int, name: str) -> dict[str, Any] | None:
    completed = [step for step in repo.list_steps(session, run_id) if step.name == name and step.status == "completed"]
    return completed[-1].output_payload if completed else None


def _validate_image_provider() -> None:
    from app.config import get_settings

    provider = get_settings().image_provider.casefold()
    if provider not in {"mock", "openai", "openai-compatible"}:
        raise RuntimeError(f"unsupported image provider: {provider}")


def _heartbeat(session: Session, run_id: int, step_id: int) -> None:
    repo.heartbeat_step(session, run_id, step_id)


def _require_active(session: Session, run_id: int, expected: str) -> None:
    session.expire_all()
    run = repo.get_run(session, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    if run.status == "canceled":
        raise ExecutionCanceled()
    if run.status != expected:
        raise RuntimeError(f"run changed state during execution: {run.status}")


def _run_is_canceled(session: Session, run_id: int) -> bool:
    session.expire_all()
    run = repo.get_run(session, run_id)
    return run is not None and run.status == "canceled"


def _mark_failed_if_active(
    session: Session, run_id: int, expected: str, phase: str, error: str
) -> None:
    now = utc_now()
    session.exec(
        update(ContentRun)
        .where(ContentRun.id == run_id, ContentRun.status == expected)
        .values(
            status="failed",
            current_step=f"{phase}_generation",
            error=error,
            failed_phase=phase,
            heartbeat_at=now,
            updated_at=now,
        )
    )
    session.commit()


def _publish_candidates_atomically(
    session: Session,
    run_id: int,
    phase_step_id: int,
    result: dict[str, Any],
    *,
    persist_round: bool,
) -> None:
    hook = globals().get("_before_text_publish")
    if hook is not None:
        hook(run_id)
    eligible = any(
        candidate.get("candidate") == result.get("recommended_candidate")
        and candidate.get("hard_report", {}).get("passed") is True
        for candidate in result.get("candidates", [])
    )
    now = utc_now()
    error = None if eligible else "candidate round produced no hard-rule-passing draft"
    session.rollback()
    transitioned = session.exec(
        update(ContentRun)
        .where(ContentRun.id == run_id, ContentRun.status == "running")
        .values(
            heartbeat_at=now,
            updated_at=now,
        )
    )
    if transitioned.rowcount != 1:
        session.rollback()
        raise ExecutionCanceled()
    if persist_round:
        content_pipeline.persist_candidate_round(
            session, run_id, result, commit=False
        )
    repo.finish_step(
        session,
        phase_step_id,
        status="completed" if eligible else "failed",
        output_payload={
            "candidate_count": len(result.get("candidates", [])),
            "recommended_candidate": result.get("recommended_candidate"),
        },
        error=error,
        commit=False,
    )
    repo.update_run(
        session,
        run_id,
        status="copy_review_required" if eligible else "failed",
        current_step="copy_review" if eligible else "text_generation",
        error=error,
        failed_phase=None if eligible else "text",
        clear_error=eligible,
        clear_failed_phase=eligible,
        heartbeat_at=now,
        commit=False,
    )
    session.commit()


def _publish_images_atomically(
    session: Session,
    run_id: int,
    phase_step_id: int,
    draft_id: int,
    generated: list[dict[str, Any]],
    qc: dict[str, Any],
) -> None:
    hook = globals().get("_before_image_publish")
    if hook is not None:
        hook(run_id)
    session.rollback()
    now = utc_now()
    transitioned = session.exec(
        update(ContentRun)
        .where(ContentRun.id == run_id, ContentRun.status == "image_running")
        .values(
            heartbeat_at=now,
            updated_at=now,
        )
    )
    if transitioned.rowcount != 1:
        session.rollback()
        raise ExecutionCanceled()
    for asset in generated:
        repo.add_image_asset(
            session,
            run_id,
            kind=asset["kind"],
            status=asset["status"],
            title=asset["title"],
            prompt=asset["prompt"],
            reference_reason=asset["reference_reason"],
            file_path=asset["file_path"],
            qc_report=qc,
            commit=False,
        )
    repo.record_step(
        session, run_id, "image_qc", {"items": generated}, qc, commit=False
    )
    repo.finish_step(
        session,
        phase_step_id,
        status="completed",
        output_payload={"draft_id": draft_id, "asset_count": len(generated)},
        commit=False,
    )
    repo.update_run(
        session,
        run_id,
        status="asset_review_required",
        current_step="asset_review",
        clear_error=True,
        clear_failed_phase=True,
        heartbeat_at=now,
        commit=False,
    )
    session.commit()
