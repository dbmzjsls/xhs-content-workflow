# Task 2 report: versioned content pipeline

## Delivered

- Added versioned YAML policy and example library under `content_library/`.
- Implemented deterministic example selection, exactly three content angles,
  one candidate per angle, hard checks with at most one repair, five-dimension
  0-20 soft scoring, deterministic ranking, round persistence, and revision
  parent-child lineage.
- Provider failures now surface instead of falling back silently to mock output.
- Revisions use the provider with original draft, rules, and instructions; they
  create a child draft instead of appending a note to the body.

## TDD evidence

1. Added `tests/test_content_pipeline.py` before implementation; initial run
   failed at collection because `content_pipeline` did not exist.
2. Implemented the pipeline incrementally and used focused tests for selection,
   three angles, ranking/hard exclusion, one-repair limit, no passing candidate,
   persistence, and parent-child revisions.
3. Updated the prior provider fallback test to require the specified strict
   failure behavior.

## Verification

- `pytest -q --basetemp .test-tmp-final` — 26 passed.
- `ruff check .` — passed.
- `git diff --check` — passed.

## Files

- `content_library/policy.yaml`
- `content_library/examples.yaml`
- `app/services/content_pipeline.py`
- `app/repositories/runs.py`
- `app/services/llm_provider.py`
- `app/services/workflow_service.py`
- `tests/test_content_pipeline.py`
- `tests/test_llm_provider.py`
- `pyproject.toml`

## Concerns

- Pytest emits a benign warning because the workspace's pre-existing
  `.pytest_cache` directory is not writable. A workspace-local `--basetemp`
  was used so temporary database tests remain isolated.
