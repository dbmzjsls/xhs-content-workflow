# GitHub Copilot repository instructions

When reviewing a pull request, write concise comments in Simplified Chinese while preserving
code identifiers, paths, and commands in their original form.

Prioritize defects that can change behavior, corrupt or expose data, bypass a review gate, make
recovery unreliable, trigger unintended external calls, or break a supported workflow. Inspect
the changed code's callers, data model, tests, and the documents in `docs/` before concluding
that an issue exists.

For every finding:

- Identify the concrete input, state, or sequence that triggers the problem.
- Explain the user or operational impact.
- Point to the smallest relevant changed line and suggest the smallest viable correction.
- Distinguish a demonstrated defect from a question or optional improvement.

Do not report personal style preferences, speculative future requirements, or issues already
reported precisely by Ruff, TypeScript, pytest, the frontend build, or Playwright. Do not ask
for real-provider tests: CI intentionally uses deterministic mock providers.

Apply the repository invariants and validation commands in `AGENTS.md`. Pay particular attention
to workflow state transitions, transactional integrity, upload and path safety, public error
redaction, Alembic compatibility, API/frontend contracts, and accidental network or paid-provider
usage. Treat the explicit v1 non-goals in `README.md` as constraints rather than missing features.
