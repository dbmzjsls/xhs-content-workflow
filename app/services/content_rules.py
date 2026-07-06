from __future__ import annotations

import re
from typing import Any

BRAND_FULL = "Cathoven猫多芬雅思"
REQUIRED_TAGS = ["#猫多芬雅思", "#cathovenielts"]
DISCOVERY_SENTENCE = f"后来才知道 {BRAND_FULL} 可以帮我把问题拆开看。"
MAX_BODY_CHARS = 400
BODY_STRIP_CHARS = "，。；\n "

NARRATIVE_ARC = ["焦虑/困惑", "挣扎/尝试", "发现", "理解/顿悟", "释然/希望"]

STYLE_ROUTES: dict[str, dict[str, str]] = {
    "拼贴风": {"structure": "A 痛点前置型", "emotion": "日常反思"},
    "杂志风": {"structure": "B 盘点清单型", "emotion": "专业洞察"},
    "大字报纯文字风": {"structure": "A 痛点前置型", "emotion": "直接冲击"},
    "真人出镜高颜值摄影风": {"structure": "C AIDA 型", "emotion": "生活共鸣"},
    "插画手绘风": {"structure": "A 痛点前置型", "emotion": "温暖治愈"},
    "综艺花字风": {"structure": "D 逆袭对比型", "emotion": "夸张自嘲"},
    "备忘录聊天框风": {"structure": "A 痛点前置型", "emotion": "私密真实"},
    "前后对比风": {"structure": "D 逆袭对比型", "emotion": "效果证明"},
}

BANNED_FORMAL_WORDS = ["此外", "总而言之", "值得一提的是", "首先", "其次", "最后"]
BANNED_HARD_SELL = ["超级好用", "绝绝子神器", "强烈推荐", "必备神器", "立刻提分", "保分"]


def normalize_brief(raw: dict[str, Any]) -> dict[str, Any]:
    topic = str(raw.get("topic") or "睡前 20 分钟改作文").strip()
    audience = str(raw.get("audience") or "雅思自学考生").strip()
    product_function = str(raw.get("product_function") or "Writing Checker").strip()
    pain_point = str(raw.get("pain_point") or "不知道作文卡在哪").strip()
    style_preference = str(raw.get("style_preference") or "备忘录聊天框风").strip()
    reference_path = (raw.get("reference_path") or None)
    return {
        "topic": topic,
        "audience": audience,
        "product_function": product_function,
        "pain_point": pain_point,
        "style_preference": style_preference,
        "reference_path": reference_path,
        "emotional_value": _emotional_value(product_function, pain_point),
        "product_role": "帮助我发现盲区的配角，不是被硬推荐的主角",
    }


def route_style(brief: dict[str, Any]) -> dict[str, Any]:
    preferred = brief.get("style_preference") or ""
    if preferred in STYLE_ROUTES:
        style = preferred
    elif "资料" in brief["pain_point"]:
        style = "备忘录聊天框风"
    elif "对比" in brief["topic"] or "以前" in brief["topic"]:
        style = "前后对比风"
    else:
        style = "备忘录聊天框风"
    base = STYLE_ROUTES[style]
    return {
        "style": style,
        "structure": base["structure"],
        "core_emotion": base["emotion"],
        "copy_angle": "先写自己的状态和发现，再让产品自然出现",
        "image_mix": ["封面图", "产品 UI 图", "情绪/场景图"],
    }


