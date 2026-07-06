from __future__ import annotations

from sqlmodel import Session

from app.repositories import runs as repo
from app.services import content_rules, image_rules, llm_provider
from app.workflow.state import WorkflowState


def run_workflow(session: Session, run_id: int, brief: dict) -> WorkflowState:
    state: WorkflowState = {"run_id": run_id, "brief": brief}
    for step in WORKFLOW_STEPS:
        state.update(step(session, state))
    return state


def _brief_normalize(session: Session, state: WorkflowState) -> WorkflowState:
    out = content_rules.normalize_brief(state["brief"])
    repo.record_step(session, state["run_id"], "brief_normalize", state["brief"], out)
    repo.update_run(session, state["run_id"], brief=out)
    return {"brief": out}


def _style_route(session: Session, state: WorkflowState) -> WorkflowState:
    out = content_rules.route_style(state["brief"])
    repo.record_step(session, state["run_id"], "style_route", state["brief"], out)
    return {"style_route": out}


def _narrative_plan(session: Session, state: WorkflowState) -> WorkflowState:
    out = content_rules.build_narrative_plan(state["brief"], state["style_route"])
    repo.record_step(
        session,
        state["run_id"],
        "narrative_plan",
        {"brief": state["brief"], "style_route": state["style_route"]},
        out,
    )
    return {"narrative_plan": out}


def _draft_generate(session: Session, state: WorkflowState) -> WorkflowState:
    out = llm_provider.generate_draft(state["brief"], state["narrative_plan"])
    repo.record_step(session, state["run_id"], "draft_generate", state["narrative_plan"], out)
    return {"draft": out}


def _humanize_check(session: Session, state: WorkflowState) -> WorkflowState:
    out = content_rules.humanize_check(state["draft"])
    repo.record_step(session, state["run_id"], "humanize_check", state["draft"], out)
    return {"humanize_report": out}


def _xhs_quality_check(session: Session, state: WorkflowState) -> WorkflowState:
    out = content_rules.xhs_quality_check(state["draft"])
    repo.record_step(session, state["run_id"], "xhs_quality_check", state["draft"], out)
    return {"quality_report": out}


def _revision(session: Session, state: WorkflowState) -> WorkflowState:
    out = content_rules.revise_draft(
        state["draft"],
        state["quality_report"],
        state["humanize_report"],
    )
    repo.record_step(
        session,
        state["run_id"],
        "revision",
        {
            "draft": state["draft"],
            "quality_report": state["quality_report"],
            "humanize_report": state["humanize_report"],
        },
        out,
    )
    repo.add_draft(
        session,
        state["run_id"],
        title=out["title"],
        body=out["body"],
        tags=out["tags"],
        first_comment=out.get("first_comment"),
        narrative_plan=state["narrative_plan"],
        quality_report=out["quality_report"],
    )
    return {"revised_draft": out}


def _image_task_classify(session: Session, state: WorkflowState) -> WorkflowState:
    out = image_rules.classify_image_tasks(state["brief"], state["style_route"])
    repo.record_step(
        session,
        state["run_id"],
        "image_task_classify",
        {"brief": state["brief"], "style_route": state["style_route"]},
        out,
    )
    return {"image_task": out}


def _reference_select(session: Session, state: WorkflowState) -> WorkflowState:
    out = image_rules.select_references(state["run_id"], state["brief"], state["image_task"])
    for ref in out:
        repo.add_reference(session, state["run_id"], **ref)
    repo.record_step(session, state["run_id"], "reference_select", state["image_task"], {"items": out})
    return {"references": out}


def _prompt_rewrite(session: Session, state: WorkflowState) -> WorkflowState:
    out = image_rules.rewrite_image_prompts(
        state["brief"],
        state["style_route"],
        state["revised_draft"],
        state["image_task"],
        state["references"],
    )
    repo.record_step(session, state["run_id"], "prompt_rewrite", state["image_task"], {"items": out})
    return {"image_prompts": out}


def _image_generate(session: Session, state: WorkflowState) -> WorkflowState:
    out = image_rules.generate_image_assets(state["run_id"], state["image_prompts"])
    repo.record_step(
        session,
        state["run_id"],
        "image_generate",
        {"items": state["image_prompts"]},
        {"items": out},
    )
    return {"image_assets": out}


def _image_qc(session: Session, state: WorkflowState) -> WorkflowState:
    qc = image_rules.image_qc(state["image_assets"])
    for asset in state["image_assets"]:
        repo.add_image_asset(
            session,
            state["run_id"],
            kind=asset["kind"],
            status=asset["status"],
            title=asset["title"],
            prompt=asset["prompt"],
            reference_reason=asset["reference_reason"],
            file_path=asset.get("file_path"),
            qc_report=qc,
        )
    repo.record_step(session, state["run_id"], "image_qc", {"items": state["image_assets"]}, qc)
    return {"image_qc": qc}


def _human_review(session: Session, state: WorkflowState) -> WorkflowState:
    out = {
        "awaiting_review": True,
        "message": "等待人工审核：通过、返修或替换最终稿。",
    }
    repo.record_step(session, state["run_id"], "human_review", state["revised_draft"], out)
    repo.update_run(session, state["run_id"], status="review_required", current_step="human_review")
    return {"awaiting_review": True}


WORKFLOW_STEPS = (
    _brief_normalize,
    _style_route,
    _narrative_plan,
    _draft_generate,
    _humanize_check,
    _xhs_quality_check,
    _revision,
    _image_task_classify,
    _reference_select,
    _prompt_rewrite,
    _image_generate,
    _image_qc,
    _human_review,
)
