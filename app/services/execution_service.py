from __future__ import annotations

import logging
from time import monotonic
from typing import Any, Callable

from sqlmodel import Session

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
    started = utc_now()
    clock = monotonic()
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

        if _completed_output(session, run_id, "candidate_round") is None:
            _heartbeat(session, run_id)
            result = content_pipeline.generate_candidate_round(brief)
            _require_active(session, run_id, "running")
            content_pipeline.persist_candidate_round(session, run_id, result)
            if result["recommended_candidate"] is None:
                raise RuntimeError("candidate round produced no hard-rule-passing draft")
        repo.record_step(
            session,
            run_id,
            "text_generation",
            {"brief": brief},
            {"candidate_count": len(repo.list_drafts(session, run_id))},
            started_at=started,
            duration_ms=int((monotonic() - clock) * 1000),
        )
        _require_active(session, run_id, "running")
        repo.update_run(
            session,
            run_id,
            status="copy_review_required",
            current_step="copy_review",
            heartbeat_at=utc_now(),
            clear_error=True,
            clear_failed_phase=True,
        )
    except ExecutionCanceled:
        return
    except Exception as exc:
        logger.exception("text execution phase failed", extra={"run_id": run_id})
        _record_phase_failure(session, run_id, "text_generation", started, clock, exc)
        repo.update_run(
            session,
            run_id,
            status="failed",
            current_step="text_generation",
            error=str(exc),
            failed_phase="text",
            heartbeat_at=utc_now(),
        )


def run_image_phase(session: Session, run_id: int) -> None:
    run = repo.get_run(session, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    started = utc_now()
    clock = monotonic()
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
                        "source": "user_upload",
                        "role": "cover_style",
                        "path": upload.file_path,
                        "reason": "User-controlled uploaded reference image.",
                    }
                )
            repo.record_step(
                session, run_id, "reference_select", route, {"items": references}
            )
            for reference in references:
                repo.add_reference(session, run_id, **reference)
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
            _heartbeat(session, run_id)
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
                )
            repo.record_step(session, run_id, "image_qc", {"items": generated}, qc)
        repo.record_step(
            session,
            run_id,
            "image_generation",
            {"draft_id": draft_id},
            {"asset_count": len(repo.list_images(session, run_id))},
            started_at=started,
            duration_ms=int((monotonic() - clock) * 1000),
        )
        _require_active(session, run_id, "image_running")
        repo.update_run(
            session,
            run_id,
            status="asset_review_required",
            current_step="asset_review",
            heartbeat_at=utc_now(),
            clear_error=True,
            clear_failed_phase=True,
        )
    except ExecutionCanceled:
        return
    except Exception as exc:
        logger.exception("image execution phase failed", extra={"run_id": run_id})
        _record_phase_failure(session, run_id, "image_generation", started, clock, exc)
        repo.update_run(
            session,
            run_id,
            status="failed",
            current_step="image_generation",
            error=str(exc),
            failed_phase="image",
            heartbeat_at=utc_now(),
        )


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


def _record_phase_failure(
    session: Session, run_id: int, name: str, started, clock: float, exc: Exception
) -> None:
    repo.record_step(
        session,
        run_id,
        name,
        {},
        {},
        status="failed",
        started_at=started,
        duration_ms=int((monotonic() - clock) * 1000),
        error=str(exc),
    )


def _validate_image_provider() -> None:
    from app.config import get_settings

    provider = get_settings().image_provider.casefold()
    if provider not in {"mock", "openai", "openai-compatible"}:
        raise RuntimeError(f"unsupported image provider: {provider}")


def _heartbeat(session: Session, run_id: int) -> None:
    repo.update_run(session, run_id, heartbeat_at=utc_now())


def _require_active(session: Session, run_id: int, expected: str) -> None:
    session.expire_all()
    run = repo.get_run(session, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    if run.status == "canceled":
        raise ExecutionCanceled()
    if run.status != expected:
        raise RuntimeError(f"run changed state during execution: {run.status}")
