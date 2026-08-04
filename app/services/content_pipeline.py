"""Deterministic, auditable content candidate pipeline.

This module deliberately has no HTTP or worker dependency.  The same inputs,
policy, examples, and mock provider always produce the same ranked round.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

import yaml
from sqlmodel import Session

from app.config import ROOT_DIR, get_settings
from app.models import Draft
from app.repositories import runs as repo
from app.services import content_rules

ANGLES = (
    "pain-scene narrative",
    "before/after contrast",
    "discovery-based experience summary",
)
LIBRARY_DIR = ROOT_DIR / "content_library"


class PipelineProvider(Protocol):
    name: str
    model: str | None

    def generate_candidate(
        self, brief: dict[str, Any], angle: str, examples: dict[str, list[dict[str, Any]]]
    ) -> dict[str, Any]: ...

    def repair_candidate(
        self,
        draft: dict[str, Any],
        brief: dict[str, Any],
        angle: str,
        issues: list[str],
    ) -> dict[str, Any]: ...

    def revise_draft(
        self,
        draft: dict[str, Any],
        brief: dict[str, Any],
        instructions: str,
        hard_rules: dict[str, Any],
    ) -> dict[str, Any]: ...


def _read_yaml(name: str) -> dict[str, Any]:
    path = LIBRARY_DIR / name
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"content library file {name} must contain a mapping")
    return data


def load_policy() -> dict[str, Any]:
    """Load the versioned policy rather than embedding mutable editorial rules."""
    policy = _read_yaml("policy.yaml")
    if not isinstance(policy.get("version"), str) or not policy["version"]:
        raise ValueError("content policy requires a non-empty version")
    if not isinstance(policy.get("brand_name"), str) or not policy["brand_name"]:
        raise ValueError("content policy requires a non-empty brand_name")
    for field in ("required_tags", "hard_sell_terms", "scene_markers", "discovery_markers"):
        value = policy.get(field)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
            raise ValueError(f"content policy {field} must be a non-empty list of strings")
    return policy


def load_examples() -> list[dict[str, Any]]:
    examples = _read_yaml("examples.yaml").get("examples")
    if not isinstance(examples, list):
        raise ValueError("content examples must be a list")
    required = {
        "id", "type", "audience_tags", "function_tags", "style_tags", "title", "body", "tags", "rationale"
    }
    text_fields = ("id", "title", "body", "rationale")
    tag_fields = ("audience_tags", "function_tags", "style_tags", "tags")
    ids: set[str] = set()
    for example in examples:
        if not isinstance(example, dict) or not required <= example.keys():
            raise ValueError("every content example must include the required fields")
        for field in text_fields:
            if not isinstance(example[field], str) or not example[field]:
                raise ValueError(f"content example {field} must be a non-empty string")
        for field in tag_fields:
            if not isinstance(example[field], list) or not all(
                isinstance(item, str) and item for item in example[field]
            ):
                raise ValueError(f"content example {field} must be a list of non-empty strings")
        if example["type"] not in {"positive", "negative"}:
            raise ValueError("example type must be positive or negative")
        if example["id"] in ids:
            raise ValueError(f"content examples contain duplicate id: {example['id']}")
        ids.add(example["id"])
    return examples


def _tokens(value: Any) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", str(value).casefold()) if token}


def _relevance(example: dict[str, Any], brief: dict[str, Any]) -> int:
    fields = (
        ("audience_tags", brief.get("audience", "")),
        ("function_tags", brief.get("product_function", "")),
        ("style_tags", brief.get("style_preference", "")),
    )
    score = 0
    for field, brief_value in fields:
        brief_tokens = _tokens(brief_value)
        for tag in example[field]:
            tag_tokens = _tokens(tag)
            if tag_tokens and (tag_tokens <= brief_tokens or tag_tokens & brief_tokens):
                score += 2 if tag_tokens <= brief_tokens else 1
    return score


def select_examples(brief: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return deterministic, relevance-sorted few-shot examples within policy limits."""
    examples = load_examples()

    def ordered(kind: str, limit: int) -> list[dict[str, Any]]:
        matches = [item for item in examples if item["type"] == kind]
        return sorted(matches, key=lambda item: (-_relevance(item, brief), item["id"]))[:limit]

    return {"positive": ordered("positive", 3), "negative": ordered("negative", 2)}


