# XHS Content Workflow

A local, auditable workbench for producing Xiaohongshu content through explicit copy and asset review gates. The v1 system is intentionally single-user, SQLite-backed, and bound to `127.0.0.1`; it does not publish to Xiaohongshu or scrape external sites.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js 22+

## Install and migrate

```powershell
uv sync --extra dev
Copy-Item .env.example .env
.\.venv\Scripts\Activate.ps1
python -m app.migrate

Set-Location frontend
npm ci
Set-Location ..
```

`python -m app.migrate` upgrades the configured file-backed SQLite database. The default is `./xhs_workflow.db`. For a first run, start from an empty/nonexistent database file; legacy databases are validated and backed up before adoption.

## Start locally

Backend:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Frontend, in a second terminal:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Open `http://127.0.0.1:5174`. The UI calls `http://127.0.0.1:8090` by default. Do not expose either development server on `0.0.0.0`; v1 has no multi-user authentication boundary.

## Safe default and real providers

`.env.example` selects deterministic `mock` text and image providers. A complete copy/image/export workflow works without API keys and makes no paid-provider calls.

Real-provider configuration is opt-in. Set `LLM_PROVIDER=openai` (or `openai-compatible`) and the compatible key/base URL/model only for an intentional local run. Image provider configuration is separate. The application never silently falls back from a failed real provider to mock output.

## Tests and regression evaluation

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
ruff check app tests migrations scripts
python -m app.evals.briefs mock-hard

Set-Location frontend
npm run build
npm run test:e2e:install
npm run test:e2e
```

The fixed Brief cases cover writing, speaking, commuting, and tutorial scenarios. `mock-hard` constructs the deterministic mock provider directly, ignores ambient provider selection, and is safe for CI.

Real-model soft-score evaluation is manual only and is never run by CI. It requires both a configured real provider and an explicit acknowledgement:

```powershell
$env:LLM_PROVIDER = 'openai'
$env:OPENAI_COMPATIBLE_API_KEY = '<key>'
python -m app.evals.briefs real-soft --allow-paid-providers
```

That command can incur provider cost. Omitting `--allow-paid-providers` fails before provider lookup.

Playwright starts both servers on fixed `127.0.0.1` ports. Its backend launcher overrides providers to mock and creates the database, exports, and uploads under a fresh OS temporary directory, so it does not touch `xhs_workflow.db`.

## Project guide

- [Workflow methodology](docs/workflow-methodology.md)
- [State machine](docs/state-machine.md)
- API health: `GET http://127.0.0.1:8090/healthz`

## Explicit non-goals for v1

- multi-user accounts, authorization, or public hosting
- Redis, Celery, or distributed workers
- automatic publishing
- external Xiaohongshu scraping
