from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, Float, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.time_utils import utc_now


class ContentRun(SQLModel, table=True):
    __tablename__ = "content_runs"

    id: int | None = Field(default=None, primary_key=True)
    status: str = Field(default="queued", index=True)
    current_step: str = Field(default="created", index=True)
    topic: str
    audience: str
    product_function: str
    pain_point: str
    style_preference: str | None = None
    reference_path: str | None = None
    brief: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    final_package: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    legacy_final_package: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    error: str | None = Field(default=None, sa_column=Column(Text))
    workflow_name: str | None = Field(default=None, index=True)
    workflow_version: str | None = None
    provider: str | None = None
    model: str | None = None
    heartbeat_at: datetime | None = Field(default=None, index=True)
    failed_phase: str | None = Field(default=None, index=True)
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
    attempt: int = Field(default=1, index=True)
    started_at: datetime | None = Field(default=None, index=True)
    heartbeat_at: datetime | None = Field(default=None, index=True)
    completed_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = Field(default=None, sa_column=Column(Text))
    error_type: str | None = Field(default=None, index=True)
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
    round: int = Field(default=1)
    candidate: int = Field(default=1)
    parent_draft_id: int | None = Field(default=None, foreign_key="drafts.id", index=True)
    angle: str | None = None
    source: str | None = None
    score: float | None = Field(default=None, sa_column=Column(Float))
    selected: bool = Field(default=False, index=True)
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


class UploadAsset(SQLModel, table=True):
    __tablename__ = "upload_assets"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int | None = Field(default=None, index=True, foreign_key="content_runs.id")
    draft_id: int | None = Field(default=None, index=True, foreign_key="drafts.id")
    kind: str
    status: str = Field(index=True)
    file_path: str
    mime_type: str | None = None
    checksum: str | None = None
    size_bytes: int | None = None
    provider: str | None = None
    remote_id: str | None = None
    metadata_payload: dict[str, Any] | None = Field(default=None, sa_column=Column("metadata", JSON))
    error: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class IdempotencyRecord(SQLModel, table=True):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("key", name="uq_idempotency_records_key"),)

    id: int | None = Field(default=None, primary_key=True)
    key: str
    scope: str = Field(index=True)
    run_id: int | None = Field(default=None, index=True, foreign_key="content_runs.id")
    request_hash: str | None = None
    response_payload: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    status: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
