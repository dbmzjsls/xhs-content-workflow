"""Add durable worker retry phase and allow pre-run uploads.

Revision ID: 20260730_0004
Revises: 20260730_0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260730_0004"
down_revision = "20260730_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("content_runs") as batch_op:
        batch_op.add_column(sa.Column("failed_phase", sa.String(), nullable=True))
        batch_op.create_index("ix_content_runs_failed_phase", ["failed_phase"])
    with op.batch_alter_table("upload_assets") as batch_op:
        batch_op.alter_column("run_id", existing_type=sa.Integer(), nullable=True)
    op.execute(
        sa.text(
            "UPDATE content_runs SET status = 'copy_review_required' "
            "WHERE status = 'review_required'"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("upload_assets") as batch_op:
        batch_op.alter_column("run_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("content_runs") as batch_op:
        batch_op.drop_index("ix_content_runs_failed_phase")
        batch_op.drop_column("failed_phase")
