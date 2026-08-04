from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import ContentRun
from app.services import content_pipeline, content_rules


def _brief() -> dict[str, str]:
    return {
        "topic": "fixing an IELTS essay",
        "audience": "IELTS self-study learner",
        "product_function": "Writing Checker",
        "pain_point": "I cannot see why my essay is stuck",
        "style_preference": "memoir",
    }


def _valid_draft(number: int) -> dict[str, object]:
    return {
        "title": f"Candidate {number}",
        "body": (
            "晚上11点在书桌前，我重读同一段雅思作文。"
            f"我改了三遍还是卡住，后来 {content_rules.BRAND_FULL} 帮我发现例子没有托住观点。"
        ),
        "tags": [*content_rules.REQUIRED_TAGS, "#study"],
        "first_comment": "What is one sentence you would check first?",
    }


def test_example_selection_is_limited_and_deterministic():
    first = content_pipeline.select_examples(_brief())
    second = content_pipeline.select_examples(_brief())

    assert first == second
    assert len(first["positive"]) <= 3
    assert len(first["negative"]) <= 2
    assert all(item["type"] == "positive" for item in first["positive"])
    assert all(item["type"] == "negative" for item in first["negative"])


def test_example_selection_orders_by_tag_relevance_then_id():
    selected = content_pipeline.select_examples(_brief())

    assert [item["id"] for item in selected["positive"]] == [
        "writing-night-desk-positive",
        "writing-before-after-positive",
        "writing-discovery-positive",
    ]
    assert [item["id"] for item in selected["negative"]] == [
        "hard-sell-negative",
        "generic-negative",
    ]


def test_generate_round_has_exactly_three_distinct_angles_and_metadata():
    result = content_pipeline.generate_candidate_round(_brief(), provider=content_pipeline.MockPipelineProvider())

    assert [candidate["candidate"] for candidate in result["candidates"]] == [1, 2, 3]
    assert [candidate["angle"] for candidate in result["candidates"]] == list(
        content_pipeline.ANGLES
    )
    assert len(result["candidates"]) == 3
    assert result["policy_version"]
    assert result["selected_example_ids"]


def test_ranking_excludes_hard_rule_failures_and_uses_candidate_number_for_ties():
    good = {**_valid_draft(1), "candidate": 1, "angle": content_pipeline.ANGLES[0]}
    bad = {
        **_valid_draft(2),
        "candidate": 2,
        "angle": content_pipeline.ANGLES[1],
        "body": "Buy now, guaranteed score improvement!",
    }
    tied = {**_valid_draft(3), "candidate": 3, "angle": content_pipeline.ANGLES[2]}

    ranked = content_pipeline.rank_candidates([good, bad, tied])

    assert ranked[0]["candidate"] == 1
    assert ranked[-1]["candidate"] == 2
    assert not ranked[-1]["recommendable"]
    assert ranked[0]["recommended"]


def test_soft_score_has_five_bounded_dimensions_and_a_100_point_total():
    report = content_pipeline.soft_score(_valid_draft(1))

    assert set(report["dimensions"]) == {
        "specificity",
        "emotional_value",
        "narrative_coherence",
        "natural_product_integration",
        "usefulness_conversational_tone",
    }
    assert all(0 <= score <= 20 for score in report["dimensions"].values())
    assert report["total"] == sum(report["dimensions"].values())
    assert 0 <= report["total"] <= 100


def test_malformed_provider_draft_is_rejected_without_mock_fallback():
    class MalformedProvider:
        name = "malformed"
        model = "test"

        def generate_candidate(self, brief, angle, examples):
            return {"title": "missing fields"}

        def repair_candidate(self, draft, brief, angle, issues):
            return draft

        def revise_draft(self, draft, brief, instructions, hard_rules):
            return draft

    with pytest.raises(RuntimeError, match="provider draft"):
        content_pipeline.generate_candidate_round(_brief(), provider=MalformedProvider())


