from __future__ import annotations

import json

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings
from app.models import ContentRun
from app.repositories import runs as repo
from app.services import export_service
from app.workflow.graph import run_workflow


def _brief() -> dict[str, str]:
    return {
        "topic": "fixing an IELTS essay",
        "audience": "IELTS self-study learner",
        "product_function": "Writing Checker",
        "pain_point": "I cannot see why my essay is stuck",
        "style_preference": "memoir",
    }


def _run(session: Session) -> ContentRun:
    run = ContentRun(
        topic="topic", audience="audience", product_function="Writing Checker", pain_point="pain"
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def test_normal_workflow_persists_three_scored_candidates_and_uses_selected(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("IMAGE_API_KEY", raising=False)
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    get_settings.cache_clear()
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        run = _run(session)
        state = run_workflow(session, run.id, _brief())
        drafts = repo.list_drafts(session, run.id)
        steps = repo.list_steps(session, run.id)

    assert len(drafts) == 3
    assert [draft.candidate for draft in drafts] == [1, 2, 3]
    assert all(draft.score is not None for draft in drafts)
    assert sum(draft.selected for draft in drafts) == 1
    selected = next(draft for draft in drafts if draft.selected)
    assert state["revised_draft"]["candidate"] == selected.candidate
    candidate_step = next(step for step in steps if step.name == "candidate_round")
    assert candidate_step.output_payload["policy_version"]
    assert candidate_step.output_payload["selected_example_ids"]
    assert candidate_step.output_payload["provider"] == "mock"
    assert candidate_step.output_payload["model"] == "deterministic-v1"
    get_settings.cache_clear()


def test_export_prefers_selected_draft_over_newer_unselected_draft(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    get_settings.cache_clear()
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        run = _run(session)
        older_selected = repo.add_draft(
            session, run.id, title="selected", body="body", tags=[], first_comment=None,
            narrative_plan={}, quality_report={"hard": {"passed": True}}, score=40, selected=True,
        )
        repo.add_draft(
            session, run.id, title="newer", body="body", tags=[], first_comment=None,
            narrative_plan={}, quality_report={"hard": {"passed": True}}, score=99, selected=False,
        )
        export_service.export_package(session, run.id)
        selected_id = older_selected.id

    payload = json.loads((tmp_path / "exports" / str(run.id) / "package.json").read_text("utf-8"))
    assert payload["draft"]["id"] == selected_id
    get_settings.cache_clear()


def test_export_falls_back_to_best_recommended_candidate(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    get_settings.cache_clear()
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        run = _run(session)
        repo.add_draft(
            session, run.id, title="low", body="body", tags=[], first_comment=None,
            narrative_plan={}, quality_report={"hard": {"passed": True}}, score=40, candidate=1,
        )
        best = repo.add_draft(
            session, run.id, title="best", body="body", tags=[], first_comment=None,
            narrative_plan={}, quality_report={"hard": {"passed": True}}, score=80, candidate=2,
        )
        repo.add_draft(
            session, run.id, title="failed", body="body", tags=[], first_comment=None,
            narrative_plan={}, quality_report={"hard": {"passed": False}}, score=100, candidate=3,
        )
        export_service.export_package(session, run.id)
        best_id = best.id

    payload = json.loads((tmp_path / "exports" / str(run.id) / "package.json").read_text("utf-8"))
    assert payload["draft"]["id"] == best_id
    get_settings.cache_clear()
