"""initial workflow schema

Revision ID: 20260703_0001
Revises:
Create Date: 2026-07-03 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260703_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_step", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("audience", sa.String(), nullable=False),
        sa.Column("product_function", sa.String(), nullable=False),
        sa.Column("pain_point", sa.String(), nullable=False),
        sa.Column("style_preference", sa.String(), nullable=True),
        sa.Column("reference_path", sa.String(), nullable=True),
        sa.Column("brief", sa.JSON(), nullable=True),
        sa.Column("final_package", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_content_runs_created_at", "content_runs", ["created_at"])
    op.create_index("ix_content_runs_current_step", "content_runs", ["current_step"])
    op.create_index("ix_content_runs_status", "content_runs", ["status"])

    op.create_table(
        "run_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("content_runs.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_run_steps_name", "run_steps", ["name"])
    op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])
    op.create_index("ix_run_steps_status", "run_steps", ["status"])

    op.create_table(
        "drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("content_runs.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("first_comment", sa.Text(), nullable=True),
        sa.Column("narrative_plan", sa.JSON(), nullable=True),
        sa.Column("quality_report", sa.JSON(), nullable=True),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_drafts_is_final", "drafts", ["is_final"])
    op.create_index("ix_drafts_run_id", "drafts", ["run_id"])

    op.create_table(
        "image_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("content_runs.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("reference_reason", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("qc_report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_image_assets_kind", "image_assets", ["kind"])
    op.create_index("ix_image_assets_run_id", "image_assets", ["run_id"])
    op.create_index("ix_image_assets_status", "image_assets", ["status"])

    op.create_table(
        "reference_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("content_runs.id"), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reference_assets_run_id", "reference_assets", ["run_id"])

    op.create_table(
        "review_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("content_runs.id"), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("replacement", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_actions_run_id", "review_actions", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_review_actions_run_id", table_name="review_actions")
    op.drop_table("review_actions")
    op.drop_index("ix_reference_assets_run_id", table_name="reference_assets")
    op.drop_table("reference_assets")
    op.drop_index("ix_image_assets_status", table_name="image_assets")
    op.drop_index("ix_image_assets_run_id", table_name="image_assets")
    op.drop_index("ix_image_assets_kind", table_name="image_assets")
    op.drop_table("image_assets")
    op.drop_index("ix_drafts_run_id", table_name="drafts")
    op.drop_index("ix_drafts_is_final", table_name="drafts")
    op.drop_table("drafts")
    op.drop_index("ix_run_steps_status", table_name="run_steps")
    op.drop_index("ix_run_steps_run_id", table_name="run_steps")
    op.drop_index("ix_run_steps_name", table_name="run_steps")
    op.drop_table("run_steps")
    op.drop_index("ix_content_runs_status", table_name="content_runs")
    op.drop_index("ix_content_runs_current_step", table_name="content_runs")
    op.drop_index("ix_content_runs_created_at", table_name="content_runs")
    op.drop_table("content_runs")
