"""Clear stale image state before legacy text recovery.

Revision ID: 20260731_0009
Revises: 20260731_0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260731_0009"
down_revision = "20260731_0008"
branch_labels = None
depends_on = None

_LEGACY_RETRY_ERROR = "legacy drafts failed current hard rules; retry text generation"


def upgrade() -> None:
    bind = op.get_bind()
    run_ids = list(
        bind.execute(
            sa.text(
                """
                SELECT id FROM content_runs
                WHERE status = 'failed'
                  AND failed_phase = 'text'
                  AND error = :legacy_error
                """
            ),
            {"legacy_error": _LEGACY_RETRY_ERROR},
        ).scalars()
    )
    for run_id in run_ids:
        # Keep source files on disk, but remove their stale public/packaging rows.
        bind.execute(
            sa.text("DELETE FROM image_assets WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
        bind.execute(
            sa.text(
                """
                UPDATE drafts
                SET selected = 0, is_final = 0
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id},
        )
        bind.execute(
            sa.text(
                """
                UPDATE content_runs
                SET final_package = NULL
                WHERE id = :run_id
                """
            ),
            {"run_id": run_id},
        )
        # These completed outputs all contain or validate data derived from the
        # old draft. Marking them failed prevents execution_service from reusing
        # them after the public text retry creates a new selected draft.
        bind.execute(
            sa.text(
                """
                UPDATE run_steps
                SET status = 'failed',
                    error = 'invalidated for legacy draft and image regeneration',
                    error_type = 'LegacyDraftIneligible'
                WHERE run_id = :run_id
                  AND name IN (
                      'prompt_rewrite', 'image_generate', 'image_qc', 'image_generation'
                  )
                  AND status = 'completed'
                """
            ),
            {"run_id": run_id},
        )


def downgrade() -> None:
    # Deleted stale rows and cleared unsafe final/selection state cannot be
    # reconstructed safely. Source files and legacy_final_package remain intact.
    pass
