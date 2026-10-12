import base64
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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


@pytest.mark.parametrize("task", image_rules.TASK_TO_STYLE)
@pytest.mark.parametrize("has_references", [True, False])
def test_every_prompt_describes_text_only_reference_metadata(task, has_references):
    brief = _brief()
    refs = [
        {"role": "cover_style", "label": "test-cover", "reason": "metadata"},
        {"role": "product_ui", "label": "test-ui", "reason": "metadata"},
    ]
    prompts = image_rules.rewrite_image_prompts(
        brief,
        content_rules.route_style(brief),
        {"title": "睡前20分钟改作文"},
        {"tasks": [task]},
        refs if has_references else [],
    )

    prompt = prompts[0]["prompt"]
    assert "Reference metadata (text only; image contents are not provided)" in prompt
    for phrase in (
        "Use the reference image",
        "Use the provided Cathoven screenshot",
        "Use the reference for collage structure",
    ):
        assert phrase not in prompt
    assert "Do not copy exact text" in prompt
    if task == "封面图":
        assert "thumbnail-readable" in prompt
    if task in {"产品 UI 图", "教程步骤图"}:
        assert "desktop web" in prompt
    if task == "产品 UI 图":
        assert "Create a desktop web layout with card hierarchy, purple UI accents, and report density." in prompt
    reason = prompts[0]["reference_reason"]
    if has_references:
        assert "cover_style" in reason
        assert "product_ui" in reason
        assert "仅使用元数据" in reason
    else:
        assert "仅来自 Brief 和风格规则" in reason


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
    assert all("仅使用元数据" in ref["reason"] for ref in refs)

    get_settings.cache_clear()


def test_cover_library_selection_describes_metadata(tmp_path, monkeypatch):
    style_dir = tmp_path / "备忘录聊天框风"
    style_dir.mkdir()
    (style_dir / "cover.png").write_bytes(b"fake")
    monkeypatch.setenv("CATHOVEN_COVER_REFERENCE_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        refs = image_rules.select_references(1, _brief(), {"tasks": ["封面图"]})
        assert refs[0]["source"] == "cover_library"
        assert "备忘录聊天框风" in refs[0]["reason"]
        assert "仅使用元数据" in refs[0]["reason"]
        assert "封面骨架" not in refs[0]["reason"]
    finally:
        get_settings.cache_clear()


def test_image_qc_describes_prompt_constraint_checks():
    qc = image_rules.image_qc([])
    assert any("prompt 约束检查" in check for check in qc["checks"])
    assert all("copy 结构" not in check for check in qc["checks"])


def test_image_generation_uses_text_only_reference_contract(tmp_path, monkeypatch):
    captured = {"generate_calls": [], "edit_called": False}

    class FakeImages:
        def generate(self, **kwargs):
            captured["generate_calls"].append(kwargs)
            return SimpleNamespace(
                data=[SimpleNamespace(b64_json=base64.b64encode(b"png-bytes").decode("ascii"))]
            )

        def edit(self, **kwargs):
            captured["edit_called"] = True
            raise AssertionError("image references must not be sent through images.edit")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.images = FakeImages()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("IMAGE_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_PROVIDER", "openai")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    get_settings.cache_clear()

    brief = _brief()
    route = content_rules.route_style(brief)
    draft = {"title": "睡前20分钟改作文", "body": "先看反馈", "tags": []}
    tasks = {"tasks": ["封面图"]}
    first_reference = tmp_path / "reference-a.png"
    second_reference = tmp_path / "reference-b.png"
    first_reference.write_bytes(b"first image bytes")
    second_reference.write_bytes(b"different image bytes")
    refs_a = [{
        "role": "cover_style",
        "path": str(first_reference),
        "label": "same-label",
        "reason": "same reason",
    }]
    refs_b = [{**refs_a[0], "path": str(second_reference)}]

    prompts_with_refs = image_rules.rewrite_image_prompts(brief, route, draft, tasks, refs_a)
    prompts_with_different_bytes = image_rules.rewrite_image_prompts(
        brief, route, draft, tasks, refs_b
    )
    assert first_reference.read_bytes() != second_reference.read_bytes()
    assert prompts_with_refs[0]["prompt"] == prompts_with_different_bytes[0]["prompt"]

    changed_role = [{**refs_a[0], "role": "product_ui"}]
    changed_reason = [{**refs_a[0], "reason": "changed reason"}]
    prompt_with_changed_role = image_rules.rewrite_image_prompts(
        brief, route, draft, tasks, changed_role
    )[0]["prompt"]
    prompt_with_changed_reason = image_rules.rewrite_image_prompts(
        brief, route, draft, tasks, changed_reason
    )[0]["prompt"]
    assert prompt_with_changed_role != prompts_with_refs[0]["prompt"]
    assert prompt_with_changed_reason != prompts_with_refs[0]["prompt"]

    prompts_without_refs = image_rules.rewrite_image_prompts(brief, route, draft, tasks, [])
    assets = image_rules.generate_image_assets(7, prompts_with_refs + prompts_without_refs)
    settings = get_settings()

    assert len(captured["generate_calls"]) == 2
    assert captured["edit_called"] is False
    assert [call.keys() for call in captured["generate_calls"]] == [
        {"model", "prompt", "response_format", "size"},
        {"model", "prompt", "response_format", "size"},
    ]
    assert captured["generate_calls"] == [
        {
            "model": settings.image_model,
            "prompt": prompts_with_refs[0]["prompt"],
            "response_format": "b64_json",
            "size": "1024x1536",
        },
        {
            "model": settings.image_model,
            "prompt": prompts_without_refs[0]["prompt"],
            "response_format": "b64_json",
            "size": "1024x1536",
        },
    ]
    assert [asset["status"] for asset in assets] == ["generated", "generated"]
    assert [Path(asset["file_path"]).read_bytes() for asset in assets] == [
        b"png-bytes",
        b"png-bytes",
    ]

    get_settings.cache_clear()
