from __future__ import annotations

import json
from typing import Any, Protocol

from app.config import get_settings


class DraftProvider(Protocol):
    name: str

    def generate_draft(self, brief: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        """Return a Xiaohongshu draft candidate before deterministic rule checks."""


class MockDraftProvider:
    name = "mock"

    def generate_draft(self, brief: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        from app.services.content_rules import generate_mock_draft

        draft = generate_mock_draft(brief, plan)
        return {**draft, "provider": self.name}


class OpenAICompatibleDraftProvider:
    name = "openai-compatible"

    def generate_draft(self, brief: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        if not settings.openai_compatible_api_key:
            raise RuntimeError("OPENAI_COMPATIBLE_API_KEY is not configured")

        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_compatible_api_key,
            base_url=settings.openai_compatible_base_url,
        )
        response = client.chat.completions.create(
            model=settings.openai_compatible_model,
            temperature=0.7,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是小红书内容工作流里的文案候选生成器。"
                        "只输出 JSON，不要解释。产品必须自然发现式出现，"
                        "不要硬广，不要使用正式论文口吻。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "brief": brief,
                            "narrative_plan": plan,
                            "required_json_schema": {
                                "title": "20字以内小红书标题",
                                "body": "20-400字正文",
                                "tags": ["#标签"],
                                "first_comment": "首评",
                            },
                            "hard_rules": [
                                "首次品牌名必须是 Cathoven猫多芬雅思",
                                "标签必须含 #猫多芬雅思 和 #cathovenielts",
                                "正文用第一人称具体场景",
                                "产品通过 后来/结果/慢慢发现 自然出现",
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return {
            "title": str(data.get("title") or brief["topic"]),
            "body": str(data.get("body") or ""),
            "tags": list(data.get("tags") or []),
            "first_comment": data.get("first_comment") or "",
            "provider": self.name,
        }


def get_draft_provider() -> DraftProvider:
    settings = get_settings()
    if settings.llm_provider.lower() in {"openai", "openai-compatible"}:
        return OpenAICompatibleDraftProvider()
    return MockDraftProvider()


def generate_draft(brief: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    provider = get_draft_provider()
    # Provider selection is explicit: an OpenAI-compatible failure must be
    # observable to the caller, never hidden by an unrelated mock response.
    return provider.generate_draft(brief, plan)
