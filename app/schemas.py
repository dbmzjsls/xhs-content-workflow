from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(default="睡前 20 分钟改作文")
    audience: str = Field(default="雅思 5.5-6.5 自学考生")
    product_function: str = Field(default="Writing Checker")
    pain_point: str = Field(default="改了很多遍作文，还是不知道卡在哪个评分维度")
    style_preference: str | None = Field(default="备忘录聊天框风")
    upload_asset_ids: list[int] = Field(default_factory=list, max_length=20)


class DraftSelection(BaseModel):
    draft_id: int


class DraftRevision(BaseModel):
    instructions: str = Field(min_length=1, max_length=500)


class DraftReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=20)
    body: str = Field(min_length=20, max_length=400)
    tags: list[str] = Field(default_factory=list, max_length=12)
    first_comment: str | None = Field(default=None, max_length=200)


class ReviewRequest(BaseModel):
    action: Literal["approve", "revise", "replace"]
    instructions: str | None = Field(default=None, max_length=500)
    replacement: DraftReplacement | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> "ReviewRequest":
        if self.action == "replace" and self.replacement is None:
            raise ValueError("replacement is required for replace action")
        return self


class StepRead(BaseModel):
    name: str
    status: str
    output_payload: dict[str, Any]
    created_at: datetime
    attempt: int
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    error: str | None


class DraftRead(BaseModel):
    id: int
    title: str
    body: str
    tags: list[str]
    first_comment: str | None
    narrative_plan: dict[str, Any]
    quality_report: dict[str, Any]
    is_final: bool
    selected: bool
    candidate: int
    parent_draft_id: int | None


class ImageRead(BaseModel):
    id: int
    kind: str
    status: str
    title: str
    prompt: str
    reference_reason: str
    url: str | None
    qc_report: dict[str, Any]


class RunRead(BaseModel):
    id: int
    status: str
    current_step: str
    topic: str
    audience: str
    product_function: str
    pain_point: str
    style_preference: str | None
    brief: dict[str, Any]
    final_package: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    steps: list[StepRead]
    drafts: list[DraftRead]
    images: list[ImageRead]


class RunSummary(BaseModel):
    id: int
    status: str
    current_step: str
    topic: str
    error: str | None
    created_at: datetime
    updated_at: datetime


class RunList(BaseModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int


class UploadRead(BaseModel):
    id: int
    mime_type: str
    size_bytes: int
    url: str
