from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from scripts.start_e2e_backend import _require_safe_environment


def _set_temp_roots(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("E2E_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'e2e.sqlite').as_posix()}")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "uploads"))


def test_e2e_launcher_rejects_non_mock_provider_before_start(tmp_path, monkeypatch) -> None:
    _set_temp_roots(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="explicit mock"):
        _require_safe_environment()


def test_e2e_launcher_accepts_explicit_mock_temp_roots(tmp_path, monkeypatch) -> None:
    _set_temp_roots(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    get_settings.cache_clear()

    _require_safe_environment()


def test_playwright_backend_uses_uv_project_environment() -> None:
    config = (Path(__file__).parents[1] / "frontend" / "playwright.config.ts").read_text(
        encoding="utf-8"
    )

    assert "command: 'uv run python scripts/start_e2e_backend.py'" in config
    assert "cwd: repositoryRoot" in config
    assert "command: 'python scripts/start_e2e_backend.py'" not in config
