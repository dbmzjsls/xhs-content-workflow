from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_revision_tabs_and_visible_selected_approval_contract_are_wired():
    preview = (ROOT / "frontend/src/components/DraftPreview.tsx").read_text("utf-8")
    detail = (ROOT / "frontend/src/components/RunDetail.tsx").read_text("utf-8")
    review = (ROOT / "frontend/src/components/ReviewBar.tsx").read_text("utf-8")
    e2e = (ROOT / "frontend/e2e/workbench.spec.ts").read_text("utf-8")

    assert "revision-tab-" in preview
    assert "返修" in preview
    assert 'role="tab"' in preview
    assert "aria-selected={item.id === draft.id}" in preview
    assert "selectedId !== undefined && draft?.id === selectedId" in detail
    assert "disabled={busy || !cleanInstructions || !reviewActionsEnabled}" in review
    assert "disabled={busy || !reviewActionsEnabled}" in review
    assert "revision-tab-" in e2e
    assert "getByTestId('revise-draft')).toBeDisabled" in e2e
    assert "getByTestId('approve-copy')).toBeDisabled" in e2e
