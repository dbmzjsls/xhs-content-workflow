# Task 5 report: integration, regression evals, CI, and docs

## Outcome

Implemented the complete offline Task 5 integration surface:

- Added fixed YAML Brief cases for writing, speaking, commuting, and tutorial scenarios.
- Added a strict fixture loader and deterministic `mock-hard` evaluator. It constructs `MockPipelineProvider` directly, so ambient `.env`, provider selection, and API keys cannot redirect CI to a paid provider.
- Added a manual-only `real-soft` command. It refuses provider lookup unless `--allow-paid-providers` is supplied and then requires an explicitly configured non-mock provider.
- Added Playwright configuration, guarded backend startup, stable UI test IDs, and a main browser journey covering upload, create, polling, three-way comparison, selection, revision, copy approval, asset approval, and ZIP export.
- Added GitHub Actions for `uv sync --extra dev`, empty-DB migration, Ruff, full Pytest, deterministic mock evaluation, `npm ci`, frontend build, Chromium installation, and Playwright.
- Added `.env.example`, a rewritten README, workflow methodology documentation, and state-machine documentation. They state the local SQLite, single-user, mock-default, and `127.0.0.1` assumptions and the explicit v1 non-goals.
- Fixed revision retry so `copy_review_required` uses `current_step=copy_review`.
- Fixed failed image-phase rendering so the image/status panel remains visible when `status=failed` and `current_step=image_generation`.

No authentication, Redis/Celery, publishing, or scraping scope was added.

## Safety controls

- Mock evaluation bypasses settings/provider lookup by constructing `MockPipelineProvider` directly.
- Playwright creates a fresh `xhs-workbench-e2e-*` directory under the OS temp directory and explicitly sets `LLM_PROVIDER=mock`, `IMAGE_PROVIDER=mock`, `DATABASE_URL`, `EXPORT_DIR`, and `UPLOAD_ROOT` for its backend process.
- `scripts/start_e2e_backend.py` refuses to start unless both providers are explicitly mock and all mutable roots are inside `E2E_RUNTIME_ROOT`, which itself must be inside the OS temp directory.
- Full verification explicitly set both providers to mock and used `C:\Users\jsls\AppData\Local\Temp\xhs-task5-verify-23ad2df4238c4d819ccfa51dd9c89293` for migration/Pytest roots.
- The real `xhs_workflow.db` retained the same observed length (`352256`) and UTC modification time (`2026-07-30T06:45:45.0408549Z`) before and after verification. Its post-check SHA-256 was `885D2EC23EF54FE0ED8E64825F1FA83103DE79675B29EEB496666622C038F787`.
- No real-model command was executed and no paid provider was called.

## TDD and focused evidence

Evaluator RED:

```text
python -m pytest tests/test_brief_evals.py -q ...
ERROR: ModuleNotFoundError: No module named 'app.evals'
```

Evaluator GREEN and safety boundary:

```text
python -m pytest tests/test_brief_evals.py -q ...
4 passed in 1.65s
```

The four cases produced three candidates each; all twelve mock candidates passed hard rules and each case had a recommendation.

Revision retry RED:

```text
assert retried_detail["current_step"] == "copy_review"
E AssertionError: assert 'copy_review_required' == 'copy_review'
```

Revision retry GREEN:

```text
python -m pytest tests/test_async_workbench_api.py -q -k revision_provider_failure ...
1 passed, 23 deselected, 1 warning in 2.87s
```

Evaluator plus guarded-launcher tests:

```text
python -m pytest tests/test_brief_evals.py tests/test_e2e_launcher.py -q ...
6 passed in 2.05s
```

## Final verification evidence

Empty database migration used an OS-temporary SQLite file:

```text
python -m app.migrate
Running upgrade 20260730_0005 -> 20260730_0006
MIGRATION_VERSION=20260730_0006
TABLE_COUNT=9
```

Complete mock two-gate/export flow under an OS temp Pytest root:

```text
python -m pytest tests/test_async_workbench_api.py::test_full_mock_flow_has_two_gates_and_durable_steps -q ...
1 passed, 1 warning in 3.29s
```

Full backend suite:

```text
python -m pytest -q --basetemp <OS-temp>/full-pytest -p no:cacheprovider
65 passed, 1 warning in 23.98s
```

The warning is the existing `StarletteDeprecationWarning` emitted by the installed FastAPI/Starlette test-client compatibility layer.

Static and frontend checks:

```text
python -m ruff check app tests migrations scripts
All checks passed!

python -c "... yaml.safe_load(...) ..."
YAML OK

npm run build
vite v8.1.3 ... built in 519ms

git diff --check
passed (only LF-to-CRLF working-copy notices)
```

## Environment limitations

Playwright source/config and CI wiring were completed, but Playwright could not be installed or executed on this host:

1. The sandboxed npm download failed with `EACCES` while connecting to the configured npm mirror.
2. The required network escalation was rejected because the host reported an account usage limit until August 6, 2026 at 2:49 PM.
3. Per the approval response, no indirect download/workaround was attempted.
4. `npm run test:e2e` therefore stopped immediately with `'playwright' is not recognized as an internal or external command`; it did not start the app or any provider.

Consequently, `frontend/package-lock.json` contains the pinned Playwright package graph but could not be regenerated/validated by an online `npm install`, and the Playwright test itself remains execution-unverified on this machine. CI installs Chromium explicitly before running it.

## Self-review

- The evaluator has tests for all four required scenario IDs, all-output hard-rule passing, ambient-provider isolation, and real-provider opt-in refusal.
- The E2E launcher has tests for rejecting a non-mock provider and accepting explicit mock/temp roots.
- The browser journey uses public API/UI behavior and stable test IDs; it does not reach into database internals.
- The state-machine change is limited to the revision retry gate name. Text/image retry behavior is unchanged.
- Failed text runs do not gain an image panel; only failed `image_generation` runs retain it.
- Workflow CI never invokes `real-soft`.
- Scope review found no auth, distributed worker, publishing, or scraping additions.

## Commit status

No commit could be created in this environment. The workspace sandbox exposes `.git` read-only, so scoped `git add` failed with:

```text
fatal: Unable to create '.git/index.lock': Permission denied
```

The required staging escalation was then rejected by the same host usage-limit gate described above. Policy forbids a workaround. All Task 5 files remain as an uncommitted scoped working-tree change; unrelated pre-existing untracked SDD briefs/review artifacts were not staged or modified.
