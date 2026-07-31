"""Make ineligible adopted review runs safely retryable.

Revision ID: 20260731_0008
Revises: 20260731_0007
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260731_0008"
down_revision = "20260731_0007"
branch_labels = None
depends_on = None


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(decoded) if isinstance(decoded, dict) else {}
    return {}


def upgrade() -> None:
    bind = op.get_bind()

    # A NULL legacy brief was normalized to {} in 0007. Text retry requires the
    # full public run brief, so reconstruct missing keys from preserved columns.
    runs = bind.execute(
        sa.text(
            """
            SELECT id, topic, audience, product_function, pain_point,
                   style_preference, brief
            FROM content_runs
            """
        )
    ).mappings()
    for run in runs:
        brief = _json_object(run["brief"])
        source = {
            "topic": run["topic"],
            "audience": run["audience"],
            "product_function": run["product_function"],
            "pain_point": run["pain_point"],
            "style_preference": run["style_preference"],
        }
        changed = False
        for key, value in source.items():
            if not brief.get(key) and value is not None:
                brief[key] = value
                changed = True
        if changed:
            bind.execute(
                sa.text("UPDATE content_runs SET brief = :brief WHERE id = :run_id"),
                {
                    "run_id": run["id"],
                    "brief": json.dumps(brief, ensure_ascii=False),
                },
            )

    review_run_ids = bind.execute(
        sa.text(
            """
            SELECT id FROM content_runs
            WHERE status IN (
                'review_required', 'copy_review_required', 'asset_review_required'
            )
            """
        )
    ).scalars()
    for run_id in review_run_ids:
        drafts = list(
            bind.execute(
                sa.text(
                    """
                    SELECT id, version, selected, quality_report
                    FROM drafts
                    WHERE run_id = :run_id
                    ORDER BY version, id
                    """
                ),
                {"run_id": run_id},
            ).mappings()
        )
        eligible = [
            draft
            for draft in drafts
            if _json_object(draft["quality_report"])
            .get("hard", {})
            .get("passed")
            is True
        ]
        explicitly_selected = [draft for draft in eligible if draft["selected"]]
        bind.execute(
            sa.text("UPDATE drafts SET selected = 0 WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
        if eligible:
            chosen = max(explicitly_selected or eligible, key=lambda row: (row["version"], row["id"]))
            bind.execute(
                sa.text("UPDATE drafts SET selected = 1 WHERE id = :draft_id"),
                {"draft_id": chosen["id"]},
            )
            continue

        # With no eligible draft, copy review has no legal transition. Move the
        # run to the existing recoverable text phase and invalidate any cached
        # candidate output so POST /retry performs a fresh deterministic round.
        bind.execute(
            sa.text(
                """
                UPDATE content_runs
                SET status = 'failed',
                    current_step = 'text_generation',
                    error = 'legacy drafts failed current hard rules; retry text generation',
                    failed_phase = 'text'
                WHERE id = :run_id
                """
            ),
            {"run_id": run_id},
        )
        bind.execute(
            sa.text(
                """
                UPDATE run_steps
                SET status = 'failed',
                    error = 'invalidated for legacy text regeneration',
                    error_type = 'LegacyDraftIneligible'
                WHERE run_id = :run_id
                  AND name IN ('candidate_round', 'text_generation')
                  AND status = 'completed'
                """
            ),
            {"run_id": run_id},
        )


def downgrade() -> None:
    # This is a data-safety correction. Restoring a hard-failing selection would
    # recreate the invalid review state, so the normalized/recoverable data stays.
    pass
