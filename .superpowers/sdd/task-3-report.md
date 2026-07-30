# Task 3 report: durable worker and backend integration

## Outcome

Implemented the local asynchronous workbench backend with the exact run states `queued`, `running`, `copy_review_required`, `image_queued`, `image_running`, `asset_review_required`, `completed`, `failed`, and `canceled`.

- `POST /api/runs` persists and returns a run with HTTP 202; it does not execute provider work in the request.
- One daemon worker serially claims text/image work. `run_once()` and `recover_stale()` provide deterministic test control. Startup recovery requeues stale `running` and `image_running` rows, while completed step output is reused on retry.
- Text execution produces exactly three scored candidates and stops at the copy gate. Selection, revision, copy approval, image execution, asset approval/export, retry, and cancellation enforce explicit transitions; illegal transitions return 409.
- Selection, revision, both approvals, retry, and cancel support `Idempotency-Key`. Replays return the stored response; reuse for a different scope/run/payload returns 409. In-process mutation locking prevents concurrent duplicate execution.
- Provider names are strict. Only explicitly selected `mock`, `openai`, or `openai-compatible` modes are accepted; missing real-provider configuration or provider errors fail the run without mock substitution.
- Uploads accept only PNG/JPEG/WebP up to 10 MiB and validate extension, MIME, and magic bytes. Files use UUID names and atomic replace. Runs accept upload IDs only; arbitrary path input is rejected.
- API payloads expose IDs and owned URLs rather than absolute paths. Upload, generated-asset, and export reads verify run ownership and resolved root containment. Generated images and exported markdown/JSON/ZIP files use temporary files plus atomic replace.
- The generic `/review` route and broad static export mount were removed.

## Files

- API/lifecycle: `app/api/runs.py`, `app/api/uploads.py`, `app/main.py`
- State and worker: `app/services/worker.py`, `app/services/execution_service.py`, `app/services/state_service.py`, `app/services/upload_service.py`
- Provider/export hardening: `app/services/content_pipeline.py`, `app/services/image_rules.py`, `app/services/export_service.py`
- Persistence/contracts: `app/config.py`, `app/models.py`, `app/repositories/runs.py`, `app/schemas.py`
- Compatibility state cleanup: `app/services/workflow_service.py`, `app/workflow/graph.py`
- Migration: `migrations/versions/20260730_0004_worker_state.py`
- Tests: `tests/test_async_workbench_api.py`, `tests/test_api.py`, `tests/test_migrate.py`

## TDD evidence

Red:

```powershell
python -m pytest tests/test_async_workbench_api.py -q --basetemp=.pytest-tmp/task3-red -p no:cacheprovider
```

Collection failed with `ModuleNotFoundError: No module named 'app.services.worker'`, proving the new async contract preceded implementation.

Intermediate green:

```powershell
python -m pytest tests/test_async_workbench_api.py -q --basetemp=.pytest-tmp/task3-green3 -p no:cacheprovider
```

Result: 9 passed. Self-review then added deterministic cancellation-during-provider coverage, arbitrary-path rejection, cross-run generated-asset denial, heartbeat refresh, concurrent idempotency serialization, and legacy-state migration.

Final focused validation:

```powershell
python -m pytest tests/test_async_workbench_api.py tests/test_migrate.py -q --basetemp=.pytest-tmp/task3-focused2 -p no:cacheprovider
```

Result: 17 passed, 1 upstream warning.

Final full validation:

```powershell
python -m pytest -q --basetemp=.pytest-tmp/task3-full-final -p no:cacheprovider
python -m ruff check app tests migrations
git diff --check
```

Results:

- Full pytest: 45 passed, 1 warning in 13.68s.
- Ruff: all checks passed.
- Diff whitespace check: passed (Git emitted only LF-to-CRLF working-copy notices).
- All workflow tests used temporary migrated SQLite databases under the workspace. No paid provider was called and the real `xhs_workflow.db` was not migrated, opened, or modified.

## Test coverage

The deterministic integration suite covers the complete mock flow and both gates; exact async creation; pagination/filter ordering; selection/revision/approval/retry/cancel idempotency; illegal transitions; text and image provider failure; phase-aware retry; stale recovery; completed-step reuse; cancellation racing provider completion; step attempts/timestamps/durations/errors/heartbeats; upload spoofing, extension/MIME mismatch, size limits, UUID storage, path containment and single-run assignment; cross-run upload/generated-asset denial; atomic owned exports; API-token enforcement; and removal of the generic review endpoint.

## Self-review and concerns

- Cancellation cannot abort an already-issued remote HTTP request, but its state wins: the worker checks state after provider return and again before phase publication, so canceled work cannot transition to a review gate or persist generated asset rows.
- The worker is intentionally single-process and SQLite-oriented. Multiple web-server processes would each create a worker and are outside the binding local single-user assumptions.
- The only warning is the existing `StarletteDeprecationWarning` from `fastapi.testclient` importing the installed Starlette/httpx compatibility layer; application code is not the source.

## Commit

- `50fda3e feat: add durable workbench backend` contains the implementation, migration, and tests.
- The report itself is committed separately after that implementation commit so it can record the implementation hash exactly.