def selected_example_ids(examples: dict[str, list[dict[str, Any]]]) -> list[str]:
    return [item["id"] for kind in ("positive", "negative") for item in examples[kind]]


def _candidate_for_angle(brief: dict[str, Any], angle: str) -> dict[str, Any]:
    pain = str(brief.get("pain_point") or "my essay was stuck")
    function = str(brief.get("product_function") or "feedback")
    scenes = {
        ANGLES[0]: (
            "晚上11点在书桌前，我又翻开同一段雅思作文。 "
            f"我卡住了，因为 {pain}. 后来，{content_rules.BRAND_FULL} 帮我看见例子没有托住观点。"
        ),
        ANGLES[1]: (
            "睡前坐在书桌前，我以前总在换词。 "
            f"现在我会用 {function} 检查例子有没有证明观点。后来，{content_rules.BRAND_FULL} 让我看清了这个前后差别。"
        ),
        ANGLES[2]: (
            "下课后的地铁上，我以为这段话只差语法。 "
            f"后来我才发现主旨本身很模糊，{content_rules.BRAND_FULL} 帮我圈出了要改的那一句。"
        ),
    }
    titles = {
        ANGLES[0]: "Essay stayed stuck",
        ANGLES[1]: "Before / after essay",
        ANGLES[2]: "Feedback clicked",
    }
    return {
        "title": titles[angle],
        "body": scenes[angle],
        "tags": ["#cathovenielts", "#ieltswriting"],
        "first_comment": "Which sentence would you check first?",
    }


class MockPipelineProvider:
    name = "mock"
    model = "deterministic-v1"

    def generate_candidate(self, brief, angle, examples):
        return _candidate_for_angle(brief, angle)

    def repair_candidate(self, draft, brief, angle, issues):
        repaired = dict(draft)
        body = str(repaired.get("body") or "")
        body = re.sub(r"(?i)buy now|guaranteed score(?: improvement)?|must-have|best ever", "", body)
        if not re.search(r"\b(later|then i realized|i discovered)\b|后来|才发现", body, re.I):
            body = f"{body.rstrip()} Later, I found one concrete sentence to revise."
        if not re.search(r"at my desk|11pm|on the subway|before bed|咖啡店|书桌|晚上|睡前", body, re.I):
            body = f"At my desk before bed, {body.lstrip()}"
        repaired["body"] = body.strip()
        if content_rules.BRAND_FULL not in body:
            body = body.replace("Cathoven", "")
            body = f"{body.rstrip()} 后来，{content_rules.BRAND_FULL} 帮我看清一处问题。"
        repaired["body"] = body.strip()
        repaired["tags"] = list(
            dict.fromkeys([*(repaired.get("tags") or []), *content_rules.REQUIRED_TAGS])
        )
        return repaired

    def revise_draft(self, draft, brief, instructions, hard_rules):
        """Rewrite the narrative by intent without quoting or appending the instruction."""
        original = str(draft.get("body") or "").strip()
        body = _mock_revision_body(instructions)
        if "short" in instructions.casefold() or "缩短" in instructions or "精简" in instructions:
            body = body[: min(len(original) - 1, 120)].rstrip(" 。.")
            if content_rules.BRAND_FULL not in body:
                body = _mock_revision_body("short")
        return {
            "title": str(draft.get("title") or "Draft"),
            "body": body[:400].rstrip(),
            "tags": list(draft.get("tags") or []),
            "first_comment": draft.get("first_comment") or "What would you revise first?",
        }


