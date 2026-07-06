from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Any

from app.config import get_settings

TASK_TO_STYLE = {
    "封面图": "high-click Xiaohongshu cover",
    "产品 UI 图": "Cathoven desktop web UI copy",
    "教程步骤图": "one-step tutorial carousel image",
    "信息图/知识卡片": "educational infographic",
    "社媒截图/UGC/评论证据图": "social proof collage",
    "情绪/场景图": "photorealistic natural study scene",
}


def classify_image_tasks(brief: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    topic = brief["topic"]
    tasks = ["封面图"]
    if any(word in topic + brief["pain_point"] for word in ["怎么", "步骤", "教程"]):
        tasks.append("教程步骤图")
    elif any(word in brief["pain_point"] for word in ["不知道", "卡", "反馈", "作文"]):
        tasks.append("产品 UI 图")
    else:
        tasks.append("情绪/场景图")
    if route["style"] in {"拼贴风", "综艺花字风"}:
        tasks.append("社媒截图/UGC/评论证据图")
    return {
        "tasks": tasks[:3],
        "principle": "先分类图片任务，再选择参考图，不默认桌面实拍或产品屏幕",
    }


def select_references(
    run_id: int,
    brief: dict[str, Any],
    image_task: dict[str, Any],
) -> list[dict[str, Any]]:
    settings = get_settings()
    refs: list[dict[str, Any]] = []
    if brief.get("reference_path"):
        refs.append({
            "source": "user",
            "role": "cover_style",
            "path": str(brief["reference_path"]),
            "reason": "用户提供参考图，优先决定封面构图、标题承载和情绪。",
        })
    else:
        cover_dir = settings.cathoven_cover_reference_dir
        style = str(brief.get("style_preference") or "备忘录聊天框风")
        style_dir = cover_dir / style
        chosen = _first_asset(style_dir) or _first_asset(cover_dir)
        if chosen:
            refs.append({
                "source": "cover_library",
                "role": "cover_style",
                "path": str(chosen),
                "reason": f"无用户参考图，按风格「{style}」从不同风格封面库选择封面骨架。",
            })

    if _needs_product_reference(image_task):
        product_dir = settings.cathoven_product_reference_dir
        product_ref = _first_asset(product_dir / "screenshots") or _first_asset(product_dir)
        if product_ref:
            refs.append({
                "source": "product_library",
                "role": "product_ui",
                "path": str(product_ref),
                "reason": "当前图片需要产品可信度，补充 Cathoven 真实 UI 素材用于界面结构。",
            })
    return refs


def _needs_product_reference(image_task: dict[str, Any]) -> bool:
    return any(task in image_task["tasks"] for task in ["产品 UI 图", "教程步骤图"])


def rewrite_image_prompts(
    brief: dict[str, Any],
    route: dict[str, Any],
    draft: dict[str, Any],
    image_task: dict[str, Any],
    references: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prompts = []
    for task in image_task["tasks"]:
        prompts.append({
            "kind": task,
            "title": _asset_title(task, draft),
            "reference_reason": _reference_reason(task, references),
            "prompt": _prompt_for(task, brief, route, draft, references),
        })
    return prompts


def generate_image_assets(run_id: int, prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    settings = get_settings()
    out_dir = settings.export_dir / str(run_id) / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = []
    for index, prompt in enumerate(prompts, start=1):
        path = out_dir / f"{index:02d}-{_safe_name(prompt['kind'])}.svg"
        status = "fallback"
        try:
            generated = _try_generate_real_image(prompt["prompt"], out_dir, index)
        except Exception:
            generated = None
        if generated:
            path = generated
            status = "generated"
        else:
            _write_svg_fallback(path, prompt["title"], prompt["kind"])
        assets.append({
            **prompt,
            "status": status,
            "file_path": str(path),
        })
    return assets


def image_qc(assets: list[dict[str, Any]]) -> dict[str, Any]:
    issues = []
    for asset in assets:
        prompt = asset["prompt"]
        if "desktop web" not in prompt and asset["kind"] in {"产品 UI 图", "教程步骤图"}:
            issues.append(f"{asset['kind']} 缺少 desktop web 约束")
        if "Do not copy exact text" not in prompt:
            issues.append(f"{asset['kind']} 缺少不复制参考图文本的约束")
        if asset["kind"] == "封面图" and "thumbnail-readable" not in prompt:
            issues.append("封面图缺少缩略图可读要求")
    return {
        "passed": not issues,
        "issues": issues,
        "checks": [
            "先匹配图片任务",
            "封面优先点击理由",
            "参考图只 copy 结构不 copy 内容",
            "Cathoven UI 仅在需要产品时出现",
            "失败时保留 prompt 与 fallback 预览",
        ],
    }


def _first_asset(path: Path) -> Path | None:
    if not path.exists():
        return None
    if path.is_file():
        return path
    for child in path.rglob("*"):
        if child.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            return child
    return None


def _asset_title(task: str, draft: dict[str, Any]) -> str:
    if task == "封面图":
        return draft["title"]
    if task == "产品 UI 图":
        return "四维度反馈截图"
    if task == "教程步骤图":
        return "先看反馈再改一段"
    if task == "社媒截图/UGC/评论证据图":
        return "大家都卡在看不见盲区"
    return "晚上书桌前的改作文瞬间"


def _reference_reason(task: str, references: list[dict[str, Any]]) -> str:
    roles = ", ".join(ref["role"] for ref in references) or "fallback style guide"
    return f"{task} 使用参考角色：{roles}。参考图只用于构图、信息密度、情绪和 UI 骨架。"


def _prompt_for(
    task: str,
    brief: dict[str, Any],
    route: dict[str, Any],
    draft: dict[str, Any],
    references: list[dict[str, Any]],
) -> str:
    ref_text = "\n".join(
        f"- {ref['role']}: {ref['path']} ({ref['reason']})" for ref in references
    ) or "- No file reference available; follow the encoded Cathoven XHS workflow."
    if task == "封面图":
        return f"""Use case: ads-marketing
Asset type: Xiaohongshu cover image

Primary request:
Create a high-click-through cover for a Xiaohongshu post about {brief['topic']}.

Reference image(s):
{ref_text}
Use the reference image for title layout, composition, color, emotion, and feed stopping power only.
Do not copy exact text, logos, usernames, faces, watermarks, or irrelevant brands.

Visual concept:
{route['style']} cover showing the feeling of {brief['pain_point']}.

Composition:
Large thumbnail-readable focal point.
Clear space for this exact short title: "{draft['title']}".
Main subject must remain recognizable in a small mobile feed.

Text:
Use only this exact short title: "{draft['title']}".
No extra readable long text.

Avoid:
long text, copied reference text, unrelated logos, fake usernames, old dates, watermark, messy tiny UI."""
    if task == "产品 UI 图":
        return f"""Use case: ui-mockup
Asset type: Cathoven UI copy for Xiaohongshu carousel

Primary request:
Create a Cathoven-style desktop web UI image about {brief['product_function']}.

Reference image(s):
{ref_text}
Use the provided Cathoven screenshot as structural reference: layout, card hierarchy, purple UI accents, and report density.
Do not copy exact text or small UI copy; recreate a plausible new UI state.

Screen:
Desktop web interface only.
Show an IELTS writing report with Task Response, Coherence, Vocabulary, Grammar, and one feedback card.
All visible dates must be 2026.

Text:
Only include short labels: "Task Response", "Coherence", "Vocabulary", "Grammar", "Example too thin".

Avoid:
mobile app UI, tablet UI, unrelated logos, old dates, unreadable dense fake text, copied exact screenshot text, generic chatbot icons."""
    if task == "教程步骤图":
        return f"""Use case: productivity-visual
Asset type: Xiaohongshu tutorial step image

Primary request:
Create one tutorial step image showing "paste essay -> read one feedback -> revise one paragraph".

Reference image(s):
{ref_text}
Do not copy exact text, screenshot copy, usernames, dates, or unrelated brand marks.

Layout:
One clear step, large focal area, optional step number, one short annotation.
Cathoven desktop web interface only, with browser chrome visible if helpful.

Text:
Only include: "只改一个点".

Avoid:
too many labels, full workflow crammed into one image, mobile UI, old dates, watermark."""
    if task == "社媒截图/UGC/评论证据图":
        return f"""Use case: ads-marketing
Asset type: social proof collage

Primary request:
Create a Xiaohongshu-style social proof image about {brief['pain_point']}.

Reference image(s):
{ref_text}
Use the reference for collage structure, comment-card rhythm, and social screenshot feel.
Do not copy exact text, real usernames, avatars, comments, platform logos, or timestamps.

Text:
Use paraphrased short snippets only: "我也是卡在TR", "不是语法的问题", "原来例子撑不住".

Avoid:
real names, real avatars, copied comments, platform logos, legal claims, watermark."""
    return f"""Use case: photorealistic-natural
Asset type: Xiaohongshu lifestyle/supporting image

Primary request:
Create a realistic image about {brief['topic']}.

Reference image(s):
{ref_text}
Do not copy exact text, logos, usernames, dates, watermarks, or unrelated brands.

Scene:
{brief['pain_point']} in a lived-in study scene: warm desk lamp, essay paper, one cup, imperfect notes.

Cathoven:
Cathoven is optional or absent. If visible, it appears only as a small desktop web screen.

Style:
Candid, lived-in, natural; not a staged product ad.

Avoid:
forced product placement, fake book brands, unrelated logos, old dates, perfect showroom desk."""


def _try_generate_real_image(prompt: str, out_dir: Path, index: int) -> Path | None:
    settings = get_settings()
    if not settings.image_api_key:
        return None
    from openai import OpenAI

    client = OpenAI(api_key=settings.image_api_key, base_url=settings.image_base_url)
    response = client.images.generate(
        model=settings.image_model,
        prompt=prompt,
        response_format="b64_json",
        size="1024x1536",
    )
    item = response.data[0]
    if not getattr(item, "b64_json", None):
        return None
    path = out_dir / f"{index:02d}-generated.png"
    path.write_bytes(base64.b64decode(item.b64_json))
    return path


def _write_svg_fallback(path: Path, title: str, kind: str) -> None:
    palette = {
        "封面图": ("#f6f1e8", "#21312f", "#e9614f"),
        "产品 UI 图": ("#f7f8fb", "#322461", "#0f9b8e"),
        "教程步骤图": ("#f4f6e8", "#263238", "#f0a202"),
        "社媒截图/UGC/评论证据图": ("#fff7ee", "#252525", "#4e8f8a"),
    }.get(kind, ("#f2efe8", "#20323c", "#d84a35"))
    bg, ink, accent = palette
    text = html.escape(title)
    kind_text = html.escape(kind)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">
  <rect width="1080" height="1440" fill="{bg}"/>
  <rect x="78" y="90" width="924" height="1260" rx="42" fill="white" stroke="{ink}" stroke-width="4"/>
  <circle cx="890" cy="210" r="74" fill="{accent}" opacity=".88"/>
  <rect x="140" y="275" width="800" height="26" rx="13" fill="{accent}" opacity=".35"/>
  <text x="140" y="430" fill="{ink}" font-size="92" font-family="Georgia, 'Noto Serif SC', serif" font-weight="700">{text}</text>
  <text x="140" y="545" fill="{ink}" font-size="44" font-family="Arial, sans-serif">{kind_text}</text>
  <rect x="140" y="650" width="800" height="390" rx="28" fill="{bg}" stroke="{accent}" stroke-width="3"/>
  <text x="185" y="770" fill="{ink}" font-size="46" font-family="Arial, sans-serif">prompt fallback</text>
  <text x="185" y="855" fill="{ink}" font-size="34" font-family="Arial, sans-serif">image provider not configured</text>
  <text x="140" y="1210" fill="{accent}" font-size="42" font-family="Arial, sans-serif" font-weight="700">Cathoven XHS Workflow</text>
</svg>"""
    path.write_text(svg, encoding="utf-8")


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value).strip("-") or "asset"
