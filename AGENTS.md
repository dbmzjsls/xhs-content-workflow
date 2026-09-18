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

Run the checks relevant to the change. Before migrations or workflow tests, point all mutable
paths at a disposable directory and force deterministic providers. On a Bash-based runner:

```text
review_tmp="$(mktemp -d)"
export DATABASE_URL="sqlite:///$review_tmp/workflow.sqlite"
export EXPORT_DIR="$review_tmp/exports"
export UPLOAD_ROOT="$review_tmp/uploads"
export LLM_PROVIDER=mock
export IMAGE_PROVIDER=mock
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
uv sync --extra dev
uv run python -m app.migrate
uv run ruff check app tests migrations scripts
uv run python -m pytest -q -p no:cacheprovider
uv run python -m app.evals.briefs mock-hard
cd frontend && npm ci && npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

Do not run `real-soft` evaluation or provide live-provider credentials during automated
validation.
