from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.time_utils import utc_now


class ContentRun(SQLModel, table=True):
    __tablename__ = "content_runs"

    id: int | None = Field(default=None, primary_key=True)
    status: str = Field(default="running", index=True)
    current_step: str = Field(default="created", index=True)
    topic: str
    audience: str
    product_function: str
    pain_point: str
    style_preference: str | None = None
    reference_path: str | None = None
    brief: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    final_package: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    error: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class RunStep(SQLModel, table=True):
    __tablename__ = "run_steps"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(index=True, foreign_key="content_runs.id")
    name: str = Field(index=True)
    status: str = Field(default="completed", index=True)
    input_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    output_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class Draft(SQLModel, table=True):
    __tablename__ = "drafts"
    __table_args__ = (UniqueConstraint("run_id", "version", name="uq_drafts_run_id_version"),)

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(index=True, foreign_key="content_runs.id")
    version: int = Field(default=1)
    title: str
    body: str = Field(sa_column=Column(Text))
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    first_comment: str | None = Field(default=None, sa_column=Column(Text))
    narrative_plan: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    quality_report: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    is_final: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utc_now)


class ImageAsset(SQLModel, table=True):
    __tablename__ = "image_assets"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(index=True, foreign_key="content_runs.id")
    kind: str = Field(index=True)
    status: str = Field(default="fallback", index=True)
    title: str
    prompt: str = Field(sa_column=Column(Text))
    reference_reason: str = Field(sa_column=Column(Text))
    file_path: str | None = None
    qc_report: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class ReferenceAsset(SQLModel, table=True):
    __tablename__ = "reference_assets"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(index=True, foreign_key="content_runs.id")
    source: str
    role: str
    path: str
    reason: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)


class ReviewAction(SQLModel, table=True):
    __tablename__ = "review_actions"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(index=True, foreign_key="content_runs.id")
    action: str
    instructions: str | None = Field(default=None, sa_column=Column(Text))
    replacement: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
