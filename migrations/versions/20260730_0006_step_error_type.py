"""Add structured error type to durable step attempts.

Revision ID: 20260730_0006
Revises: 20260730_0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260730_0006"
down_revision = "20260730_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("run_steps") as batch_op:
        batch_op.add_column(sa.Column("error_type", sa.String(), nullable=True))
        batch_op.create_index("ix_run_steps_error_type", ["error_type"])


def downgrade() -> None:
    with op.batch_alter_table("run_steps") as batch_op:
        batch_op.drop_index("ix_run_steps_error_type")
        batch_op.drop_column("error_type")