def _mock_revision_body(instructions: str) -> str:
    """Map revision intent to an actual post rewrite, not a hidden instruction note."""
    lower = instructions.casefold()
    prefix = (
        f"晚上在书桌前，我又读了一遍那段作文。后来，{content_rules.BRAND_FULL} "
        "让我发现例子没有回应观点。"
    )
    if any(
        phrase in lower
        for phrase in ("product feel", "less product", "hard sell", "advertising", "weaken product")
    ) or any(
        token in instructions for token in ("弱化", "产品感", "广告感")
    ):
        return f"{prefix} I kept the tool in the background and rewrote the example myself."
    if any(token in lower for token in ("record", "ending", "authentic")) or any(
        token in instructions for token in ("记录", "结尾", "真实")
    ):
        return f"{prefix} I wrote that one mistake into tonight's study record before closing the notebook."
    if any(token in lower for token in ("conversation", "conversational", "casual")) or any(
        token in instructions for token in ("口语", "聊天", "自然")
    ):
        return f"{prefix} Honestly, I only fixed that one line tonight."
    if any(token in lower for token in ("short", "shorten", "concise")) or any(
        token in instructions for token in ("缩短", "精简")
    ):
        return f"晚上书桌前，我看作文。后来，{content_rules.BRAND_FULL} 让我发现例子没回应观点。I fixed one line."
    return f"{prefix} I paused, rewrote one line, and left the rest for tomorrow."


