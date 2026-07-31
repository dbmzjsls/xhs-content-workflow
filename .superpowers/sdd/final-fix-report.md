# Final review fix report

Date: 2026-07-31
Branch: `xhs-workbench-v1`

## Outcome

All four final-review blockers are fixed with regression coverage.

1. Legacy compatibility
   - Added forward-only head migration `20260731_0007` without modifying 0003-0006.
   - Normalizes model-required legacy NULL JSON/text fields and makes those columns non-null.
   - Recomputes a deterministic current `hard` report for every existing draft while retaining prior quality evidence under `legacy_quality_report`.
   - Selects the latest `(version, id)` draft only for review/asset-review runs that have no selection.
   - Migration coverage starts with realistic 0002 `review_required` rows, NULL payloads, two draft versions, and NULL image fields; after upgrade it verifies GET detail, selection, revision, and copy approval.

2. Public path boundary and legacy exports
   - Public serialization recursively sanitizes absolute Windows drive, Windows UNC, and POSIX paths from arbitrary strings, including draft/image fields and image prompts/reference reasons.
   - `final_package` is now an exact allowlist of run-owned export URLs.
   - Export markdown/JSON/ZIP content uses the same sanitizer.
   - Migration preserves every old package descriptor privately in `legacy_final_package`, clears its public descriptor, and returns completed legacy runs to asset review. Existing files are left untouched but all legacy download endpoints return 409 until a safe re-export.

3. Revision UI consistency
   - Parent drafts and child revisions are all rendered in the tab list; children are explicitly labeled `Revision`.
   - Visible draft state is controlled by `App`.
   - Copy approval is disabled unless the visible draft is the backend-selected draft, with a handler guard as a second boundary.
   - The Playwright flow now verifies revision visibility plus approval disabled/enabled behavior when switching away from/back to the selected revision.
   - An offline source contract test covers the wiring.

4. Missing generated files
   - Asset approval validates every stored image path for run-root containment and file existence before marking a draft final or writing package files.
   - Validation failure rolls back approval/idempotency work, records a failed `asset_validation` attempt, moves the run to retryable failed image state, clears public package state, and returns a controlled 409.
   - Image retry removes stale asset rows, invalidates cached `image_generate`/`image_qc` successes, regenerates with the mock provider, and then allows approval/export.

## Verification evidence

- Focused review regressions: `13 passed, 1 warning`.
- Migration suite after realistic `review_required` adjustment: `9 passed, 1 warning`.
- Full backend suite with no pytest cache and a workspace-local OS temp/basetemp root: `73 passed, 1 warning in 28.52s`.
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
