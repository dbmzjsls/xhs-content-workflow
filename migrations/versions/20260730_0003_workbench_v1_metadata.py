"""add v1 workbench workflow metadata

Revision ID: 20260730_0003
Revises: 20260706_0002
Create Date: 2026-07-30 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260730_0003"
down_revision = "20260706_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("content_runs") as batch_op:
        batch_op.add_column(sa.Column("workflow_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("workflow_version", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("provider", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("model", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_content_runs_heartbeat_at", ["heartbeat_at"])
        batch_op.create_index("ix_content_runs_workflow_name", ["workflow_name"])

    with op.batch_alter_table("run_steps") as batch_op:
        batch_op.add_column(
            sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1"))
        )
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("error", sa.Text(), nullable=True))
        batch_op.create_index("ix_run_steps_attempt", ["attempt"])
        batch_op.create_index("ix_run_steps_started_at", ["started_at"])

    with op.batch_alter_table("drafts") as batch_op:
        batch_op.add_column(sa.Column("round", sa.Integer(), nullable=False, server_default=sa.text("1")))
        batch_op.add_column(sa.Column("candidate", sa.Integer(), nullable=False, server_default=sa.text("1")))
        batch_op.add_column(
            sa.Column(
                "parent_draft_id",
                sa.Integer(),
                sa.ForeignKey("drafts.id", name="fk_drafts_parent_draft_id"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("angle", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("score", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_index("ix_drafts_parent_draft_id", ["parent_draft_id"])
        batch_op.create_index("ix_drafts_selected", ["selected"])

    op.create_table(
        "upload_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("content_runs.id"), nullable=False),
        sa.Column("draft_id", sa.Integer(), sa.ForeignKey("drafts.id"), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("checksum", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("remote_id", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_upload_assets_draft_id", "upload_assets", ["draft_id"])
    op.create_index("ix_upload_assets_run_id", "upload_assets", ["run_id"])
    op.create_index("ix_upload_assets_status", "upload_assets", ["status"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("content_runs.id"), nullable=True),
        sa.Column("request_hash", sa.String(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_idempotency_records_key"),
    )
    op.create_index("ix_idempotency_records_run_id", "idempotency_records", ["run_id"])
    op.create_index("ix_idempotency_records_scope", "idempotency_records", ["scope"])
    op.create_index("ix_idempotency_records_status", "idempotency_records", ["status"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_status", table_name="idempotency_records")
    op.drop_index("ix_idempotency_records_scope", table_name="idempotency_records")
    op.drop_index("ix_idempotency_records_run_id", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index("ix_upload_assets_status", table_name="upload_assets")
    op.drop_index("ix_upload_assets_run_id", table_name="upload_assets")
    op.drop_index("ix_upload_assets_draft_id", table_name="upload_assets")
    op.drop_table("upload_assets")

    with op.batch_alter_table("drafts") as batch_op:
        batch_op.drop_index("ix_drafts_selected")
        batch_op.drop_index("ix_drafts_parent_draft_id")
        batch_op.drop_column("selected")
        batch_op.drop_column("score")
        batch_op.drop_column("source")
        batch_op.drop_column("angle")
        batch_op.drop_constraint("fk_drafts_parent_draft_id", type_="foreignkey")
        batch_op.drop_column("parent_draft_id")
        batch_op.drop_column("candidate")
        batch_op.drop_column("round")

    with op.batch_alter_table("run_steps") as batch_op:
        batch_op.drop_index("ix_run_steps_started_at")
        batch_op.drop_index("ix_run_steps_attempt")
        batch_op.drop_column("error")
        batch_op.drop_column("duration_ms")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("attempt")

    with op.batch_alter_table("content_runs") as batch_op:
        batch_op.drop_index("ix_content_runs_workflow_name")
        batch_op.drop_index("ix_content_runs_heartbeat_at")
        batch_op.drop_column("heartbeat_at")
        batch_op.drop_column("model")
        batch_op.drop_column("provider")
        batch_op.drop_column("workflow_version")
        batch_op.drop_column("workflow_name")
