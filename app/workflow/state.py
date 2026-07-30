from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    run_id: int
    brief: dict[str, Any]
    style_route: dict[str, Any]
    narrative_plan: dict[str, Any]
    candidate_round: dict[str, Any]
    draft: dict[str, Any]
    humanize_report: dict[str, Any]
    quality_report: dict[str, Any]
    revised_draft: dict[str, Any]
    image_task: dict[str, Any]
    references: list[dict[str, Any]]
    image_prompts: list[dict[str, Any]]
    image_assets: list[dict[str, Any]]
    image_qc: dict[str, Any]
    awaiting_review: bool
