import pytest

from app.config import get_settings
from app.services import content_rules, llm_provider


def test_openai_provider_without_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    get_settings.cache_clear()

    brief = content_rules.normalize_brief({
        "topic": "edit an IELTS essay",
        "audience": "IELTS student",
        "product_function": "Writing Checker",
        "pain_point": "I do not know what is wrong",
        "style_preference": "memoir",
    })
    route = content_rules.route_style(brief)
    plan = content_rules.build_narrative_plan(brief, route)

    with pytest.raises(RuntimeError, match="OPENAI_COMPATIBLE_API_KEY"):
        llm_provider.generate_draft(brief, plan)

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    get_settings.cache_clear()
