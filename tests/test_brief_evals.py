from __future__ import annotations

import pytest

from app.evals import briefs


def test_fixed_mock_brief_cases_all_pass_hard_rules() -> None:
    results = briefs.evaluate_mock_hard()

    assert [result["id"] for result in results] == [
        "writing",
        "speaking",
        "commuting",
        "tutorial",
    ]
    for result in results:
        assert result["provider"] == "mock"
        assert result["candidate_count"] == 3
        assert result["recommended_candidate"] in {1, 2, 3}
        assert result["passed"] is True
        assert result["failures"] == []


def test_mock_eval_ignores_ambient_real_provider_configuration(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "must-not-be-used")

    def provider_lookup_must_not_run():
        raise AssertionError("ambient provider lookup was used")

    monkeypatch.setattr(
        briefs.content_pipeline,
        "get_pipeline_provider",
        provider_lookup_must_not_run,
    )

    assert all(result["provider"] == "mock" for result in briefs.evaluate_mock_hard())


def test_real_soft_eval_requires_explicit_paid_provider_opt_in(monkeypatch) -> None:
    def provider_lookup_must_not_run():
        raise AssertionError("provider lookup happened before opt-in validation")

    monkeypatch.setattr(
        briefs.content_pipeline,
        "get_pipeline_provider",
        provider_lookup_must_not_run,
    )

    with pytest.raises(PermissionError, match="allow-paid-providers"):
        briefs.evaluate_real_soft(allow_paid_providers=False)


def test_cli_rejects_real_soft_without_explicit_opt_in() -> None:
    with pytest.raises(SystemExit) as exc_info:
        briefs.main(["real-soft"])

    assert exc_info.value.code == 2
