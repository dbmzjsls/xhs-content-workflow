# Final review fix report

Date: 2026-07-31
Branch: `xhs-workbench-v1`

## Outcome

All four final-review blockers are fixed with regression coverage.

1. Legacy compatibility
   - Added forward migrations `20260731_0007` and `20260731_0008` without rewriting committed migrations.
   - Normalizes model-required legacy NULL JSON/text fields and makes those columns non-null.
   - Recomputes a deterministic current `hard` report for every existing draft while retaining prior quality evidence under `legacy_quality_report`.
   - Preserves an explicitly selected hard-passing draft; otherwise selects the latest hard-passing `(version, id)` draft. A newer hard-failing draft is never selected over an eligible draft.
   - When a legacy review/asset-review run has no hard-passing draft, 0008 reconstructs its brief from preserved run columns, clears unsafe selection, invalidates cached candidate output, and moves it to recoverable `failed/text` state.
   - Migration coverage starts with realistic 0002 `review_required` rows, NULL payloads, mixed valid/invalid draft versions, and NULL image fields; after upgrade it verifies GET detail, selection, revision, and copy approval.
   - A separate invalid-only legacy regression verifies public GET, POST `/retry`, fresh mock text generation, restored copy review, and legal copy approval rather than leaving cancellation as the only transition.

2. Public path boundary and legacy exports
   - Public serialization recursively sanitizes absolute Windows drive, Windows UNC, and POSIX paths from arbitrary strings, including draft/image fields and image prompts/reference reasons.
   - `final_package` is now an exact allowlist of run-owned export URLs.
   - Export markdown/JSON/ZIP content uses the same sanitizer.
   - Migration preserves every old package descriptor privately in `legacy_final_package` and clears its public descriptor. Completed legacy runs with eligible drafts return to asset review; runs without an eligible draft enter recoverable text retry. Existing files are left untouched and all legacy download endpoints return 409 until a safe re-export.

3. Revision UI consistency
   - Parent drafts and child revisions are all rendered in the tab list; children are explicitly labeled `Revision`.
   - Visible draft state is controlled by `App`.
   - Both revision and copy approval are disabled unless the visible draft is the backend-selected draft, with handler guards as a second boundary.
   - The Playwright flow now verifies revision visibility plus revision/approval disabled/enabled behavior when switching away from/back to the selected revision.
   - An offline source contract test covers the wiring.

4. Missing generated files
   - Asset approval validates every stored image path for run-root containment and file existence before marking a draft final or writing package files.
   - Validation failure rolls back approval/idempotency work, records a failed `asset_validation` attempt, moves the run to retryable failed image state, clears public package state, and returns a controlled 409.
   - Image retry removes stale asset rows, invalidates cached `image_generate`/`image_qc` successes, regenerates with the mock provider, and then allows approval/export.

## Verification evidence

- Initial focused review regressions: `13 passed, 1 warning`.
- Follow-up migration and frontend contract suite: `11 passed, 1 warning`.
- Migration suite includes 10 tests, including mixed-validity and invalid-only public retry coverage.
- Full backend suite with no pytest cache and a workspace-local OS temp/basetemp root: `74 passed, 1 warning in 36.28s`.
- Ruff: `All checks passed!` for `app migrations tests`.
- Frontend production build: TypeScript + Vite succeeded; 1572 modules transformed.
- Diff whitespace check: `git diff --check` passed.
- Playwright execution was attempted once. The local `playwright` executable is not installed (`'playwright' is not recognized...`); per instruction, no browser/package download or retry was attempted. The updated spec is covered by the offline source contract and TypeScript production build.
- The only test warning is the existing Starlette/httpx deprecation warning.

## Safety evidence

- All database tests used SQLite files below the workspace-local pytest temp root.
- Text and image providers were explicitly `mock` in workflow regressions.
- The real `xhs_workflow.db` was not opened or modified.
- No paid provider and no Playwright download was invoked.
- Legacy export files are preserved in place; migration only revokes public access and archives their database descriptor.

## Remaining concern

Browser-level E2E execution still needs an environment with the already-installed Playwright CLI/browser. No functional or static test failures remain.
