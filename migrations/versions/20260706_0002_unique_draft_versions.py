"""add unique draft version constraint

Revision ID: 20260706_0002
Revises: 20260703_0001
Create Date: 2026-07-06 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260706_0002"
down_revision = "20260703_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    unique_constraints = sa.inspect(op.get_bind()).get_unique_constraints("drafts")
    if any(
        constraint.get("column_names") == ["run_id", "version"]
        for constraint in unique_constraints
    ):
        return
    with op.batch_alter_table("drafts") as batch_op:
        batch_op.create_unique_constraint(
            "uq_drafts_run_id_version",
            ["run_id", "version"],
        )


def downgrade() -> None:
    # The initial schema owns this invariant; 0002 remains as an upgrade bridge
    # for databases created by the earlier form of 0001.
    pass
