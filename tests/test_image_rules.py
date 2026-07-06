import base64
import sys
from types import SimpleNamespace

from app.config import get_settings
from app.services import content_rules, image_rules


def _brief():
    return content_rules.normalize_brief({
        "topic": "睡前20分钟改作文",
        "audience": "雅思考生",
        "product_function": "Writing Checker",
        "pain_point": "作文改了很多遍，还是不知道卡在哪",
        "style_preference": "备忘录聊天框风",
    })


def test_image_router_does_not_default_to_single_desktop_scene():
    brief = _brief()
    route = content_rules.route_style(brief)
    tasks = image_rules.classify_image_tasks(brief, route)

    assert "封面图" in tasks["tasks"]
    assert "产品 UI 图" in tasks["tasks"]
    assert tasks["principle"].startswith("先分类图片任务")


def test_prompt_rewrite_keeps_reference_and_cathoven_constraints():
    brief = _brief()
    route = content_rules.route_style(brief)
    draft = {
        "title": "睡前20分钟改作文",
        "body": "晚上书桌前，后来才知道 Cathoven猫多芬雅思 能拆开看。",
        "tags": ["#猫多芬雅思", "#cathovenielts"],
    }
    tasks = {"tasks": ["封面图", "产品 UI 图"]}
    refs = [{"role": "cover_style", "path": "fake.png", "reason": "test"}]
    prompts = image_rules.rewrite_image_prompts(brief, route, draft, tasks, refs)

    assert "thumbnail-readable" in prompts[0]["prompt"]
    assert "Do not copy exact text" in prompts[0]["prompt"]
    assert "Desktop web interface only" in prompts[1]["prompt"]
    assert "All visible dates must be 2026" in prompts[1]["prompt"]


def test_user_reference_still_adds_product_ui_reference_when_needed(tmp_path, monkeypatch):
    product_dir = tmp_path / "product"
    screenshots = product_dir / "screenshots"
    screenshots.mkdir(parents=True)
    (screenshots / "ui.png").write_bytes(b"fake")
    monkeypatch.setenv("CATHOVEN_PRODUCT_REFERENCE_DIR", str(product_dir))
    get_settings.cache_clear()

    brief = _brief()
    brief["reference_path"] = str(tmp_path / "user-cover.png")
    refs = image_rules.select_references(
        1,
        brief,
        {"tasks": ["封面图", "产品 UI 图"]},
    )

    assert refs[0]["source"] == "user"
    assert any(ref["role"] == "product_ui" for ref in refs)

    get_settings.cache_clear()


def test_real_image_generation_requests_base64_response(tmp_path, monkeypatch):
    captured = {}

    class FakeImages:
        def generate(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                data=[SimpleNamespace(b64_json=base64.b64encode(b"png-bytes").decode("ascii"))]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.images = FakeImages()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("IMAGE_API_KEY", "test-key")
    get_settings.cache_clear()

    path = image_rules._try_generate_real_image("prompt", tmp_path, 1)

    assert path == tmp_path / "01-generated.png"
    assert path.read_bytes() == b"png-bytes"
    assert captured["response_format"] == "b64_json"

    get_settings.cache_clear()
