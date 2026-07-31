"""Normalize adopted legacy rows and invalidate pre-boundary exports.

Revision ID: 20260731_0007
Revises: 20260730_0006
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260731_0007"
down_revision = "20260730_0006"
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

    with op.batch_alter_table("content_runs") as batch_op:
        batch_op.add_column(sa.Column("legacy_final_package", sa.JSON(), nullable=True))

    # Pre-boundary package files were rendered before arbitrary-string path
    # sanitization existed. Preserve their descriptor for audit, but revoke all
    # public download capability and require an explicit safe re-export.
    bind.execute(
        sa.text(
            """
            UPDATE content_runs
            SET legacy_final_package = final_package,
                final_package = NULL,
                status = CASE WHEN status = 'completed' THEN 'asset_review_required' ELSE status END,
                current_step = CASE WHEN status = 'completed' THEN 'asset_review' ELSE current_step END
            WHERE final_package IS NOT NULL
            """
        )
    )

    bind.execute(sa.text("UPDATE content_runs SET brief = '{}' WHERE brief IS NULL"))
    bind.execute(
        sa.text(
            "UPDATE run_steps SET input_payload = '{}' WHERE input_payload IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE run_steps SET output_payload = '{}' WHERE output_payload IS NULL"
        )
    )
    bind.execute(sa.text("UPDATE drafts SET body = '' WHERE body IS NULL"))
    bind.execute(sa.text("UPDATE drafts SET tags = '[]' WHERE tags IS NULL"))
    bind.execute(
        sa.text("UPDATE drafts SET narrative_plan = '{}' WHERE narrative_plan IS NULL")
    )
    bind.execute(
        sa.text("UPDATE drafts SET quality_report = '{}' WHERE quality_report IS NULL")
    )
    bind.execute(sa.text("UPDATE image_assets SET prompt = '' WHERE prompt IS NULL"))
    bind.execute(
        sa.text("UPDATE image_assets SET reference_reason = '' WHERE reference_reason IS NULL")
    )
    bind.execute(
        sa.text("UPDATE image_assets SET qc_report = '{}' WHERE qc_report IS NULL")
    )
    bind.execute(
        sa.text("UPDATE reference_assets SET reason = '' WHERE reason IS NULL")
    )

    # Recompute the current hard-rule report deterministically. Existing evidence
    # remains embedded for audit, while eligibility never trusts a legacy
    # top-level `passed` flag as a current hard-rule pass.
    from app.services.content_pipeline import hard_rule_check

    drafts = bind.execute(
        sa.text("SELECT id, title, body, tags, first_comment, quality_report FROM drafts")
    ).mappings()
    for draft in drafts:
        tags = draft["tags"]
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (TypeError, ValueError):
                tags = []
        if not isinstance(tags, list):
            tags = []
        prior = _json_object(draft["quality_report"])
        normalized = dict(prior)
        if prior and "legacy_quality_report" not in normalized:
            normalized["legacy_quality_report"] = prior
        normalized["hard"] = hard_rule_check(
            {
                "title": draft["title"] or "",
                "body": draft["body"] or "",
                "tags": tags,
                "first_comment": draft["first_comment"] or "",
            }
        )
        bind.execute(
            sa.text("UPDATE drafts SET quality_report = :report WHERE id = :draft_id"),
            {
                "draft_id": draft["id"],
                "report": json.dumps(normalized, ensure_ascii=False),
            },
        )

    review_runs = bind.execute(
        sa.text(
            """
            SELECT id
            FROM content_runs
            WHERE status IN ('review_required', 'copy_review_required', 'asset_review_required')
              AND EXISTS (SELECT 1 FROM drafts WHERE drafts.run_id = content_runs.id)
              AND NOT EXISTS (
                  SELECT 1 FROM drafts
                  WHERE drafts.run_id = content_runs.id AND drafts.selected = 1
              )
            """
        )
    ).scalars()
    for run_id in review_runs:
        latest_id = bind.execute(
            sa.text(
                """
                SELECT id FROM drafts
                WHERE run_id = :run_id
                ORDER BY version DESC, id DESC
                LIMIT 1
                """
            ),
            {"run_id": run_id},
        ).scalar_one()
        bind.execute(
            sa.text("UPDATE drafts SET selected = 1 WHERE id = :draft_id"),
            {"draft_id": latest_id},
        )

    with op.batch_alter_table("content_runs") as batch_op:
        batch_op.alter_column("brief", existing_type=sa.JSON(), nullable=False)
    with op.batch_alter_table("run_steps") as batch_op:
        batch_op.alter_column("input_payload", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("output_payload", existing_type=sa.JSON(), nullable=False)
    with op.batch_alter_table("drafts") as batch_op:
        batch_op.alter_column("body", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("tags", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("narrative_plan", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("quality_report", existing_type=sa.JSON(), nullable=False)
    with op.batch_alter_table("image_assets") as batch_op:
        batch_op.alter_column("prompt", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("reference_reason", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("qc_report", existing_type=sa.JSON(), nullable=False)
    with op.batch_alter_table("reference_assets") as batch_op:
        batch_op.alter_column("reason", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE content_runs
            SET final_package = legacy_final_package,
                status = CASE
                    WHEN status = 'asset_review_required' AND final_package IS NULL
                    THEN 'completed' ELSE status END,
                current_step = CASE
                    WHEN status = 'asset_review_required' AND final_package IS NULL
                    THEN 'export_package' ELSE current_step END
            WHERE legacy_final_package IS NOT NULL AND final_package IS NULL
            """
        )
    )
    with op.batch_alter_table("reference_assets") as batch_op:
        batch_op.alter_column("reason", existing_type=sa.Text(), nullable=True)
    with op.batch_alter_table("image_assets") as batch_op:
        batch_op.alter_column("qc_report", existing_type=sa.JSON(), nullable=True)
        batch_op.alter_column("reference_reason", existing_type=sa.Text(), nullable=True)
        batch_op.alter_column("prompt", existing_type=sa.Text(), nullable=True)
    with op.batch_alter_table("drafts") as batch_op:
        batch_op.alter_column("quality_report", existing_type=sa.JSON(), nullable=True)
        batch_op.alter_column("narrative_plan", existing_type=sa.JSON(), nullable=True)
        batch_op.alter_column("tags", existing_type=sa.JSON(), nullable=True)
        batch_op.alter_column("body", existing_type=sa.Text(), nullable=True)
    with op.batch_alter_table("run_steps") as batch_op:
        batch_op.alter_column("output_payload", existing_type=sa.JSON(), nullable=True)
        batch_op.alter_column("input_payload", existing_type=sa.JSON(), nullable=True)
    with op.batch_alter_table("content_runs") as batch_op:
        batch_op.alter_column("brief", existing_type=sa.JSON(), nullable=True)
        batch_op.drop_column("legacy_final_package")
