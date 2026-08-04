from __future__ import annotations

from sqlmodel import Session

from app.repositories import runs as repo
from app.services import content_pipeline, content_rules, image_rules
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
    result = content_pipeline.generate_candidate_round(state["brief"])
    content_pipeline.persist_candidate_round(session, state["run_id"], result)
    selected = next((item for item in result["candidates"] if item["recommended"]), None)
    if selected is None:
        raise ValueError("candidate round produced no hard-rule-passing draft")
    return {"candidate_round": result, "draft": selected, "revised_draft": selected}


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
    repo.update_run(
        session, state["run_id"], status="copy_review_required", current_step="copy_review"
    )
    return {"awaiting_review": True}


WORKFLOW_STEPS = (
    _brief_normalize,
    _style_route,
    _narrative_plan,
    _draft_generate,
    _image_task_classify,
    _reference_select,
    _prompt_rewrite,
    _image_generate,
    _image_qc,
    _human_review,
)
