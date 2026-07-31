from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"


def test_ci_temp_paths_are_configured_after_runner_start() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "${{ runner.temp }}" not in workflow
    assert 'DATABASE_URL=sqlite:///$RUNNER_TEMP/empty-migration.sqlite' in workflow
    assert 'EXPORT_DIR=$RUNNER_TEMP/exports' in workflow
    assert 'UPLOAD_ROOT=$RUNNER_TEMP/uploads' in workflow
    assert '>> "$GITHUB_ENV"' in workflow
