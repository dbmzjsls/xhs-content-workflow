"""add unique draft version constraint

Revision ID: 20260706_0002
Revises: 20260703_0001
Create Date: 2026-07-06 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "20260706_0002"
down_revision = "20260703_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("drafts") as batch_op:
        batch_op.create_unique_constraint(
            "uq_drafts_run_id_version",
            ["run_id", "version"],
        )


def downgrade() -> None:
    with op.batch_alter_table("drafts") as batch_op:
        batch_op.drop_constraint("uq_drafts_run_id_version", type_="unique")
