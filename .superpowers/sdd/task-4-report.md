# Task 4 frontend report

## Delivered

- Replaced the former single-run UI with a durable workbench: newest-first run history is loaded from `GET /api/runs`, and any saved run can be reopened after a browser refresh.
- `POST /api/runs` now accepts the v1 `202` response. Active runs (`queued`, `running`, `image_queued`, `image_running`) refresh every 1.5 seconds and polling ends at either review gate or a terminal state.
- Added three switchable candidate tabs. Their angle, hard-rule verdict, five soft-score dimensions, total, and recommendation are taken from the durable `candidate_round` step payload; selection uses the run's actual `draft_id`.
- Replaced the arbitrary local reference-path field with a browser file field. Submission uploads through `POST /api/uploads` and sends its returned ID as `upload_asset_ids`.
- Wired Task 3 mutation endpoints with unique idempotency keys: selection, real revision instructions, copy approval, retry, cancellation, asset approval, and final ZIP download.
- Kept the image panel hidden until copy approval has advanced the run. The review bar explicitly labels copy vs. asset review and only exposes state-valid operations.
- Removed `VITE_API_TOKEN` use. API errors now display the public FastAPI detail in the main workspace, including errors returned from review controls.

## API-contract evidence

The implementation was checked against `app/api/runs.py`, `app/api/uploads.py`, and `app/schemas.py` at backend commit `a371f19`. No backend changes were needed. Candidate score metadata is correctly read from `RunStep.output_payload.candidates`, because the public `DraftRead` schema intentionally does not expose persisted `angle`/`score` fields.

## Verification

```text
frontend> npm run build
tsc -b && vite build
✓ built in 1.27s
```

There was no frontend test runner in `frontend/package.json`; no framework migration was added. Task 5 is the requested Playwright coverage point.
