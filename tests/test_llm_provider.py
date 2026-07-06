from app.config import get_settings
from app.services import content_rules, llm_provider


def test_openai_provider_without_key_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    get_settings.cache_clear()

    brief = content_rules.normalize_brief({
        "topic": "睡前20分钟改作文",
        "audience": "雅思考生",
        "product_function": "Writing Checker",
        "pain_point": "不知道作文卡在哪",
        "style_preference": "备忘录聊天框风",
    })
    route = content_rules.route_style(brief)
    plan = content_rules.build_narrative_plan(brief, route)

    draft = llm_provider.generate_draft(brief, plan)

    assert draft["provider"] == "mock-fallback"
    assert "Cathoven猫多芬雅思" in draft["body"]

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    get_settings.cache_clear()