def build_narrative_plan(brief: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    scene = _scene_for(brief)
    return {
        "arc": NARRATIVE_ARC,
        "scene": scene,
        "beats": [
            f"在{scene}里被「{brief['pain_point']}」卡住",
            "试过资料、模板或自己反复改，但还是不踏实",
            f"后来才发现 {BRAND_FULL} 可以把问题拆开看",
            f"重点不是炫功能，而是终于知道「{brief['emotional_value']}」",
            "结尾停在一个小行动或轻问题，不做强行总结",
        ],
        "golden_sentence": "不是写得不好，是看不见自己的盲区。",
        "structure": route["structure"],
    }


def generate_mock_draft(brief: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    topic = brief["topic"]
    title = _short_title(topic)
    body = (
        f"{plan['scene']}的时候，我又把那篇雅思作文翻出来了。\n\n"
        f"说出来有点丢人，明明已经改了好几遍，还是感觉哪里不对，"
        f"但又说不出到底是语法、逻辑，还是题目没答到。\n\n"
        f"后来才知道 {BRAND_FULL} 可以把作文按几个维度拆开看。"
        f"结果最扎心的不是语法，而是它提醒我：那段我写得最用力的例子，其实没撑住观点。\n\n"
        "我当时真的愣了一下。\n\n"
        f"{plan['golden_sentence']}\n\n"
        "今天先不继续存新资料了，先把这一段改清楚。"
    )
    tags = [
        "#雅思写作",
        "#雅思备考",
        "#英语学习",
        "#AI批改",
        "#学习日常",
        *REQUIRED_TAGS,
    ]
    return {
        "title": title,
        "body": body,
        "tags": tags,
        "first_comment": "我现在会先看题有没有答全，再去管高级词。",
    }


def humanize_check(draft: dict[str, Any]) -> dict[str, Any]:
    text = f"{draft.get('title', '')}\n{draft.get('body', '')}"
    issues = []
    for word in BANNED_FORMAL_WORDS:
        if word in text:
            issues.append(f"书面词过重：{word}")
    for word in BANNED_HARD_SELL:
        if word in text:
            issues.append(f"硬广/夸张表达：{word}")
    if "我" not in draft.get("body", ""):
        issues.append("正文缺少第一人称叙事")
    if "后来" not in draft.get("body", ""):
        issues.append("缺少发现式转折")
    return {
        "passed": not issues,
        "issues": issues,
        "checks": [
            "像在跟朋友说话",
            "有具体场景",
            "产品作为故事配角",
            "不是论文结构",
        ],
    }


def xhs_quality_check(draft: dict[str, Any]) -> dict[str, Any]:
    body = draft.get("body", "")
    tags = draft.get("tags", [])
    issues = []
    if len(draft.get("title", "")) > 20:
        issues.append("标题超过 20 字")
    if not (20 <= len(body) <= 400):
        issues.append("正文需控制在 20-400 字")
    if not _first_brand_mention_is_full(body):
        issues.append(f"正文首次产品名必须写 {BRAND_FULL}")
    if body.count(BRAND_FULL) > 1:
        issues.append("完整品牌名不应重复出现")
    for tag in REQUIRED_TAGS:
        if tag not in tags:
            issues.append(f"缺少标签 {tag}")
    if not re.search(r"(后来|结果|慢慢发现|意外的是)", body):
        issues.append("产品出现方式不像“发现”，需要加自然转折")
    if not re.search(r"(凌晨|睡前|地铁|咖啡|书桌|晚上|通勤|考前)", body):
        issues.append("缺少具体时间/地点/状态")
    if any(word in body for word in ["推荐你", "大家一定要", "必须用"]):
        issues.append("语气像推荐，不像分享经历")
    return {
        "passed": not issues,
        "issues": issues,
        "metrics": {
            "title_chars": len(draft.get("title", "")),
            "body_chars": len(body),
            "tag_count": len(tags),
            "brand_mentions": body.count(BRAND_FULL),
        },
    }


def revise_draft(draft: dict[str, Any], quality: dict[str, Any], humanize: dict[str, Any]) -> dict[str, Any]:
    revised = {**draft}
    revised["title"] = _short_title(revised.get("title") or "睡前改作文")
    body = revised.get("body", "")
    body = _normalize_brand_mentions(body)
    body = body.replace("我推荐你", "后来我才知道")
    body = body.replace("大家一定要", "我现在会")
    body = body.replace("此外", "还有")
    if BRAND_FULL not in body:
        body = body.rstrip() + f"\n\n{DISCOVERY_SENTENCE}"
    if not re.search(r"(后来|结果|慢慢发现|意外的是)", body):
        body = body.replace(BRAND_FULL, f"后来才知道 {BRAND_FULL}", 1)
    body = _dedupe_full_brand(body)
    body = _fit_body(body)
    if len(body) < 20:
        body = "睡前改作文的时候，我才发现自己不是不会写，是一直看不见问题。"
    tags = list(dict.fromkeys([*(revised.get("tags") or []), *REQUIRED_TAGS]))
    revised["body"] = body
    revised["tags"] = tags[:12]
    revised["quality_report"] = {
        "pre_revision": {
            "quality": quality,
            "humanize": humanize,
        },
        "post_revision": xhs_quality_check(revised),
    }
    return revised


def _emotional_value(product_function: str, pain_point: str) -> str:
    if "Writing" in product_function or "作文" in product_function:
        return "终于知道卡分点在哪"
    if "Speaking" in product_function or "口语" in product_function:
        return "开口练习没那么尴尬"
    if "CEFR" in product_function:
        return "知道自己的真实水平"
    return f"把「{pain_point}」变得可拆解"


def _scene_for(brief: dict[str, Any]) -> str:
    text = f"{brief.get('topic', '')}{brief.get('pain_point', '')}"
    if "睡前" in text:
        return "睡前台灯旁"
    if "通勤" in text or "地铁" in text:
        return "地铁上"
    if "咖啡" in text:
        return "咖啡店靠窗"
    if "资料" in text:
        return "晚上整理电脑文件夹"
    return "晚上书桌前"


def _short_title(title: str) -> str:
    title = re.sub(r"\s+", "", title)
    if len(title) <= 20:
        return title
    return title[:20]


def _first_brand_mention_is_full(body: str) -> bool:
    match = re.search(r"(?i)cathoven|猫多芬", body)
    if match is None:
        return False
    return body[match.start() : match.start() + len(BRAND_FULL)] == BRAND_FULL


def _normalize_brand_mentions(body: str) -> str:
    body = re.sub(r"Cathoven(?!猫多芬雅思)", BRAND_FULL, body, count=1, flags=re.IGNORECASE)
    body = re.sub(r"(?<!Cathoven)猫多芬雅思", BRAND_FULL, body, count=1)
    return body


def _dedupe_full_brand(body: str) -> str:
    first = body.find(BRAND_FULL)
    if first == -1:
        return body
    head = body[: first + len(BRAND_FULL)]
    tail = body[first + len(BRAND_FULL) :].replace(BRAND_FULL, "它")
    return head + tail


def _fit_body(body: str) -> str:
    if len(body) <= MAX_BODY_CHARS:
        return body
    for lead_chars in (260, 240):
        if _first_brand_mention_is_full(body[:MAX_BODY_CHARS]):
            break
        lead = body[:lead_chars].rstrip(BODY_STRIP_CHARS)
        body = f"{lead}。\n\n{DISCOVERY_SENTENCE}"
        if len(body) <= MAX_BODY_CHARS:
            return body
    return body[: MAX_BODY_CHARS - 1].rstrip(BODY_STRIP_CHARS) + "。"
