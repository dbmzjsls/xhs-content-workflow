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

## Final review-parent selection remediation

- `review_run(..., action="revise")` now resolves its parent with
  `get_selected_or_recommended_draft()`, so an unrelated newer draft cannot
  displace the selected candidate.
- Added an end-to-end normal-round → revise → approve/export regression test
  that verifies the exported child points to the original selected parent.
- Narrowed mock product-intent detection to explicit phrases; ordinary words
  such as `readable` no longer trigger the advertising rewrite path.

### Exact parent-selection test evidence

- `pytest tests/test_content_pipeline.py tests/test_candidate_workflow.py tests/test_api.py -q -p no:cacheprovider --basetemp .test-tmp-task2-parent-green` — `21 passed`.
- `pytest -q -p no:cacheprovider --basetemp .test-tmp-task2-parent-full` — `37 passed`.
- `ruff check .` — `All checks passed!`.
- `git diff --check` — passed.

## Final revision-selection remediation

- A persisted provider revision now becomes the run's only selected draft in
  the same draft-persistence transaction, so approval/export selects the child
  rather than its parent.
- Mock revisions now select an intent-specific narrative rewrite (product in
  the background, study-record ending, conversational voice, shorter version,
  or generic restructure). They do not append or quote reviewer instructions.
- Added example-library value-type and duplicate-ID validation.

### Exact final-remediation test evidence

- `pytest tests/test_content_pipeline.py tests/test_candidate_workflow.py tests/test_api.py tests/test_llm_provider.py -q -p no:cacheprovider --basetemp .test-tmp-task2-finalfix-focused` — `21 passed`.
- `pytest -q -p no:cacheprovider --basetemp .test-tmp-task2-finalfix-full` — `36 passed`.
- `ruff check .` — `All checks passed!`.
- `git diff --check` — passed.

### Final rerun after selection-uniqueness review

- `pytest tests/test_content_pipeline.py tests/test_candidate_workflow.py tests/test_api.py tests/test_llm_provider.py -q -p no:cacheprovider --basetemp .test-tmp-task2-final-focused` — `19 passed`.
- `pytest -q -p no:cacheprovider --basetemp .test-tmp-task2-final-full` — `34 passed`.
- `ruff check .` — `All checks passed!`.
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

## Review remediation (2026-07-30)

- Integrated `generate_candidate_round()` and `persist_candidate_round()` into
  the normal synchronous workflow. The selected candidate is now the draft
  used by image prompt generation and human review.
- Added selected-or-recommended draft lookup for finalization/export. It never
  falls back to the newest draft merely because it has the highest version.
- Made mock revisions instruction-dependent via a deterministic focus extracted
  from the supplied instructions; real-provider revision payloads remain
  instruction-driven.
- Added validation for every required policy collection and the `地铁` scene
  marker.

### Exact review-remediation test evidence

- `pytest tests/test_content_pipeline.py tests/test_candidate_workflow.py tests/test_llm_provider.py -q --basetemp .test-tmp-task2-focused` — `14 passed`.
- `pytest -q -p no:cacheprovider --basetemp .test-tmp-task2-full` — `34 passed`.
- `ruff check .` — `All checks passed!`.
- `git diff --check` — passed.
