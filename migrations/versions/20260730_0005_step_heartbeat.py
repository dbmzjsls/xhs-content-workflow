"""Add heartbeat audit data to durable step attempts.

Revision ID: 20260730_0005
Revises: 20260730_0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260730_0005"
down_revision = "20260730_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("run_steps") as batch_op:
        batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_run_steps_heartbeat_at", ["heartbeat_at"])


def downgrade() -> None:
    with op.batch_alter_table("run_steps") as batch_op:
        batch_op.drop_index("ix_run_steps_heartbeat_at")
        batch_op.drop_column("heartbeat_at")
