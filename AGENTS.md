# Repository guidance

## Product boundaries

- This is a local, single-user workbench. Keep development services bound to `127.0.0.1`;
  there is no multi-user authentication or public deployment boundary.
- Do not add automatic Xiaohongshu publishing or external scraping. Those are explicit v1
  non-goals.
- Mock text and image providers are the safe default. Tests and CI must not call paid providers
  or require provider credentials.

## Architecture invariants

- Treat the workflow state machine and its review gates as product behavior. Validate state
  transitions, retries, cancellation, idempotency, worker recovery, and concurrent updates.
- Keep database changes backward-compatible through Alembic migrations. Never silently discard
  an existing SQLite database, run history, drafts, uploads, or exports.
- Keep filesystem paths and provider errors out of public API payloads. Uploads must remain
  size-limited, type-validated, and contained under the configured upload root.
- Keep the React frontend aligned with the FastAPI response schemas and workflow states.

## Validation

Run the checks relevant to the change. The full CI-equivalent sequence is:

```text
uv sync --extra dev
uv run python -m app.migrate
uv run ruff check app tests migrations scripts
uv run python -m pytest -q -p no:cacheprovider
uv run python -m app.evals.briefs mock-hard
cd frontend && npm ci && npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

Use temporary database, export, and upload paths when exercising workflows. Do not run
`real-soft` evaluation or enable real providers during automated validation.
