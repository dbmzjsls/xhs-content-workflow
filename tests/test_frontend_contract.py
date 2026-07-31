from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_revision_tabs_and_visible_selected_approval_contract_are_wired():
    preview = (ROOT / "frontend/src/components/DraftPreview.tsx").read_text("utf-8")
    app = (ROOT / "frontend/src/App.tsx").read_text("utf-8")
    review = (ROOT / "frontend/src/components/ReviewBar.tsx").read_text("utf-8")
    e2e = (ROOT / "frontend/e2e/workbench.spec.ts").read_text("utf-8")

    assert "revision-tab-" in preview
    assert "Revision" in preview
    assert "visibleDraftId" in app
    assert "visibleDraftId === selected?.id" in app
    assert "reviewActionsEnabled" in review
    assert "disabled={busy || !instructions.trim() || !reviewActionsEnabled}" in review
    assert "disabled={busy || !reviewActionsEnabled}" in review
    assert "if (run && visibleDraftId === selected?.id) await api.revise" in app
    assert "revision-tab-" in e2e
    assert "toBeDisabled" in e2e
    assert "getByTestId('revise-draft')).toBeDisabled" in e2e