def test_one_repair_is_attempted_but_a_second_failure_is_not_repaired():
    class RepairingProvider:
        name = "test"
        model = "test-model"

        def generate_candidate(self, brief, angle, examples):
            return {**_valid_draft(1), "body": "Buy now, guaranteed score improvement!"}

        def repair_candidate(self, draft, brief, angle, issues):
            return {**draft, "body": "Buy now, guaranteed score improvement!"}

        def revise_draft(self, draft, brief, instructions, hard_rules):
            return draft

    result = content_pipeline.generate_candidate_round(_brief(), provider=RepairingProvider())

    assert all(candidate["repair_attempts"] == 1 for candidate in result["candidates"])
    assert all(not candidate["hard_report"]["passed"] for candidate in result["candidates"])
    assert result["recommended_candidate"] is None


def test_persisted_candidates_and_provider_revision_keep_real_parent_child_link():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        run = ContentRun(
            topic="topic", audience="audience", product_function="Writing Checker", pain_point="pain"
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        round_result = content_pipeline.generate_candidate_round(
            _brief(), provider=content_pipeline.MockPipelineProvider()
        )
        drafts = content_pipeline.persist_candidate_round(session, run.id, round_result)
        parent = drafts[0]
        child = content_pipeline.create_revision(
            session,
            parent,
            _brief(),
            "Make the ending more practical.",
            provider=content_pipeline.MockPipelineProvider(),
        )
        parent_id = parent.id
        child_parent_id = child.parent_draft_id
        child_round = child.round
        parent_round = parent.round
        child_body = child.body
        parent_body = parent.body

    assert len(drafts) == 3
    assert child_parent_id == parent_id
    assert child_round == parent_round + 1
    assert child_body != parent_body
    assert "revision note" not in child_body.lower()


def test_mock_revision_changes_with_the_supplied_instructions():
    provider = content_pipeline.MockPipelineProvider()
    draft = _valid_draft(1)
    instructions = [
        "Make the product feel less prominent.",
        "Change the ending into an authentic record.",
        "Make the tone more conversational.",
        "Make it shorter.",
        "Reshape the narrative.",
    ]
    revisions = [provider.revise_draft(draft, _brief(), instruction, {}) for instruction in instructions]

    assert all(revised["body"] != draft["body"] for revised in revisions)
    assert len({revised["body"] for revised in revisions}) == len(revisions)
    assert all(instruction.casefold() not in revised["body"].casefold() for instruction, revised in zip(instructions, revisions))
    assert all(content_pipeline.hard_rule_check(revised)["passed"] for revised in revisions)
    assert len(revisions[3]["body"]) < len(draft["body"])
    readable = provider.revise_draft(draft, _brief(), "Make it more readable.", {})
    assert "tool in the background" not in readable["body"]


def test_policy_requires_non_empty_string_collections(monkeypatch):
    monkeypatch.setattr(
        content_pipeline,
        "_read_yaml",
        lambda name: {
            "version": "x",
            "brand_name": "Cathoven猫多芬雅思",
            "required_tags": [],
            "hard_sell_terms": ["buy now"],
            "scene_markers": ["地铁"],
            "discovery_markers": ["后来"],
        },
    )

    with pytest.raises(ValueError, match="required_tags"):
        content_pipeline.load_policy()


def test_examples_reject_duplicate_ids_and_invalid_tag_value_types(monkeypatch):
    valid = {
        "id": "example",
        "type": "positive",
        "audience_tags": ["ielts"],
        "function_tags": ["writing"],
        "style_tags": ["memoir"],
        "title": "title",
        "body": "body",
        "tags": ["#tag"],
        "rationale": "why",
    }
    monkeypatch.setattr(content_pipeline, "_read_yaml", lambda name: {"examples": [valid, dict(valid)]})
    with pytest.raises(ValueError, match="duplicate"):
        content_pipeline.load_examples()

    invalid = {**valid, "id": "other", "tags": "#not-a-list"}
    monkeypatch.setattr(content_pipeline, "_read_yaml", lambda name: {"examples": [invalid]})
    with pytest.raises(ValueError, match="tags"):
        content_pipeline.load_examples()