class OpenAICompatiblePipelineProvider:
    name = "openai-compatible"

    @property
    def model(self) -> str:
        return get_settings().openai_compatible_model

    def _complete(self, instruction: str, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        if not settings.openai_compatible_api_key:
            raise RuntimeError("OPENAI_COMPATIBLE_API_KEY is not configured")
        from openai import OpenAI

        response = OpenAI(
            api_key=settings.openai_compatible_api_key,
            base_url=settings.openai_compatible_base_url,
        ).chat.completions.create(
            model=settings.openai_compatible_model,
            temperature=0.4,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        try:
            data = json.loads(response.choices[0].message.content or "")
        except (AttributeError, IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError("provider returned invalid JSON") from exc
        return _strict_draft(data)

    def generate_candidate(self, brief, angle, examples):
        return self._complete(
            "Return only a JSON object with title, body, tags, and first_comment. Do not make sales promises.",
            {"brief": brief, "angle": angle, "examples": examples},
        )

    def repair_candidate(self, draft, brief, angle, issues):
        return self._complete(
            "Return only a repaired JSON draft. Resolve every listed hard-rule issue without sales language.",
            {"draft": draft, "brief": brief, "angle": angle, "issues": issues},
        )

    def revise_draft(self, draft, brief, instructions, hard_rules):
        return self._complete(
            "Return only a complete rewritten JSON draft, not a revision note or commentary.",
            {"original_draft": draft, "brief": brief, "instructions": instructions, "hard_rules": hard_rules},
        )


def _strict_draft(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) - {"title", "body", "tags", "first_comment"}:
        raise RuntimeError("provider draft must be an object with only draft fields")
    if not isinstance(data.get("title"), str) or not isinstance(data.get("body"), str):
        raise RuntimeError("provider draft requires string title and body")
    if not isinstance(data.get("tags"), list) or not all(isinstance(tag, str) for tag in data["tags"]):
        raise RuntimeError("provider draft requires a string tag list")
    if not isinstance(data.get("first_comment"), str):
        raise RuntimeError("provider draft requires a string first_comment")
    return {key: data[key] for key in ("title", "body", "tags", "first_comment")}


def _draft_fields(draft: dict[str, Any]) -> dict[str, Any]:
    return {key: draft.get(key, "" if key != "tags" else []) for key in ("title", "body", "tags", "first_comment")}


def get_pipeline_provider() -> PipelineProvider:
    configured = get_settings().llm_provider.casefold()
    if configured in {"openai", "openai-compatible"}:
        return OpenAICompatiblePipelineProvider()
    if configured == "mock":
        return MockPipelineProvider()
    raise RuntimeError(f"unsupported LLM provider: {configured}")


def hard_rule_check(draft: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    title = str(draft.get("title") or "")
    body = str(draft.get("body") or "")
    tags = draft.get("tags") or []
    text = f"{title}\n{body}".casefold()
    issues: list[str] = []
    if not (1 <= len(title) <= 20):
        issues.append("title must be 1-20 characters")
    if not (20 <= len(body) <= 400):
        issues.append("body must be 20-400 characters")
    if not isinstance(tags, list) or any(tag not in tags for tag in policy["required_tags"]):
        issues.append("required tags are missing")
    if not re.search(r"\b(i|my)\b|我", body, re.I):
        issues.append("body requires a first-person voice")
    if not any(marker.casefold() in text for marker in policy["discovery_markers"]):
        issues.append("body requires a discovery transition")
    if not any(marker.casefold() in text for marker in policy["scene_markers"]):
        issues.append("body requires a concrete scene")
    if policy["brand_name"].casefold() not in text:
        issues.append("body requires the brand name")
    for term in policy["hard_sell_terms"]:
        if term.casefold() in text:
            issues.append(f"forbidden hard-sell language: {term}")
    legacy_quality = content_rules.xhs_quality_check(draft)
    legacy_humanize = content_rules.humanize_check(draft)
    issues.extend(f"existing quality rule: {issue}" for issue in legacy_quality["issues"])
    issues.extend(f"existing humanize rule: {issue}" for issue in legacy_humanize["issues"])
    return {
        "passed": not issues,
        "issues": issues,
        "existing_quality": legacy_quality,
        "existing_humanize": legacy_humanize,
    }


def soft_score(draft: dict[str, Any], hard_report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Five deterministic 0-20 dimensions; no provider judgment is needed for tests/mock."""
    body = str(draft.get("body") or "")
    lower = body.casefold()
    words = re.findall(r"\b\w+\b", lower)
    specificity = min(20, 8 + 4 * sum(marker.casefold() in lower for marker in load_policy()["scene_markers"]) + min(4, len(words) // 12))
    emotional = min(20, 8 + 3 * sum(word in lower for word in ("felt", "stuck", "relieved", "worried", "开心", "焦虑")))
    coherence = min(20, 8 + 4 * sum(word in lower for word in ("before", "after", "later", "then", "后来", "才发现")))
    integration = min(20, 6 + (8 if "cathoven" in lower else 0) + (4 if "later" in lower or "后来" in lower else 0))
    usefulness = min(20, 8 + 4 * sum(word in lower for word in ("check", "revise", "sentence", "example", "改", "检查")))
    dimensions = {
        "specificity": specificity,
        "emotional_value": emotional,
        "narrative_coherence": coherence,
        "natural_product_integration": integration,
        "usefulness_conversational_tone": usefulness,
    }
    return {"dimensions": dimensions, "total": sum(dimensions.values()), "hard_passed": bool((hard_report or hard_rule_check(draft))["passed"])}


def _evaluate_candidate(draft: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    hard_report = hard_rule_check(draft, policy)
    score_report = soft_score(draft, hard_report)
    return {**draft, "hard_report": hard_report, "score_report": score_report, "score": score_report["total"]}


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evaluated = []
    policy = load_policy()
    for candidate in candidates:
        item = candidate if "hard_report" in candidate and "score_report" in candidate else _evaluate_candidate(candidate, policy)
        evaluated.append({**item, "recommendable": item["hard_report"]["passed"], "recommended": False})
    ranked = sorted(evaluated, key=lambda item: (not item["recommendable"], -item["score"], item["candidate"]))
    if ranked and ranked[0]["recommendable"]:
        ranked[0]["recommended"] = True
    return ranked


def generate_candidate_round(
    brief: dict[str, Any], provider: PipelineProvider | None = None
) -> dict[str, Any]:
    policy = load_policy()
    selected = select_examples(brief)
    provider = provider or get_pipeline_provider()
    candidates = []
    for number, angle in enumerate(ANGLES, start=1):
        draft = provider.generate_candidate(brief, angle, selected)
        draft = _strict_draft(draft)
        draft.update({"candidate": number, "angle": angle, "source": provider.name, "repair_attempts": 0})
        evaluated = _evaluate_candidate(draft, policy)
        if not evaluated["hard_report"]["passed"]:
            repaired = provider.repair_candidate(
                _draft_fields(draft), brief, angle, evaluated["hard_report"]["issues"]
            )
            repaired = _strict_draft(repaired)
            repaired.update({"candidate": number, "angle": angle, "source": provider.name, "repair_attempts": 1})
            evaluated = _evaluate_candidate(repaired, policy)
        candidates.append(evaluated)
    ranked = rank_candidates(candidates)
    recommended = next((item["candidate"] for item in ranked if item["recommended"]), None)
    return {
        "policy_version": policy["version"],
        "selected_example_ids": selected_example_ids(selected),
        "selected_examples": selected,
        "provider": provider.name,
        "model": provider.model,
        "candidates": sorted(ranked, key=lambda item: item["candidate"]),
        "ranking": [item["candidate"] for item in ranked],
        "recommended_candidate": recommended,
    }


def persist_candidate_round(
    session: Session,
    run_id: int,
    result: dict[str, Any],
    *,
    round_number: int = 1,
    commit: bool = True,
) -> list[Draft]:
    """Persist all three candidates and an auditable selection decision."""
    drafts = []
    for candidate in result["candidates"]:
        drafts.append(
            repo.add_draft(
                session,
                run_id,
                title=candidate["title"], body=candidate["body"], tags=candidate["tags"],
                first_comment=candidate["first_comment"],
                narrative_plan={"angle": candidate["angle"]},
                quality_report={"hard": candidate["hard_report"], "soft": candidate["score_report"]},
                round=round_number, candidate=candidate["candidate"], angle=candidate["angle"],
                source=candidate["source"], score=candidate["score"], selected=candidate["recommended"],
                commit=commit,
            )
        )
    repo.record_step(
        session,
        run_id,
        "candidate_round",
        {"round": round_number},
        result,
        commit=commit,
    )
    repo.update_run(
        session,
        run_id,
        provider=result["provider"],
        model=result["model"],
        commit=commit,
    )
    return drafts


def create_revision(
    session: Session,
    parent: Draft,
    brief: dict[str, Any],
    instructions: str,
    *,
    provider: PipelineProvider | None = None,
    commit: bool = True,
    record_step: bool = True,
) -> Draft:
    if parent.id is None:
        raise ValueError("parent draft must be persisted")
    provider = provider or get_pipeline_provider()
    policy = load_policy()
    original = {"title": parent.title, "body": parent.body, "tags": parent.tags, "first_comment": parent.first_comment or ""}
    revised = _strict_draft(provider.revise_draft(original, brief, instructions, policy))
    evaluated = _evaluate_candidate(revised, policy)
    if not evaluated["hard_report"]["passed"]:
        raise ValueError("provider revision violates hard rules")
    child = repo.add_draft(
        session, parent.run_id, title=evaluated["title"], body=evaluated["body"], tags=evaluated["tags"],
        first_comment=evaluated["first_comment"], narrative_plan={"angle": parent.angle, "revision_instructions": instructions},
        quality_report={"hard": evaluated["hard_report"], "soft": evaluated["score_report"], "parent_draft_id": parent.id},
        round=parent.round + 1, candidate=parent.candidate, parent_draft_id=parent.id,
        angle=parent.angle, source=f"revision:{provider.name}", score=evaluated["score"], selected=True,
        commit=commit,
    )
    if record_step:
        repo.record_step(session, parent.run_id, "draft_revision", {"parent_draft_id": parent.id, "instructions": instructions}, {
            "child_draft_id": child.id, "policy_version": policy["version"], "provider": provider.name, "model": provider.model,
        }, commit=commit)
    return child
