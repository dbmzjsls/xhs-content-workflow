---
name: code-review
description: Review pull requests for this local FastAPI, SQLModel, Alembic, and React workflow. Use this skill for every PR code review, especially changes involving workflow states, review gates, worker recovery, uploads, migrations, provider calls, API contracts, or Playwright flows.
---

# Pull request review workflow

## Gather context

1. Read the PR title, description, linked issue, and complete diff.
2. Read `AGENTS.md`, `.github/copilot-instructions.md`, and applicable path instructions.
3. Inspect affected callers, schemas, persistence code, tests, `docs/state-machine.md`, and
   `docs/workflow-methodology.md` as relevant.
4. Consult GitHub Actions results through the GitHub MCP tools when available. Use Playwright MCP
   context only when the changed browser flow cannot be evaluated from tests and code alone.
5. Read `checklists/repository-checklist.md` and apply only the sections relevant to the diff.

## Analyze

Trace concrete inputs and state transitions through the changed code. Give highest priority to
data loss, authorization or path exposure, bypassed human review gates, duplicate work,
non-idempotent retries, broken recovery, unintended network calls, and backend/frontend contract
drift. Check that tests exercise the failure or boundary case rather than merely executing the
happy path.

## Report

Create an inline finding only when the issue is introduced or exposed by the PR and can be
demonstrated from repository context. In Simplified Chinese, state the trigger, impact, and a
minimal correction. Keep identifiers and commands unchanged. If evidence is incomplete, ask a
clearly labeled question instead of asserting a defect. Do not produce a comment merely to prove
that the review ran.
